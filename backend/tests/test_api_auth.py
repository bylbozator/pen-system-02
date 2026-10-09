"""Интеграционные тесты аутентификации через API (TestClient)."""


class TestLogin:
    def test_login_success(self, client):
        resp = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "TestPass123!"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["user"]["username"] == "admin"
        assert body["user"]["role_name"] == "администратор"
        assert body["user"]["is_active"] is True

    def test_login_wrong_password(self, client):
        resp = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "WrongPass1!"},
        )
        assert resp.status_code == 401
        assert "Неверное имя пользователя" in resp.json()["detail"]

    def test_login_unknown_user(self, client):
        resp = client.post(
            "/api/auth/login",
            json={"username": "nobody", "password": "TestPass123!"},
        )
        assert resp.status_code == 401

    def test_login_bad_body(self, client):
        resp = client.post("/api/auth/login", json={"username": "admin"})
        assert resp.status_code == 422


class TestMe:
    def test_me_authenticated(self, client):
        client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "TestPass123!"},
        )
        resp = client.get("/api/auth/me")
        assert resp.status_code == 200
        assert resp.json()["username"] == "admin"

    def test_me_without_token(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401


class TestChangePassword:
    def test_full_flow(self, client):
        client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "TestPass123!"},
        )
        headers = {"X-CSRF-Token": client.cookies.get("csrf_token", "")}
        resp = client.post(
            "/api/auth/change-password",
            json={"old_password": "TestPass123!", "new_password": "NewPass456!"},
            headers=headers,
        )
        assert resp.status_code == 200

        old = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "TestPass123!"},
        )
        assert old.status_code == 401

        new = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "NewPass456!"},
        )
        assert new.status_code == 200

    def test_wrong_old_password(self, client):
        client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "TestPass123!"},
        )
        headers = {"X-CSRF-Token": client.cookies.get("csrf_token", "")}
        resp = client.post(
            "/api/auth/change-password",
            json={"old_password": "Wrong1!", "new_password": "NewPass456!"},
            headers=headers,
        )
        assert resp.status_code == 400

    def test_weak_new_password(self, client):
        client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "TestPass123!"},
        )
        headers = {"X-CSRF-Token": client.cookies.get("csrf_token", "")}
        resp = client.post(
            "/api/auth/change-password",
            json={"old_password": "TestPass123!", "new_password": "weak"},
            headers=headers,
        )
        assert resp.status_code == 400


class TestLogout:
    def test_logout_revokes_token(self, client):
        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "TestPass123!"},
        )
        token = login.json()["access_token"]
        assert token

        logout = client.post("/api/auth/logout")
        assert logout.status_code == 200

        # После logout токен отозван и работать не должен
        client.cookies.set("access_token", token, path="/")
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401