import pytest
from conftest import load_sample

from speakscore.web import create_app


@pytest.fixture
def client():
    app = create_app({"TESTING": True, "MAX_TRANSCRIPT_CHARS": 2000})
    return app.test_client()


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_index_renders_with_samples(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"SpeakScore" in response.data
    assert b"Strong" in response.data


def test_score_returns_report(client):
    transcript, duration = load_sample("strong")
    response = client.post(
        "/api/score", json={"transcript": transcript, "duration_seconds": duration}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["score"] >= 75
    assert [c["id"] for c in data["criteria"]] == [
        "content",
        "speech_rate",
        "language",
        "clarity",
        "engagement",
    ]
    assert data["stats"]["wpm"] > 0


def test_duration_is_optional(client):
    response = client.post("/api/score", json={"transcript": "My name is Asha. Thank you."})
    assert response.status_code == 200
    assert response.get_json()["criteria"][1]["scored"] is False


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"data": "not json", "content_type": "application/json"}, "JSON object"),
        ({"data": "transcript=hi"}, "JSON object"),
        ({"json": ["a", "list"]}, "JSON object"),
        ({"json": {}}, "'transcript' is required"),
        ({"json": {"transcript": 123}}, "'transcript' is required"),
        ({"json": {"transcript": "   "}}, "non-empty"),
        ({"json": {"transcript": "x" * 2001}}, "at most 2000"),
        ({"json": {"transcript": "Hi there", "duration_seconds": "52"}}, "must be a number"),
        ({"json": {"transcript": "Hi there", "duration_seconds": -1}}, "greater than 0"),
        ({"json": {"transcript": "Hi there", "duration_seconds": True}}, "must be a number"),
    ],
)
def test_bad_requests_return_400_with_message(client, kwargs, message):
    response = client.post("/api/score", **kwargs)
    assert response.status_code == 400
    assert message in response.get_json()["error"]


def test_wrong_method_and_unknown_route_return_json(client):
    assert client.get("/api/score").status_code == 405
    assert "error" in client.get("/api/score").get_json()
    missing = client.get("/api/nope")
    assert missing.status_code == 404
    assert "error" in missing.get_json()


def test_oversized_body_is_rejected(client):
    response = client.post("/api/score", json={"transcript": "word " * 60_000})
    assert response.status_code == 413
    assert "error" in response.get_json()


def test_config_from_environment(monkeypatch):
    monkeypatch.setenv("SPEAKSCORE_MAX_TRANSCRIPT_CHARS", "10")
    client = create_app({"TESTING": True}).test_client()
    response = client.post("/api/score", json={"transcript": "far too long for ten"})
    assert response.status_code == 400
    assert "at most 10" in response.get_json()["error"]
