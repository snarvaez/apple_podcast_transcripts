from search_app import create_app
from search_app.config import Config
from search_app.db import close_client


def test_home_renders_without_mongo():
    Config.MONGODB_URI = ""
    close_client()
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert b"Find the episode" in response.data
    assert b"jquery" in response.data.lower()


def test_search_without_mongo_is_service_unavailable():
    Config.MONGODB_URI = ""
    close_client()
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    response = client.get("/api/search", query_string={"q": "ransomware"})
    assert response.status_code == 503
    assert response.get_json()["query"] == "ransomware"
