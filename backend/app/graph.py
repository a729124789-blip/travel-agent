"""
LangGraph 图组装：把 8 个节点组装成可调度的智能体图

流程：
  START → load_memory → intent
       → (Send API 按 agent_schedule 动态 fan-out P1 节点)
         ├─ event_collection
         ├─ preference
         ├─ info_query
         ├─ rag
         └─ memory_query
       → join → itinerary_planning(条件) → aggregate → save_memory → END

记忆闭环：
  - load_memory: 注入长期记忆（偏好/行程/摘要）到 state
  - save_memory: 把 preference_updates 写回长期记忆；行程确认后把 origin 存为 last_origin
"""
from typing import Literal
from loguru import logger
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from langgraph.checkpoint.memory import MemorySaver

from app.state import TravelState
from app.nodes.intent import intent_node
from app.nodes.event_collection import event_collection_node
from app.nodes.preference import preference_node
from app.nodes.info_query import info_query_node
from app.nodes.rag import rag_node
from app.nodes.memory_query import memory_query_node
from app.nodes.itinerary_planning import itinerary_planning_node
from app.nodes.aggregate import aggregate_node

from app.memory.memory_manager import MemoryManager
from app.config import settings


# ============================================================
# 记忆管理器注册表：按 user_id 缓存 MemoryManager 实例
# ============================================================
_memory_managers: dict[str, MemoryManager] = {}


def get_memory_manager(user_id: str, session_id: str = "default") -> MemoryManager:
    """获取（或创建）指定用户的记忆管理器"""
    key = f"{user_id}::{session_id}"
    if key not in _memory_managers:
        _memory_managers[key] = MemoryManager(
            user_id=user_id,
            session_id=session_id,
            storage_path=settings.memory_path,
        )
    return _memory_managers[key]


def clear_memory_managers():
    """清空记忆管理器缓存（测试/管理用）"""
    _memory_managers.clear()


# ============================================================
# 记忆加载节点
# ============================================================
async def load_memory(state: TravelState) -> dict:
    """从长期记忆注入用户偏好、历史行程、记忆摘要到 state"""
    user_id = state.get("user_id", "default_user")
    session_id = state.get("session_id", "default")
    mm = get_memory_manager(user_id, session_id)

    preferences = mm.long_term.get_preference()
    trip_history = mm.long_term.get_trip_history(5)
    memory_summary = await mm.get_long_term_summary()

    # 短期记忆对话上下文（用于意图消歧）
    context_string = mm.short_term.get_context_string(3)
    if not context_string or context_string == "无历史对话":
        context_string = "无历史对话"

    logger.info(f"记忆加载: user={user_id}, 偏好={preferences}, 行程={len(trip_history)}条")
    return {
        "preferences": preferences or {},
        "trip_history": trip_history or [],
        "memory_summary": memory_summary or "",
        "context_string": context_string,
    }


# ============================================================
# 动态调度：根据 agent_schedule 决定 P1 并行执行哪些节点
# ============================================================
def route_p1(state: TravelState) -> list[Send]:
    """根据 agent_schedule 中的 P1 节点，动态 fan-out 并行执行"""
    schedule = state.get("agent_schedule", [])
    sends: list[Send] = []

    for task in schedule:
        name = task.get("agent_name")
        if not name:
            continue
        if name == "event_collection":
            sends.append(Send("event_collection", state))
        elif name == "preference":
            sends.append(Send("preference", state))
        elif name in ("information_query", "info_query"):
            sends.append(Send("info_query", state))
        elif name == "rag_knowledge":
            sends.append(Send("rag", state))
        elif name == "memory_query":
            sends.append(Send("memory_query", state))

    # 如果没有任何 P1 节点，给一个空 join 保证流程继续
    if not sends:
        sends.append(Send("join", state))
    return sends


# ============================================================
# Join 节点：P1 并行结果汇聚，判断是否需要行程规划
# ============================================================
async def join(state: TravelState) -> dict:
    """P1 节点并行完成后汇聚（当前无需额外逻辑，仅标记）"""
    return {}


def route_p2(state: TravelState) -> Literal["itinerary_planning", "aggregate"]:
    """判断是否需要执行行程规划：行程规划意图 且 有目的地"""
    intents = state.get("intents", [])
    event_info = state.get("event_info", {})
    has_plan_intent = any(
        i.get("type") == "itinerary_planning" for i in intents
    )
    has_destination = bool(event_info and event_info.get("destination"))
    if has_plan_intent and has_destination:
        return "itinerary_planning"
    return "aggregate"


