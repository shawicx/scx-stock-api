"""
@description pytest 全局配置：测试 token 环境变量 + auth_headers fixture。

SCX_TEST_TOKEN 必须在 scx_stock.config.settings 被导入前设置（lru_cache）。
"""

import os

import pytest

# 在任何 scx_stock 模块被导入前设置
os.environ.setdefault("SCX_TEST_TOKEN", "test-token-for-smoke-tests")

_TEST_TOKEN = os.environ["SCX_TEST_TOKEN"]


@pytest.fixture
def auth_headers():
    """每个测试自动注入 X-Access-Token 头。"""
    return {"X-Access-Token": _TEST_TOKEN}
