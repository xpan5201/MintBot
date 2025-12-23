"""
异步配置加载器 - v2.32.0

提供异步配置文件加载接口，避免阻塞主线程。

核心功能:
- 异步文件读取
- 配置缓存
- 热重载支持
- 性能监控
"""

import asyncio
import json
import yaml
from pathlib import Path
from typing import Any, Dict, Optional
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from src.utils.logger import get_logger
from src.utils.cache_manager import cache_manager

logger = get_logger(__name__)


class ConfigFileHandler(FileSystemEventHandler):
    """配置文件变更监听器"""
    
    def __init__(self, callback):
        self.callback = callback
        super().__init__()
    
    def on_modified(self, event):
        if not event.is_directory:
            asyncio.create_task(self.callback(event.src_path))


class AsyncConfigLoader:
    """异步配置加载器"""
    
    def __init__(
        self,
        config_dir: Path,
        enable_cache: bool = True,
        enable_hot_reload: bool = False,
    ):
        """
        初始化异步配置加载器
        
        Args:
            config_dir: 配置文件目录
            enable_cache: 是否启用缓存
            enable_hot_reload: 是否启用热重载
        """
        self.config_dir = config_dir
        self.enable_cache = enable_cache
        self.enable_hot_reload = enable_hot_reload
        
        # 文件监听器
        self._observer: Optional[Observer] = None
        self._reload_callbacks: Dict[str, list] = {}
        
        # 统计信息
        self._stats = {
            "total_loads": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_time": 0.0,
        }
        
        logger.info(f"异步配置加载器初始化: 目录={config_dir}, 缓存={enable_cache}, 热重载={enable_hot_reload}")
        
        # 启动热重载
        if enable_hot_reload:
            self._start_hot_reload()
    
    async def load_json(
        self,
        filename: str,
        use_cache: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        异步加载JSON配置文件
        
        Args:
            filename: 文件名
            use_cache: 是否使用缓存
        
        Returns:
            配置字典，失败返回None
        """
        start_time = time.perf_counter()
        file_path = self.config_dir / filename
        
        # 检查缓存
        if use_cache and self.enable_cache:
            cache_key = f"config_json_{filename}"
            cached_config = cache_manager.config_cache.get(cache_key)
            if cached_config is not None:
                self._stats["cache_hits"] += 1
                logger.debug(f"配置缓存命中: {filename}")
                return cached_config
        
        # 缓存未命中，异步加载
        self._stats["cache_misses"] += 1
        
        try:
            loop = asyncio.get_running_loop()
            config = await loop.run_in_executor(
                None,
                self._load_json_sync,
                file_path
            )
            
            # 添加到缓存
            if use_cache and self.enable_cache and config is not None:
                cache_key = f"config_json_{filename}"
                cache_manager.config_cache.set(cache_key, config)
            
            # 更新统计
            elapsed = time.perf_counter() - start_time
            self._stats["total_loads"] += 1
            self._stats["total_time"] += elapsed
            
            logger.debug(f"配置加载完成: {filename}, 耗时: {elapsed*1000:.1f}ms")
            return config
            
        except Exception as e:
            logger.error(f"异步加载JSON配置失败 {filename}: {e}")
            return None
    
    def _load_json_sync(self, file_path: Path) -> Dict[str, Any]:
        """同步加载JSON文件（在线程池中执行）"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载JSON文件失败 {file_path}: {e}")
            raise
    
    async def load_yaml(
        self,
        filename: str,
        use_cache: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        异步加载YAML配置文件
        
        Args:
            filename: 文件名
            use_cache: 是否使用缓存
        
        Returns:
            配置字典，失败返回None
        """
        start_time = time.perf_counter()
        file_path = self.config_dir / filename
        
        # 检查缓存
        if use_cache and self.enable_cache:
            cache_key = f"config_yaml_{filename}"
            cached_config = cache_manager.config_cache.get(cache_key)
            if cached_config is not None:
                self._stats["cache_hits"] += 1
                logger.debug(f"配置缓存命中: {filename}")
                return cached_config
        
        # 缓存未命中，异步加载
        self._stats["cache_misses"] += 1

        try:
            loop = asyncio.get_running_loop()
            config = await loop.run_in_executor(
                None,
                self._load_yaml_sync,
                file_path
            )

            # 添加到缓存
            if use_cache and self.enable_cache and config is not None:
                cache_key = f"config_yaml_{filename}"
                cache_manager.config_cache.set(cache_key, config)

            # 更新统计
            elapsed = time.perf_counter() - start_time
            self._stats["total_loads"] += 1
            self._stats["total_time"] += elapsed

            logger.debug(f"配置加载完成: {filename}, 耗时: {elapsed*1000:.1f}ms")
            return config

        except Exception as e:
            logger.error(f"异步加载YAML配置失败 {filename}: {e}")
            return None

    def _load_yaml_sync(self, file_path: Path) -> Dict[str, Any]:
        """同步加载YAML文件（在线程池中执行）"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"加载YAML文件失败 {file_path}: {e}")
            raise

    def _start_hot_reload(self):
        """启动热重载监听"""
        try:
            self._observer = Observer()
            handler = ConfigFileHandler(self._on_config_changed)
            self._observer.schedule(handler, str(self.config_dir), recursive=False)
            self._observer.start()
            logger.info("配置文件热重载已启动")
        except Exception as e:
            logger.error(f"启动热重载失败: {e}")

    async def _on_config_changed(self, file_path: str):
        """配置文件变更回调"""
        filename = Path(file_path).name
        logger.info(f"检测到配置文件变更: {filename}")

        # 清除缓存
        if self.enable_cache:
            cache_key_json = f"config_json_{filename}"
            cache_key_yaml = f"config_yaml_{filename}"
            cache_manager.config_cache.delete(cache_key_json)
            cache_manager.config_cache.delete(cache_key_yaml)

        # 调用注册的回调
        if filename in self._reload_callbacks:
            for callback in self._reload_callbacks[filename]:
                try:
                    await callback(filename)
                except Exception as e:
                    logger.error(f"配置重载回调失败: {e}")

    def register_reload_callback(self, filename: str, callback):
        """注册配置重载回调"""
        if filename not in self._reload_callbacks:
            self._reload_callbacks[filename] = []
        self._reload_callbacks[filename].append(callback)
        logger.debug(f"注册配置重载回调: {filename}")

    def stop_hot_reload(self):
        """停止热重载"""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            logger.info("配置文件热重载已停止")

    def get_stats(self) -> Dict:
        """获取统计信息"""
        stats = self._stats.copy()
        total_requests = stats["cache_hits"] + stats["cache_misses"]
        if total_requests > 0:
            stats["cache_hit_rate"] = stats["cache_hits"] / total_requests
        else:
            stats["cache_hit_rate"] = 0.0

        if stats["total_loads"] > 0:
            stats["avg_load_time"] = stats["total_time"] / stats["total_loads"]
        else:
            stats["avg_load_time"] = 0.0

        return stats


# 全局异步配置加载器实例
_global_config_loader: Optional[AsyncConfigLoader] = None


def get_async_config_loader(
    config_dir: Path,
    enable_cache: bool = True,
    enable_hot_reload: bool = False,
) -> AsyncConfigLoader:
    """
    获取全局异步配置加载器（单例模式）

    Args:
        config_dir: 配置文件目录
        enable_cache: 是否启用缓存
        enable_hot_reload: 是否启用热重载

    Returns:
        AsyncConfigLoader: 异步配置加载器
    """
    global _global_config_loader

    if _global_config_loader is None:
        _global_config_loader = AsyncConfigLoader(
            config_dir=config_dir,
            enable_cache=enable_cache,
            enable_hot_reload=enable_hot_reload,
        )

    return _global_config_loader


# 示例用法
if __name__ == "__main__":
    async def test():
        """测试异步配置加载"""
        from pathlib import Path

        config_dir = Path("config")
        loader = get_async_config_loader(config_dir, enable_cache=True)

        # 加载JSON配置
        config = await loader.load_json("config.json")
        if config:
            print(f"JSON配置加载成功: {len(config)} 项")

        # 测试缓存
        await loader.load_json("config.json")  # 应该命中缓存

        # 获取统计
        stats = loader.get_stats()
        print(f"统计信息: {stats}")

    # 运行测试
    asyncio.run(test())
