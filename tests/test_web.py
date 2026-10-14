import logging
from datetime import datetime
from urllib.parse import urljoin, urlsplit

import pytest
from starlette.testclient import TestClient

from pdp_station.application import (
    NetworkSummary,
    RelationReadiness,
    StationDataset,
    StationSummary,
)
from pdp_station.web import create_app


class FakeRepository:
    def __init__(self):
        self.readiness_checks = 0

    def ready(self):
        self.readiness_checks += 1
        return (RelationReadiness("crmp.meta_station", True, True, True),)

    def networks(self):
        return (
            NetworkSummary(
                "FLNRO-WMB",
                "Wildfire Management Branch",
                "Wildfire weather observations",
            ),
            NetworkSummary("ALPHA", "Alpha Network"),
        )

    def network(self, name):
        return next(
            (network for network in self.networks() if network.name == name), None
        )

    def stations(self, network):
        return (
            StationSummary(43, "1003", "Zulu Station"),
            StationSummary(42, "1002", "Example Station"),
            StationSummary(41, "1001"),
        )

    def station_id(self, network, native_id):
        if (network, native_id) == ("FLNRO-WMB", "1002"):
            return 42
        return None

    def published_station_id(self, station_id):
        return station_id if station_id == 42 else None

    def describe(self, station_id, climatology=False):
        return StationDataset(station_id, climatology, ("obs_time", "temperature"))

    def rows(self, query):
        yield (datetime(2025, 1, 2), 12.5)


class UnavailableRepository(FakeRepository):
    def ready(self):
        raise RuntimeError("database credentials must not reach the response")


def test_readyz_reports_database_readiness():
    repository = FakeRepository()
    client = TestClient(create_app(repository=repository))

    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.text == "ok"
    assert response.headers["content-type"].startswith("text/plain")
    assert repository.readiness_checks == 1


def test_readyz_verbose_reports_individual_checks():
    client = TestClient(create_app(repository=FakeRepository()))

    response = client.get("/readyz?verbose")

    assert response.status_code == 200
    assert response.text == (
        "[+]database connection\n"
        "[+]crmp.meta_station existence\n"
        "[+]crmp.meta_station schema_usage\n"
        "[+]crmp.meta_station select\n"
        "readyz check passed\n"
    )


def test_readyz_verbose_reports_failed_relation_check():
    repository = FakeRepository()
    repository.ready = lambda: (RelationReadiness("crmp.obs_raw", True, True, False),)
    client = TestClient(create_app(repository=repository))

    response = client.get("/readyz?verbose")

    assert response.status_code == 503
    assert "[+]crmp.obs_raw existence\n" in response.text
    assert "[+]crmp.obs_raw schema_usage\n" in response.text
    assert "[-]crmp.obs_raw select\n" in response.text
    assert response.text.endswith("readyz check failed\n")


def test_readyz_returns_503_without_exposing_database_error(caplog):
    client = TestClient(create_app(repository=UnavailableRepository()))

    with caplog.at_level(logging.ERROR, logger="pdp_station.web"):
        response = client.get("/readyz?verbose")

    assert response.status_code == 503
    assert response.text == "[-]database failed\nreadyz check failed\n"
    assert "credentials" not in response.text
    error = next(record for record in caplog.records if record.levelno == logging.ERROR)
    assert error.exc_info is not None


def test_health_endpoint_is_replaced_by_readyz():
    client = TestClient(create_app(repository=FakeRepository()))

    assert client.get("/health").status_code == 404


