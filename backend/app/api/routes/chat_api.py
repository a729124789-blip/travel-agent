"""
正式聊天 API 路由：面向前端对话场景

- POST /api/chat/intent   意图识别（表单预填充用）
- POST /api/chat/plan     行程规划（走完整 graph）
- POST /api/chat/message  通用对话（走完整 graph，含记忆/信息/RAG/偏好）
- GET  /api/chat/history  历史会话（长期记忆）
- GET  /api/preferences   读取偏好
- POST /api/preferences   保存偏好
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from loguru import logger
import json
import asyncio

from app.graph import run_graph, get_memory_manager, app_graph, run_form_plan
from app.nodes.intent import intent_node
from app.nodes.day_planning import day_planning_node
from app.services.llm_service import llm_service

router = APIRouter(prefix="/chat", tags=["chat"])


# ============================================================
# 请求/响应模型
# ============================================================
class ChatRequest(BaseModel):
    user_input: str = Field(..., description="用户输入", examples=["我想3月去杭州玩三天，喜欢住汉庭"])
    user_id: str = Field(default="default_user", description="用户 ID")
    session_id: str = Field(default="default", description="会话 ID")


class IntentResponse(BaseModel):
    intents: list = []
    key_entities: dict = {}
    rewritten_query: str = ""
    agent_schedule: list = []


# ============================================================
# 1. 意图识别（表单预填充）
# ============================================================
@router.post("/intent", response_model=IntentResponse, summary="意图识别（表单预填充）")
async def chat_intent(req: ChatRequest):
    """识别意图 + 提取关键实体，供前端表单自动填充。

    例如 `我想3月去杭州玩三天` → 表单自动填入 destination=杭州, start_date=2027-03, duration_days=3。
    """
    try:
        # 复用 load_memory，拿到完整上下文（偏好/行程/短期对话），与完整 graph 保持一致
        from app.graph import load_memory
        loaded = await load_memory({
            "user_id": req.user_id,
            "session_id": req.session_id,
        })
        state = {
            "user_input": req.user_input,
            "context_string": loaded.get("context_string", "无历史对话"),
            "preferences": loaded.get("preferences", {}),
        }
        result = await intent_node(state)
        logger.info(f"chat/intent: {req.user_input[:30]} -> {[i.get('type') for i in result.get('intents', [])]}")
        return result
    except Exception as e:
        logger.error(f"chat/intent 失败: {e}")
        raise HTTPException(status_code=500, detail=f"意图识别失败: {str(e)}")


# ============================================================
# 2. 行程规划（完整 graph）
# ============================================================
@router.post("/plan", summary="行程规划")
async def chat_plan(req: ChatRequest):
    """走完整 LangGraph 流程，生成行程规划并写回记忆。

    返回：final_response + 各节点结果（event_info / itinerary / preferences 等）。
    """
    try:
        state = await run_graph(req.user_input, req.user_id, req.session_id)
        logger.info(f"chat/plan: {req.user_input[:30]} -> 完成")
        return {
            "final_response": state.get("final_response", ""),
            "event_info": state.get("event_info", {}),
            "itinerary": state.get("itinerary", {}),
            "preference_updates": state.get("preference_updates", []),
            "intents": state.get("intents", []),
            "key_entities": state.get("key_entities", {}),
            "rewritten_query": state.get("rewritten_query", ""),
            "agent_schedule": state.get("agent_schedule", []),
            "errors": state.get("errors", []),
        }
    except Exception as e:
        logger.error(f"chat/plan 失败: {e}")
        raise HTTPException(status_code=500, detail=f"行程规划失败: {str(e)}")


# ============================================================
# 3. 通用对话（完整 graph）
# ============================================================
@router.post("/message", summary="通用对话")
async def chat_message(req: ChatRequest):
    """通用对话入口：根据意图自动路由到行程/记忆/信息/RAG/偏好等。

    返回：final_response + 完整节点结果。
    """
    try:
        state = await run_graph(req.user_input, req.user_id, req.session_id)
        logger.info(f"chat/message: {req.user_input[:30]} -> 完成")
        return {
            "final_response": state.get("final_response", ""),
            "intents": state.get("intents", []),
            "event_info": state.get("event_info", {}),
            "itinerary": state.get("itinerary", {}),
            "preference_updates": state.get("preference_updates", []),
            "info_query_result": state.get("info_query_result", {}),
            "rag_result": state.get("rag_result", {}),
            "memory_result": state.get("memory_result", {}),
            "key_entities": state.get("key_entities", {}),
            "rewritten_query": state.get("rewritten_query", ""),
            "agent_schedule": state.get("agent_schedule", []),
            "errors": state.get("errors", []),
        }
    except Exception as e:
        logger.error(f"chat/message 失败: {e}")
        raise HTTPException(status_code=500, detail=f"对话处理失败: {str(e)}")


# ============================================================
# 3.5 表单直通行程规划（结构化字段，跳过 intent 二次识别）
# ============================================================
class FormPlanRequest(BaseModel):
    departure_city: str = Field(default="", description="出发城市")
    city: str = Field(..., description="目的地城市")
    start_date: str = Field(default="", description="开始日期 YYYY-MM-DD")
    end_date: str = Field(default="", description="结束日期 YYYY-MM-DD")
    travel_days: int = Field(default=1, description="旅行天数")
    transportation: str = Field(default="", description="交通方式")
    accommodation: str = Field(default="", description="住宿偏好")
    preferences: list = Field(default=[], description="旅行偏好标签")
    free_text_input: str = Field(default="", description="额外要求")
    user_id: str = Field(default="default_user", description="用户 ID")
    session_id: str = Field(default="default", description="会话 ID")


@router.post("/form-plan", summary="表单直通行程规划")
async def chat_form_plan(req: FormPlanRequest):
    """接收前端表单结构化字段，跳过 intent 识别直接生成行程。

    适用于前端表单「确认并生成」：字段已由用户确认，无需 LLM 二次提取。
    返回 final_response + 完整节点结果。
    """
    try:
        form_data = req.model_dump()
        state = await run_form_plan(form_data, req.user_id, req.session_id)
        logger.info(f"chat/form-plan: {req.city} {req.travel_days}天 -> 完成")
        return {
            "final_response": state.get("final_response", ""),
            "intents": state.get("intents", []),
            "event_info": state.get("event_info", {}),
            "itinerary": state.get("itinerary", {}),
            "preference_updates": state.get("preference_updates", []),
            "key_entities": state.get("key_entities", {}),
            "rewritten_query": state.get("rewritten_query", ""),
            "agent_schedule": state.get("agent_schedule", []),
            "errors": state.get("errors", []),
        }
    except Exception as e:
        logger.error(f"chat/form-plan 失败: {e}")
        raise HTTPException(status_code=500, detail=f"行程规划失败: {str(e)}")


# ============================================================
# 4. 历史会话
# ============================================================
@router.get("/history", summary="历史会话")
async def chat_history(
    user_id: str = Query("default_user", description="用户 ID"),
    session_id: str = Query("default", description="会话 ID"),
    limit: int = Query(20, description="返回条数"),
):
    """获取用户的长期记忆（对话历史 + 行程历史）"""
    try:
        mm = get_memory_manager(user_id, session_id)
        return {
            "chat_history": mm.long_term.get_chat_history(limit),
            "trip_history": mm.long_term.get_trip_history(limit),
            "preferences": mm.long_term.get_preference(),
            "statistics": mm.long_term.get_statistics(),
        }
    except Exception as e:
        logger.error(f"chat/history 失败: {e}")
        raise HTTPException(status_code=500, detail=f"读取历史失败: {str(e)}")


# ============================================================
# 4.5 历史删除（对话记录 / 行程足迹）
# ============================================================
class DeleteChatRequest(BaseModel):
    user_id: str = Field(default="default_user", description="用户 ID")
    session_id: str = Field(default="default", description="会话 ID")
    timestamps: list = Field(..., description="要删除的消息 timestamp 列表（同一对话的 user/assistant 共享 timestamp）")


class DeleteTripRequest(BaseModel):
    user_id: str = Field(default="default_user", description="用户 ID")
    session_id: str = Field(default="default", description="会话 ID")
    trip_id: str = Field(..., description="要删除的行程 ID（如 trip_3）")


@router.post("/history/delete-chat", summary="删除对话记录")
async def delete_chat_history(req: DeleteChatRequest):
    """按 timestamp 删除一组或多组对话记录（user 与对应 assistant 消息成对删除）。

    请求示例：{"timestamps": ["2026-09-02T18:15:40.195737"]}
    """
    try:
        mm = get_memory_manager(req.user_id, req.session_id)
        removed = mm.long_term.delete_chat_messages(req.timestamps)
        return {"ok": True, "removed": removed}
    except Exception as e:
        logger.error(f"删除对话记录失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除对话记录失败: {str(e)}")


@router.post("/history/delete-trip", summary="删除行程足迹")
async def delete_trip_history(req: DeleteTripRequest):
    """按 trip_id 删除单条行程记录。

    请求示例：{"trip_id": "trip_3"}
    """
    try:
        mm = get_memory_manager(req.user_id, req.session_id)
        ok = mm.long_term.delete_trip_by_id(req.trip_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"未找到行程记录: {req.trip_id}")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除行程失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除行程失败: {str(e)}")


# ============================================================
# 5. 偏好管理
# ============================================================
class PreferenceSaveRequest(BaseModel):
    pref_type: str = Field(..., description="偏好类型（last_origin/hotel_brands/...）")
    value: str = Field(..., description="偏好值")
    action: str = Field(default="replace", description="replace/append")


@router.get("/preferences", summary="读取偏好")
async def get_preferences(
    user_id: str = Query("default_user", description="用户 ID"),
    session_id: str = Query("default", description="会话 ID"),
):
    """读取用户偏好"""
    mm = get_memory_manager(user_id, session_id)
    return {"preferences": mm.long_term.get_preference()}


@router.post("/preferences", summary="保存偏好")
async def save_preference(req: PreferenceSaveRequest, user_id: str = "default_user", session_id: str = "default"):
    """保存/更新用户偏好"""
    try:
        mm = get_memory_manager(user_id, session_id)
        current = mm.long_term.get_preference(req.pref_type)
        if req.action == "append":
            if isinstance(current, list):
                if req.value not in current:
                    mm.long_term.save_preference(req.pref_type, current + [req.value])
            else:
                mm.long_term.save_preference(req.pref_type, [current, req.value] if current else [req.value])
        else:
            mm.long_term.save_preference(req.pref_type, req.value)
        return {"ok": True, "preferences": mm.long_term.get_preference()}
    except Exception as e:
        logger.error(f"保存偏好失败: {e}")
        raise HTTPException(status_code=500, detail=f"保存偏好失败: {str(e)}")


# ============================================================
# 6. LLM 状态
# ============================================================
@router.get("/llm-status", summary="LLM 服务状态")
async def llm_status():
    """查看各任务类型 LLM 的熔断器状态"""
    return {"models": llm_service.get_status()}


# ============================================================
# 7. SSE 流式对话
# ============================================================
def _sse(data: dict) -> str:
    """格式化 SSE 事件：data: {json}\n\n"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _initial_state(user_input: str, user_id: str, session_id: str) -> dict:
    """构造与 run_graph 一致的初始 state（供 astream 使用）"""
    return {
        "user_id": user_id,
        "session_id": session_id,
        "user_input": user_input,
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


@router.post("/message/stream", summary="通用对话（SSE 流式）")
async def chat_message_stream(req: ChatRequest):
    """SSE 流式对话：走完整 LangGraph 图，逐步推送进度事件与最终文本分块。

    事件格式（text/event-stream）：
    - {"type": "progress", "node": "intent", "message": "正在识别你的意图..."}
    - {"type": "delta", "content": "..."}  最终回复文本分块
    - {"type": "done"} / {"type": "error", "message": "..."}
    """
    async def gen():
        try:
            initial = _initial_state(req.user_input, req.user_id, req.session_id)
            progress_messages = {
                "load_memory": "正在读取你的旅行记忆...",
                "intent": "正在识别你的意图...",
                "event_collection": "正在整理行程信息...",
                "preference": "正在保存你的偏好...",
                "info_query": "正在查询实时信息...",
                "rag": "正在检索商旅知识库...",
                "memory_query": "正在回忆你的旅行历史...",
                "join": "正在汇总分析...",
                "itinerary_planning": "正在为你规划行程...",
                "aggregate": "正在整理最终方案...",
            }
            async for step in app_graph.astream(
                initial,
                config={"configurable": {"thread_id": f"{req.user_id}:{req.session_id}"}},
            ):
                # step 是 {节点名: 该节点返回的增量}
                for node_name, node_out in step.items():
                    # 推送节点进度
                    if node_name in progress_messages:
                        yield _sse({"type": "progress", "node": node_name, "message": progress_messages[node_name]})
                        await asyncio.sleep(0.02)  # 让前端有时间渲染进度
                    # 若该节点产出了 final_response，则分块推送最终文本
                    if isinstance(node_out, dict) and node_out.get("final_response"):
                        text = node_out["final_response"]
                        for i in range(0, len(text), 4):  # 每次 4 字符
                            yield _sse({"type": "delta", "content": text[i:i+4]})
                            await asyncio.sleep(0.015)  # 打字机节奏
            yield _sse({"type": "done"})
        except Exception as e:
            logger.error(f"chat/message/stream 失败: {e}")
            yield _sse({"type": "error", "message": str(e)})

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/form-plan/stream", summary="表单直通行程规划（SSE 流式）")
async def chat_form_plan_stream(req: FormPlanRequest):
    """表单直通行程规划的 SSE 流式版本。

    与 /form-plan 逻辑一致，但将最终行程文本分块推送，前端实现打字机效果。
    事件格式同上。
    """
    async def gen():
        try:
            yield _sse({"type": "progress", "node": "itinerary_planning", "message": "正在为你规划行程..."})
            form_data = req.model_dump()
            state = await run_form_plan(form_data, req.user_id, req.session_id)
            text = state.get("final_response", "")
            if text:
                for i in range(0, len(text), 4):
                    yield _sse({"type": "delta", "content": text[i:i+4]})
                    await asyncio.sleep(0.015)
            else:
                yield _sse({"type": "delta", "content": "（行程生成完成，但没有可显示的内容）"})
            yield _sse({"type": "done"})
        except Exception as e:
            logger.error(f"chat/form-plan/stream 失败: {e}")
            yield _sse({"type": "error", "message": str(e)})

    return StreamingResponse(gen(), media_type="text/event-stream")


# ============================================================
# 3.8 逐天行程规划（SSE 流式）：一次生成一天，用户满意再继续
# ============================================================
class DayPlanRequest(BaseModel):
    departure_city: str = Field(default="", description="出发城市")
    city: str = Field(..., description="目的地城市")
    start_date: str = Field(default="", description="开始日期 YYYY-MM-DD")
    end_date: str = Field(default="", description="结束日期 YYYY-MM-DD")
    travel_days: int = Field(default=1, description="旅行天数")
    transportation: str = Field(default="", description="交通方式")
    accommodation: str = Field(default="", description="住宿偏好")
    preferences: list = Field(default=[], description="旅行偏好标签")
    free_text_input: str = Field(default="", description="额外要求")
    current_day: int = Field(default=1, description="本次要生成第几天（从1开始）")
    previous_days: list = Field(default=[], description="已生成天数的 Markdown 文本列表（按天序）")
    used_poi_names: list = Field(default=[], description="已展示过的景点/餐厅名（用于跨天去重，避免同一天重复卡片）")
    feedback: str = Field(default="", description="用户对当天/前一天的修改意见（可选）")
    user_id: str = Field(default="default_user", description="用户 ID")
    session_id: str = Field(default="default", description="会话 ID")


@router.post("/day-plan/stream", summary="逐天行程规划（SSE 流式）")
async def chat_day_plan_stream(req: DayPlanRequest):
    """逐天生成行程：每次只生成 current_day 这一天，返回详细单日行程（SSE 流式）。

    流程：
      1. 前端表单确认后首次调用 current_day=1 生成第1天
      2. 前端把已生成的文本累积到 previous_days，用户回复"继续"后 current_day=2 再调用
      3. 用户对某天不满意可传 feedback，后端据此重生成该天

    事件格式：
      - {"type": "progress", "message": "正在为你规划第X天..."}
      - {"type": "meta", "day": X, "total_days": N}  当天开始标记
      - {"type": "delta", "content": "..."}          Markdown 文本分块
      - {"type": "done"} / {"type": "error", "message": "..."}
    """
    async def gen():
        try:
            day = max(1, req.current_day)
            total = max(1, req.travel_days)
            yield _sse({"type": "progress", "message": f"正在为你规划第 {day} 天行程..."})

            # 构造 event_info（与 run_form_plan 一致）
            departure = (req.departure_city or "").strip()
            destination = (req.city or "").strip()
            preferences = req.preferences or []
            free_text = (req.free_text_input or "").strip()

            # 用户自然语言表达（供规划参考）
            user_input = f"从{departure}出发去{destination}" if departure else f"去{destination}"
            if req.start_date:
                user_input += f"，{req.start_date}出发"
            if req.travel_days:
                user_input += f"，玩{req.travel_days}天"
            if req.transportation:
                user_input += f"，乘坐{req.transportation}"
            if req.accommodation:
                user_input += f"，住宿{req.accommodation}"
            if preferences:
                user_input += f"，偏好{('、'.join(preferences))}"
            if free_text:
                user_input += f"，{free_text}"
            if req.feedback:
                user_input += f"。用户修改意见：{req.feedback}"

            event_info = {
                "origin": departure or None,
                "destination": destination or None,
                "start_date": req.start_date or None,
                "end_date": req.end_date or None,
                "duration_days": total,
                "return_location": departure or None,
                "trip_purpose": "旅游",
                "transportation": req.transportation or None,
                "accommodation": req.accommodation or None,
                "free_text_input": req.free_text_input or "",
                "missing_info": [],
            }

            # 记忆偏好
            from app.graph import get_memory_manager
            mm = get_memory_manager(req.user_id, req.session_id)
            memory_prefs = mm.long_term.get_preference() or {}

            state = {
                "user_id": req.user_id,
                "session_id": req.session_id,
                "user_input": user_input,
                "event_info": event_info,
                "current_preferences": memory_prefs,
                "day_plan_state": {
                    "current_day": day,
                    "total_days": total,
                    "previous_days": req.previous_days or [],
                    "used_poi_names": req.used_poi_names or [],
                    "feedback": req.feedback or "",
                },
            }

            result = {}
            # 通过队列把模型思考过程（reasoning_content）实时转发为 SSE 事件
            reasoning_q: asyncio.Queue = asyncio.Queue()

            async def on_reasoning(seg: str):
                reasoning_q.put_nowait(seg)

            async def run_node():
                result["res"] = await day_planning_node(state, on_reasoning=on_reasoning)

            node_task = asyncio.create_task(run_node())
            # 模型思考期间（glm 深度思考可能长达数十秒）实时推送思考过程，避免用户以为卡死
            while not node_task.done():
                try:
                    seg = await asyncio.wait_for(reasoning_q.get(), timeout=0.2)
                    yield _sse({"type": "reasoning", "content": seg})
                except asyncio.TimeoutError:
                    continue
            # 节点已结束，排空残留的思考片段
            while not reasoning_q.empty():
                yield _sse({"type": "reasoning", "content": reasoning_q.get_nowait()})
            await node_task  # 若节点抛异常，此处抛出，由外层 except 兜底
            res = result.get("res", {})
            md_text = res.get("day_plan_md", "")
            if md_text:
                yield _sse({"type": "meta", "day": day, "total_days": total})
                for i in range(0, len(md_text), 4):
                    yield _sse({"type": "delta", "content": md_text[i:i+4]})
                    await asyncio.sleep(0.015)
                # 高德补充的景点/餐厅真实信息（图片/经纬度/评分/营业时间）
                poi_list = res.get("day_plan", {}).get("attraction_details", []) or []
                if poi_list:
                    yield _sse({"type": "poi", "pois": poi_list})
                # 12306 真实车次信息（当天跨城移动时）
                train_list = res.get("day_plan", {}).get("train_details", []) or []
                if train_list:
                    yield _sse({"type": "train", "trains": train_list})
                # 当天天气
                weather_info = res.get("day_plan", {}).get("weather")
                if weather_info:
                    yield _sse({"type": "weather", "weather": weather_info})
                # 真实酒店推荐（第1天）
                hotel_list = res.get("day_plan", {}).get("hotels", []) or []
                if hotel_list:
                    yield _sse({"type": "hotel", "hotels": hotel_list})
            else:
                yield _sse({"type": "delta", "content": "（当天行程生成失败，请重试或换个说法）"})
            yield _sse({"type": "done"})
        except Exception as e:
            logger.error(f"chat/day-plan/stream 失败: {e}")
            yield _sse({"type": "error", "message": str(e)})

    return StreamingResponse(gen(), media_type="text/event-stream")
