from fastapi.testclient import TestClient


def test_first_dashboard_is_default_and_deletion_promotes_the_next(
    registered: tuple[TestClient, str],
) -> None:
    client, csrf = registered
    headers = {"X-CSRF-Token": csrf}
    first = client.post(
        "/api/v1/dashboards",
        headers=headers,
        json={
            "name": "Overview",
            "layout": {"preset": "overview-v1", "widgets": []},
        },
    )
    assert first.status_code == 201
    assert first.json()["is_default"] is True
    assert first.json()["layout"]["preset"] == "overview-v1"
    second = client.post(
        "/api/v1/dashboards",
        headers=headers,
        json={"name": "Diagnostics", "layout": {"widgets": []}},
    )
    assert second.status_code == 201
    assert second.json()["is_default"] is False

    deleted = client.delete(f"/api/v1/dashboards/{first.json()['id']}", headers=headers)
    assert deleted.status_code == 204
    remaining = client.get("/api/v1/dashboards").json()
    assert len(remaining) == 1
    assert remaining[0]["id"] == second.json()["id"]
    assert remaining[0]["is_default"] is True