# ============================================================
# 记忆写回节点
# ============================================================
async def save_memory(state: TravelState) -> dict:
    """
    把本轮结果写回长期记忆：
    1. 偏好变更（preference_updates）→ save_preference
    2. 行程规划完成 → 保存行程历史 + last_origin
    3. 记录对话到长期记忆
    """
    user_id = state.get("user_id", "default_user")
    session_id = state.get("session_id", "default")
    mm = get_memory_manager(user_id, session_id)

    # 1. 偏好写回
    for pref in state.get("preference_updates", []):
        ptype = pref.get("type")
        value = pref.get("value")
        action = pref.get("action", "replace")
        if not ptype or not value:
            continue
        if action == "append":
            current = mm.long_term.get_preference(ptype)
            if isinstance(current, list):
                if value not in current:
                    mm.long_term.save_preference(ptype, current + [value])
            else:
                mm.long_term.save_preference(ptype, [current, value] if current else [value])
            logger.info(f"偏好追加: {ptype} += {value}")
        else:
            mm.long_term.save_preference(ptype, value)
            logger.info(f"偏好覆盖: {ptype} = {value}")

    # 2. 行程确认：只有本次真正生成了行程才保存历史 + last_origin
    #    （防止上一轮残留的 event_info 被误存）
    event_info = state.get("event_info", {})
    itinerary = state.get("itinerary", {})
    intents = state.get("intents", [])
    is_planning = any(i.get("type") == "itinerary_planning" for i in intents)
    has_real_itinerary = bool(itinerary and itinerary.get("daily_plans"))
    if is_planning and has_real_itinerary and event_info and event_info.get("destination"):
        origin = event_info.get("origin")
        destination = event_info.get("destination")
        mm.long_term.save_trip_history({
            "origin": origin,
            "destination": destination,
            "start_date": event_info.get("start_date"),
            "end_date": event_info.get("end_date"),
            "purpose": event_info.get("trip_purpose", "旅游"),
            "transportation": event_info.get("transportation"),
            "summary": itinerary.get("title", ""),
        })
        logger.info(f"行程已保存: {origin} → {destination}")

        # last_origin 闭环：确认行程后把 origin 存为默认出发地
        if origin:
            mm.long_term.save_preference("last_origin", origin)
            logger.info(f"默认出发地已更新: {origin}")

    # 3. 记录对话
    user_input = state.get("user_input", "")
    final_response = state.get("final_response", "")
    if user_input:
        mm.add_message("user", user_input)
    if final_response:
        mm.add_message("assistant", final_response)

    return {}


# ============================================================
# 图构建
# ============================================================
def build_graph():
    """构建并编译 LangGraph 图（含 Checkpointer）"""
    g = StateGraph(TravelState)

    # 节点注册
    g.add_node("load_memory", load_memory)
    g.add_node("intent", intent_node)
    g.add_node("event_collection", event_collection_node)
    g.add_node("preference", preference_node)
    g.add_node("info_query", info_query_node)
    g.add_node("rag", rag_node)
    g.add_node("memory_query", memory_query_node)
    g.add_node("join", join)
    g.add_node("itinerary_planning", itinerary_planning_node)
    g.add_node("aggregate", aggregate_node)
    g.add_node("save_memory", save_memory)

    # 边
    g.add_edge(START, "load_memory")
    g.add_edge("load_memory", "intent")

    # 动态 fan-out：intent 后按 agent_schedule 分发 P1
    g.add_conditional_edges(
        "intent",
        route_p1,
        ["event_collection", "preference", "info_query", "rag", "memory_query", "join"],
    )

    # P1 节点全部汇聚到 join（注意：不包含 join 自身，避免自环）
    for node in ("event_collection", "preference", "info_query", "rag", "memory_query"):
        g.add_edge(node, "join")

    # join 后条件决定是否行程规划
    g.add_conditional_edges(
        "join",
        route_p2,
        {"itinerary_planning": "itinerary_planning", "aggregate": "aggregate"},
    )

    # 行程规划后走聚合
    g.add_edge("itinerary_planning", "aggregate")

    # 聚合后写回记忆
    g.add_edge("aggregate", "save_memory")
    g.add_edge("save_memory", END)

    # Checkpointer：支持会话级状态保存/恢复
    checkpointer = MemorySaver()
    return g.compile(checkpointer=checkpointer)


# 全局图实例
app_graph = build_graph()


