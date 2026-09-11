from search_app import create_app


def test_home_renders_without_mongo():
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert b"Find the episode" in response.data
    assert b"jquery" in response.data.lower()


def test_search_without_mongo_is_service_unavailable():
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    response = client.get("/api/search", query_string={"q": "ransomware"})
    assert response.status_code == 503
    assert response.get_json()["query"] == "ransomware"
