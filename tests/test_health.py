from httpx import AsyncClient


async def test_liveness_reports_service_version(client: AsyncClient):
    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Sourcebeam AI API",
        "version": "2.0.0",
    }


async def test_readiness_checks_database(client: AsyncClient):
    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "available"}
