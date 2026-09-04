"""
信息查询节点：天气（wttr.in）或网络搜索（DDGS）+ LLM 总结
"""
from datetime import datetime
from loguru import logger

from app.state import TravelState
from app.services.llm_service import llm_service
from app.services.search_service import (
    is_weather_query,
    extract_city_from_query,
    query_weather,
    web_search,
)


async def info_query_node(state: TravelState) -> dict:
    """
    LangGraph 节点：信息查询

    - 天气类问题 → wttr.in 直接查
    - 其他问题 → DDGS 搜索 + LLM 总结
    返回 {"info_query_result": {...}} 更新到 state。
    """
    user_input = state.get("user_input", "")
    rewritten = state.get("rewritten_query", "") or user_input
    query = rewritten or user_input

    if not query:
        return {"info_query_result": {"query_type": "未知", "query_success": False, "results": {"message": "无查询内容"}}}

    # 天气类优先走 wttr.in
    if is_weather_query(query):
        city = extract_city_from_query(query)
        if not city:
            return {
                "info_query_result": {
                    "query_type": "天气查询",
                    "query_success": False,
                    "results": {"message": "未识别到城市，请说明具体城市，如：杭州下周的天气怎么样？"},
                }
            }
        logger.info(f"天气查询: {city}")
        result = await query_weather(city)
        return {"info_query_result": result}

    # 其他走网络搜索
    logger.info(f"网络搜索: {query[:50]}")
    search_result = await web_search(query)
    if not search_result.get("query_success"):
        return {"info_query_result": search_result}

    # LLM 总结搜索结果
    sources = search_result["results"].get("sources", [])
    results_text = ""
    for i, r in enumerate(sources, 1):
        results_text += f"\n{i}. {r['title']}\n{r['snippet']}\n"

    now = datetime.now()
    current_date = now.strftime("%Y年%m月%d日")
    weekday = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]

    prompt = f"""根据以下搜索结果，简洁地回答用户的问题。

【当前时间】
{current_date} {weekday}
（用户查询中的相对时间请基于此日期理解，如"明天"、"2月28日"等）

【用户问题】
{query}

【搜索结果】
{results_text}

【任务说明】
请直接回答用户的问题，保持简洁，引用来源时注明序号。"""

    try:
        summary = await llm_service.ainvoke(
            [{"role": "user", "content": prompt}],
            task_type="default",
        )
        result = {
            "query_type": "网络搜索",
            "query_success": True,
            "results": {
                "summary": summary.strip() if summary else "无法生成摘要",
                "sources": sources,
            },
        }
        return {"info_query_result": result}
    except Exception as e:
        logger.error(f"搜索总结失败: {e}")
        return {"info_query_result": search_result}
