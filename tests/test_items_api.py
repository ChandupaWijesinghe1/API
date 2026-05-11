from fastapi.testclient import TestClient
import pytest


def test_health_returns_ok(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_and_get_item_happy_path(client: TestClient):
    create_res = client.post(
        "/items",
        json={
            "name": "Book",
            "description": "Python guide",
            "quantity": 3,
            "status": "active",
        },
    )
    assert create_res.status_code == 201
    created = create_res.json()
    assert created["name"] == "Book"
    assert created["status"] == "active"
    assert "id" in created
    assert "created_at" in created
    assert "updated_at" in created

    get_res = client.get(f"/items/{created['id']}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == created["id"]


def test_list_items_can_filter_by_status_and_search(client: TestClient):
    client.post("/items", json={"name": "Python Book", "quantity": 2, "status": "active"})
    client.post("/items", json={"name": "Notebook", "quantity": 1, "status": "inactive"})
    client.post("/items", json={"name": "Pen", "description": "blue ink", "status": "active"})

    status_res = client.get("/items", params={"status": "inactive"})
    assert status_res.status_code == 200
    status_items = status_res.json()
    assert len(status_items) == 1
    assert status_items[0]["name"] == "Notebook"

    search_res = client.get("/items", params={"search": "python"})
    assert search_res.status_code == 200
    search_items = search_res.json()
    assert len(search_items) == 1
    assert search_items[0]["name"] == "Python Book"


def test_patch_updates_selected_fields_only(client: TestClient):
    created = client.post(
        "/items",
        json={"name": "Keyboard", "description": "mechanical", "quantity": 1, "status": "active"},
    ).json()

    patch_res = client.patch(
        f"/items/{created['id']}",
        json={"description": "wireless", "status": "inactive"},
    )
    assert patch_res.status_code == 200
    patched = patch_res.json()
    assert patched["name"] == "Keyboard"
    assert patched["description"] == "wireless"
    assert patched["status"] == "inactive"
    assert patched["quantity"] == 1


def test_duplicate_creation_returns_409(client: TestClient):
    payload = {
        "name": "Mouse",
        "description": "optical",
        "quantity": 1,
        "status": "active",
    }
    first = client.post("/items", json=payload)
    assert first.status_code == 201

    duplicate = client.post("/items", json=payload)
    assert duplicate.status_code == 409
    assert "Duplicate item" in duplicate.json()["detail"]


def test_invalid_id_and_missing_item_cases(client: TestClient):
    invalid = client.get("/items/not-a-uuid")
    assert invalid.status_code == 422
    assert "Invalid item_id format" in invalid.json()["detail"]

    missing_id = "00000000-0000-0000-0000-000000000000"
    missing = client.get(f"/items/{missing_id}")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Item not found."}


def test_delete_twice_returns_204_then_404(client: TestClient):
    created = client.post("/items", json={"name": "Cable", "quantity": 1, "status": "active"}).json()

    first_delete = client.delete(f"/items/{created['id']}")
    assert first_delete.status_code == 204
    assert first_delete.text == ""

    second_delete = client.delete(f"/items/{created['id']}")
    assert second_delete.status_code == 404
    assert second_delete.json() == {"detail": "Item not found."}


def test_put_replaces_all_fields_and_updates_timestamp(client: TestClient):
    created = client.post(
        "/items",
        json={
            "name": "Monitor",
            "description": "old",
            "quantity": 1,
            "status": "active",
        },
    ).json()

    replaced = client.put(
        f"/items/{created['id']}",
        json={
            "name": "Monitor 2",
            "description": "new",
            "quantity": 2,
            "status": "inactive",
        },
    )
    assert replaced.status_code == 200
    body = replaced.json()
    assert body["name"] == "Monitor 2"
    assert body["description"] == "new"
    assert body["quantity"] == 2
    assert body["status"] == "inactive"
    assert body["created_at"] == created["created_at"]
    assert body["updated_at"] != created["updated_at"]


def test_put_missing_item_returns_404(client: TestClient):
    missing_id = "00000000-0000-0000-0000-000000000001"
    response = client.put(
        f"/items/{missing_id}",
        json={"name": "A", "description": "B", "quantity": 1, "status": "active"},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Item not found."}


def test_patch_missing_item_returns_404(client: TestClient):
    missing_id = "00000000-0000-0000-0000-000000000001"
    response = client.patch(f"/items/{missing_id}", json={"name": "Updated"})
    assert response.status_code == 404
    assert response.json() == {"detail": "Item not found."}


def test_patch_empty_payload_returns_422(client: TestClient):
    created = client.post("/items", json={"name": "Chair", "quantity": 1, "status": "active"}).json()
    response = client.patch(f"/items/{created['id']}", json={})
    assert response.status_code == 422
    assert "At least one field must be provided" in str(response.json())


@pytest.mark.parametrize(
    "payload,error_fragment",
    [
        ({"name": "", "quantity": 1, "status": "active"}, "string_too_short"),
        ({"name": "Pen", "quantity": 0, "status": "active"}, "greater_than_equal"),
        ({"name": "Pen", "quantity": 1, "status": "paused"}, "literal_error"),
        ({"quantity": 1, "status": "active"}, "missing"),
    ],
)
def test_post_validation_edge_cases(client: TestClient, payload: dict, error_fragment: str):
    response = client.post("/items", json=payload)
    assert response.status_code == 422
    assert error_fragment in str(response.json())


@pytest.mark.parametrize(
    "query,expected_error",
    [
        ({"status": "paused"}, "literal_error"),
        ({"search": ""}, "string_too_short"),
    ],
)
def test_list_validation_query_edge_cases(client: TestClient, query: dict, expected_error: str):
    response = client.get("/items", params=query)
    assert response.status_code == 422
    assert expected_error in str(response.json())
