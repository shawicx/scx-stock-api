"""
@description 冒烟测试：验证包可导入、应用可创建、路由已挂载。
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from scx_stock.main import create_app

    app = create_app()
    # 跳过 lifespan 中的 DB 初始化，直接测路由
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_app_importable():
    """应用可导入并创建。"""
    from scx_stock.main import create_app

    app = create_app()
    assert app.title == "scx-stock-api"


def test_stock_route_mounted(client):
    """个股路由已挂载。"""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/api/v1/stock/{code}" in paths
    assert "/api/v1/search" in paths
    assert "/admin/sync" in paths
    assert "/health" in paths
    assert "/health/ready" in paths


def test_liveness_endpoint(client):
    """存活探针始终 200 + code 0。"""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "ok"


def test_response_format_uniform(client):
    """成功响应统一为 {code, message, data} 格式。"""
    resp = client.get("/health")
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "data"}
    assert body["message"] == "ok"


def test_param_validation_error_format(client):
    """参数校验失败返回统一格式（含 code 42201）。"""
    # search 缺少必填 q 参数
    resp = client.get("/api/v1/search")
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == 42201
    assert "message" in body


def test_invalid_code_rejected(client):
    """非法代码返回 400。"""
    resp = client.get("/api/v1/stock/abc123")
    assert resp.status_code == 400


def test_unknown_stock_returns_graceful_error(client):
    """格式合法但数据源取不到的代码，应优雅降级（不返回 500）。

    注：此用例依赖网络与数据源，结果不确定；仅断言不崩溃。
    """
    resp = client.get("/api/v1/stock/899999")
    assert resp.status_code != 500
    assert resp.status_code in (200, 404, 502)
