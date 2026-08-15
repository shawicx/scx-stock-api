"""
@description 配置加载测试：验证 .env 路径解析不依赖进程工作目录。
"""

import os
from pathlib import Path

import pytest

from scx_stock.config import settings as settings_mod


def test_env_file_points_to_project_root():
    """_ENV_FILE 指向项目根目录的 .env（绝对路径）。"""
    assert settings_mod._ENV_FILE.is_absolute()
    # 项目根：包含 pyproject.toml 的目录
    assert (settings_mod._ENV_FILE.parent / "pyproject.toml").exists()
    assert settings_mod._ENV_FILE.name == ".env"


def test_project_root_located_regardless_of_cwd(tmp_path, monkeypatch):
    """从任意 cwd 启动，_project_root() 都能定位到同一项目根。"""
    root_in_project = settings_mod._project_root()

    # 切换到一个无关临时目录，重新计算应得到相同结果
    monkeypatch.chdir(tmp_path)
    root_from_tmp = settings_mod._project_root()

    assert root_from_tmp == root_in_project


def test_get_settings_loads_env_overrides_defaults(monkeypatch):
    """.env 中的值覆盖 settings.py 默认值。

    通过临时设置 SCX_ 环境变量验证优先级（不依赖真实 .env 内容）。
    """
    # 清理 lru_cache 以应用新的环境变量
    settings_mod.get_settings.cache_clear()
    monkeypatch.setenv("SCX_DB_USER", "test_user_xyz")
    try:
        s = settings_mod.get_settings()
        assert s.db_user == "test_user_xyz"
    finally:
        settings_mod.get_settings.cache_clear()
        monkeypatch.delenv("SCX_DB_USER", raising=False)


def test_env_file_value_is_absolute_path_string():
    """Settings.model_config 的 env_file 是绝对路径字符串。"""
    env_file = settings_mod.Settings.model_config.get("env_file")
    assert isinstance(env_file, str)
    assert Path(env_file).is_absolute()


def test_auth_code_ttl_default_and_env_override(monkeypatch):
    """授权码有效期默认 72 小时（3 天），SCX_AUTH_CODE_TTL_HOURS 可覆盖。"""
    settings_mod.get_settings.cache_clear()
    try:
        s = settings_mod.get_settings()
        assert s.auth_code_ttl_hours == 72

        monkeypatch.setenv("SCX_AUTH_CODE_TTL_HOURS", "168")
        settings_mod.get_settings.cache_clear()
        s_override = settings_mod.get_settings()
        assert s_override.auth_code_ttl_hours == 168
    finally:
        settings_mod.get_settings.cache_clear()
        monkeypatch.delenv("SCX_AUTH_CODE_TTL_HOURS", raising=False)
