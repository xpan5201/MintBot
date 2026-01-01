"""
异步图片加载器 - v2.32.0

提供异步图片加载接口，避免阻塞主线程，提升GUI响应速度。

核心功能:
- 异步图片加载
- 图片缓存
- 缩略图生成
- 批量加载
- 性能监控
"""

import asyncio
from pathlib import Path
from typing import Optional, Dict, Tuple
from PIL import Image
import time
from concurrent.futures import ThreadPoolExecutor
import threading

from src.utils.logger import get_logger

logger = get_logger(__name__)


class AsyncImageLoader:
    """异步图片加载器"""

    def __init__(
        self,
        max_workers: int = 4,
        cache_size: int = 100,
        thumbnail_size: Tuple[int, int] = (256, 256),
    ):
        """
        初始化异步图片加载器

        Args:
            max_workers: 最大工作线程数
            cache_size: 缓存大小
            thumbnail_size: 缩略图尺寸
        """
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.cache_size = cache_size
        self.thumbnail_size = thumbnail_size
        self._cache_lock = threading.Lock()

        # 图片缓存 {path: (image, timestamp)}
        self._cache: Dict[str, Tuple[Image.Image, float]] = {}
        self._cache_order: list = []  # LRU顺序

        # 统计信息
        self._stats = {
            "total_loads": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_time": 0.0,
        }

        logger.info(f"异步图片加载器初始化: 工作线程={max_workers}, 缓存大小={cache_size}")

    def _load_image_sync(self, image_path: Path) -> Image.Image:
        """同步加载图片（在线程池中执行）"""
        try:
            image = Image.open(image_path)
            # 转换为RGB模式（如果需要）
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGB")
            return image
        except Exception as e:
            logger.error(f"加载图片失败 {image_path}: {e}")
            raise

    async def load_image(
        self,
        image_path: Path,
        use_cache: bool = True,
    ) -> Optional[Image.Image]:
        """
        异步加载图片

        Args:
            image_path: 图片路径
            use_cache: 是否使用缓存

        Returns:
            PIL Image对象，失败返回None
        """
        start_time = time.perf_counter()
        path_str = str(image_path)

        # 检查缓存
        if use_cache:
            with self._cache_lock:
                if path_str in self._cache:
                    self._stats["cache_hits"] += 1
                    image, _ = self._cache[path_str]

                    # 更新LRU顺序
                    try:
                        self._cache_order.remove(path_str)
                    except ValueError:
                        pass
                    self._cache_order.append(path_str)

                    logger.debug(f"图片缓存命中: {image_path.name}")
                    return image

        # 缓存未命中，异步加载
        self._stats["cache_misses"] += 1

        try:
            loop = asyncio.get_running_loop()
            image = await loop.run_in_executor(self.executor, self._load_image_sync, image_path)

            # 添加到缓存
            if use_cache:
                with self._cache_lock:
                    self._add_to_cache(path_str, image)

            # 更新统计
            elapsed = time.perf_counter() - start_time
            self._stats["total_loads"] += 1
            self._stats["total_time"] += elapsed

            logger.debug(f"图片加载完成: {image_path.name}, 耗时: {elapsed * 1000:.1f}ms")
            return image

        except Exception as e:
            logger.error(f"异步加载图片失败 {image_path}: {e}")
            return None

    def _add_to_cache(self, path: str, image: Image.Image):
        """添加图片到缓存（LRU策略）"""
        # 如果缓存已满，移除最旧的
        if len(self._cache) >= self.cache_size:
            oldest_path = self._cache_order.pop(0)
            del self._cache[oldest_path]

        # 添加新图片
        self._cache[path] = (image, time.time())
        self._cache_order.append(path)

    async def load_thumbnail(
        self,
        image_path: Path,
        size: Optional[Tuple[int, int]] = None,
        use_cache: bool = True,
    ) -> Optional[Image.Image]:
        """
        异步加载缩略图

        Args:
            image_path: 图片路径
            size: 缩略图尺寸，默认使用初始化时的尺寸
            use_cache: 是否使用缓存

        Returns:
            PIL Image对象（缩略图），失败返回None
        """
        if size is None:
            size = self.thumbnail_size

        # 加载原图
        image = await self.load_image(image_path, use_cache=use_cache)
        if image is None:
            return None

        # 生成缩略图
        try:
            thumbnail = image.copy()
            thumbnail.thumbnail(size, Image.Resampling.LANCZOS)
            return thumbnail
        except Exception as e:
            logger.error(f"生成缩略图失败 {image_path}: {e}")
            return None

    async def load_images_batch(
        self,
        image_paths: list[Path],
        use_cache: bool = True,
    ) -> list[Optional[Image.Image]]:
        """
        批量异步加载图片

        Args:
            image_paths: 图片路径列表
            use_cache: 是否使用缓存

        Returns:
            PIL Image对象列表
        """
        tasks = [self.load_image(path, use_cache=use_cache) for path in image_paths]
        return await asyncio.gather(*tasks, return_exceptions=False)

    def clear_cache(self):
        """清空缓存"""
        with self._cache_lock:
            self._cache.clear()
            self._cache_order.clear()
        logger.info("图片缓存已清空")

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

        stats["cache_size"] = len(self._cache)
        return stats

    def shutdown(self):
        """关闭加载器"""
        self.executor.shutdown(wait=True)
        self.clear_cache()
        logger.info("异步图片加载器已关闭")


# 全局异步图片加载器实例
_global_image_loader: Optional[AsyncImageLoader] = None


def get_async_image_loader(
    max_workers: int = 4,
    cache_size: int = 100,
) -> AsyncImageLoader:
    """
    获取全局异步图片加载器（单例模式）

    Args:
        max_workers: 最大工作线程数
        cache_size: 缓存大小

    Returns:
        AsyncImageLoader: 异步图片加载器
    """
    global _global_image_loader

    if _global_image_loader is None:
        _global_image_loader = AsyncImageLoader(
            max_workers=max_workers,
            cache_size=cache_size,
        )

    return _global_image_loader


# 示例用法
if __name__ == "__main__":

    async def test():
        """测试异步图片加载"""
        loader = get_async_image_loader(max_workers=4, cache_size=10)

        # 测试单张图片加载
        test_image = Path("test.jpg")
        if test_image.exists():
            image = await loader.load_image(test_image)
            if image:
                print(f"图片加载成功: {image.size}")

            # 测试缩略图
            thumbnail = await loader.load_thumbnail(test_image, size=(128, 128))
            if thumbnail:
                print(f"缩略图生成成功: {thumbnail.size}")

            # 测试缓存
            await loader.load_image(test_image)  # 应该命中缓存

            # 获取统计
            stats = loader.get_stats()
            print(f"统计信息: {stats}")

        # 关闭加载器
        loader.shutdown()

    # 运行测试
    asyncio.run(test())
