from httpx import AsyncClient


async def test_register_session_logout_and_login(client: AsyncClient):
    register = await client.post(
        "/api/auth/register",
        json={
            "email": "User@Example.com",
            "display_name": "Test User",
            "password": "long-secure-password",
        },
    )
    assert register.status_code == 201
    assert register.json()["user"]["email"] == "user@example.com"
    assert "HttpOnly" in register.headers["set-cookie"]
    assert "password" not in register.text

    current = await client.get("/api/auth/me")
    assert current.status_code == 200

    captured_session = client.cookies.get("sourcebeam_session")
    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 401

    client.cookies.set("sourcebeam_session", captured_session)
    assert (await client.get("/api/auth/me")).status_code == 401
    client.cookies.delete("sourcebeam_session")

    bad_login = await client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "wrong"},
    )
    assert bad_login.status_code == 401

    login = await client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "long-secure-password"},
    )
    assert login.status_code == 200


async def test_duplicate_registration_is_rejected(client: AsyncClient):
    payload = {
        "email": "same@example.com",
        "display_name": "Same User",
        "password": "long-secure-password",
    }
    assert (await client.post("/api/auth/register", json=payload)).status_code == 201
    assert (await client.post("/api/auth/register", json=payload)).status_code == 409


async def test_login_rate_limit_runs_before_password_work(client: AsyncClient):
    payload = {"email": "missing@example.com", "password": "wrong"}
    responses = [await client.post("/api/auth/login", json=payload) for _ in range(9)]
    assert [response.status_code for response in responses[:8]] == [401] * 8
    assert responses[8].status_code == 429
    assert "Retry-After" in responses[8].headers
