"""Юнит-тесты автоопределения ролей колонок по заголовкам план/факт таблиц."""
from types import SimpleNamespace

from app.services.column_detection_service import (
    SUPPORTED_ROLES,
    detect_table_type,
    suggest_for_dataset,
)


def _dataset(headers, name="Тест"):
    columns = [{"id": chr(65 + i), "header": h, "type": "string"} for i, h in enumerate(headers)]
    return SimpleNamespace(id=1, name=name, columns=columns)


class TestDetectTableType:
    def test_plan_table(self):
        headers = ["кол-во по потребности", "стоимость, руб"]
        assert detect_table_type(headers) == "plan"

    def test_fact_table(self):
        headers = ["цена, руб. без ндс", "дата поступления"]
        assert detect_table_type(headers) == "fact"

    def test_explicit_plan_markers(self):
        headers = ["заявлено к приобретению", "месяц потребности"]
        assert detect_table_type(headers) == "plan"

    def test_explicit_fact_markers(self):
        headers = ["исполнение", "кол-во по спецификации"]
        assert detect_table_type(headers) == "fact"

    def test_unknown(self):
        assert detect_table_type(["имя", "примечание"]) == "unknown"


class TestSuggestForDataset:
    def test_plan_mapping(self):
        ds = _dataset(["Наименование материала", "кол-во по потребности", "стоимость, руб"])
        res = suggest_for_dataset(ds)
        assert res["_table_type"] == "plan"
        assert res["group"] == "A"
        assert res["plan_qty"] == "B"
        assert res["plan_cost"] == "C"
        # для план-таблиц факт-роли не имеют смысла
        assert res["actual_qty"] is None
        assert res["actual_cost"] is None

    def test_fact_mapping(self):
        ds = _dataset(["кол-во по потребности в спецификации", "цена, руб. без ндс"])
        res = suggest_for_dataset(ds)
        assert res["_table_type"] == "fact"
        assert res["actual_qty"] == "A"
        assert res["actual_cost"] == "B"
        assert res["plan_qty"] is None
        assert res["plan_cost"] is None

    def test_all_supported_roles_present(self):
        ds = _dataset(["Наименование", "ЕИ", "кол-во", "стоимость, руб"])
        res = suggest_for_dataset(ds)
        assert set(SUPPORTED_ROLES).issubset(res.keys())

    def test_highest_weight_wins(self):
        ds = _dataset(["материал", "полное наименование материала"])
        res = suggest_for_dataset(ds)
        assert res["group"] == "B"  # вес 100 против 50