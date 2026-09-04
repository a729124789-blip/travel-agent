"""
事项收集节点：从用户输入中提取结构化旅行信息（出发地、目的地、日期、天数等）
"""
import re
from datetime import datetime, date, timedelta
from loguru import logger

from app.state import TravelState
from app.services.llm_service import llm_service


_WEEKDAY_CN = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
_CN_NUM = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

# 用户明确指定的交通方式 → 归一化值（长词优先，避免"动车"先被"动"误伤等）
_TRANSPORT_KEYWORDS: list[tuple[str, str]] = [
    ("高铁/动车", "高铁"), ("高铁", "高铁"), ("动车", "高铁"),
    ("火车", "火车"), ("硬座", "火车"), ("硬卧", "火车"), ("软卧", "火车"),
    ("普快", "火车"), ("普速", "火车"), ("绿皮", "火车"), ("卧铺", "火车"),
    ("飞机", "飞机"), ("航班", "飞机"), ("航空", "飞机"), ("乘机", "飞机"),
    ("自驾", "自驾"), ("开车", "自驾"), ("驾车", "自驾"), ("租车", "自驾"),
    ("大巴", "大巴"), ("长途汽车", "大巴"), ("客车", "大巴"),
    ("轮船", "轮船"), ("邮轮", "轮船"), ("游轮", "轮船"), ("渡轮", "轮船"), ("坐船", "轮船"),
    ("公交", "公共交通"), ("地铁", "公共交通"), ("公共交通", "公共交通"),
]


def _extract_explicit_transport(user_input: str) -> str | None:
    """从用户输入中确定性提取明确指定的交通方式；用户明确说了就以用户为准"""
    for kw, val in _TRANSPORT_KEYWORDS:
        if kw in user_input:
            return val
    return None


def _cn2num(s: str) -> int:
    """中文数字转阿拉伯数字（十以内，够用）"""
    if not s:
        return 0
    if s == "十":
        return 10
    if len(s) == 1:
        return _CN_NUM.get(s, 0)
    if s.endswith("十"):
        return _CN_NUM.get(s[0], 1) * 10
    if s.startswith("十"):
        return 10 + _CN_NUM.get(s[1], 0)
    return int(s) if s.isdigit() else 0


def _preprocess_dates(user_input: str, today: date) -> str:
    """
    将口语化相对日期替换为具体日期（YYYY年MM月DD日），避免 LLM 推算错误。
    覆盖：明天/后天/大后天、下周X、下个周X、本周X、周X（最近的未来）、X天后、周末。
    返回替换后的文本。
    """
    text = user_input

    # 1. 明天 / 后天 / 大后天（长词优先，避免"大后天"先被"后天"吃掉）
    for n, kw in [(3, "大后天"), (2, "后天"), (1, "明天")]:
        if kw in text:
            d = (today + timedelta(days=n)).strftime("%Y年%m月%d日")
            text = text.replace(kw, d)

    # 2. 下周X / 下个周X（= 下一周的周X，先定位下周一再加偏移）
    def sub_next_week(m):
        wd = _WEEKDAY_CN.get(m.group(1))
        if wd is None:
            return m.group(0)
        # 下周一距离今天的天数（1~7），再加目标周几偏移
        days_to_next_monday = 7 - today.weekday()
        d = today + timedelta(days=days_to_next_monday + wd)
        return d.strftime("%Y年%m月%d日")

    text = re.sub(r"下(?:个)?周([一二三四五六日天])", sub_next_week, text)

    # 3. 本周X
    def sub_this_week(m):
        wd = _WEEKDAY_CN.get(m.group(1))
        if wd is None:
            return m.group(0)
        days_ahead = (wd - today.weekday()) % 7
        d = today + timedelta(days=days_ahead)
        return d.strftime("%Y年%m月%d日")

    text = re.sub(r"本周([一二三四五六日天])", sub_this_week, text)

    # 4. 周末（本周六）
    if "周末" in text:
        sat = today + timedelta(days=(5 - today.weekday()) % 7)
        text = text.replace("周末", sat.strftime("%Y年%m月%d日"))

    # 5. 裸"周X"（不含"下/本"前缀）→ 最近的未来周X（今天恰为周X则取今天）
    def sub_weekday(m):
        wd = _WEEKDAY_CN.get(m.group(1))
        if wd is None:
            return m.group(0)
        days_ahead = (wd - today.weekday()) % 7
        d = today + timedelta(days=days_ahead)
        return d.strftime("%Y年%m月%d日")

    text = re.sub(r"(?<![下本])周([一二三四五六日天])", sub_weekday, text)

    # 6. X天后 / X天之后（阿拉伯 + 中文数字）
    text = re.sub(
        r"(\d+)天(?:之后|后)",
        lambda m: (today + timedelta(days=int(m.group(1)))).strftime("%Y年%m月%d日"),
        text,
    )
    text = re.sub(
        r"([一二两三四五六七八九十]+)天(?:之后|后)",
        lambda m: (today + timedelta(days=_cn2num(m.group(1)))).strftime("%Y年%m月%d日"),
        text,
    )

    return text


