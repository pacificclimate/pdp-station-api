import logging

from starlette.testclient import TestClient

from pdp_station.application import NetworkSummary, RelationReadiness, StationSummary
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


def test_network_index_links_to_network_station_page():
    client = TestClient(create_app(repository=FakeRepository()))

    response = client.get("/")

    assert response.status_code == 200
    assert "Wildfire Management Branch" in response.text
    assert 'href="/networks/FLNRO-WMB"' in response.text
    assert response.text.index("Alpha Network") < response.text.index(
        "Wildfire Management Branch"
    )


def test_station_index_links_to_public_dap_html_response():
    client = TestClient(create_app(repository=FakeRepository()))

    response = client.get("/networks/FLNRO-WMB")

    assert response.status_code == 200
    assert "Wildfire weather observations" in response.text
    assert "Example Station" in response.text
    assert 'href="/dap/raw/FLNRO-WMB/1002.html">1002</a>' in response.text
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
        assert response.headers["location"].endswith("/networks/FLNRO-WMB")


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
        assert response.headers["location"].endswith("/")
