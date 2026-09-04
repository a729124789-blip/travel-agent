"""
聚合节点：汇总所有节点结果，生成面向用户的最终回复

根据主导意图（intents）选择性地组织 final_response：
- itinerary_planning（行程规划）：展示行程 + 待补充信息
- memory_query（记忆查询）：展示记忆回答
- information_query（信息查询）：展示搜索/天气结果
- rag_knowledge（知识库问答）：展示知识库回答
- preference（偏好管理）：确认偏好已保存
"""
import json
from loguru import logger

from app.state import TravelState


def _find_primary_intent(intents: list) -> str:
    """找到最高优先级的意图类型（intents 已按置信度排序）"""
    if not intents:
        return "general"
    # intents 通常形如 [{"type": "itinerary_planning", "confidence": 0.9, ...}]
    return intents[0].get("type", "general")


def _format_event_summary(event_info: dict) -> str:
    """格式化行程信息摘要"""
    if not event_info:
        return ""
    origin = event_info.get("origin", "？")
    dest = event_info.get("destination", "？")
    start = event_info.get("start_date", "")
    end = event_info.get("end_date", "")
    days = event_info.get("duration_days", "")
    purpose = event_info.get("trip_purpose", "")
    transport = event_info.get("transportation", "")

    parts = []
    if origin and dest:
        parts.append(f"{origin} → {dest}")
    if days:
        parts.append(f"{days}天")
    if start:
        parts.append(f"{start}" + (f" 至 {end}" if end and end != start else ""))
    if transport:
        parts.append(f"交通：{transport}")
    if purpose:
        parts.append(f"目的：{purpose}")
    return "，".join(parts) if parts else ""


def _format_itinerary(itinerary: dict) -> str:
    """格式化行程为可读文本"""
    if not itinerary or not itinerary.get("daily_plans"):
        return "（行程规划未能生成）"
    title = itinerary.get("title", "行程规划")
    duration = itinerary.get("duration", "")
    route = itinerary.get("route", "")
    budget = itinerary.get("estimated_budget", "")
    lines = [f"# {title}" + (f"（{duration}）" if duration else "")]
    if route:
        lines.append(f"路线：{route}")
    if budget:
        lines.append(f"预算：{budget}")
    lines.append("")

    for plan in itinerary.get("daily_plans", []):
        day = plan.get("day", "?")
        date = plan.get("date", "")
        theme = plan.get("theme", "")
        city = plan.get("city", "")
        header = f"## 第{day}天" + (f" {date}" if date else "") + (f" · {theme}" if theme else "") + (f"（{city}）" if city else "")
        lines.append(header)
        for act in plan.get("activities", []):
            time = act.get("time", "")
            location = act.get("location", "")
            desc = act.get("description", "")
            transport = act.get("transport", "")
            line = f"- {time} {location}"
            if desc:
                line += f"\n  {desc}"
            if transport:
                line += f"\n  🚗 {transport}"
            lines.append(line)
        meals = plan.get("meals", {})
        if meals:
            lunch = meals.get("lunch", "")
            dinner = meals.get("dinner", "")
            if lunch or dinner:
                lines.append(f"- 🍽 午餐：{lunch or '自理'} / 晚餐：{dinner or '自理'}")
        lines.append("")

    notes = itinerary.get("notes", [])
    if notes:
        lines.append("## 注意事项")
        for note in notes:
            lines.append(f"- {note}")
    return "\n".join(lines)


def _format_preferences(preferences: list) -> str:
    """格式化偏好更新确认"""
    if not preferences:
        return ""
    lines = []
    for pref in preferences:
        ptype = pref.get("type", "")
        value = pref.get("value", "")
        action = pref.get("action", "replace")
        type_names = {
            "last_origin": "默认出发地",
            "hotel_brands": "酒店偏好",
            "airlines": "航空公司偏好",
            "seat_preference": "座位偏好",
            "meal_preference": "餐食偏好",
            "budget_level": "预算等级",
            "transportation_preference": "交通偏好",
            "food_preference": "美食偏好",
        }
        name = type_names.get(ptype, ptype)
        action_text = "已更新为" if action == "replace" else "已追加"
        lines.append(f"- {name}：{action_text}「{value}」")
    return "\n".join(lines)


async def aggregate_node(state: TravelState) -> dict:
    """
    LangGraph 节点：聚合所有节点结果，生成 final_response

    读取 state 中各节点输出，按主导意图组织最终回复。
    """
    intents = state.get("intents", [])
    primary = _find_primary_intent(intents)

    # 收集错误
    errors = []
    for key in ("event_info", "info_query_result", "rag_result", "memory_result", "itinerary"):
        val = state.get(key)
        if isinstance(val, dict) and val.get("status") == "error":
            errors.append(val.get("message", f"{key} 执行失败"))

    # 偏好管理意图
    if primary == "preference" and state.get("preference_updates"):
        pref_list = state["preference_updates"]
        if pref_list:
            text = f"好的，已记住您的偏好：\n\n{_format_preferences(pref_list)}"
            return {"final_response": text, "errors": errors}

    # 记忆查询意图
    if primary == "memory_query" and state.get("memory_result"):
        mem = state["memory_result"]
        if mem.get("status") == "success":
            return {"final_response": mem.get("answer", ""), "errors": errors}

    # 信息查询意图
    if primary == "information_query" and state.get("info_query_result"):
        info = state["info_query_result"]
        if info.get("status") == "error":
            return {"final_response": f"信息查询失败：{info.get('results', {}).get('message', '未知错误')}", "errors": errors}
        summary = info.get("results", {}).get("summary", "")
        if summary:
            return {"final_response": summary, "errors": errors}

    # RAG 知识库意图
    if primary == "rag_knowledge" and state.get("rag_result"):
        rag = state["rag_result"]
        if rag.get("status") == "success":
            answer = rag.get("answer", "")
            if rag.get("retrieved_documents"):
                answer += "\n\n> 依据商旅知识库回答"
            return {"final_response": answer, "errors": errors}
        if rag.get("status") == "no_knowledge":
            return {"final_response": rag.get("answer", "知识库中没有找到相关信息。"), "errors": errors}

    # 行程规划意图（核心）
    if primary == "itinerary_planning" or state.get("itinerary"):
        event_summary = _format_event_summary(state.get("event_info", {}))
        itinerary = state.get("itinerary", {})

        # 待补充信息
        missing = state.get("event_info", {}).get("missing_info", [])
        missing_text = ""
        if missing:
            missing_text = "\n\n📋 以下信息可补充，让行程更精准：\n" + "\n".join(f"- {m}" for m in missing)

        if itinerary and itinerary.get("daily_plans"):
            text = _format_itinerary(itinerary)
            if event_summary:
                text = f"**行程概览：{event_summary}**\n\n" + text
            if missing_text:
                text += missing_text
            return {"final_response": text, "errors": errors}

        # 行程信息不全
        if event_summary:
            return {
                "final_response": f"已识别您的行程：{event_summary}。\n\n请补充以下信息后为您生成完整行程：\n" + "\n".join(f"- {m}" for m in missing) if missing else "请补充出发地、日期等信息。",
                "errors": errors,
            }

    # 兜底：通用回复
    if errors:
        return {"final_response": "部分功能执行遇到问题，请稍后重试。\n" + "\n".join(f"- {e}" for e in errors), "errors": errors}
    return {"final_response": "收到，请告诉我您的旅行计划，我会帮您规划行程。", "errors": errors}
