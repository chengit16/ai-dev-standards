"""验证健康接口的真实 HTTP 响应和 OpenAPI 声明。"""

from fastapi.testclient import TestClient

from app import create_app


def test_health_contract() -> None:
    """客户端探测读取固定状态字段，并可通过 OpenAPI 追溯。"""
    with TestClient(create_app()) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        operation = client.get("/openapi.json").json()["paths"]["/api/health"]["get"]
        assert operation["operationId"] == "health"
        assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/HealthResponse"
        }
