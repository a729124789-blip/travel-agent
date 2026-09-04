"""
记忆管理器：统一管理短期 + 长期记忆，提供综合上下文查询
"""
from typing import Dict, Any, Optional
from loguru import logger

from .short_term import ShortTermMemory
from .long_term import LongTermMemory


class MemoryManager:
    """
    统一管理两层记忆：
    - 短期记忆：当前会话最近对话
    - 长期记忆：用户偏好、历史行程、跨会话聊天记录
    """

    def __init__(self, user_id: str, session_id: str, storage_path: str = "data/memory",
                 llm=None, max_turns: int = 10):
        """
        Args:
            user_id: 用户ID
            session_id: 会话ID
            storage_path: 长期记忆存储路径
            llm: langchain-openai ChatOpenAI 实例（用于长期记忆总结，可选）
            max_turns: 短期记忆最大轮数
        """
        self.user_id = user_id
        self.session_id = session_id
        self.llm = llm
        self.short_term = ShortTermMemory(max_turns=max_turns)
        self.long_term = LongTermMemory(user_id, storage_path)
        logger.info(f"记忆管理器初始化: user={user_id}, session={session_id}")

    def add_message(self, role: str, content: str, metadata: Dict = None):
        """同时写入短期和长期记忆"""
        self.short_term.add_message(role, content, metadata)
        self.long_term.add_chat_message(role, content, self.session_id)

    def get_full_context(self) -> Dict[str, Any]:
        """获取完整上下文（两层记忆）"""
        return {
            "short_term": {
                "recent_dialogue": self.short_term.get_recent_context(5),
                "context_string": self.short_term.get_context_string(5),
                "statistics": self.short_term.get_statistics()
            },
            "long_term": {
                "preferences": self.long_term.get_preference(),
                "chat_history": self.long_term.get_chat_history(10),
                "trip_history": self.long_term.get_trip_history(5),
                "frequent_destinations": self.long_term.get_frequent_destinations(3),
                "statistics": self.long_term.get_statistics()
            }
        }

    def get_context_for_agent(self, long_term_summary: str = None) -> str:
        """获取格式化的上下文字符串，供 Agent prompt 使用"""
        lines = []

        if long_term_summary:
            lines.append("【历史会话总结】")
            lines.append(long_term_summary)
            lines.append("")

        prefs = self.long_term.get_preference()
        if any(v for v in prefs.values() if v):
            lines.append("【用户偏好】")
            for key, value in prefs.items():
                if value:
                    lines.append(f"- {key}: {value}")
            lines.append("")

        context_str = self.short_term.get_context_string(3)
        if context_str != "无历史对话":
            lines.append("【当前会话对话】")
            lines.append(context_str)
            lines.append("")

        return "\n".join(lines) if lines else "无上下文信息"

    def end_session(self):
        self.short_term.clear()
        logger.info(f"会话结束: {self.session_id}")

    async def get_long_term_summary(self, max_messages: int = 50) -> str:
        """使用 LLM 总结长期聊天历史和行程记录"""
        if not self.llm:
            return ""

        # 排除当前会话的聊天记录
        all_history = self.long_term.get_chat_history(limit=max_messages)
        other_sessions = [m for m in all_history if m.get("session_id") != self.session_id]
        trip_history = self.long_term.get_trip_history(limit=20)

        if not other_sessions and not trip_history:
            return ""

        history_text = []
        for msg in other_sessions[-max_messages:]:
            ts = msg.get("timestamp", "")
            history_text.append(f"[{ts}] {msg.get('role', '?')}: {msg.get('content', '')}")
        history_str = "\n".join(history_text) if history_text else "（无聊天记录）"

        trip_text = []
        for trip in trip_history:
            origin = trip.get("origin", "未知")
            dest = trip.get("destination", "未知")
            start = trip.get("start_date", "")
            end = trip.get("end_date", "")
            purpose = trip.get("purpose", "旅游")
            ts = trip.get("timestamp", "")
            date_part = f"({start} 至 {end})" if start and end else f"({start})" if start else ""
            trip_text.append(f"[{ts}] {origin} → {dest} {date_part} - {purpose}")
        trip_str = "\n".join(trip_text) if trip_text else "（无行程记录）"

        prompt = f"""请总结以下历史信息中的关键内容，包括：
1. 用户的旅行偏好和习惯
2. 用户询问过的重要问题
3. 用户的出行历史和目的地
4. 其他重要的上下文信息

【历史聊天记录】
{history_str}

【历史行程记录】
{trip_str}

请用简洁的语言总结（不超过200字）："""

        try:
            from langchain_core.messages import HumanMessage
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            summary = response.content if hasattr(response, 'content') else str(response)
            logger.info(f"长期记忆总结生成完成 ({len(summary)}字)")
            return summary.strip()
        except Exception as e:
            logger.error(f"长期记忆总结失败: {e}")
            return ""
