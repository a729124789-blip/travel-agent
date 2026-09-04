"""
LLM 服务：封装 ChatOpenAI，按任务类型路由模型，内置熔断+重试
"""
import asyncio
from typing import List, Dict, Any, Optional, Callable, Awaitable
from loguru import logger
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from openai import AsyncOpenAI

from app.config import settings
from app.utils.circuit_breaker import CircuitBreaker, CircuitOpenError
from app.utils.llm_resilience import retry_with_backoff
from app.utils.json_parser import robust_json_parse, extract_content


class LLMService:
    """
    按任务类型管理多个 ChatOpenAI 实例，每个实例独立熔断器。
    目前所有任务类型统一用 deepseek-v4-flash-0731，后续改配置即可切换。
    """

    def __init__(self):
        self._models: Dict[str, ChatOpenAI] = {}
        self._breakers: Dict[str, CircuitBreaker] = {}

        for task_type, model_cfg in settings.llm_models.items():
            self._models[task_type] = ChatOpenAI(
                model=model_cfg["model"],
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                temperature=model_cfg.get("temperature", 0.7),
                max_tokens=model_cfg.get("max_tokens", 4096),
            )
            self._breakers[task_type] = CircuitBreaker(
                failure_threshold=settings.circuit_failure_threshold,
                recovery_timeout_sec=settings.circuit_recovery_timeout_sec,
            )
            logger.info(f"LLM 模型已加载: task={task_type}, model={model_cfg['model']}")

    def _get_llm(self, task_type: str) -> ChatOpenAI:
        return self._models.get(task_type, self._models["default"])

    def _get_breaker(self, task_type: str) -> CircuitBreaker:
        return self._breakers.get(task_type, self._breakers["default"])

    async def ainvoke(
        self,
        messages: List[Dict[str, str] | HumanMessage | SystemMessage],
        task_type: str = "default",
    ) -> str:
        """
        调用 LLM，返回纯文本内容。
        内置熔断器检查 + 指数退避重试。

        Args:
            messages: 消息列表，支持 dict 格式或 langchain Message 对象
            task_type: 任务类型（default/intent/planning/rag）
        """
        breaker = self._get_breaker(task_type)
        breaker.raise_if_open()

        # 统一转换为 langchain Message 对象
        lc_messages = self._to_langchain_messages(messages)
        llm = self._get_llm(task_type)

        async def _call():
            return await llm.ainvoke(lc_messages)

        try:
            response = await retry_with_backoff(
                _call,
                max_retries=settings.max_retries,
                base_delay_sec=settings.retry_base_delay_sec,
                max_delay_sec=settings.retry_max_delay_sec,
            )
            breaker.record_success()
            content = extract_content(response)
            # deepseek 偶发返回空内容：视为失败，额外指数退避重试
            empty_attempts = 0
            while (not content or not content.strip()) and empty_attempts < settings.max_retries:
                empty_attempts += 1
                delay = min(settings.retry_base_delay_sec * (2 ** (empty_attempts - 1)), settings.retry_max_delay_sec)
                logger.warning(f"LLM 返回空内容 (第{empty_attempts}/{settings.max_retries}次重试, {delay:.1f}s后) task={task_type}")
                await asyncio.sleep(delay)
                response = await retry_with_backoff(
                    _call,
                    max_retries=1,
                    base_delay_sec=settings.retry_base_delay_sec,
                    max_delay_sec=settings.retry_max_delay_sec,
                )
                content = extract_content(response)
            if not content or not content.strip():
                raise ValueError("LLM 返回空内容（重试后仍为空）")
            logger.debug(f"LLM 调用成功: task={task_type}, {len(content)}字")
            return content
        except CircuitOpenError:
            raise
        except Exception as e:
            breaker.record_failure()
            logger.error(f"LLM 调用失败: task={task_type}, error={e}")
            raise

    async def ainvoke_json(
        self,
        messages: List[Dict[str, str] | HumanMessage | SystemMessage],
        task_type: str = "default",
        fallback: Optional[dict] = None,
    ) -> dict:
        """调用 LLM 并鲁棒解析 JSON 输出；解析失败时重新调用 LLM（最多 max_retries 次）"""
        text = await self.ainvoke(messages, task_type)
        for attempt in range(settings.max_retries):
            try:
                return robust_json_parse(text, fallback=fallback)
            except Exception as e:
                delay = min(settings.retry_base_delay_sec * (2 ** attempt), settings.retry_max_delay_sec)
                logger.warning(f"LLM JSON 解析失败 (第{attempt + 1}/{settings.max_retries}次重试, {delay:.1f}s后) task={task_type}: {e}")
                await asyncio.sleep(delay)
                text = await self.ainvoke(messages, task_type)
        # 最后再尝试一次，仍失败则抛错（由调用方兜底）
        return robust_json_parse(text, fallback=fallback)

    @staticmethod
    def _resolve_llm_conn(llm: ChatOpenAI) -> dict:
        """从 ChatOpenAI 实例解析连接参数（兼容不同属性命名，并解开 langchain 的 SecretStr）"""
        model = getattr(llm, "model_name", None) or getattr(llm, "model", "") or ""
        api_key = (
            getattr(llm, "openai_api_key", None)
            or getattr(llm, "api_key", None)
            or settings.llm_api_key
        )
        # langchain 的 api key 是 SecretStr 包装，需解包为明文
        if hasattr(api_key, "get_secret_value"):
            api_key = api_key.get_secret_value()
        base_url = (
            getattr(llm, "openai_api_base", None)
            or getattr(llm, "base_url", None)
            or settings.llm_base_url
        )
        temperature = getattr(llm, "temperature", 0.7)
        max_tokens = getattr(llm, "max_tokens", 4096)
        return {
            "model": model,
            "api_key": api_key,
            "base_url": base_url,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

    async def astream_chat(
        self,
        messages: List[Dict[str, str] | HumanMessage | SystemMessage],
        task_type: str = "default",
        on_reasoning: Optional[Callable[[str], Awaitable[None]]] = None,
        on_delta: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> str:
        """
        流式调用 LLM，实时回调两路增量：
          - on_reasoning(content): 模型思考过程（reasoning_content，如 glm 深度思考的英文思考）
          - on_delta(content): 最终正文增量
        返回完整正文文本。

        说明：langchain 的流式会丢弃 reasoning_content（OpenAI 兼容接口里深度思考模型
        的思考内容在 delta.reasoning_content 中），因此这里直接用 openai SDK 流式解析。
        """
        llm = self._get_llm(task_type)
        conn = self._resolve_llm_conn(llm)

        # 统一转换为 openai 消息格式
        lc_messages = self._to_langchain_messages(messages)
        _role_map = {"human": "user", "ai": "assistant", "system": "system"}
        openai_messages = []
        for m in lc_messages:
            role = _role_map.get(m.type, "user")
            openai_messages.append({"role": role, "content": m.content})

        client = AsyncOpenAI(api_key=conn["api_key"], base_url=conn["base_url"])
        full = ""
        breaker = self._get_breaker(task_type)
        # 深度思考类模型可通过 reasoning_effort 控制思考量（low/high/max），无配置则不透传
        model_cfg = settings.llm_models.get(task_type, {})
        reasoning_effort = model_cfg.get("reasoning_effort")
        try:
            breaker.raise_if_open()
            _kwargs = dict(
                model=conn["model"],
                messages=openai_messages,
                temperature=conn["temperature"],
                max_tokens=conn["max_tokens"],
                stream=True,
            )
            if reasoning_effort:
                _kwargs["reasoning_effort"] = reasoning_effort
            stream = await client.chat.completions.create(**_kwargs)
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta is None:
                    continue
                r = getattr(delta, "reasoning_content", None) or ""
                if r and on_reasoning:
                    await on_reasoning(r)
                c = getattr(delta, "content", None) or ""
                if c:
                    full += c
                    if on_delta:
                        await on_delta(c)
            if not full or not full.strip():
                raise ValueError("LLM 流式返回空内容")
            breaker.record_success()
            logger.debug(f"LLM 流式调用成功: task={task_type}, {len(full)}字")
            return full
        except CircuitOpenError:
            raise
        except Exception as e:
            breaker.record_failure()
            logger.error(f"LLM 流式调用失败: task={task_type}, error={e}")
            raise

    async def astream_chat_json(
        self,
        messages: List[Dict[str, str] | HumanMessage | SystemMessage],
        task_type: str = "default",
        on_reasoning: Optional[Callable[[str], Awaitable[None]]] = None,
        on_delta: Optional[Callable[[str], Awaitable[None]]] = None,
        fallback: Optional[dict] = None,
    ) -> dict:
        """流式调用 LLM 并鲁棒解析 JSON（思考过程通过 on_reasoning 实时回调）"""
        text = await self.astream_chat(messages, task_type, on_reasoning=on_reasoning, on_delta=on_delta)
        for attempt in range(settings.max_retries):
            try:
                return robust_json_parse(text, fallback=fallback)
            except Exception as e:
                delay = min(settings.retry_base_delay_sec * (2 ** attempt), settings.retry_max_delay_sec)
                logger.warning(f"LLM 流式 JSON 解析失败 (第{attempt + 1}/{settings.max_retries}次重试, {delay:.1f}s后) task={task_type}: {e}")
                await asyncio.sleep(delay)
                text = await self.astream_chat(messages, task_type, on_reasoning=on_reasoning, on_delta=on_delta)
        return robust_json_parse(text, fallback=fallback)

    @staticmethod
    def _to_langchain_messages(messages) -> list:
        """将 dict 格式消息转换为 langchain Message 对象"""
        result = []
        for msg in messages:
            if isinstance(msg, (HumanMessage, SystemMessage, AIMessage)):
                result.append(msg)
            elif isinstance(msg, dict):
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "system":
                    result.append(SystemMessage(content=content))
                elif role == "assistant":
                    result.append(AIMessage(content=content))
                else:
                    result.append(HumanMessage(content=content))
        return result

    def get_status(self) -> dict:
        """获取所有模型的熔断器状态"""
        return {
            task: breaker.get_status()
            for task, breaker in self._breakers.items()
        }


# 全局单例
llm_service = LLMService()
