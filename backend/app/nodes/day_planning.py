"""
单日行程规划节点：逐天生成详细行程（方案A：一次只生成一天）

与 itinerary_planning（一次性生成全部）不同，本节点聚焦"当前某一天"，
要求输出足够详细、可落地、有具体操作价值的行程内容：
  - 城际交通：具体车次/线路、票价区间、到哪个站、市内接驳建议
  - 景点：具体名字、开放时间/预约提示、游览时长、门票参考
  - 美食：具体餐厅/小吃店名、所在街区、人均参考（宁缺毋滥，不编造虚假店名时用街区+类型描述）
  - 住宿：推荐区域、酒店类型/品牌、价格区间
  - 当日节奏：上午/中午/下午/晚上分段

生成策略：
  - 每次只生成 day = current_day 这一天
  - 参考 previous_days（已生成天数的摘要）避免重复、保持连贯
  - 支持用户 feedback：用户对前一天/当天不满意时，可传入修改意见重生成
"""
import json
from datetime import datetime, timedelta
from loguru import logger

from app.state import TravelState
from app.services.llm_service import llm_service
from app.services.amap_mcp import amap_mcp
from app.services.rail12306_mcp import rail_mcp
from app.services.hotel_mcp import hotel_mcp

# 单日行程规划 prompt
DAY_PLAN_PROMPT = """你是资深旅行规划专家，正在为一位真实用户【逐步规划】一次行程。
【关键语言要求】你的所有内部推理/思考（reasoning）必须使用简体中文书写，禁止使用英文思考。用户是中文用户，思考全程用中文，即使最终输出是 JSON，思考过程也必须是中文。
【重要】你本次只规划第 {current_day} 天（共 {total_days} 天），不要规划其他天！

【当前时间】
{today_date} {weekday}，当前季节是{current_season}

【用户需求（已从表单确认）】
{user_input}

【已生成的行程摘要（供你参考，避免重复，保持连贯）】
{previous_days_text}

{pref_text}
【本次任务】
生成第 {current_day} 天（{day_date}）的详细行程。要求：

1. **只输出这一天**，输出 JSON 结构见下方格式，不要输出其他天的内容。
2. **内容必须具体、可落地、对用户有实际帮助**，宁可详细不要空泛。参考以下颗粒度：
   - 交通：城际大交通给出具体方式、大致车次类型/耗时/票价区间（如"高铁南京南→上海虹桥，1-2小时，二等座140-170元"）；市内交通给出地铁线/公交/步行建议。
   - 景点：给出具体景点名、建议时段、游览时长、门票参考、是否需要提前预约。
   - 美食：给出具体店名或街区名。**有把握的真实热门店名可直接推荐**（如"小杨生煎""大壶春""沈大成"等知名老字号）；不确定时给出"XX路美食街/商圈 + 风味类型"的可靠描述，不要编造虚假的详细地址。
   - 住宿（仅第1天详细给）：推荐具体区域 + 酒店类型/连锁品牌 + 价格区间（如"中山公园附近，汉庭/如家等连锁，200-350元/晚"）。
   - 节奏：按 上午 / 中午 / 下午 / 晚上 分段，每段给明确安排。
3. **交通方式强约束（最高优先级）**：用户明确指定的城际大交通方式（如火车/高铁/飞机/自驾）必须严格遵守，预算、路线、用时都按该方式计算。**用户说"坐火车"就按普通火车规划（票价、车次、用时均按火车，如南京→上海普速列车约2.5-3小时、硬座约90-120元），绝不擅自改成高铁/飞机。** 若该方式客观不可行（如坐火车出国），才需在 tips 中说明原因并询问是否更换，不得擅自替换。
4. **景点数量适度**：一天 2-3 个核心景点即可，不要贪多，保证每个都安排得从容。
5. **衔接连贯**：参考已生成天数，不要与之前内容重复；第 1 天要包含"抵达+安顿+初步游览"，最后一天可包含"返程"。
6. 预算：给出当天合理的预算估算（门票+餐饮+市内交通）。
7. **attractions 列表（重要）**：把当天正文中**明确提及的所有具体景点、餐厅、酒店、民宿名称**都整理进 attractions 数组（每个 name 必须是真实可被地图搜索到的名称，3-8 个）。**必须包含住宿部分推荐/提到的酒店、民宿名**（如“布丁酒店(杭州大厦武林广场地铁站店)”“布丁严选酒店”等，凡正文写到的具体住宿名都要列入，不要遗漏）；不要把整句描述或“XX路美食街”这种泛称放进去，只放具体店名/景点名。这个列表用于后续调高德地图补充图片、评分、位置，名称越准确越好。
8. **跨天去重**：查看上方"已生成的行程摘要"，若某景点/餐厅/住宿在前几天已经出现并重点安排过，本天就**不要再重复列进 attractions**（正文文字中可以提"可再次前往"，但卡片列表不要重复）。同一天内不同名称指向同一地点时只保留一个（如"外滩"与"外滩观景平台"只留一个）。

【输出格式】(严格JSON，只输出 JSON，不要输出其他文字)
{{
    "day": {current_day},
    "date": "{day_date}",
    "theme": "当日主题一句话",
    "title": "第{current_day}天：{{简短标题}}",
    "sections": [
        {{
            "period": "上午",
            "content": "详细安排（交通/景点/时长/门票/预约等）"
        }},
        {{
            "period": "中午",
            "content": "午餐推荐（具体店名/街区 + 风味 + 人均）"
        }},
        {{
            "period": "下午",
            "content": "详细安排"
        }},
        {{
            "period": "晚上",
            "content": "晚餐 + 晚间活动安排"
        }}
    ],
    "accommodation": "当日住宿建议（第1天详细给，后续天可写'延续前日住宿'）",
    "budget": "当日预算估算（含门票/餐饮/市内交通）",
    "tips": ["小贴士1", "小贴士2"],
    "attractions": [
        {{
            "name": "当天一个具体的景点或餐厅名（如'西湖风景名胜区'/'小杨生煎'，必须是能被地图搜索到的真实名称，不要写成整句描述）",
            "type": "景点 / 美食 / 住宿"
        }}
    ]
}}"""


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


