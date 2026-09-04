"""
LLM 韧性：可重试错误判断、指数退避重试、健康检查
"""
import asyncio
import random
from typing import TypeVar, Callable, Awaitable, Tuple
from loguru import logger

from .circuit_breaker import CircuitBreaker, CircuitOpenError

T = TypeVar("T")


def is_retriable_error(exc: BaseException) -> bool:
    """判断是否为可重试错误（网络/超时/限流/5xx）"""
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError, OSError)):
        return True
    msg = str(exc).lower()
    if any(k in msg for k in ["429", "rate limit", "too many requests"]):
        return True
    if any(k in msg for k in ["500", "502", "503", "504"]):
        return True
    if "timeout" in msg or "timed out" in msg:
        return True
    return False


async def retry_with_backoff(
    coro_factory: Callable[[], Awaitable[T]],
    max_retries: int = 3,
    base_delay_sec: float = 1.0,
    max_delay_sec: float = 30.0,
    jitter: bool = True,
) -> T:
    """指数退避重试（不含首次，最多调用 1+max_retries 次）"""
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except CircuitOpenError:
            raise
        except Exception as e:
            last_exc = e
            if attempt == max_retries or not is_retriable_error(e):
                raise
            delay = min(base_delay_sec * (2 ** attempt), max_delay_sec)
            if jitter:
                delay = delay * (0.5 + random.random())
            logger.warning(f"调用失败 (第{attempt + 1}/{max_retries + 1}次), {delay:.1f}s后重试: {e}")
            await asyncio.sleep(delay)
    raise last_exc


async def run_health_check(
    base_url: str, api_key: str, model_name: str, timeout_sec: float = 10.0
) -> Tuple[bool, str]:
    """对 LLM 服务做最小化健康检查"""
    try:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=0,
            max_tokens=5,
            timeout=timeout_sec,
        )
        from langchain_core.messages import HumanMessage
        response = await llm.ainvoke([HumanMessage(content="1")])
        return True, "ok"
    except Exception as e:
        return False, str(e)
