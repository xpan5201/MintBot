"""
配置管理模块

提供应用程序的配置管理功能。
"""

from .settings import Settings, TTSConfig, load_settings

__all__ = ["Settings", "TTSConfig", "load_settings"]