@pytest.mark.parametrize("prefix", ("/data/pcds", "/met-data-portal-pcds/api/data"))
@pytest.mark.parametrize("root", ("/lister", "/pcds/lister"))
@pytest.mark.parametrize(
    ("suffix", "target"),
    (
        ("", "/"),
        ("/", "/"),
        ("/raw/FLNRO-WMB/", "/networks/FLNRO-WMB"),
        ("/raw/FLNRO-WMB/1002/", "/dap/raw/FLNRO-WMB/1002.html"),
        ("/raw/FLNRO-WMB/1002.rsql.html", "/dap/stations/42.html"),
        ("/raw/FLNRO-WMB/1002.rsql.csv", "/dap/stations/42.csv"),
        ("/climo/FLNRO-WMB/1002.csql.csv", "/dap/climatologies/42.csv"),
    ),
)
def test_public_legacy_redirect_stays_within_proxy_mount(prefix, root, suffix, target):
    client = TestClient(create_app(repository=FakeRepository()))
    public_url = "https://example.test" + prefix + root + suffix
    # Traefik strips the complete public mount before forwarding each request.
    response = client.get(root + suffix, follow_redirects=False)
    assert response.status_code == 307
    destination = urljoin(public_url, response.headers["location"])
    assert destination == "https://example.test" + prefix + target
    internal_path = urlsplit(destination).path[len(prefix) :]
    final = client.get(internal_path)
    assert final.status_code == 200
    if target.endswith(".csv"):
        assert "12.5" in final.text