SYSTEM_PROMPT = """你是事项收集专家，负责从用户输入中提取旅行的基础信息。

【提取要求】
请尽可能提取以下信息：
1. origin - 出发地
2. destination - 目的地
3. start_date - 出发日期（YYYY-MM-DD格式）
4. end_date - 返程日期
5. duration_days - 行程天数
6. return_location - 返程地
7. trip_purpose - 行程目的（旅游/出差/探亲等）
8. transportation - 建议交通方式（根据距离自动推断）

【交通方式建议规则】
- 同城市或相邻城市（<100km）：公共交通
- 100~800km：高铁/动车
- >800km或跨海峡：飞机
- 用户明确指定交通方式时，以用户为准

【日期处理规则】
- 用户说"2月27日"或"2.27"等相对时间，根据当前时间推断完整日期
- 用户说"明天"、"后天"、"下周"等，根据当前时间计算具体日期
- 所有日期必须输出完整的YYYY-MM-DD格式
- 用户未指定日期时，start_date默认为今天

【特殊处理】
- "X一日游"：destination设为X，duration_days=1
- origin优先使用上次出发地(last_origin)；只有上次出发地就是X或没有last_origin时，origin才设为X
- 用户没说出发地但有上次出发地记录，origin推断为上次出发地
- 中文数字天数（如"三天"）转换为阿拉伯数字

【输出格式】严格返回JSON，不要任何额外文字：
{
    "origin": "北京",
    "destination": "杭州",
    "start_date": "2026-03-01",
    "end_date": "2026-03-03",
    "duration_days": 3,
    "return_location": "北京",
    "trip_purpose": "旅游",
    "transportation": "高铁/动车",
    "missing_info": [],
    "summary": "北京到杭州3日游"
}

缺失的信息在missing_info中列出，对应字段设为null。"""


async def event_collection_node(state: TravelState) -> dict:
    """
    LangGraph 节点：提取旅行事项信息

    从 state 读取 user_input，调用 LLM 提取结构化信息，
    返回 {"event_info": {...}} 更新到 state。
    """
    user_input = state.get("user_input", "")
    if not user_input:
        logger.warning("event_collection: user_input 为空")
        return {"event_info": {"missing_info": ["用户输入"], "extracted_count": 0}}

    # 当前时间
    now = datetime.now()
    current_date = now.strftime("%Y年%m月%d日")
    weekday = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]

    # 确定性日期预处理器：把"下周五/明天/X天后"等口语化相对日期换成具体日期，避免 LLM 推算错误
    processed_input = _preprocess_dates(user_input, now.date())
    if processed_input != user_input:
        logger.info(f"日期预处理器: '{user_input}' -> '{processed_input}'")

    # 用户偏好（用于推断出发地）
    preferences = state.get("preferences", {})
    bg_parts = []
    if isinstance(preferences, dict):
        if preferences.get("last_origin"):
            bg_parts.append(f"• 上次出发地: {preferences['last_origin']}")
        if preferences.get("hotel_brands"):
            bg_parts.append(f"• 酒店偏好: {preferences['hotel_brands']}")
    background = ""
    if bg_parts:
        background = "【用户背景信息】（可用于推断缺失信息）\n" + "\n".join(bg_parts) + "\n\n"

    user_prompt = f"""【当前时间】
{current_date} {weekday}

{background}【用户输入】
{processed_input}"""

    try:
        result = await llm_service.ainvoke_json(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            task_type="default",
            fallback={"missing_info": ["解析失败"], "extracted_count": 0},
        )
        logger.info(f"事项收集完成: {result.get('summary', 'N/A')} (缺失: {result.get('missing_info', [])})")
        # 用户明确指定交通方式时，以用户输入为准（LLM 偶发忽略，需确定性兜底）
        explicit = _extract_explicit_transport(user_input)
        if explicit and result.get("transportation") != explicit:
            logger.info(f"用户明确交通方式: {explicit}（覆盖 LLM 输出 {result.get('transportation')}）")
            result["transportation"] = explicit
        return {"event_info": result}
    except Exception as e:
        logger.error(f"事项收集失败: {e}")
        return {"event_info": {"missing_info": ["服务异常"], "extracted_count": 0, "error": str(e)}}
