"""
记忆查询节点：基于用户长期记忆回答历史相关问题
（我去过哪些地方 / 我之前说过什么偏好 / 上次去北京是什么时候）
"""
from loguru import logger

from app.state import TravelState
from app.services.llm_service import llm_service


def _format_trip_history(trip_history: list) -> str:
    """格式化旅行历史"""
    if not trip_history:
        return "（暂无旅行记录）"
    lines = []
    for i, trip in enumerate(trip_history, 1):
        origin = trip.get("origin", "未知")
        dest = trip.get("destination", "未知")
        start = trip.get("start_date", "")
        end = trip.get("end_date", "")
        purpose = trip.get("purpose", "旅游")
        ts = trip.get("timestamp", "")
        if start and end:
            lines.append(f"{i}. {origin} → {dest} ({start} 至 {end}) - {purpose}")
        elif start:
            lines.append(f"{i}. {origin} → {dest} ({start}) - {purpose}")
        else:
            lines.append(f"{i}. {origin} → {dest} - {purpose} (记录时间: {ts})")
    return "\n".join(lines)


def _format_preferences(preferences: dict) -> str:
    """格式化用户偏好"""
    if not preferences or not any(v for v in preferences.values() if v):
        return "（暂无偏好记录）"
    lines = []
    pref_names = {
        "last_origin": "默认出发地",
        "hotel_brands": "酒店偏好",
        "airlines": "航空公司偏好",
        "seat_preference": "座位偏好",
        "meal_preference": "餐食偏好",
        "budget_level": "预算等级",
        "transportation_preference": "交通偏好",
        "food_preference": "美食偏好",
    }
    for key, value in preferences.items():
        if value:
            name = pref_names.get(key, key)
            lines.append(f"- {name}: {value}")
    return "\n".join(lines) if lines else "（暂无偏好记录）"


async def memory_query_node(state: TravelState) -> dict:
    """
    LangGraph 节点：记忆查询

    从 state 读取 user_input、trip_history、preferences、memory_summary，
    调用 LLM 生成基于记忆的回答。
    """
    user_input = state.get("user_input", "")
    if not user_input:
        return {"memory_result": {"status": "error", "message": "无法获取用户查询"}}

    # 从 state 获取记忆数据（由 graph 组装时注入）
    trip_history = state.get("trip_history", [])
    preferences = state.get("current_preferences", {})
    chat_summary = state.get("memory_summary", "")

    trip_text = _format_trip_history(trip_history)
    pref_text = _format_preferences(preferences)

    prompt = f"""你是个人记忆助手，请基于用户的历史记忆回答问题。

【用户问题】
{user_input}

【用户旅行历史】
{trip_text}

【用户偏好】
{pref_text}

【历史对话摘要】
{chat_summary if chat_summary else "（暂无历史对话摘要）"}

【任务说明】
基于用户的历史记忆回答，如无相关记录请诚实说明，不要编造。"""

    try:
        answer = await llm_service.ainvoke(
            messages=[
                {"role": "system", "content": "你是个人记忆助手，帮助用户查询和理解他们的历史记录。"},
                {"role": "user", "content": prompt},
            ],
            task_type="default",
        )
        if not answer:
            answer = "无法基于记忆生成回答"

        logger.info(f"记忆查询回答: {user_input[:30]}...")
        return {
            "memory_result": {
                "status": "success",
                "query": user_input,
                "answer": answer,
                "memory_sources": {
                    "trip_count": len(trip_history),
                    "has_preferences": any(v for v in preferences.values() if v),
                    "has_chat_summary": bool(chat_summary),
                },
            }
        }
    except Exception as e:
        logger.error(f"记忆查询失败: {e}")
        return {
            "memory_result": {
                "status": "error",
                "message": f"记忆查询失败: {str(e)}",
                "query": user_input,
            }
        }
