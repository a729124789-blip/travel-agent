"""
意图识别节点：识别用户意图、提取关键实体、决定调度哪些子节点
"""
from datetime import datetime
from loguru import logger

from app.state import TravelState
from app.services.llm_service import llm_service
from app.nodes.event_collection import _preprocess_dates


# 可调度节点描述（用于 prompt 中让 LLM 了解每个节点的能力）
AVAILABLE_NODES = """
**Priority 1（并行执行 - 信息收集类）：**
- event_collection: 事项收集 - 提取出发地、目的地、日期、天数、交通方式等行程基础信息
- preference: 偏好管理 - 识别并保存用户的旅行偏好（酒店品牌、航空公司、饮食禁忌等）
- information_query: 信息查询 - 联网查询天气、景点信息、交通情况等客观信息
- rag_knowledge: RAG知识库 - 查询差旅政策、报销标准等企业内部知识库
- memory_query: 记忆查询 - 查询用户的历史行程、偏好和聊天记录

**Priority 2（依赖 Priority 1 - 行程规划类）：**
- itinerary_planning: 行程规划 - 综合所有信息生成详细的每日行程安排
"""

SYSTEM_PROMPT = """你是高级意图识别专家。分析用户查询，识别意图并输出结构化决策。只输出JSON，不要其他文本。

【意图区分原则】
基于语义理解判断，不要机械匹配关键词：
- "我去过北京吗？" → memory_query（询问自己的历史）
- "北京有什么好玩的？" → information_query（询问客观信息）
- "我想去北京玩3天" → itinerary_planning（规划未来行程）
- "我喜欢住汉庭" → preference（保存偏好）
- memory_query 优先于 information_query（涉及用户自己的历史时）

【行程规划强识别规则】
- 用户提到"想去XX玩/旅游/出差N天/从A到B"等明确的行程需求时，无论是否有历史对话上下文，都必须识别为 itinerary_planning（最高优先级）
- 历史对话上下文只是补充信息，不能把明确的行程需求误判为其他意图
- 只有纯粹的客观信息询问（"XX天气怎么样"、"XX门票多少钱"、"XX有什么好玩的"）才识别为 information_query

【优先级规则】
- Priority 1 的节点互不依赖，可并行执行
- Priority 2 的节点需要 Priority 1 的结果
- 行程规划类请求必须包含 event_collection（P1）和 itinerary_planning（P2）
- 涉及偏好表达时必须包含 preference（P1）
- 询问历史/个人信息时必须包含 memory_query（P1）
- 询问天气/景点/攻略时必须包含 information_query（P1）
- 询问差旅政策/报销标准时必须包含 rag_knowledge（P1）"""


# 常见城市表（启发式兜底用）
_CITY_PATTERN = r'(北京|上海|广州|深圳|杭州|成都|重庆|西安|南京|武汉|长沙|苏州|厦门|青岛|大连|天津|三亚|昆明|桂林|丽江|大理|香港|澳门|哈尔滨|沈阳|济南|郑州|合肥|南昌|福州|贵阳|南宁|兰州|西宁|拉萨|乌鲁木齐|呼和浩特|银川|海口|珠海)'


def _heuristic_intent(text: str) -> dict:
    """
    启发式意图兜底：当 LLM 输出无法解析（JSON 解析失败）或调用异常时，
    根据文本信号判断是否为行程规划请求，避免明确行程被误判为信息查询。

    Returns:
        可直接作为 fallback 的意图决策 dict
    """
    import re
    travel_signals = [
        r'\d+[天日]游', r'[一二三四五六七八九十]+[天日]游',
        r'去', r'到', r'旅游', r'旅行', r'出差', r'玩', r'游',
        r'从.{2,6}(?:到|去|往)',
        r'\d+[天晚]',
    ]
    is_travel = any(re.search(p, text) for p in travel_signals)
    has_city = bool(re.search(_CITY_PATTERN, text))

    if is_travel and has_city:
        return {
            "reasoning": "意图识别解析失败，基于行程信号启发式判定为行程规划",
            "intents": [{"type": "itinerary_planning", "confidence": 0.7, "description": "行程规划", "reason": "包含明确行程信号"}],
            "key_entities": {},
            "rewritten_query": text,
            "agent_schedule": [
                {"agent_name": "event_collection", "priority": 1, "reason": "提取行程基础信息", "expected_output": "行程信息"},
                {"agent_name": "itinerary_planning", "priority": 2, "reason": "生成行程", "expected_output": "行程"},
            ],
        }
    return {
        "reasoning": "意图识别解析失败，使用默认查询策略",
        "intents": [{"type": "information_query", "confidence": 0.5, "description": "默认查询", "reason": "解析失败且无行程信号"}],
        "key_entities": {},
        "rewritten_query": text,
        "agent_schedule": [{"agent_name": "information_query", "priority": 1, "reason": "默认", "expected_output": "查询结果"}],
    }


