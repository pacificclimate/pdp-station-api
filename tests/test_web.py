from starlette.testclient import TestClient

from pdp_station.application import NetworkSummary, StationSummary
from pdp_station.web import create_app


class FakeRepository:
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