@pytest.mark.parametrize(
    ("path", "location"),
    (
        ("/pcds/lister", "../"),
        ("/pcds/lister/", "../../"),
        ("/pcds/lister/raw", "../../"),
        ("/pcds/lister/raw/", "../../../"),
        ("/pcds/lister/climo", "../../"),
        ("/pcds/lister/climo/", "../../../"),
        (
            "/pcds/lister/raw/FLNRO-WMB",
            "../../../networks/FLNRO-WMB",
        ),
        (
            "/pcds/lister/raw/FLNRO-WMB/",
            "../../../../networks/FLNRO-WMB",
        ),
        (
            "/pcds/lister/climo/FLNRO-WMB",
            "../../../networks/FLNRO-WMB",
        ),
        (
            "/pcds/lister/climo/FLNRO-WMB/",
            "../../../../networks/FLNRO-WMB",
        ),
    ),
)
@pytest.mark.parametrize("standalone", (False, True))
def test_legacy_lister_catalog_paths_redirect_to_current_catalog(
    path, location, standalone
):
    if standalone:
        path = path.removeprefix("/pcds")
        location = location.removeprefix("../") or "./"
    client = TestClient(create_app(repository=FakeRepository()))

    response = client.get(path, follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == location


@pytest.mark.parametrize(
    ("path", "location"),
    (
        (
            "/pcds/lister/raw/FLNRO-WMB/1002.rsql.html",
            "../../../../dap/stations/42.html",
        ),
        (
            "/pcds/lister/raw/FLNRO-WMB/1002.rsql.nc",
            "../../../../dap/stations/42.nc",
        ),
        (
            "/pcds/lister/climo/FLNRO-WMB/1002.csql.csv",
            "../../../../dap/climatologies/42.csv",
        ),
        (
            "/pcds/lister/raw/FLNRO-WMB/1002.rsql.xls",
            "../../../../dap/stations/42.xlsx",
        ),
        (
            "/pcds/lister/raw/FLNRO-WMB/1002",
            "../../../../dap/raw/FLNRO-WMB/1002.html",
        ),
        (
            "/pcds/lister/climo/FLNRO-WMB/1002",
            "../../../../dap/climo/FLNRO-WMB/1002.html",
        ),
        (
            "/pcds/lister/raw/FLNRO-WMB/1002/",
            "../../../../../dap/raw/FLNRO-WMB/1002.html",
        ),
    ),
)
@pytest.mark.parametrize("standalone", (False, True))
def test_legacy_lister_redirects_native_id_pages_and_station_id_datasets(
    path, location, standalone
):
    if standalone:
        path = path.removeprefix("/pcds")
        location = location.removeprefix("../")
    client = TestClient(create_app(repository=FakeRepository()))

    response = client.get(path, follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == location


def test_legacy_redirect_preserves_the_constraint_query_verbatim():
    client = TestClient(create_app(repository=FakeRepository()))
    query = "station_observations.air_temp,station_observations.time"

    response = client.get(
        f"/pcds/lister/raw/FLNRO-WMB/1002.rsql.csv?{query}",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == ("../../../../dap/stations/42.csv?" + query)


def test_unknown_legacy_sql_dataset_is_not_found():
    client = TestClient(create_app(repository=FakeRepository()))

    response = client.get("/pcds/lister/raw/FLNRO-WMB/unknown.rsql.csv")

    assert response.status_code == 404
    assert response.text == "Station FLNRO-WMB/unknown was not found"


@pytest.mark.parametrize("method", ("get", "post"))
@pytest.mark.parametrize(
    ("path", "location"),
    (
        ("/pcds/agg", "../agg?data-format=csv"),
        ("/pcds/agg/", "../../agg?data-format=csv"),
    ),
)
def test_legacy_aggregate_paths_redirect_and_preserve_the_method(
    method, path, location
):
    client = TestClient(create_app(repository=FakeRepository()))

    response = getattr(client, method)(
        path + "?data-format=csv", follow_redirects=False
    )

    assert response.status_code == 307
    assert response.headers["location"] == location


def test_invalid_legacy_dataset_response_is_rejected():
    client = TestClient(create_app(repository=FakeRepository()))

    response = client.get("/pcds/lister/raw/FLNRO-WMB/1002.rsql.exe")

    assert response.status_code == 400
    assert response.text == "Legacy station response format is not supported"


def test_network_index_links_to_network_station_page():
    client = TestClient(create_app(repository=FakeRepository()))

    response = client.get("/")

    assert response.status_code == 200
    assert "Wildfire Management Branch" in response.text
    assert 'href="./networks/FLNRO-WMB"' in response.text
    assert response.text.index("Alpha Network") < response.text.index(
        "Wildfire Management Branch"
    )


def test_station_index_links_to_public_dap_html_response():
    client = TestClient(create_app(repository=FakeRepository()))

    response = client.get("/networks/FLNRO-WMB")

    assert response.status_code == 200
    assert "Wildfire weather observations" in response.text
    assert "Example Station" in response.text
    assert 'href="../dap/raw/FLNRO-WMB/1002.html">1002</a>' in response.text
    assert 'href="../">All networks</a>' in response.text
    assert response.text.index("1001") < response.text.index("1002")
    assert response.text.index("1002") < response.text.index("1003")


def test_unknown_network_is_not_found():
    client = TestClient(create_app(repository=FakeRepository()))

    response = client.get("/networks/unknown")

    assert response.status_code == 404


def test_pydap_network_breadcrumbs_redirect_to_catalog():
    client = TestClient(create_app(repository=FakeRepository()))

    for path in (
        "/dap/raw/FLNRO-WMB",
        "/dap/raw/FLNRO-WMB/",
        "/dap/climo/FLNRO-WMB",
        "/dap/climo/FLNRO-WMB/",
    ):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 307
        expected = (
            "../../../networks/FLNRO-WMB"
            if path.endswith("/")
            else "../../networks/FLNRO-WMB"
        )
        assert response.headers["location"] == expected


def test_pydap_root_breadcrumbs_redirect_to_network_index():
    client = TestClient(create_app(repository=FakeRepository()))

    for path in (
        "/dap",
        "/dap/",
        "/dap/raw",
        "/dap/raw/",
        "/dap/climo",
        "/dap/climo/",
        "/dap/stations",
        "/dap/stations/",
        "/dap/climatologies",
        "/dap/climatologies/",
    ):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 307
        depth = len([part for part in path.split("/") if part])
        if not path.endswith("/"):
            depth -= 1
        expected = "../" * depth or "./"
        assert response.headers["location"] == expected
