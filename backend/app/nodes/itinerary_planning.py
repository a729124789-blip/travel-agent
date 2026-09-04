"""
行程规划节点：基于事项收集结果（event_info）+ 用户偏好生成完整行程
（每日安排、交通、住宿、预算，信息不完整也给出可用规划）
"""
from datetime import datetime
from loguru import logger

from app.state import TravelState
from app.services.llm_service import llm_service


def _format_preferences(preferences: dict) -> str:
    """格式化用户偏好（规划时优先考虑）"""
    if not preferences or not any(v for v in preferences.values() if v):
        return ""
    parts = ["【用户偏好】（规划时优先考虑）"]
    pref_names = {
        "hotel_brands": "酒店偏好",
        "airlines": "航空偏好",
        "seat_preference": "座位偏好",
        "meal_preference": "餐食偏好",
        "budget_level": "预算等级",
        "transportation_preference": "交通偏好",
        "food_preference": "美食偏好",
        "last_origin": "默认出发地",
    }
    for key, value in preferences.items():
        if not value:
            continue
        name = pref_names.get(key, key)
        if isinstance(value, list):
            parts.append(f"• {name}: {', '.join(str(v) for v in value)}")
        else:
            parts.append(f"• {name}: {value}")
    if len(parts) > 1:
        return "\n".join(parts) + "\n\n"
    return ""


async def itinerary_planning_node(state: TravelState) -> dict:
    """
    LangGraph 节点：行程规划

    输入：state.event_info（事项收集结果）+ state.current_preferences（用户偏好）
    输出：{"itinerary": {...}, "planning_complete": bool}
    """
    event_info = state.get("event_info", {})
    preferences = state.get("current_preferences", {})
    user_input = state.get("user_input", "")

    # 当前时间/季节
    now = datetime.now()
    current_date = now.strftime("%Y年%m月%d日")
    current_month = now.month
    current_season = (
        "冬季" if current_month in [12, 1, 2]
        else "春季" if current_month in [3, 4, 5]
        else "夏季" if current_month in [6, 7, 8]
        else "秋季"
    )
    weekday = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]

    pref_text = _format_preferences(preferences)

    prompt = f"""你是一个高级行程规划专家。

【当前时间】
{current_date} {weekday}，当前季节是{current_season}

【用户需求】
{user_input}

{pref_text}【已收集的行程信息】
{event_info}

【交通方式强约束（最高优先级，必须严格遵守）】
1. event_info 中 transportation 字段代表"用户明确指定的城际往返大交通方式"（如火车、高铁、飞机、自驾、公共交通等）。行程的往返路线、时间安排、预算计算必须严格按用户指定的方式，**禁止擅自替换成其他方式**。
2. 用户说"坐火车"就按火车规划（票价、用时、路线均按普通火车），**不要因为高铁更快就改成高铁**；用户说"坐飞机"就按飞机。
3. 判断用户指定的方式是否**客观不可行**（如：从大陆坐火车去日本/去香港国外、没有该交通方式可达）：
   - 若可行：严格按指定方式规划，预算按该方式计算。
   - 若不可行：**不得擅自改用其他方式**。必须在 notes 中【明确说明不可行原因】，并礼貌询问用户是否需要更换为可行方式（给出建议替代方案），本次规划可按"待用户确认"处理，不要替用户做决定。
4. daily_plans 中每个景点的 transport 字段是"市内交通/到达景点的方式"（地铁、公交、打车、步行），与城际大交通是两码事，可以正常建议，但**不能把市内交通与城际交通混为一谈**。

【行程规划指南】
1. 永远提供有价值的行程规划，即使信息不完整；不要因为缺少天气、交通等细节就拒绝规划。
2. 有目的地和日期：给出该地标志性景点的游览路线。
3. 缺少出发地：假设从目的地市内出发，规划市内一日游。
4. 缺少天气：根据当前季节给出建议。
5. 每日安排 2-3 个主要景点，考虑交通时间和距离，安排午餐/晚餐，给出大致时间（如 09:00-12:00）。
6. 预算必须基于用户指定的大交通方式计算（如用户坐火车，就不能算高铁票价）。
7. 缺失信息在 notes 中提醒用户补充，但不影响主体规划。

【输出格式】(严格JSON，不要输出其他文字)
{{
    "itinerary": {{
        "title": "北京3日游",
        "duration": "3天",
        "route": "南京 -> 北京",
        "daily_plans": [
            {{
                "day": 1,
                "date": "2026-09-03",
                "city": "北京",
                "theme": "历史文化之旅",
                "activities": [
                    {{
                        "time": "09:00-12:00",
                        "location": "故宫博物院",
                        "description": "游览故宫，感受皇家建筑群的宏伟...",
                        "transport": "地铁1号线天安门东站"
                    }}
                ],
                "meals": {{ "lunch": "...", "dinner": "..." }}
            }}
        ],
        "notes": ["建议提前7天预约故宫门票..."],
        "estimated_budget": "约2000元"
    }},
    "planning_complete": true
}}"""

    try:
        result = await llm_service.ainvoke_json(
            messages=[
                {"role": "system", "content": "你是高级行程规划专家，输出严格的 JSON 格式。"},
                {"role": "user", "content": prompt},
            ],
            task_type="planning",
        )
        if not isinstance(result, dict) or "itinerary" not in result:
            raise ValueError("模型输出缺少 itinerary 字段")
        logger.info(f"行程规划完成: {result.get('itinerary', {}).get('title', '')}")
        return result
    except Exception as e:
        logger.error(f"行程规划失败: {e}")
        return {
            "itinerary": {
                "title": "行程规划",
                "duration": "待完善",
                "daily_plans": [],
            },
            "planning_complete": False,
            "error": f"行程规划过程中出现问题：{str(e)}",
        }
