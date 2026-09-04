"""
偏好管理节点：识别并提取用户的长期偏好（酒店品牌、航空公司、座位、饮食等）
输出 preferences 列表，由调用方写回长期记忆
"""
from loguru import logger

from app.state import TravelState
from app.services.llm_service import llm_service


SYSTEM_PROMPT = """你是用户偏好分析专家，负责从用户输入中提取长期偏好。

【意图判断】
1. **追加（append）**：用户想增加新选项，关键词「还」「也」「另外」「以及」
2. **覆盖（replace）**：用户想更新/替换，关键词「搬家到」「改成」「现在是」「换成」
3. **首次设置**：当前没有该字段，用 replace

【常见偏好类型】
- last_origin: 默认出发地/常住地（"搬家到上海"→ last_origin=上海）
- hotel_brands: 酒店品牌（如汉庭、如家、全季）
- airlines: 航空公司（如东航、南航）
- seat_preference: 座位偏好（靠窗/过道）
- meal_preference: 餐食偏好
- budget_level: 预算等级
- transportation_preference: 交通偏好
- food_preference: 美食偏好
（支持自定义）

【特殊规则】
- 用户说"我搬家到XX"、"我现在住XX"、"我常住XX"，识别为 last_origin=XX（replace）

【输出格式】严格JSON：
{
    "preferences": [
        {"type": "hotel_brands", "value": "汉庭", "action": "append"},
        {"type": "seat_preference", "value": "靠窗", "action": "replace"}
    ],
    "has_preferences": true
}

如果用户未提及任何偏好，返回 {"preferences": [], "has_preferences": false}"""


async def preference_node(state: TravelState) -> dict:
    """
    LangGraph 节点：偏好提取

    返回 {"preference_updates": [...]}，由 graph 的 save_memory 节点写回长期记忆。
    注意：last_origin 默认出发地不由本节点维护，由行程确认时保存。
    """
    user_input = state.get("user_input", "")
    if not user_input:
        return {"preference_updates": [], "has_preferences": False}

    # 获取当前已保存的偏好（用于判断 append/replace）
    current_prefs = state.get("current_preferences", {})
    current_prefs_str = str(current_prefs) if current_prefs else "{}"

    user_prompt = f"""【当前已保存的用户偏好】
{current_prefs_str}

【新的用户输入】
{user_input}"""

    try:
        result = await llm_service.ainvoke_json(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            task_type="default",
            fallback={"preferences": [], "has_preferences": False},
        )
        prefs = result.get("preferences", [])
        if prefs:
            types = [p.get("type") for p in prefs]
            logger.info(f"偏好识别: {types}")
        else:
            logger.info("偏好识别: 无新偏好")
        return {
            "preference_updates": prefs,
            "has_preferences": bool(prefs),
        }
    except Exception as e:
        logger.error(f"偏好识别失败: {e}")
        return {"preferences": [], "has_preferences": False, "error": str(e)}
