"""
聊天相关 API 路由（开发测试端点）
每个端点都配有默认测试用例 + 功能描述，可直接在 /docs 中一键调用。
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field
from loguru import logger

from app.nodes.event_collection import event_collection_node
from app.nodes.intent import intent_node
from app.nodes.preference import preference_node
from app.nodes.memory_query import memory_query_node
from app.nodes.info_query import info_query_node
from app.nodes.rag import rag_node
from app.nodes.itinerary_planning import itinerary_planning_node
from app.nodes.aggregate import aggregate_node

router = APIRouter()


# ============================================================
# 1. 事项收集 event_collection
# ============================================================
class EventCollectionRequest(BaseModel):
    user_input: str = Field(
        default="我想去杭州旅游三天，从南京出发",
        description="用户原始输入（包含目的地、天数、出发地等信息）",
        examples=["我想去杭州旅游三天，从南京出发"],
    )
    home_location: str = Field(
        default="南京",
        description="默认出发地（实际集成时由记忆系统提供，测试可手动指定）",
        examples=["南京"],
    )


class EventCollectionResponse(BaseModel):
    origin: str | None = None
    destination: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    duration_days: int | None = None
    return_location: str | None = None
    trip_purpose: str | None = None
    transportation: str | None = None
    missing_info: list = []
    summary: str | None = None


@router.post("/test/event-collection", response_model=EventCollectionResponse, summary="事项收集")
async def test_event_collection(req: EventCollectionRequest):
    """从用户输入中提取结构化行程信息：出发地、目的地、日期、天数、交通方式等。

    - 交通方式自动推断：同城<100km→公共交通；100~800km→高铁；>800km→飞机；用户指定优先
    - 出发地默认取 home_location（last_origin）
    - 缺失字段写入 missing_info，供用户补全

    默认用例：`我想去杭州旅游三天，从南京出发` → 南京→杭州，高铁
    """
    state = {
        "user_input": req.user_input,
        "preferences": {"home_location": req.home_location},
    }
    result = await event_collection_node(state)
    info = result.get("event_info", {})
    logger.info(f"测试端点 event_collection: {req.user_input} -> {info.get('summary')}")
    return info


# ============================================================
# 2. 意图识别 intent
# ============================================================
class IntentRequest(BaseModel):
    user_input: str = Field(
        default="我想3月去杭州玩三天，喜欢住汉庭",
        description="用户原始输入",
        examples=["我想3月去杭州玩三天，喜欢住汉庭"],
    )
    context_string: str = Field(
        default="无历史对话",
        description="历史对话上下文（可留空）",
        examples=["无历史对话"],
    )


class IntentResponse(BaseModel):
    intents: list = []
    key_entities: dict = {}
    rewritten_query: str = ""
    agent_schedule: list = []


@router.post("/test/intent", response_model=IntentResponse, summary="意图识别")
async def test_intent(req: IntentRequest):
    """识别用户意图（可多意图）、提取关键实体、重写查询、生成智能体调度计划。

    识别结果含：
    - intents：多意图 + 置信度（如行程规划 0.95、偏好提取 0.9）
    - key_entities：目的地、日期、天数等
    - rewritten_query：标准化后的查询
    - agent_schedule：按优先级排序的执行计划（P1 收集 → P2 规划）

    默认用例：`我想3月去杭州玩三天，喜欢住汉庭` → 行程规划 + 偏好提取
    """
    state = {
        "user_input": req.user_input,
        "context_string": req.context_string,
    }
    result = await intent_node(state)
    logger.info(f"测试端点 intent: {req.user_input} -> {[i.get('type') for i in result.get('intents', [])]}")
    return result


# ============================================================
# 3. 偏好提取 preference
# ============================================================
class PreferenceRequest(BaseModel):
    user_input: str = Field(
        default="我还喜欢如家",
        description="用户偏好表达（追加/覆盖）",
        examples=["我还喜欢如家", "我搬家到上海了", "我常坐东航"],
    )
    context_string: str = Field(
        default="无历史对话",
        description="历史对话上下文（可留空）",
        examples=["无历史对话"],
    )


class PreferenceResponse(BaseModel):
    preferences: list = []
    has_preferences: bool = False


@router.post("/test/preference", response_model=PreferenceResponse, summary="偏好提取")
async def test_preference(req: PreferenceRequest):
    """识别用户偏好并区分动作：
    - append（追加）：「还」「也」→ 在已有偏好上追加
    - replace（覆盖）：「搬家到」「改成」→ 覆盖原值

    偏好类型：hotel_brands / airlines / seat_preference / last_origin 等。
    「搬家到XX」→ 更新 last_origin（默认出发地）。

    默认用例：`我还喜欢如家` → hotel_brands append 如家
    """
    state = {
        "user_input": req.user_input,
        "context_string": req.context_string,
    }
    result = await preference_node(state)
    logger.info(f"测试端点 preference: {req.user_input} -> {result.get('preferences')}")
    return result


# ============================================================
# 4. 记忆查询 memory_query
# ============================================================
class MemoryQueryRequest(BaseModel):
    user_input: str = Field(
        default="我去过哪些地方？",
        description="用户记忆类问题",
        examples=["我去过哪些地方？", "我上次去北京是什么时候？", "我有什么偏好？"],
    )
    trip_history: list = Field(
        default=[
            {"origin": "南京", "destination": "杭州", "start_date": "2026-03-01",
             "end_date": "2026-03-03", "purpose": "旅游"},
            {"origin": "南京", "destination": "北京", "start_date": "2026-05-10",
             "end_date": "2026-05-12", "purpose": "出差"},
        ],
        description="旅行历史（实际集成时由长期记忆提供）",
    )
    preferences: dict = Field(
        default={"last_origin": "南京", "hotel_brands": ["汉庭"]},
        description="用户偏好（实际集成时由长期记忆提供）",
    )
    memory_summary: str = Field(
        default="",
        description="历史对话摘要（可留空）",
    )


class MemoryQueryResponse(BaseModel):
    status: str = ""
    query: str = ""
    answer: str = ""
    memory_sources: dict = {}


@router.post("/test/memory-query", response_model=MemoryQueryResponse, summary="记忆查询")
async def test_memory_query(req: MemoryQueryRequest):
    """基于用户长期记忆回答历史相关问题：
    - 旅行历史（去过哪些地方）
    - 用户偏好（住宿、出行等）
    - 历史对话摘要

    LLM 基于记忆生成自然语言回答，无记录时诚实说明，不编造。

    默认用例：`我去过哪些地方？` → 杭州、北京两次行程
    """
    state = {
        "user_input": req.user_input,
        "trip_history": req.trip_history,
        "current_preferences": req.preferences,
        "memory_summary": req.memory_summary,
    }
    result = await memory_query_node(state)
    logger.info(f"测试端点 memory-query: {req.user_input}")
    return result.get("memory_result", {})


# ============================================================
# 5. 信息查询 info_query
# ============================================================
class InfoQueryRequest(BaseModel):
    user_input: str = Field(
        default="杭州天气怎么样？",
        description="信息类问题（天气 / 网络搜索）",
        examples=["杭州天气怎么样？", "北京故宫的门票多少钱？"],
    )
    rewritten_query: str = Field(
        default="",
        description="标准化查询（留空则用 user_input）",
    )


@router.post("/test/info-query", summary="信息查询")
async def test_info_query(req: InfoQueryRequest):
    """实时信息查询：
    - 天气类问题 → wttr.in 免费接口（实时天气 + 未来3日预报）
    - 其他问题 → DDGS 网络搜索 + LLM 总结

    默认用例：`杭州天气怎么样？` → 杭州实时天气
    """
    state = {
        "user_input": req.user_input,
        "rewritten_query": req.rewritten_query or req.user_input,
    }
    result = await info_query_node(state)
    logger.info(f"测试端点 info-query: {req.user_input}")
    return result.get("info_query_result", {})


# ============================================================
# 6. RAG 知识库问答 rag
# ============================================================
class RagRequest(BaseModel):
    user_input: str = Field(
        default="出差住宿标准是多少？",
        description="商旅知识类问题",
        examples=["出差住宿标准是多少？", "航班延误了怎么办？", "机票应该提前多久预订？"],
    )
    rewritten_query: str = Field(
        default="",
        description="标准化查询（留空则用 user_input）",
    )


@router.post("/test/rag", summary="知识库问答（RAG）")
async def test_rag(req: RagRequest):
    """基于商旅知识库（Milvus + bge 嵌入）的语义检索问答：
    - 检索最相关的知识片段（top_k=3）
    - LLM 严格基于知识库回答，知识库没有时诚实说明，不编造

    默认用例：`出差住宿标准是多少？` → 分城市等级的住宿标准
    """
    state = {
        "user_input": req.user_input,
        "rewritten_query": req.rewritten_query or req.user_input,
    }
    result = await rag_node(state)
    logger.info(f"测试端点 rag: {req.user_input}")
    return result.get("rag_result", {})


# ============================================================
# 7. 行程规划 itinerary_planning
# ============================================================
class ItineraryRequest(BaseModel):
    user_input: str = Field(
        default="我想去杭州旅游三天，喜欢杭帮菜，住汉庭或如家",
        description="用户需求（可简要）",
    )
    event_info: dict = Field(
        default={
            "origin": "南京",
            "destination": "杭州",
            "start_date": "2026-09-05",
            "end_date": "2026-09-07",
            "duration_days": 3,
            "return_location": "南京",
            "trip_purpose": "旅游",
            "transportation": "高铁",
            "summary": "南京到杭州 3 日游",
        },
        description="事项收集结果（实际集成时由 event_collection 提供）",
    )
    preferences: dict = Field(
        default={"hotel_brands": ["汉庭", "如家"], "food_preference": "杭帮菜"},
        description="用户偏好（实际集成时由长期记忆提供）",
    )


@router.post("/test/itinerary", summary="行程规划")
async def test_itinerary(req: ItineraryRequest):
    """基于事项收集结果 + 用户偏好生成完整行程规划：
    - 每日 2-3 个主要景点，含时间安排、交通方式、用餐推荐
    - 自动融入用户偏好（酒店品牌、美食偏好等）
    - 信息不完整时也给出可用规划，缺失项在 notes 中提醒

    默认用例：南京→杭州 3 日游（汉庭/如家住宿，杭帮菜）
    """
    state = {
        "user_input": req.user_input,
        "event_info": req.event_info,
        "current_preferences": req.preferences,
    }
    result = await itinerary_planning_node(state)
    logger.info(f"测试端点 itinerary: {req.event_info.get('destination', '')}")
    return result


# ============================================================
# 8. 聚合输出 aggregate
# ============================================================
class AggregateRequest(BaseModel):
    intents: list = Field(
        default=[{"type": "itinerary_planning", "confidence": 0.95, "description": "行程规划"}],
        description="意图识别结果",
    )
    event_info: dict = Field(
        default={
            "origin": "南京", "destination": "杭州",
            "start_date": "2026-09-05", "end_date": "2026-09-07",
            "duration_days": 3, "trip_purpose": "旅游", "transportation": "高铁",
            "missing_info": [],
        },
        description="事项收集结果",
    )
    preferences: dict = Field(
        default={},
        description="偏好结果",
    )
    info_query_result: dict = Field(
        default={},
        description="信息查询结果",
    )
    rag_result: dict = Field(
        default={},
        description="RAG 结果",
    )
    memory_result: dict = Field(
        default={},
        description="记忆查询结果",
    )
    itinerary: dict = Field(
        default={
            "title": "杭州3日游", "duration": "3天", "route": "南京 -> 杭州",
            "daily_plans": [
                {
                    "day": 1, "date": "2026-09-05", "city": "杭州", "theme": "西湖",
                    "activities": [
                        {"time": "09:00-12:00", "location": "西湖", "description": "游西湖", "transport": "地铁"}
                    ],
                    "meals": {"lunch": "楼外楼", "dinner": "河坊街"},
                }
            ],
            "notes": ["提前预约"], "estimated_budget": "约2000元",
        },
        description="行程规划结果",
    )


@router.post("/test/aggregate", summary="聚合输出")
async def test_aggregate(req: AggregateRequest):
    """汇总各节点结果，按主导意图生成面向用户的最终回复：
    - 行程规划：行程概览 + 每日安排 + 待补充信息
    - 偏好/记忆/信息/RAG：各自组织回答
    - 检测节点错误，给出兜底回复

    默认用例：行程规划意图 + 完整行程 → 格式化行程文本
    """
    state = {
        "intents": req.intents,
        "event_info": req.event_info,
        "preferences": req.preferences,
        "info_query_result": req.info_query_result,
        "rag_result": req.rag_result,
        "memory_result": req.memory_result,
        "itinerary": req.itinerary,
    }
    result = await aggregate_node(state)
    logger.info(f"测试端点 aggregate: intents={[i.get('type') for i in req.intents]}")
    return result
