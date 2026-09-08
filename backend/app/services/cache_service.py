"""
Redis 缓存服务：用户偏好热数据缓存，降低 JSON 文件读写频率
"""
import json
from typing import Any, Optional
from loguru import logger

try:
    import redis
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False
    logger.warning("redis 包未安装，缓存服务将降级为无缓存模式")


class CacheService:
    """Redis 缓存封装，带自动降级（Redis 不可用时静默跳过）"""

    def __init__(self, redis_url: str = "redis://localhost:6379/0", default_ttl: int = 3600):
        self.default_ttl = default_ttl
        self._client = None
        self._enabled = False
        self._hits = 0
        self._misses = 0

        if not _REDIS_AVAILABLE:
            logger.warning("CacheService 降级：redis 包未安装")
            return

        try:
            self._client = redis.from_url(redis_url, decode_responses=True)
            self._client.ping()
            self._enabled = True
            logger.info(f"Redis 缓存已连接: {redis_url}")
        except Exception as e:
            logger.warning(f"Redis 连接失败，缓存降级: {e}")
            self._client = None
            self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return round(self._hits / total, 3) if total > 0 else 0.0

    def get(self, key: str) -> Optional[Any]:
        """读取缓存，返回反序列化后的对象或 None"""
        if not self._enabled or self._client is None:
            return None
        try:
            raw = self._client.get(key)
            if raw is not None:
                self._hits += 1
                return json.loads(raw)
            self._misses += 1
            return None
        except Exception as e:
            logger.debug(f"缓存读取失败: {e}")
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """写入缓存，value 会被 JSON 序列化"""
        if not self._enabled or self._client is None:
            return False
        try:
            self._client.setex(key, ttl or self.default_ttl, json.dumps(value, ensure_ascii=False))
            return True
        except Exception as e:
            logger.debug(f"缓存写入失败: {e}")
            return False

    def invalidate(self, key: str) -> bool:
        """失效指定缓存键"""
        if not self._enabled or self._client is None:
            return False
        try:
            self._client.delete(key)
            return True
        except Exception as e:
            logger.debug(f"缓存失效失败: {e}")
            return False

    def get_stats(self) -> dict:
        return {
            "enabled": self._enabled,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
        }


# 全局单例
_cache_service: Optional[CacheService] = None


def init_cache(redis_url: str = "redis://localhost:6379/0", default_ttl: int = 3600) -> CacheService:
    """初始化全局缓存服务"""
    global _cache_service
    _cache_service = CacheService(redis_url, default_ttl)
    return _cache_service


def get_cache() -> Optional[CacheService]:
    """获取全局缓存服务实例"""
    return _cache_service
