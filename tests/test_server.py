"""HTTP surface and the live WebSocket protocol."""
import pytest

pytest.importorskip("feat", reason="py-feat is not installed")
pytest.importorskip("fastapi")

import rppg_core as core                               # noqa: E402
from fastapi.testclient import TestClient              # noqa: E402

from painface.server import app                        # noqa: E402

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_describes_the_instrument(client):
    h = client.get("/api/health").json()
    assert h["ok"] and h["version"]
    assert h["pspi"]["max"] == 16.0
    assert len(h["pspi"]["terms"]) == 4
    assert len(h["detected_aus"]) == 20
    assert set(h["pain_aus"]) <= set(h["detected_aus"])
    assert 0 < h["fusion"]["trigger_off"] < h["fusion"]["trigger_on"] < 1


def test_au_reference_lists_every_unit(client):
    assert len(client.get("/api/aus").text.strip().splitlines()) == 20


def test_export_without_a_session_is_a_404(client):
    import painface.server as srv
    srv._last_session = None
    assert client.get("/api/session.json").status_code == 404


class TestLive:
    def test_handshake_advertises_the_vocabulary(self, client):
        with client.websocket_connect("/ws/live") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello"
            assert hello["pspi_max"] == 16.0
            assert len(hello["pain_aus"]) > 0

    def test_rgb_is_always_acknowledged_even_before_vitals_exist(self, client):
        """A client must never block waiting for a reply that only comes later."""
        with client.websocket_connect("/ws/live") as ws:
            ws.receive_json()
            ws.send_json({"type": "rgb", "t": [0.0, 0.1], "rgb": [[180, 120, 95]] * 2})
            r = ws.receive_json()
            assert r["type"] == "vitals" and r["vitals"]["ready"] is False

    def test_a_full_trace_produces_vitals(self, client):
        t, rgb = core.synthetic_rgb(40, 30.0, hr=72, rr=15)
        with client.websocket_connect("/ws/live") as ws:
            ws.receive_json()
            ws.send_json({"type": "config", "window_s": 30.0, "analysis_interval_s": 0})
            ws.receive_json()
            last = None
            for s in range(40):
                m = (t >= s) & (t < s + 1)
                ws.send_json({"type": "rgb", "t": t[m].tolist(), "rgb": rgb[:, m].T.tolist()})
                last = ws.receive_json()
            v = last["vitals"]
            assert v["ready"] and v["sampling_ok"]
            assert v["fused_hr"] == pytest.approx(72.0, abs=1.5)
            assert v["hrv_ready"]

    def test_supplied_aus_run_the_real_fusion(self, client):
        """The simulator path must not be a separate scoring implementation."""
        with client.websocket_connect("/ws/live") as ws:
            ws.receive_json()
            ws.send_json({"type": "aus", "t": 1.0, "quality": 0.95,
                          "aus": {"AU04": 0.85, "AU07": 0.8, "AU09": 0.7,
                                  "AU10": 0.55, "AU43": 0.45, "AU12": 0.02},
                          "emotions": {"Neutral": 0.6, "Sad": 0.4}})
            r = ws.receive_json()
            assert r["type"] == "au" and r["simulated"] is True
            assert r["pain"]["nrs"] > 5.0
            assert r["pain"]["facial"]["smile"] < 0.1

    def test_a_smile_sent_as_aus_scores_low(self, client):
        with client.websocket_connect("/ws/live") as ws:
            ws.receive_json()
            ws.send_json({"type": "aus", "t": 1.0,
                          "aus": {"AU06": 0.6, "AU10": 0.85, "AU12": 0.98, "AU04": 0.002},
                          "emotions": {"Happy": 0.99}})
            p = ws.receive_json()["pain"]
            assert p["facial"]["pspi"] > 5.0        # raw over-reads
            assert p["nrs"] < 3.0                   # corrected does not

    def test_recording_then_exporting_round_trips(self, client):
        with client.websocket_connect("/ws/live") as ws:
            ws.receive_json()
            ws.send_json({"type": "session", "action": "start", "label": "unit"})
            ws.receive_json()
            for i in range(6):
                ws.send_json({"type": "aus", "t": i * 0.5,
                              "aus": {"AU04": 0.8, "AU07": 0.8, "AU09": 0.7, "AU12": 0.01}})
                ws.receive_json()
            ws.send_json({"type": "session", "action": "stop"})
            summary = ws.receive_json()["summary"]
            assert summary["samples"] == 6

        assert client.get("/api/session").json()["samples"] == 6
        assert client.get("/api/session.json").status_code == 200
        csv_text = client.get("/api/session.csv").text
        assert len(csv_text.strip().splitlines()) == 7       # header + 6

    def test_unknown_and_malformed_messages_are_ignored(self, client):
        with client.websocket_connect("/ws/live") as ws:
            ws.receive_json()
            ws.send_text("not json at all")
            ws.send_json({"type": "nonsense"})
            ws.send_json({"type": "aus", "aus": {}})
            ws.send_json({"type": "ping"})
            assert ws.receive_json()["type"] == "pong"
