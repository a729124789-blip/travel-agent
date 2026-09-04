"""
熔断器：连续失败后暂停调用，避免雪崩；超时后半开试探恢复
"""
import time
from enum import Enum
from typing import Optional
from loguru import logger


class CircuitState(Enum):
    CLOSED = "closed"           # 正常调用
    OPEN = "open"               # 拒绝调用，直接降级
    HALF_OPEN = "half_open"     # 试探性放行


class CircuitOpenError(Exception):
    """熔断器打开时抛出"""
    pass


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout_sec: float = 60.0,
                 half_open_successes: int = 2):
        self.failure_threshold = failure_threshold
        self.recovery_timeout_sec = recovery_timeout_sec
        self.half_open_successes = half_open_successes
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_success_count = 0
        self._last_failure_time: Optional[float] = None
        self._opened_at: Optional[float] = None

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            if time.monotonic() - self._opened_at >= self.recovery_timeout_sec:
                logger.info("熔断器: OPEN -> HALF_OPEN")
                self._state = CircuitState.HALF_OPEN
                self._half_open_success_count = 0
        return self._state

    def allow_call(self) -> bool:
        s = self.state
        return s != CircuitState.OPEN

    def record_success(self):
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_success_count += 1
            if self._half_open_success_count >= self.half_open_successes:
                logger.info("熔断器: HALF_OPEN -> CLOSED (恢复)")
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._opened_at = None
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def record_failure(self):
        self._last_failure_time = time.monotonic()
        if self._state == CircuitState.HALF_OPEN:
            logger.warning("熔断器: HALF_OPEN -> OPEN (半开期失败)")
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            self._failure_count = 0
            return
        if self._state == CircuitState.CLOSED:
            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
                logger.warning(f"熔断器: CLOSED -> OPEN (连续失败{self.failure_threshold}次)")
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()

    def raise_if_open(self):
        if not self.allow_call():
            raise CircuitOpenError("服务暂时不可用，请稍后再试")

    def get_status(self) -> dict:
        return {
            "state": self.state.value,
            "failure_count": self._failure_count,
            "last_failure_time": self._last_failure_time,
            "opened_at": self._opened_at,
        }
