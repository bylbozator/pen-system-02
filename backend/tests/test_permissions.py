"""Юнит-тесты прав доступа на уровне колонок и фильтра строк."""
from types import SimpleNamespace

from app.dependencies import apply_row_filter, can_edit_column
from app import models


def _user(role_name="экономист", permissions=None, user_id=1, department=None):
    return SimpleNamespace(
        id=user_id,
        department=department,
        role=SimpleNamespace(name=role_name, permissions=permissions or {}),
    )


def _dataset(owner_id=1, columns=None, row_filter=None):
    return SimpleNamespace(
        owner_id=owner_id,
        columns=columns or [],
        row_filter=row_filter,
    )


class TestCanEditColumn:
    def test_no_restrictions(self):
        ds = _dataset(columns=[{"id": "A", "editableBy": []}])
        assert can_edit_column(_user(), ds, "A", SimpleNamespace())

    def test_empty_editable_by_means_anyone(self):
        ds = _dataset(columns=[{"id": "A", "editableBy": ["экономист"]}])
        assert can_edit_column(_user("экономист"), ds, "A", SimpleNamespace())

    def test_role_not_allowed(self):
        # владелец (owner_id=999) отличается от пользователя (user_id=1),
        # чтобы проверка именно по editableBy
        ds = _dataset(owner_id=999, columns=[{"id": "A", "editableBy": ["экономист"]}])
        assert not can_edit_column(_user("снабжение"), ds, "A", SimpleNamespace())

    def test_full_access_allowed(self):
        ds = _dataset(owner_id=999, columns=[{"id": "A", "editableBy": ["экономист"]}])
        user = _user("something", permissions={"full_access": True})
        assert can_edit_column(user, ds, "A", SimpleNamespace())

    def test_owner_allowed(self):
        ds = _dataset(owner_id=5, columns=[{"id": "A", "editableBy": ["экономист"]}])
        assert can_edit_column(_user(user_id=5), ds, "A", SimpleNamespace())

    def test_unknown_column_creatable(self):
        ds = _dataset(columns=[{"id": "A", "editableBy": []}])
        assert can_edit_column(_user("экономист"), ds, "ZZ", SimpleNamespace())


class TestApplyRowFilter:
    @staticmethod
    def _make_dataset_with_rows(db, row_filter, rows_data):
        ds = models.Dataset(
            name=f"datasets via filter {id(row_filter)}",
            owner_id=1,
            columns=[{"id": "dept", "header": "Отдел", "type": "string", "editableBy": []}],
            row_filter=row_filter,
        )
        db.add(ds)
        db.flush()
        for data in rows_data:
            db.add(models.Row(dataset_id=ds.id, data=data, row_order=0))
        db.commit()
        return ds

    def test_no_filter_returns_same_query(self, db_session):
        ds = self._make_dataset_with_rows(db_session, None, [{"dept": "Цех"}])
        base = db_session.query(models.Row).filter(models.Row.dataset_id == ds.id)
        assert apply_row_filter(base, ds, _user(department="Цех"), db_session).count() == 1

    def test_filter_by_department(self, db_session):
        ds = self._make_dataset_with_rows(
            db_session,
            {"column_id": "dept", "type": "department"},
            [{"dept": "Цех"}, {"dept": "Склад"}],
        )
        base = db_session.query(models.Row).filter(models.Row.dataset_id == ds.id)
        user = _user(department="Склад")
        assert apply_row_filter(base, ds, user, db_session).count() == 1

    def test_filter_by_role(self, db_session):
        ds = self._make_dataset_with_rows(
            db_session,
            {"column_id": "dept", "type": "role"},
            [{"dept": "экономист"}, {"dept": "снабжение"}],
        )
        base = db_session.query(models.Row).filter(models.Row.dataset_id == ds.id)
        user = _user(role_name="экономист")
        assert apply_row_filter(base, ds, user, db_session).count() == 1

    def test_user_without_value_sees_nothing(self, db_session):
        ds = self._make_dataset_with_rows(
            db_session,
            {"column_id": "dept", "type": "department"},
            [{"dept": "Цех"}],
        )
        base = db_session.query(models.Row).filter(models.Row.dataset_id == ds.id)
        user = _user(department=None)
        assert apply_row_filter(base, ds, user, db_session).count() == 0