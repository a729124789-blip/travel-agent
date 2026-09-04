"""
LangGraph 全局状态定义
所有节点共享的状态字典，节点返回的 dict 会合并到状态中
"""
from typing import TypedDict, Optional


class TravelState(TypedDict, total=False):
    """旅行助手 Graph 的全局状态"""

    # ===== 会话信息 =====
    user_id: str
    session_id: str

    # ===== 用户输入 =====
    user_input: str

    # ===== 意图识别结果（intent_node 输出）=====
    intents: list[dict]           # [{type, confidence, description, reason}]
    key_entities: dict            # {origin, destination, date, duration, other}
    rewritten_query: str          # 标准化后的查询
    agent_schedule: list[dict]    # [{agent_name, priority, reason, expected_output}]

    # ===== 记忆上下文（load_memory 节点注入）=====
    preferences: dict             # 长期记忆偏好快照：{last_origin, hotel_brands, ...}
    trip_history: list[dict]      # 历史行程
    memory_summary: str           # 长期记忆摘要
    context_string: str           # 短期记忆对话上下文

    # ===== P1 并行信息收集结果 =====
    event_info: dict              # 事项收集：{origin, destination, start_date, end_date, missing_info}
    preference_updates: list      # 偏好提取：[{type, value, action}]（本次变更，待写回）
    info_query_result: dict       # 信息查询：{summary, sources}
    rag_result: dict              # RAG 检索：{answer, sources}
    memory_result: dict           # 记忆查询：{answer, result}

    # ===== P2 行程规划结果 =====
    itinerary: dict               # {title, duration, daily_plans, meals, notes}

    # ===== 最终输出 =====
    final_response: str
    errors: list[str]
