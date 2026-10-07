import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

LAUREL_ID = 4839


def test_get_item_returns_real_record():
    response = client.get(f"/items/{LAUREL_ID}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == LAUREL_ID
    assert body["name"] == "Laurel"
    assert len(body["nodes"]) > 0


def test_get_item_includes_known_coordinate():
    response = client.get(f"/items/{LAUREL_ID}")
    nodes = response.json()["nodes"]
    assert any(
        n["x"] is not None
        and abs(n["x"] - (-611.869)) < 1e-3
        and abs(n["y"] - 718.873) < 1e-3
        for n in nodes
    )


def test_get_item_unknown_id_returns_404():
    response = client.get("/items/999999999")
    assert response.status_code == 404
    assert "detail" in response.json()


def test_search_ranks_exact_match_first():
    response = client.get("/items", params={"q": "laurel"})
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "laurel"
    assert body["count"] >= 1
    assert body["results"][0]["name"] == "Laurel"


def test_search_is_case_insensitive():
    lower = client.get("/items", params={"q": "laurel"}).json()
    upper = client.get("/items", params={"q": "LAUREL"}).json()
    assert [r["id"] for r in lower["results"]] == [r["id"] for r in upper["results"]]


def test_search_requires_query():
    assert client.get("/items").status_code == 422


def test_search_respects_limit():
    response = client.get("/items", params={"q": "e", "limit": 3})
    assert response.status_code == 200
    assert len(response.json()["results"]) <= 3
