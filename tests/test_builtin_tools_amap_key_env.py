from __future__ import annotations

from src.agent import builtin_tools


def test_builtin_tools_amap_key_prefers_env(monkeypatch) -> None:
    monkeypatch.setenv("AMAP_API_KEY", "env_key")
    monkeypatch.setenv("GAODE_API_KEY", "gaode_key")
    assert builtin_tools._get_amap_key() == "env_key"


def test_builtin_tools_amap_key_uses_gaode_env(monkeypatch) -> None:
    monkeypatch.delenv("AMAP_API_KEY", raising=False)
    monkeypatch.setenv("GAODE_API_KEY", "gaode_key")
    assert builtin_tools._get_amap_key() == "gaode_key"


def test_builtin_tools_amap_key_falls_back_to_config(monkeypatch) -> None:
    monkeypatch.delenv("AMAP_API_KEY", raising=False)
    monkeypatch.delenv("GAODE_API_KEY", raising=False)
    monkeypatch.setattr(builtin_tools, "_get_config", lambda: {"AMAP": {"api_key": "cfg_key"}})
    assert builtin_tools._get_amap_key() == "cfg_key"


def test_builtin_tools_amap_key_env_overrides_config(monkeypatch) -> None:
    monkeypatch.setenv("AMAP_API_KEY", "env_key")
    monkeypatch.setattr(builtin_tools, "_get_config", lambda: {"AMAP": {"api_key": "cfg_key"}})
    assert builtin_tools._get_amap_key() == "env_key"