def _compute_day_date(start_date: str, current_day: int) -> str:
    """根据出发日期和第几天推算当天日期 YYYY-MM-DD"""
    try:
        d = datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days=current_day - 1)
        return d.strftime("%Y-%m-%d")
    except Exception:
        return start_date or ""


def _day_to_markdown(day_plan: dict) -> str:
    """把单日行程 JSON 转成可读 Markdown 文本"""
    if not day_plan or not isinstance(day_plan, dict):
        return "（当天行程生成失败）"
    day = day_plan.get("day", "?")
    date = day_plan.get("date", "")
    theme = day_plan.get("theme", "")
    title = day_plan.get("title", f"第{day}天")
    lines = []
    lines.append(f"## {title}" + (f"  · {date}" if date else "") + (f"\n\n*{theme}*" if theme else ""))
    lines.append("")
    # 天气行（若当天有真实预报）
    weather = day_plan.get("weather") if isinstance(day_plan.get("weather"), dict) else None
    if weather:
        w_line = (
            f"🌤️ 天气：{weather.get('dayweather','')}/{weather.get('nightweather','')} "
            f"{weather.get('daytemp','?')}°C ~ {weather.get('nighttemp','?')}°C"
        )
        if weather.get("wind"):
            w_line += f"（{weather.get('wind')}风）"
        lines.append(f"> {w_line}")
        lines.append("")

    for sec in day_plan.get("sections", []):
        period = sec.get("period", "")
        content = sec.get("content", "")
        lines.append(f"### ☀️ {period}" if period in ("上午", "中午") else f"### 🌙 {period}" if period in ("晚上", "夜晚") else f"### {period}")
        lines.append(content if content else "（待安排）")
        lines.append("")

    acc = day_plan.get("accommodation", "")
    if acc:
        lines.append(f"### 🏨 住宿\n{acc}")
        lines.append("")
    budget = day_plan.get("budget", "")
    if budget:
        lines.append(f"### 💰 当日预算\n{budget}")
        lines.append("")
    tips = day_plan.get("tips", [])
    if tips:
        lines.append("### 💡 小贴士")
        for tip in tips:
            lines.append(f"- {tip}")
        lines.append("")
    return "\n".join(lines)


