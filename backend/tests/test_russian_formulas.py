"""Юнит-тесты конвертации русских имён функций Excel в английские."""
import pytest

from app.services.russian_formulas import convert_russian_formula


class TestConvertRussianFormula:
    @pytest.mark.parametrize(
        "source,expected",
        [
            ("=СУММ(A1:A10)", "=SUM(A1:A10)"),
            ("=СРЗНАЧ(B2:B5)+МАКС(C2)", "=AVERAGE(B2:B5)+MAX(C2)"),
            ("=ЕСЛИ(A1>0;СУММ(B1);ПРОИЗВЕД(C1;C2))", "=IF(A1>0;SUM(B1);PRODUCT(C1;C2))"),
            ("=ЕСЛИ(СУММ(A:A)>100;\"СУММ\"&A1;0)", '=IF(SUM(A:A)>100;"СУММ"&A1;0)'),
            ("=ПРОИЗВЕД(СУММ(A1:A3);2)", "=PRODUCT(SUM(A1:A3);2)"),
            ("=МИН(A1;B1)", "=MIN(A1;B1)"),
            ("=СЖПРОБЕЛЫ(A1)", "=TRIM(A1)"),
        ],
    )
    def test_conversion(self, source, expected):
        assert convert_russian_formula(source) == expected

    def test_non_equation_returns_as_is(self):
        assert convert_russian_formula("СУММ(A1)") == "СУММ(A1)"
        assert convert_russian_formula("просто текст") == "просто текст"

    def test_empty_and_none(self):
        assert convert_russian_formula("") == ""
        assert convert_russian_formula(None) is None

    def test_function_name_in_operand_position(self):
        assert convert_russian_formula("=A1+СУММ(B2:C2)") == "=A1+SUM(B2:C2)"

    def test_word_before_name_is_not_needed(self):
        # Названия-подстроки без открывающей скобки не конвертируются
        assert convert_russian_formula("=год") == "=год"