"""Юнит-тесты логики аутентификации: пароли, токены, права."""
import pytest
from fastapi import HTTPException
from jose import jwt
from types import SimpleNamespace

from app.auth import (
    create_access_token,
    get_password_hash,
    has_permission,
    validate_password_strength,
    verify_password,
)
from app.config import settings


class TestPasswordStrength:
    @pytest.mark.parametrize(
        "password",
        [
            "Str0ng!Pass",
            "aB3$xYz7890!",
            "Correct Horse Battery Staple 1!",
        ],
    )
    def test_valid_password_pass(self, password):
        assert validate_password_strength(password) is True

    @pytest.mark.parametrize(
        "password,detail_part",
        [
            ("Short1!", "минимум 8 символов"),
            ("abcdefgh1!", "заглавную букву"),
            ("ABCDEFGH1!", "строчную букву"),
            ("Abcdefgh!", "цифру"),
            ("Abcdefgh1", "специальный символ"),
        ],
    )
    def test_invalid_password_raises(self, password, detail_part):
        with pytest.raises(HTTPException) as exc:
            validate_password_strength(password)
        assert detail_part in str(exc.value.detail)


class TestPasswordHashing:
    def test_hash_verify_roundtrip(self):
        hashed = get_password_hash("SuperSecret1!")
        assert hashed != "SuperSecret1!"
        assert verify_password("SuperSecret1!", hashed)

    def test_verify_wrong_password(self):
        hashed = get_password_hash("SuperSecret1!")
        assert not verify_password("SuperSecret2!", hashed)


class TestAccessToken:
    def test_token_roundtrip(self):
        token = create_access_token(data={"sub": "42"})
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        assert payload["sub"] == "42"
        assert payload["jti"]
        assert payload["iat"] <= payload["exp"]

    def test_token_expiry_respected(self):
        from datetime import timedelta
        token = create_access_token(data={"sub": "1"}, expires_delta=timedelta(seconds=-5))
        with pytest.raises(Exception):
            jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


class TestHasPermission:
    @staticmethod
    def _user(permissions, role_name="тестовая роль"):
        return SimpleNamespace(
            role=SimpleNamespace(name=role_name, permissions=permissions or {})
        )

    @staticmethod
    def _db():
        return SimpleNamespace()

    def test_direct_permission(self):
        user = self._user({"can_view_datasets": True})
        assert has_permission(user, "can_view_datasets", self._db())

    def test_missing_permission(self):
        user = self._user({"can_view_datasets": True})
        assert not has_permission(user, "can_export", self._db())

    def test_full_access_grants_anything(self):
        user = self._user({"full_access": True})
        assert has_permission(user, "can_manage_roles", self._db())

    def test_user_without_role(self):
        user = SimpleNamespace(role=None)
        assert not has_permission(user, "full_access", self._db())