async def run_graph(
    user_input: str,
    user_id: str = "default_user",
    session_id: str = "default",
) -> dict:
    """
    运行完整图流程，返回最终 state。

    Args:
        user_input: 用户输入
        user_id: 用户 ID
        session_id: 会话 ID（可复用同一会话实现多轮对话）
    """
    initial_state: TravelState = {
        "user_id": user_id,
        "session_id": session_id,
        "user_input": user_input,
        # 每轮对话是独立任务，清空上一轮的结果类字段，避免 Checkpointer 残留污染
        "intents": [],
        "key_entities": {},
        "rewritten_query": "",
        "agent_schedule": [],
        "event_info": {},
        "preference_updates": [],
        "info_query_result": {},
        "rag_result": {},
        "memory_result": {},
        "itinerary": {},
        "final_response": "",
        "errors": [],
    }

    # 用 thread_id 实现会话级 Checkpointer 状态隔离
    result = await app_graph.ainvoke(
        initial_state,
        config={"configurable": {"thread_id": f"{user_id}:{session_id}"}},
    )
    return result


async def run_form_plan(
    form_data: dict,
    user_id: str = "default_user",
    session_id: str = "default",
) -> dict:
    """
    表单直通行程规划：跳过 intent 二次识别（避免拼接句误判），
    直接用前端结构化表单字段构造 event_info，强制走行程规划链路。

    流程：注入 event_info → itinerary_planning → aggregate → save_memory

    form_data 关键字段：
        departure_city / city / start_date / end_date / travel_days
        transportation / accommodation / preferences / free_text_input
    """
    # 从表单构造 event_info
    departure = (form_data.get("departure_city") or "").strip()
    destination = (form_data.get("city") or "").strip()
    start_date = (form_data.get("start_date") or "").strip()
    end_date = (form_data.get("end_date") or "").strip()
    travel_days = form_data.get("travel_days")
    transportation = (form_data.get("transportation") or "").strip()
    accommodation = (form_data.get("accommodation") or "").strip()
    preferences = form_data.get("preferences") or []
    free_text = (form_data.get("free_text_input") or "").strip()

    try:
        travel_days = int(travel_days) if travel_days else None
    except (TypeError, ValueError):
        travel_days = None

    event_info = {
        "origin": departure or None,
        "destination": destination or None,
        "start_date": start_date or None,
        "end_date": end_date or None,
        "duration_days": travel_days,
        "return_location": departure or None,
        "trip_purpose": "旅游",
        "transportation": transportation or None,
        "accommodation": accommodation or None,
        "missing_info": [],
    }
    if not event_info["origin"]:
        event_info["missing_info"].append("出发地")
    if not event_info["destination"]:
        event_info["missing_info"].append("目的地")
    if not event_info["start_date"]:
        event_info["missing_info"].append("出发日期")

    # 用户自然语言表达（供 itinerary_planning 参考额外诉求）
    user_input = f"从{departure}出发去{destination}" if departure else f"去{destination}"
    if start_date:
        user_input += f"，{start_date}出发"
    if travel_days:
        user_input += f"，玩{travel_days}天"
    if transportation:
        user_input += f"，乘坐{transportation}"
    if accommodation:
        user_input += f"，住宿{accommodation}"
    if preferences:
        user_input += f"，偏好{('、'.join(preferences))}"
    if free_text:
        user_input += f"，{free_text}"

    # 记忆加载（注入偏好，供规划参考）
    mm = get_memory_manager(user_id, session_id)
    memory_prefs = mm.long_term.get_preference() or {}

    state: TravelState = {
        "user_id": user_id,
        "session_id": session_id,
        "user_input": user_input,
        "intents": [{"type": "itinerary_planning", "confidence": 1.0}],
        "key_entities": {},
        "rewritten_query": user_input,
        "agent_schedule": [],
        "preferences": memory_prefs,
        "trip_history": mm.long_term.get_trip_history(5),
        "memory_summary": await mm.get_long_term_summary() or "",
        "context_string": mm.short_term.get_context_string(3) or "无历史对话",
        "event_info": event_info,
        "preference_updates": [],
        "info_query_result": {},
        "rag_result": {},
        "memory_result": {},
        "itinerary": {},
        "final_response": "",
        "errors": [],
    }

    # 手动串联：itinerary_planning → aggregate → save_memory
    step1 = await itinerary_planning_node(state)
    state.update(step1)
    step2 = await aggregate_node(state)
    state.update(step2)
    await save_memory(state)

    return state
