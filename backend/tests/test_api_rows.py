"""Интеграционные тесты строк: CRUD, оптимистичная блокировка, уникальность, история."""
import pytest

from conftest import csrf_headers, login


def _make_dataset(client, name, unique_columns=None):
    payload = {"name": name}
    if unique_columns:
        payload["unique_columns"] = unique_columns
    resp = client.post("/api/datasets/", json=payload, headers=csrf_headers(client))
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_row(client, dataset_id, data, versions_headers=None):
    return client.post(
        f"/api/datasets/{dataset_id}/rows/",
        json={"data": data, "row_order": 0},
        headers=versions_headers or csrf_headers(client),
    )


@pytest.fixture()
def admin(client):
    resp = login(client, "admin", "TestPass123!")
    assert resp.status_code == 200
    return client


class TestCreateRow:
    def test_create_and_list(self, admin):
        ds = _make_dataset(admin, "Строки")
        resp = _create_row(admin, ds["id"], {"A": "Труба стальная", "B": "1500"})
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["version"] == 1
        assert body["sheet_id"] == "main"
        assert body["data"]["A"] == "Труба стальная"

        listing = admin.get(f"/api/datasets/{ds['id']}/rows/").json()
        assert listing["total"] == 1
        assert listing["items"][0]["id"] == body["id"]

    def test_unknown_column_auto_created(self, admin):
        ds = _make_dataset(admin, "Авто-колонки")
        resp = _create_row(admin, ds["id"], {"M": "значение"})
        assert resp.status_code == 201, resp.text


class TestOptimisticLock:
    def test_update_bumps_version(self, admin, client):
        ds = _make_dataset(admin, "Версии")
        row = _create_row(admin, ds["id"], {"A": "v1"}).json()

        resp = client.patch(
            f"/api/datasets/{ds['id']}/rows/{row['id']}",
            json={"data": {"A": "v2"}, "version": row["version"]},
            headers=csrf_headers(client),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["version"] == row["version"] + 1
        assert resp.json()["data"]["A"] == "v2"

    def test_stale_version_conflict(self, admin, client):
        ds = _make_dataset(admin, "Конфликт версий")
        row = _create_row(admin, ds["id"], {"A": "один"}).json()

        # Первый апдейт успешен
        first = client.patch(
            f"/api/datasets/{ds['id']}/rows/{row['id']}",
            json={"data": {"A": "два"}, "version": row["version"]},
            headers=csrf_headers(client),
        )
        assert first.status_code == 200
        current_version = first.json()["version"]

        # Второй клиент шлёт устаревшую версию
        resp = client.patch(
            f"/api/datasets/{ds['id']}/rows/{row['id']}",
            json={"data": {"A": "три"}, "version": row["version"]},
            headers=csrf_headers(client),
        )
        assert resp.status_code == 409
        assert resp.headers.get("X-Current-Version") == str(current_version)


class TestUniqueness:
    def test_duplicate_value_conflict(self, admin):
        ds = _make_dataset(admin, "Уникальные", unique_columns=["A"])
        assert _create_row(admin, ds["id"], {"A": "МК-001"}).status_code == 201

        resp = _create_row(admin, ds["id"], {"A": "МК-001"})
        assert resp.status_code == 409
        assert "уже существует" in resp.json()["detail"]


class TestDeleteRow:
    def test_delete(self, admin):
        ds = _make_dataset(admin, "Для удаления")
        row = _create_row(admin, ds["id"], {"A": "удалю"}).json()

        resp = admin.delete(
            f"/api/datasets/{ds['id']}/rows/{row['id']}", headers=csrf_headers(admin)
        )
        assert resp.status_code == 204

        listing = admin.get(f"/api/datasets/{ds['id']}/rows/").json()
        assert listing["total"] == 0


class TestCellHistory:
    def test_cell_history_records_changes(self, admin, client):
        ds = _make_dataset(admin, "История ячеек")
        row = _create_row(admin, ds["id"], {"A": "старое"}).json()

        update = client.patch(
            f"/api/datasets/{ds['id']}/rows/{row['id']}",
            json={"data": {"A": "новое"}, "version": row["version"]},
            headers=csrf_headers(client),
        )
        assert update.status_code == 200

        history = client.get(
            f"/api/datasets/{ds['id']}/rows/{row['id']}/cells/A/history",
            headers=csrf_headers(client),
        ).json()
        # create + update (порядок по changed_at desc может совпадать по времени — не полагаемся на индекс 0)
        assert len(history) >= 2
        update = next(h for h in history if h["new_value"] == "новое")
        assert update["old_value"] == "старое"
        assert any(h["new_value"] == "старое" and h["old_value"] is None for h in history)


class TestRowHistory:
    def test_row_history_present(self, admin, client):
        ds = _make_dataset(admin, "История строк")
        row = _create_row(admin, ds["id"], {"A": "первый"}).json()

        client.patch(
            f"/api/datasets/{ds['id']}/rows/{row['id']}",
            json={"data": {"A": "второй"}, "version": row["version"]},
            headers=csrf_headers(client),
        )

        history = client.get(
            f"/api/datasets/{ds['id']}/rows/{row['id']}/history",
            headers=csrf_headers(client),
        ).json()
        # эндпоинт возвращает список записей версий, не словарь с total
        assert len(history) >= 2