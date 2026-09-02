from fastapi.testclient import TestClient

from . import server


client = TestClient(server.app)


def test_config_points_at_realtime_server() -> None:
    response = client.get("/api/config")
    assert response.status_code == 200
    body = response.json()
    assert body["s2sUrl"] == server.SPEECH_TO_SPEECH_URL
    assert body["allowDirect"] is True
    assert body["lb"] is False
    assert body["rtc"] is False


def test_interface_is_served() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "ConvFill Realtime" in response.text


def test_search_requires_a_key(monkeypatch) -> None:
    monkeypatch.setattr(server, "SERPER_API_KEY", "")
    response = client.post("/api/search", json={"query": "test"})
    assert response.status_code == 503


def test_agents_sdk_bundle_is_served() -> None:
    response = client.get("/vendor/openai-realtime-agents.umd.js")
    assert response.status_code == 200
    assert "OpenAIAgentsRealtime" in response.text
