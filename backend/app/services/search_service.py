"""
搜索服务：天气查询（wttr.in）+ 网络搜索（DDGS）
DDGS 是同步库，用 asyncio.to_thread 避免阻塞事件循环
"""
import asyncio
import re
from loguru import logger


_SUSPICIOUS_DOMAIN_PATTERN = re.compile(r"\.(cc|tk|ml|ga|cf|gq|xyz|top|work|click|link|pw|buzz)(/|$)", re.I)
_RANDOM_DOMAIN_PATTERN = re.compile(r"^[a-z0-9]{10,}$", re.I)

COMMON_CITIES = [
    "北京", "上海", "广州", "深圳", "杭州", "南京", "成都", "武汉", "西安", "苏州",
    "天津", "重庆", "厦门", "青岛", "大连", "宁波", "无锡", "长沙", "郑州", "济南",
    "哈尔滨", "沈阳", "昆明", "合肥", "福州", "石家庄", "南昌", "贵阳", "太原", "南宁",
]


def _is_suspicious_url(url: str) -> bool:
    """过滤疑似垃圾站点"""
    if not url or not url.startswith("http"):
        return True
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc or ""
        host = host.split(":")[0].lower()
        if not host:
            return True
        if _SUSPICIOUS_DOMAIN_PATTERN.search(host):
            return True
        parts = host.rsplit(".", 2)
        name = parts[0] if parts else ""
        if len(name) >= 10 and _RANDOM_DOMAIN_PATTERN.match(name):
            return True
        return False
    except Exception:
        return False


def is_weather_query(query: str) -> bool:
    q = (query or "").strip()
    return any(k in q for k in ["天气", "气温", "下雨", "预报"])


def extract_city_from_query(query: str) -> str:
    """从问题中提取城市名"""
    q = (query or "").strip()
    for city in COMMON_CITIES:
        if city in q:
            return city
    m = re.search(r"[\u4e00-\u9fa5]{2,6}", q)
    return m.group(0).strip() if m else ""


def _fetch_weather_sync(city: str) -> dict:
    """同步获取天气（wttr.in）"""
    import httpx
    url = f"https://wttr.in/{city}?format=j1"
    resp = httpx.get(url, timeout=10.0, headers={"User-Agent": "curl/7.64.1"})
    resp.raise_for_status()
    return resp.json()


def _search_sync(query: str) -> list:
    """同步网络搜索（DDGS）"""
    from ddgs import DDGS
    ddgs = DDGS()
    search_results = []
    for backend in ("bing", "duckduckgo", "auto"):
        try:
            raw = ddgs.text(query, max_results=10, safesearch="on", region="cn-zh", backend=backend)
            search_results = list(raw)
            if search_results:
                break
        except Exception as e:
            logger.debug(f"DDGS backend {backend} 失败: {e}")
            continue
    results = []
    for result in search_results:
        href = result.get("href", "")
        if _is_suspicious_url(href):
            continue
        results.append({
            "title": result.get("title", ""),
            "snippet": result.get("body", ""),
            "url": href,
        })
        if len(results) >= 5:
            break
    return results


async def query_weather(city: str) -> dict:
    """异步天气查询"""
    try:
        data = await asyncio.to_thread(_fetch_weather_sync, city)
        current = data.get("current_condition", [{}])[0]
        temp_c = current.get("temp_C", "?")
        wdesc = current.get("weatherDesc", [{}])
        desc = (wdesc[0].get("value") if wdesc else None) or "—"
        humidity = current.get("humidity", "?")
        weather_text = f"{city}当前天气：{desc}，气温 {temp_c}°C，湿度 {humidity}%。"
        forecasts = []
        for day in data.get("weather", [])[:5]:
            date = day.get("date", "")
            maxtemp = day.get("maxtempC", "?")
            mintemp = day.get("mintempC", "?")
            h = (day.get("hourly") or [{}])[0] if day.get("hourly") else {}
            daily_desc = (h.get("weatherDesc") or [{}])[0].get("value", "—") if h else "—"
            forecasts.append(f"{date}: {daily_desc}，{mintemp}~{maxtemp}°C")
        if forecasts:
            weather_text += " 未来几日：" + "；".join(forecasts[:3])
        return {
            "query_type": "天气查询",
            "query_success": True,
            "results": {
                "summary": weather_text,
                "sources": [{"url": "https://wttr.in", "title": "wttr.in"}],
            },
        }
    except Exception as e:
        logger.warning(f"天气查询失败: {e}")
        return {
            "query_type": "天气查询",
            "query_success": False,
            "results": {"message": f"天气接口暂时不可用: {e}"},
        }


async def web_search(query: str) -> dict:
    """异步网络搜索"""
    try:
        results = await asyncio.to_thread(_search_sync, query)
        if not results:
            return {
                "query_type": "网络搜索",
                "query_success": False,
                "results": {"message": "未找到相关结果"},
            }
        return {
            "query_type": "网络搜索",
            "query_success": True,
            "results": {"sources": results},
        }
    except Exception as e:
        logger.error(f"网络搜索失败: {e}")
        return {
            "query_type": "网络搜索",
            "query_success": False,
            "results": {"error": f"搜索失败: {str(e)}"},
        }
