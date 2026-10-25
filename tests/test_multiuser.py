"""Two clients at once must not see each other's recording."""
import pytest

pytest.importorskip("feat", reason="py-feat is not installed")
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient          # noqa: E402
from painface.server import app                    # noqa: E402
import painface.server as srv                      # noqa: E402

pytestmark = pytest.mark.slow

PAIN = {"AU04": 0.85, "AU07": 0.8, "AU09": 0.7, "AU10": 0.55, "AU12": 0.02}
CALM = {"AU04": 0.02, "AU07": 0.03, "AU12": 0.02}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def record(ws, aus, n, label):
    ws.send_json({"type": "session", "action": "start", "label": label}); ws.receive_json()
    for i in range(n):
        ws.send_json({"type": "aus", "t": i * 0.5, "aus": aus}); ws.receive_json()
    ws.send_json({"type": "session", "action": "stop"})
    return ws.receive_json()["summary"]


def test_each_connection_gets_its_own_session_id(client):
    with client.websocket_connect("/ws/live") as a, client.websocket_connect("/ws/live") as b:
        sa, sb = a.receive_json(), b.receive_json()
        assert sa["sid"] and sb["sid"]
        assert sa["sid"] != sb["sid"]


def test_concurrent_recordings_do_not_overwrite_each_other(client):
    with client.websocket_connect("/ws/live") as a, client.websocket_connect("/ws/live") as b:
        sid_a = a.receive_json()["sid"]
        sid_b = b.receive_json()["sid"]
        sum_a = record(a, PAIN, 6, "A")
        sum_b = record(b, CALM, 3, "B")

        assert sum_a["samples"] == 6 and sum_b["samples"] == 3

        # each client's export must return that client's own recording
        got_a = client.get(f"/api/session?sid={sid_a}").json()
        got_b = client.get(f"/api/session?sid={sid_b}").json()
        assert got_a["samples"] == 6 and got_a["label"] == "A"
        assert got_b["samples"] == 3 and got_b["label"] == "B"
        assert got_a["nrs_peak"] > got_b["nrs_peak"]

        csv_a = client.get(f"/api/session.csv?sid={sid_a}").text
        assert len(csv_a.strip().splitlines()) == 7        # header + 6


def test_unknown_session_id_is_a_404(client):
    assert client.get("/api/session?sid=deadbeefcafe").status_code == 404


def test_omitting_the_id_still_serves_the_latest(client):
    """Keeps the single-user localhost case working unchanged."""
    with client.websocket_connect("/ws/live") as a:
        a.receive_json()
        record(a, PAIN, 4, "solo")
    assert client.get("/api/session").json()["samples"] == 4


def test_offline_analysis_does_not_claim_a_live_slot(client):
    with client.websocket_connect("/ws/live") as a:
        sid = a.receive_json()["sid"]
        record(a, PAIN, 5, "live")
    srv._publish(srv.PainSession(label="offline-run"), "offline")
    assert client.get(f"/api/session?sid={sid}").json()["label"] == "live"


def test_health_reports_capacity(client):
    h = client.get("/api/health").json()
    assert "clients" in h and h["max_clients"] >= 1