async def intent_node(state: TravelState) -> dict:
    """
    LangGraph 节点：意图识别 + 实体提取 + 调度决策

    输出更新到 state:
    - intents: 意图列表
    - key_entities: 关键实体（用于前端表单自动填充）
    - rewritten_query: 标准化后的查询
    - agent_schedule: 调度计划（决定后续执行哪些节点）
    """
    user_input = state.get("user_input", "")
    if not user_input:
        return {
            "intents": [],
            "key_entities": {},
            "rewritten_query": "",
            "agent_schedule": [],
        }

    # 当前时间
    now = datetime.now()
    current_time = now.strftime("%Y年%m月%d日 %H:%M")
    weekday = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]

    # 确定性日期预处理器：把"下周五/明天/X天后"等口语化相对日期换成具体日期，避免 LLM 推算错误
    processed_input = _preprocess_dates(user_input, now.date())
    if processed_input != user_input:
        logger.info(f"[intent] 日期预处理器: '{user_input}' -> '{processed_input}'")

    # 对话历史上下文（从短期记忆或 state 中获取）
    context_str = state.get("context_string", "无历史对话")

    # 用户偏好（用于推断缺失信息：出发地等）
    preferences = state.get("preferences", {})
    bg_parts = []
    if isinstance(preferences, dict):
        if preferences.get("last_origin"):
            bg_parts.append(f"• 上次出发地(last_origin): {preferences['last_origin']}")
        if preferences.get("transportation_preference"):
            bg_parts.append(f"• 交通偏好: {preferences['transportation_preference']}")
        if preferences.get("food_preference"):
            bg_parts.append(f"• 美食偏好: {preferences['food_preference']}")
        if preferences.get("hotel_brands"):
            bg_parts.append(f"• 酒店偏好: {preferences['hotel_brands']}")
    background = ""
    if bg_parts:
        background = "【用户偏好背景】（用于补全缺失信息）\n" + "\n".join(bg_parts) + "\n\n"

    user_prompt = f"""【当前时间】
{current_time} {weekday}
（用户说"2月28日"或"明天"等相对时间时，根据当前时间推断完整日期）

{background}【用户Query】
{processed_input}

【对话历史上下文】
{context_str}

【可调度的节点】
{AVAILABLE_NODES}

【任务要求】
1. 推理：分析用户核心诉求、关键实体、是否需要上下文消歧
2. 多意图识别：识别所有可能意图，每个分配置信度(0-1)和原因
3. Query改写：标准化口语化表达，补全省略信息
4. 调度决策：基于意图决定调用哪些节点，设置优先级

【输出格式】严格JSON：
{{
    "reasoning": "详细推理过程",
    "intents": [
        {{
            "type": "itinerary_planning/preference/information_query/memory_query/rag_knowledge",
            "confidence": 0.95,
            "description": "意图说明",
            "reason": "识别原因"
        }}
    ],
    "key_entities": {{
        "origin": "出发地",
        "destination": "目的地",
        "start_date": "出发日期YYYY-MM-DD",
        "end_date": "返程日期",
        "duration_days": 3,
        "transportation": "建议交通方式",
        "budget": {{
            "train_price": "交通费用（纯数字，如50；无则null）",
            "hotel_price": "住宿每晚价格（纯数字或区间如100-130；无则null）"
        }},
        "other": "其他关键信息"
    }},
    "rewritten_query": "标准化后的查询",
    "agent_schedule": [
        {{
            "agent_name": "节点名称",
            "priority": 1,
            "reason": "调用原因",
            "expected_output": "期望输出"
        }}
    ]
}}

缺失的字段设为null。直接输出JSON：
【补全规则】若用户没说出出发地（origin 为 null），但偏好背景中有 last_origin（上次出发地），则 origin 取 last_origin，并在 other 中注明"根据偏好设置出发地为X"；同理，用户没说交通方式时可用交通偏好补全。"""

    try:
        result = await llm_service.ainvoke_json(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            task_type="intent",
            fallback=_heuristic_intent(user_input),
        )

        intents = result.get("intents", [])
        schedule = result.get("agent_schedule", [])
        intent_types = [i.get("type") for i in intents]
        scheduled = [a.get("agent_name") for a in schedule]
        logger.info(f"意图识别完成: 意图={intent_types}, 调度={scheduled}")

        return {
            "intents": intents,
            "key_entities": result.get("key_entities", {}),
            "rewritten_query": result.get("rewritten_query", user_input),
            "agent_schedule": schedule,
        }
    except Exception as e:
        logger.error(f"意图识别失败: {e}")
        fallback = _heuristic_intent(user_input)
        fallback["reasoning"] = f"意图识别异常，使用启发式策略: {str(e)}"
        fallback["errors"] = [f"intent_node: {str(e)}"]
        return fallback