async def day_planning_node(state: TravelState, on_reasoning=None) -> dict:
    """
    LangGraph 节点：生成指定某一天的详细行程

    输入（state）：
      - event_info: 行程信息（origin/destination/start_date/duration_days/transportation 等）
      - current_preferences: 用户偏好
      - day_plan_state: { "current_day": int, "total_days": int, "previous_days": [str...], "feedback": str|None }

    Args:
        on_reasoning: 可选异步回调，实时接收模型思考过程增量（用于 SSE 推送"思考中"）
    """
    event_info = state.get("event_info", {})
    preferences = state.get("current_preferences", {})
    user_input = state.get("user_input", "")
    dplan = state.get("day_plan_state", {}) or {}

    current_day = int(dplan.get("current_day", 1))
    total_days = int(dplan.get("total_days", 1))
    previous_days = dplan.get("previous_days", []) or []
    used_poi_names = dplan.get("used_poi_names", []) or []
    feedback = dplan.get("feedback") or ""

    # 当前时间/季节
    now = datetime.now()
    current_date_cn = now.strftime("%Y年%m月%d日")
    current_month = now.month
    current_season = (
        "冬季" if current_month in [12, 1, 2]
        else "春季" if current_month in [3, 4, 5]
        else "夏季" if current_month in [6, 7, 8]
        else "秋季"
    )
    weekday = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]

    # 推算当天日期
    start_date = event_info.get("start_date", "")
    day_date = _compute_day_date(start_date, current_day) or start_date
    # 中文格式（用于 prompt 展示）
    day_date_cn = day_date
    if day_date:
        try:
            day_date_cn = datetime.strptime(day_date, "%Y-%m-%d").strftime("%Y年%m月%d日")
        except Exception:
            pass

    pref_text = _format_preferences(preferences)

    # 已生成天数摘要
    if previous_days:
        prev_text = "\n".join(f"[第{i+1}天] {text[:400]}" for i, text in enumerate(previous_days) if text)
        if not prev_text:
            prev_text = "（暂无）"
    else:
        prev_text = "（暂无，这是第1天）"

    # 用户修改意见
    feedback_text = ""
    if feedback:
        feedback_text = f"\n【用户对行程的修改意见（必须认真采纳）】\n{feedback}\n"

    # ===== 12306 真实车次查询（当天涉及跨城交通时） =====
    # 第1天查 出发地->目的地；最后一天查 目的地->出发地（返程）
    train_info_text = ""
    train_details = []  # 随结果带出的真实车次数据
    origin = event_info.get("origin") or event_info.get("departure_city", "")
    destination = event_info.get("destination", "")
    transportation = str(event_info.get("transportation", "") or "")
    if (
        rail_mcp.enabled
        and origin
        and destination
        and origin != destination
        and day_date
        and ("火车" in transportation or "高铁" in transportation or "动车" in transportation or "铁路" in transportation or not transportation)
    ):
        if current_day == 1:
            frm, to, seg = origin, destination, "去程"
        elif current_day == total_days:
            frm, to, seg = destination, origin, "返程"
        else:
            frm, to, seg = None, None, None
        if frm and to:
            try:
                # 根据用户交通偏好筛选车次：明确"火车"→优先普速K/T/Z；"高铁/动车"→优先G/D/C
                prefer_type = None
                tl = transportation.lower()
                if any(k in tl for k in ("高铁", "动车", "g字头", "d字头")):
                    prefer_type = "high_speed"
                elif any(k in tl for k in ("火车", "普速", "硬座", "绿皮")):
                    prefer_type = "train"
                res = await rail_mcp.enrich_train_plan(day_date, frm, to, max_trains=5, prefer_type=prefer_type)
                if res.get("ok") and res.get("trains"):
                    train_details = res["trains"]
                    lines = [
                        f"【重要：{seg}交通必须引用下面的真实车次（{day_date} {frm}->{to}，来自12306实时余票）】",
                        "【规则】如当天需要跨城乘坐火车/高铁，你必须从下列车次中挑选 1-2 个最合适的（考虑出发时间、票价、余票），在行程的交通描述中明确写出车次号、发车/到达时间、票价和历时。禁止编造不存在的车次号。如无合适车次，请说明。】",
                    ]
                    if res.get("message"):
                        lines.append(f"【备注】{res['message']}")
                    for t in train_details[:5]:
                        seats = "，".join(
                            f"{s['type']}{s['price']}元" for s in t.get("seats", [])[:3]
                        ) or "暂无"
                        lines.append(
                            f"- {t['train_no']} {t.get('dep_time','')}->{t.get('arr_time','')} 历时{t.get('duration','')} | {seats}"
                        )
                    train_info_text = "\n".join(lines) + "\n\n"
                    logger.info(f"12306车次查询成功: {frm}->{to} {day_date} 共{len(train_details)}个 prefer={prefer_type}")
            except Exception as e:
                logger.warning(f"12306车次查询失败（不阻塞）: {e}")

    # ===== 目的地天气查询（影响当日行程安排） =====
    # 高德预报一般覆盖未来4天；当天日期在预报范围内用真实天气，否则用季节兜底
    weather_text = ""
    weather_card = None  # 可选的天气卡片数据
    if destination and day_date:
        try:
            w_res = await amap_mcp.weather(destination)
            forecasts = w_res.get("forecasts", []) if isinstance(w_res, dict) else []
            # 找与当天日期匹配的预报
            target_fc = None
            for fc in forecasts:
                if fc.get("date", "").startswith(day_date):
                    target_fc = fc
                    break
            if target_fc:
                dayw = target_fc.get("dayweather", "")
                nightw = target_fc.get("nightweather", "")
                dayt = target_fc.get("daytemp", "")
                nightt = target_fc.get("nighttemp", "")
                wind = target_fc.get("daywind", "")
                weather_text = (
                    f"【当天天气（来自高德实时预报）】{destination} {day_date} 白天{dayw}/{nightw}，"
                    f"温度{dayt}°C~{nightt}°C，风向{wind}。\n"
                    "【天气调整要求】请严格根据上述天气安排当日行程："
                    "若下雨/阴天→优先安排室内景点（博物馆/展馆/商场）、提醒带伞、减少露天长时间活动；"
                    "若高温（≥33°C）→中午避开暴晒、把户外活动安排在早晚、提醒补水防晒；"
                    "若大风→减少水上/高空/户外徒步项目。"
                    "在行程正文中自然引用天气（如\"今日小雨，建议以室内为主\"）。\n\n"
                )
                weather_card = {
                    "city": destination,
                    "date": day_date,
                    "dayweather": dayw,
                    "nightweather": nightw,
                    "daytemp": dayt,
                    "nighttemp": nightt,
                    "wind": wind,
                }
                logger.info(f"天气查询成功: {destination} {day_date} {dayw} {dayt}~{nightt}°C")
            else:
                # 超出预报范围 → 用季节常识兜底，让 LLM 处理，不编造具体温度
                weather_text = (
                    f"【天气说明】{destination} 在 {day_date} 的实时天气超出预报范围（高德最多预报4天）。\n"
                    f"请基于{current_season}（{current_month}月）该地的气候常识做合理推断安排行程，"
                    "例如夏季注意防晒防暑、冬季注意保暖、梅雨季/雨季提醒带伞，但不要在行程中编造精确的气温数值。\n\n"
                )
                logger.info(f"天气超出预报范围，用季节兜底: {destination} {day_date}")
        except Exception as e:
            logger.warning(f"天气查询失败（不阻塞）: {e}")

    # ===== 真实酒店查询（第1天详细推荐住宿） =====
    hotel_info_text = ""
    hotel_list = []  # 随结果带出的真实酒店数据
    # 判断本天是否需要住宿：非最后一天需住宿；第1天做详细推荐
    need_hotel = current_day < total_days or current_day == 1
    if need_hotel and destination and day_date:
        try:
            # 入住=当天，退房=次日（或行程最后一天则退房日=行程结束次日）
            check_in = day_date
            end_date = event_info.get("end_date") or ""
            if end_date and day_date <= end_date:
                # 最后一天退房 = 结束日期+1；否则次日退房
                check_out = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
                if current_day < total_days:
                    check_out = (datetime.strptime(day_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                check_out = (datetime.strptime(day_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            free_text = event_info.get("free_text_input") or user_input or ""
            h_res = await hotel_mcp.enrich_hotel(
                destination=destination,
                check_in=check_in,
                check_out=check_out,
                preferences=preferences,
                free_text=free_text,
                guests=1,
            )
            if h_res.get("ok") and h_res.get("hotels"):
                hotel_list = h_res["hotels"]
                lines = [
                    f"【重要：住宿必须引用下面的真实酒店（{destination}，来自RollingGo酒店实时数据）】",
                    "【规则】在\"住宿\"部分从下列真实酒店中挑选最合适的 2-3 家（结合用户预算与偏好），明确写出酒店名、每晚价格、所在区域/地址和推荐理由。禁止编造不存在的酒店。价格允许在用户预算上限的合理浮动范围内（≤预算上限×2，如 130 预算可推荐至 260 左右），超出的可列出并说明\"略超预算但更舒适/位置更好\"；仅在候选都远超预算上限×2 时才不推荐并说明原因。",
                ]
                for h in hotel_list[:4]:
                    lines.append(
                        f"- {h.get('name','')}：{h.get('starRating','?')}星，¥{h.get('lowestPrice','?')}/晚，{h.get('address','')}"
                    )
                hotel_info_text = "\n".join(lines) + "\n\n"
                logger.info(f"酒店查询成功: {destination} {check_in}~{check_out} 共{len(hotel_list)}家")
            else:
                # 无符合预算的酒店 → 诚实说明，不编造酒店名
                reason = h_res.get("message", "未查询到合适的酒店")
                hotel_info_text = (
                    f"【住宿说明】实时酒店数据未找到符合用户预算的酒店（{reason}）。"
                    "请不要编造不存在的酒店名；在\"住宿\"部分给出建议："
                    "提示用户通过美团/飞猪/携程等平台自行预订符合预算的经济型连锁酒店（如汉庭、如家等），"
                    "并说明该预算下建议选择的地段（如地铁沿线稍远区域），或询问用户是否愿意适当放宽预算。\n\n"
                )
                logger.info(f"酒店无符合预算选项: {destination} {check_in}~{check_out} {reason}")
        except Exception as e:
            logger.warning(f"酒店查询失败（不阻塞）: {e}")

    prompt = DAY_PLAN_PROMPT.format(
        current_day=current_day,
        total_days=total_days,
        today_date=current_date_cn,
        day_date=day_date_cn,
        weekday=weekday,
        current_season=current_season,
        user_input=user_input or "（请基于 event_info 合理规划）",
        previous_days_text=prev_text,
        pref_text=pref_text,
    )
    if feedback_text:
        prompt += feedback_text
    if weather_text:
        prompt += weather_text
    if hotel_info_text:
        prompt += hotel_info_text
    if train_info_text:
        prompt += train_info_text

    try:
        result = await llm_service.astream_chat_json(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是高级行程规划专家，只输出严格的 JSON。\n"
                        "在输出最终 JSON 前，请先进行有价值的行程规划思考（例如：目的地当天天气与游玩节奏、"
                        "交通与住宿如何衔接、哪些美食和景点值得推荐、时间与预算如何分配）。"
                        "思考过程会实时展示给用户，请**全程使用中文思考**（不要使用英文或其他语言），"
                        "聚焦规划要点、条理清晰，不要重复同一内容的多种方案，也不要长篇自我复述。"
                        "思考结束后，再基于思考输出完整、实用、细节丰富的行程 JSON。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            task_type="planning",
            on_reasoning=on_reasoning,
        )
        if not isinstance(result, dict) or "sections" not in result:
            raise ValueError("模型输出缺少 sections 字段")
        # 补全字段（date 强制覆盖为确定性计算的行程当天日期，不依赖 LLM 输出）
        result["day"] = current_day
        result["date"] = day_date_cn or day_date
        result.setdefault("theme", "")
        result.setdefault("title", f"第{current_day}天")
        result.setdefault("sections", [])
        result.setdefault("accommodation", "")
        result.setdefault("budget", "")
        result.setdefault("tips", [])
        attractions_raw = result.get("attractions", []) or []

        # 用高德 MCP 补充真实景点/餐厅信息（图片/经纬度/评分/营业时间）
        attraction_details = []
        if amap_mcp.enabled and attractions_raw:
            # 提取名称列表，并过滤掉已展示过的重复名称（跨天去重）
            used_set = {str(n).strip() for n in used_poi_names if str(n).strip()}
            names = [a.get("name", "") for a in attractions_raw if isinstance(a, dict) and a.get("name")]
            # 当天内部也去重（保留首次出现的顺序）
            seen_day = set()
            filtered_names = []
            for n in names:
                n = str(n).strip()
                if not n:
                    continue
                if n in used_set or n in seen_day:
                    continue
                seen_day.add(n)
                filtered_names.append(n)
            if filtered_names:
                logger.info(f"调高德补充 {len(filtered_names)} 个POI(去重后): {filtered_names}")
            city = event_info.get("destination", "")
            # 跨城行程（如第1天白天在出发地、晚上到目的地）时 POI 可能分布在多个城市，
            # 候选城市列表 = [出发地, 目的地]（出发地优先：第1天景点/美食多在出发地，
            # 且同名品牌店在多地存在时优先落在出发地；酒店名带"上海"等城市字样时靠分支关键词加分锁定目的地）。
            # 避免"南京夫子庙"被错配成"上海文庙"、"南京大牌档"被错配成北京/上海店。
            origin_city = event_info.get("origin") or ""
            candidate_cities = [c for c in (origin_city, city) if c]
            if filtered_names:
                try:
                    attraction_details = await amap_mcp.enrich_attractions(filtered_names, cities=candidate_cities)
                except Exception as e:
                    logger.warning(f"高德补充POI失败（不阻塞主流程）: {e}")
                    attraction_details = []
            # 补充不在规划中的热门景点（丰富"景点推荐"栏）：第1天必补，
            # 无论行程内景点是否充足，都补齐热门景点，确保景点栏至少 3 个（放一排）
            if current_day == 1 and destination:
                try:
                    existing = {str(a.get("poi_name") or a.get("name") or "").strip() for a in attraction_details if a.get("name")}
                    # 当前已有多少景点类 POI
                    have = sum(1 for a in attraction_details if a.get("category") == "attraction")
                    need = max(3 - have, 1)
                    hot = await amap_mcp.hot_attractions(city, exclude_names=list(existing), limit=need + 2)
                    added = 0
                    for h in hot:
                        if added >= need:
                            break
                        hn = str(h.get("poi_name") or h.get("name") or "").strip()
                        if hn and hn not in existing:
                            attraction_details.append(h)
                            existing.add(hn)
                            added += 1
                    if added:
                        logger.info(f"补充热门景点 {added} 个（景点栏现有{have}个，补齐至≥3）")
                except Exception as e:
                    logger.debug(f"热门景点补充失败（不阻塞）: {e}")
            result["attraction_details"] = attraction_details
        # 12306 真实车次数据（供前端展示）
        if train_details:
            result["train_details"] = train_details
        # 天气卡片（供前端展示）
        if weather_card:
            result["weather"] = weather_card
        # 真实酒店列表（供前端展示）
        if hotel_list:
            result["hotels"] = hotel_list

        md_text = _day_to_markdown(result)
        logger.info(f"单日行程生成完成: day={current_day} date={day_date} title={result.get('title')} poi={len(attraction_details)}")
        return {
            "day_plan": result,
            "day_plan_md": md_text,
            "day_plan_state": {**dplan, "last_generated_day": current_day},
        }
    except Exception as e:
        logger.error(f"单日行程生成失败: {e}")
        return {
            "day_plan": {},
            "day_plan_md": "",
            "errors": [str(e)],
        }

