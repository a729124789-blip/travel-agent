"""
短期记忆：存储当前会话最近的对话历史，用于上下文理解和消歧
"""
from typing import List, Dict, Any
from datetime import datetime
from loguru import logger


class ShortTermMemory:
    """存储最近 N 轮对话，自动淘汰旧消息"""

    def __init__(self, max_turns: int = 10):
        self.max_turns = max_turns
        self.messages: List[Dict[str, Any]] = []

    def add_message(self, role: str, content: str, metadata: Dict = None):
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        self.messages.append(message)

        # 每轮 = 2条消息（用户 + 助手）
        max_messages = self.max_turns * 2
        if len(self.messages) > max_messages:
            self.messages = self.messages[-max_messages:]

        logger.debug(f"短期记忆新增: {role}")

    def get_recent_context(self, n_turns: int = None) -> List[Dict[str, Any]]:
        if n_turns is None:
            return self.messages.copy()
        n_messages = n_turns * 2
        return self.messages[-n_messages:] if len(self.messages) > n_messages else self.messages.copy()

    def get_context_string(self, n_turns: int = 5) -> str:
        messages = self.get_recent_context(n_turns)
        if not messages:
            return "无历史对话"
        lines = []
        for msg in messages:
            role_name = "用户" if msg["role"] == "user" else "助手"
            lines.append(f"{role_name}: {msg['content']}")
        return "\n".join(lines)

    def clear(self):
        self.messages = []
        logger.info("短期记忆已清空")

    def get_statistics(self) -> Dict[str, Any]:
        return {
            "total_messages": len(self.messages),
            "max_turns": self.max_turns,
            "oldest_message_time": self.messages[0]["timestamp"] if self.messages else None,
            "newest_message_time": self.messages[-1]["timestamp"] if self.messages else None
        }
