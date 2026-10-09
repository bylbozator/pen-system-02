"""Интеграционные тесты датасетов: создание, RBAC, архив, дублирование."""
import pytest

from conftest import csrf_headers, login


def _create_user(client, username, password, permissions):
    """Создаёт роль и пользователя через admin API, возвращает TestClient, залогиненный новым юзером."""
    headers = csrf_headers(client)
    role_resp = client.post(
        "/api/admin/roles",
        json={"name": f"Роль {username}", "permissions": permissions, "description": "test"},
        headers=headers,
    )
    assert role_resp.status_code == 201, role_resp.text
    role_id = role_resp.json()["id"]

    user_resp = client.post(
        "/api/admin/users",
        json={
            "username": username,
            "email": f"{username}@test.ru",
            "password": password,
            "role_id": role_id,
            "last_name": "Тестов",
            "first_name": username,
        },
        headers=headers,
    )
    assert user_resp.status_code == 201, user_resp.text

    from fastapi.testclient import TestClient

    from app.main import app

    # Отдельный TestClient со своей cookie-корзиной (lifespan уже отработал в фикстуре client)
    new_client = TestClient(app)
    login_resp = new_client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert login_resp.status_code == 200, login_resp.text
    return new_client


@pytest.fixture()
def admin(client):
    resp = login(client, "admin", "TestPass123!")
    assert resp.status_code == 200
    return client


class TestCreateDataset:
    def test_create_default_columns(self, admin):
        resp = admin.post("/api/datasets/", json={"name": "Поставки МТР"}, headers=csrf_headers(admin))
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] > 0
        assert body["name"] == "Поставки МТР"
        assert body["archived"] is False
        assert len(body["columns"]) == 10
        assert body["owner_name"] == "admin"

    def test_duplicate_name_rejected(self, admin):
        admin.post("/api/datasets/", json={"name": "Дубликат"}, headers=csrf_headers(admin))
        resp = admin.post("/api/datasets/", json={"name": "Дубликат"}, headers=csrf_headers(admin))
        assert resp.status_code == 400
        assert "уже существует" in resp.json()["detail"]


class TestDatasetVisibility:
    def test_regular_user_sees_only_own(self, admin):
        admin.post("/api/datasets/", json={"name": "Секретный план"}, headers=csrf_headers(admin))

        other = _create_user(admin, "econ_user1", "StrongPass1!", {"can_create_datasets": True})
        resp = other.post("/api/datasets/", json={"name": "Мой бюджет"}, headers=csrf_headers(other))
        assert resp.status_code == 201

        listing = other.get("/api/datasets/")
        assert listing.status_code == 200
        names = [d["name"] for d in listing.json()["items"]]
        assert "Мой бюджет" in names
        assert "Секретный план" not in names

    def test_admin_sees_everything(self, admin, client):
        admin.post("/api/datasets/", json={"name": "Виден всем"}, headers=csrf_headers(admin))

        other = _create_user(
            client, "econ_user2", "StrongPass1!", {"can_create_datasets": True}
        )
        other.post("/api/datasets/", json={"name": "Другой план"}, headers=csrf_headers(other))

        listing = admin.get("/api/datasets/")
        names = [d["name"] for d in listing.json()["items"]]
        assert "Виден всем" in names
        assert "Другой план" in names


class TestArchiveRestoreDuplicate:
    def test_archive_and_hide(self, admin):
        ds = admin.post("/api/datasets/", json={"name": "Для архива"}, headers=csrf_headers(admin)).json()
        assert admin.delete(f"/api/datasets/{ds['id']}", headers=csrf_headers(admin)).status_code == 204

        listing = admin.get("/api/datasets/").json()
        assert "Для архива" not in [d["name"] for d in listing["items"]]

        full = admin.get("/api/datasets/", params={"include_archived": "true"}).json()
        assert any(d["name"] == "Для архива" and d["archived"] for d in full["items"])

    def test_restore_from_archive(self, admin):
        ds = admin.post("/api/datasets/", json={"name": "Вернуть из архива"}, headers=csrf_headers(admin)).json()
        admin.delete(f"/api/datasets/{ds['id']}", headers=csrf_headers(admin))

        resp = admin.post(f"/api/datasets/{ds['id']}/restore", headers=csrf_headers(admin))
        assert resp.status_code == 200

        got = admin.get(f"/api/datasets/{ds['id']}").json()
        assert got["archived"] is False

    def test_duplicate_copies_rows(self, admin):
        ds = admin.post("/api/datasets/", json={"name": "Оригинал"}, headers=csrf_headers(admin)).json()
        row = admin.post(
            f"/api/datasets/{ds['id']}/rows/",
            json={"data": {"A": "Труба 50", "B": "10"}, "row_order": 0},
            headers=csrf_headers(admin),
        )
        assert row.status_code == 201, row.text

        dup = admin.post(
            f"/api/datasets/{ds['id']}/duplicate",
            params={"new_name": "Копия оригинала"},
            headers=csrf_headers(admin),
        )
        assert dup.status_code == 201
        dup_body = dup.json()
        assert dup_body["id"] != ds["id"]
        assert dup_body["name"] == "Копия оригинала"

        rows = admin.get(f"/api/datasets/{dup_body['id']}/rows/").json()
        assert rows["total"] == 1
        assert rows["items"][0]["data"]["A"] == "Труба 50"

    def test_permanent_delete_requires_archive_and_admin(self, admin):
        ds = admin.post("/api/datasets/", json={"name": "Удалить совсем"}, headers=csrf_headers(admin)).json()

        resp = admin.delete(f"/api/datasets/{ds['id']}/permanent", headers=csrf_headers(admin))
        assert resp.status_code == 400  # сначала архивировать

        admin.delete(f"/api/datasets/{ds['id']}", headers=csrf_headers(admin))
        resp = admin.delete(f"/api/datasets/{ds['id']}/permanent", headers=csrf_headers(admin))
        assert resp.status_code == 204

        assert admin.get(f"/api/datasets/{ds['id']}").status_code == 404


class TestAdminUsers:
    def test_create_user_and_login(self, client):
        login(client, "admin", "TestPass123!")
        other = _create_user(client, "mo", "StrongPass1!", {"can_view_datasets": True})
        me = other.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["username"] == "mo"

    def test_non_admin_cannot_manage_users(self, client):
        admin = login(client, "admin", "TestPass123!")
        other = _create_user(client, "mo2", "StrongPass1!", {"can_create_datasets": True})

        resp = other.get("/api/admin/users", headers=csrf_headers(other))
        assert resp.status_code == 403