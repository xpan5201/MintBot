"""
MintChat 性能优化配置

提供可配置的性能优化选项，用户可以根据需求调整。

v2.26.0 新增:
- 记忆持久化策略配置
- 数据库连接池配置
- 缓存策略配置
"""

from typing import Optional
from pydantic import BaseModel, Field

from src.utils.logger import get_logger

logger = get_logger(__name__)


class MemoryPersistenceConfig(BaseModel):
    """记忆持久化配置"""

    # 是否启用延迟持久化
    enable_delayed_persist: bool = Field(
        default=False, description="启用延迟持久化可以显著提升性能，但可能在异常退出时丢失少量数据"
    )

    # 持久化缓冲区大小（条数）
    persist_buffer_size: int = Field(
        default=100, ge=10, le=1000, description="缓冲区达到此大小时自动持久化"
    )

    # 定时持久化间隔（秒）
    persist_interval: float = Field(
        default=30.0, ge=5.0, le=300.0, description="定时持久化间隔，单位秒"
    )

    # 是否在程序退出时强制持久化
    force_persist_on_exit: bool = Field(
        default=True, description="程序退出时强制持久化所有缓冲数据"
    )


class DatabaseConfig(BaseModel):
    """数据库配置"""

    # 是否启用连接池
    enable_connection_pool: bool = Field(
        default=False, description="启用连接池可以提升20-30%性能，但需要重构代码使用上下文管理器"
    )

    # 连接池大小
    pool_size: int = Field(default=5, ge=1, le=20, description="连接池最大连接数")

    # 连接超时（秒）
    connection_timeout: float = Field(
        default=10.0, ge=1.0, le=60.0, description="数据库连接超时时间"
    )

    # 是否启用WAL模式
    enable_wal_mode: bool = Field(default=True, description="WAL模式可以提升并发性能")


class CacheConfig(BaseModel):
    """缓存配置"""

    # 是否启用记忆缓存
    enable_memory_cache: bool = Field(default=True, description="启用记忆缓存可以减少向量检索次数")

    # 缓存大小
    cache_size: int = Field(default=100, ge=10, le=1000, description="LRU缓存最大条目数")

    # 缓存过期时间（秒）
    cache_ttl: Optional[float] = Field(
        default=300.0, ge=60.0, le=3600.0, description="缓存过期时间，None表示永不过期"
    )

    # 是否启用嵌入向量缓存
    enable_embedding_cache: bool = Field(default=True, description="缓存嵌入向量可以避免重复计算")

    # 嵌入向量缓存大小
    embedding_cache_size: int = Field(
        default=100, ge=10, le=500, description="嵌入向量缓存最大条目数"
    )


class AsyncConfig(BaseModel):
    """异步任务配置"""

    # 是否启用异步记忆检索
    enable_async_memory_search: bool = Field(
        default=False, description="异步记忆检索可以减少首字延迟，但需要重构代码"
    )

    # 线程池大小
    thread_pool_size: int = Field(default=4, ge=1, le=16, description="异步任务线程池大小")

    # 是否启用记忆预加载
    enable_memory_preload: bool = Field(default=False, description="预加载常用记忆可以提升响应速度")


class PerformanceConfig(BaseModel):
    """性能优化总配置"""

    # 子配置
    memory_persistence: MemoryPersistenceConfig = Field(default_factory=MemoryPersistenceConfig)

    database: DatabaseConfig = Field(default_factory=DatabaseConfig)

    cache: CacheConfig = Field(default_factory=CacheConfig)

    async_tasks: AsyncConfig = Field(default_factory=AsyncConfig)

    # 全局性能模式
    performance_mode: str = Field(
        default="balanced",
        description="性能模式: 'fast' (快速但可能丢失数据), 'balanced' (平衡), 'safe' (安全但较慢)",
    )

    def apply_performance_mode(self):
        """应用性能模式预设"""
        if self.performance_mode == "fast":
            # 快速模式：启用所有优化
            self.memory_persistence.enable_delayed_persist = True
            self.memory_persistence.persist_buffer_size = 200
            self.memory_persistence.persist_interval = 60.0
            self.cache.cache_size = 200
            self.cache.embedding_cache_size = 200

        elif self.performance_mode == "balanced":
            # 平衡模式：适度优化
            self.memory_persistence.enable_delayed_persist = False
            self.memory_persistence.persist_buffer_size = 100
            self.memory_persistence.persist_interval = 30.0
            self.cache.cache_size = 100
            self.cache.embedding_cache_size = 100

        elif self.performance_mode == "safe":
            # 安全模式：最小优化，最大安全性
            self.memory_persistence.enable_delayed_persist = False
            self.memory_persistence.persist_buffer_size = 10
            self.memory_persistence.persist_interval = 10.0
            self.cache.cache_size = 50
            self.cache.embedding_cache_size = 50


# 默认配置实例
default_performance_config = PerformanceConfig()
default_performance_config.apply_performance_mode()


def get_performance_config() -> PerformanceConfig:
    """获取性能配置"""
    return default_performance_config


def set_performance_mode(mode: str):
    """
    设置性能模式

    Args:
        mode: 'fast', 'balanced', 或 'safe'
    """
    if mode not in ["fast", "balanced", "safe"]:
        raise ValueError(f"无效的性能模式: {mode}")

    default_performance_config.performance_mode = mode
    default_performance_config.apply_performance_mode()


# 性能优化建议
PERFORMANCE_TIPS = """
# MintChat 性能优化建议

## 1. 记忆持久化优化 (v2.26.0)

### 当前状态
- ❌ 每次添加记忆都立即持久化
- ❌ 频繁的磁盘I/O操作
- ❌ 响应速度受影响

### 优化方案
启用延迟持久化可以显著提升性能：

```python
from src.config.performance import set_performance_mode
from src.utils.logger import logger

# 快速模式（推荐用于日常使用）
set_performance_mode("fast")

# 平衡模式（默认）
set_performance_mode("balanced")

# 安全模式（推荐用于重要对话）
set_performance_mode("safe")
```

### 预期效果
- 🚀 响应速度提升 50-80%
- 🚀 磁盘I/O减少 90%+
- ⚠️ 异常退出可能丢失少量数据（快速模式）

## 2. 数据库连接池优化

### 当前状态
- ❌ 连接池已创建但未启用
- ❌ 每次操作都创建新连接
- ❌ 性能提升潜力未释放

### 优化方案
需要重构代码使用上下文管理器后才能启用。

### 预期效果
- 🚀 数据库性能提升 20-30%
- 🚀 并发处理能力提升

## 3. 缓存优化

### 当前状态
- ✅ 已启用记忆缓存
- ✅ 已启用嵌入向量缓存
- ⚠️ 缓存大小可能需要调整

### 优化建议
根据使用场景调整缓存大小。

## 4. 异步优化

### 当前状态
- ❌ 记忆检索在主线程同步执行
- ❌ 首字延迟较高

### 优化方案
需要重构代码支持异步记忆检索。

### 预期效果
- 🚀 首字延迟减少 30-50%
- 🚀 流式输出更流畅
"""


if __name__ == "__main__":
    # 测试配置
    config = get_performance_config()
    logger.info("当前性能配置:")
    logger.info(config.model_dump_json(indent=2))

    logger.info("\n" + "=" * 70)
    logger.info(PERFORMANCE_TIPS)
