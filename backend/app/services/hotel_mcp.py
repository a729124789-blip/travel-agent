"""
酒店搜索与智能推荐 MCP 客户端封装（streamable_http / JSON-RPC）

通过魔搭 ModelScope 托管的 RollingGo 酒店 MCP（https://mcp.api-inference.modelscope.net/<UUID>/mcp）调用：
  - hotelSearchAndRecommend  酒店搜索推荐（场景识别→参数补全→搜索→详情→推荐理由）
  - getHotelDetail          获取单个酒店详情（房型价格/退改政策）

调用方式与高德/12306 MCP 一致：httpx + JSON-RPC，零额外依赖。
"""
import json
from loguru import logger
import httpx

from app.config import settings

# 酒店 MCP URL 从环境变量读取（含用户专属 UUID，不硬编码）
HOTEL_MCP_URL = settings.hotel_mcp_url

# 偏好类型 -> MCP 星级筛选映射
_BUDGET_TO_STAR = {
    "经济": "经济型",
    "舒适": "舒适型",
    "高档": "高档型",
    "豪华": "豪华型",
}
_BUDGET_TO_MAX_PRICE = {
    "经济": 300,
    "舒适": 600,
    "高档": 1200,
    "豪华": 3000,
}


class HotelMCPService:
    """RollingGo 酒店 MCP 服务封装"""

    def __init__(self, url: str = HOTEL_MCP_URL):
        self.url = url
        self.protocol_version = "2025-03-26"
        self._seq = 0

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    async def _rpc(self, method: str, params: dict) -> dict:
        self._seq += 1
        payload = {"jsonrpc": "2.0", "id": self._seq, "method": method, "params": params}
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": self.protocol_version,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(self.url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        if "error" in data:
            raise RuntimeError(f"酒店MCP错误: {data['error']}")
        return data.get("result", {})

    @staticmethod
    def _extract_text(result: dict) -> str:
        content = result.get("content", [])
        return "".join(i.get("text", "") for i in content if i.get("type") == "text")

    async def search_recommend(
        self,
        destination: str,
        check_in: str,
        check_out: str,
        query: str = "",
        star_rating: str | None = None,
        max_price: int | None = None,
        guests: int = 1,
        scene: str = "通用",
    ) -> dict:
        """酒店搜索推荐，返回结构化结果 {ok, hotels, ...}"""
        args = {
            "destination": destination,
            "checkIn": check_in,
            "checkOut": check_out,
            "query": query or f"在{destination}入住{check_in}至{check_out}",
            "guests": guests,
        }
        if star_rating:
            args["starRating"] = star_rating
        if max_price:
            args["maxPrice"] = max_price
        if scene and scene != "通用":
            args["scene"] = scene
        try:
            result = await self._rpc("tools/call", {"name": "hotelSearchAndRecommend", "arguments": args})
            text = self._extract_text(result).strip()
            data = json.loads(text)
            return {"ok": True, **data}
        except Exception as e:
            logger.warning(f"酒店搜索失败 {destination} {check_in}~{check_out}: {e}")
            return {"ok": False, "error": str(e), "hotels": []}

    def _extract_budget_from_prefs(self, preferences: dict, free_text: str = "") -> tuple[str | None, int | None, str | None]:
        """从用户偏好+自由文本提取预算档位、价格上限、星级筛选"""
        budget_level = str(preferences.get("budget_level") or "")
        hotel_brands = preferences.get("hotel_brands") or ""
        food = str(preferences.get("food_preference") or "")

        # 从 budget_level + free_text 判断（如"经济实惠""预算200-300""便宜点100-130左右"）
        budget_text = (budget_level + " " + str(food) + " " + str(free_text)).lower()
        star = None
        max_price = None
        for key, val in _BUDGET_TO_STAR.items():
            if key in budget_text:
                star = val
                max_price = _BUDGET_TO_MAX_PRICE[key]
                break
        # 若文本含具体价格区间/单值，解析上限（覆盖"100-130""便宜点100-130左右""大概200元"等）
        import re
        # 区间：两位以上数字 + 分隔符（- ~ 到 至）
        m = re.search(r"(\d{2,})\s*(?:-|~|～|到|至)\s*(\d{2,})", budget_text)
        if m:
            max_price = max(int(m.group(1)), int(m.group(2)))
        else:
            # 单值：数字 + 元/块（避免误匹配 2 位年份等，要求至少 2 位且不超过 4 位）
            m2 = re.search(r"(\d{2,4})\s*(?:元|块钱|元\/晚|块)", budget_text)
            if m2:
                max_price = int(m2.group(1))
        # 场景推断
        scene = "通用"
        if any(k in budget_text for k in ("商务", "出差", "会议")):
            scene = "商务"
        elif any(k in budget_text for k in ("亲子", "带娃", "孩子", "儿童")):
            scene = "亲子"
        elif any(k in budget_text for k in ("背包", "穷游", "大学生", "学生", "青年", "经济")):
            scene = "背包"
        elif any(k in budget_text for k in ("度假", "休闲", "旅游")):
            scene = "度假"
        return star, max_price, scene

    async def enrich_hotel(
        self,
        destination: str,
        check_in: str,
        check_out: str,
        preferences: dict | None = None,
        free_text: str = "",
        guests: int = 1,
    ) -> dict:
        """
        为某天住宿补充真实酒店推荐。

        返回：{ "ok": bool, "hotels": [...], "message": str }
        """
        prefs = preferences or {}
        star, max_price, scene = self._extract_budget_from_prefs(prefs, free_text)
        # 拼 query：偏好 + 用户自由文本（保留价格描述，RollingGo MCP 对 query 中的价格数字敏感，
        # 去掉后反而会返回高价酒店；价格上限由 max_price 参数 + 本地硬过滤双重控制）
        query_parts = []
        bl = prefs.get("budget_level") or ""
        if bl:
            query_parts.append(f"预算{bl}")
        hb = prefs.get("hotel_brands") or ""
        if hb:
            query_parts.append(f"偏好{hb}")
        if free_text:
            query_parts.append(free_text)
        # 关键：query 必须以"{destination}住宿{check_in}至{check_out}"开头（不带"在"字），
        # RollingGo 对 query 措辞极敏感，已验证该格式能触发低价酒店推荐；后面再拼偏好/自由文本
        base_query = f"{destination}住宿{check_in}至{check_out}"
        query = base_query + ("，" + "，".join(query_parts) if query_parts else "")

        res = await self.search_recommend(
            destination=destination,
            check_in=check_in,
            check_out=check_out,
            query=query,
            star_rating=star,
            # 传给 MCP 的价格上限放宽到 ×2，让候选更充足，本地再做预算硬过滤
            max_price=int(max_price * 2) if max_price else None,
            guests=guests,
            scene=scene,
        )
        if not res.get("ok"):
            return {"ok": False, "hotels": [], "message": res.get("error", "查询失败")}
        hotels = res.get("hotels", []) or []
        if not hotels:
            return {"ok": False, "hotels": [], "message": f"未查询到 {destination} 的酒店"}
        # 硬约束：用户明确给出价格上限时，只保留符合预算的（上限放宽到 ×2，如 130 预算可推至 260，
        # 宁可位置偏一点也要满足预算需求）；若 ×2 内仍无候选，则去掉价格上限再查一次，
        # 仅保留"轻微超预算"（≤×3，如 130→390）的酒店，尽量给到建议；若仍无，诚实兜底，绝不推天价酒店
        if max_price:
            cap = int(max_price * 2)
            in_budget = [h for h in hotels if (h.get("lowestPrice") or 0) <= cap]
            if not in_budget:
                # 多 query 兜底：RollingGo 对 query 措辞极敏感（已验证"想住经济实惠的酒店，预算X左右"能触发低价推荐），
                # 用多个不同措辞的 query 依次搜索并合并去重，提高命中低价酒店的概率
                alt_suffixes = [
                    f"，想住经济实惠的酒店，预算{max_price}左右",
                    f"，{max_price}元以内经济实惠的酒店",
                    "，性价比高的平价住宿，干净卫生",
                ]
                merged: list[dict] = []
                seen: set[str] = set()
                for suffix in alt_suffixes:
                    alt_query = base_query + suffix
                    rn = await self.search_recommend(
                        destination=destination,
                        check_in=check_in,
                        check_out=check_out,
                        query=alt_query,
                        star_rating=star,
                        guests=guests,
                        scene=scene,
                    )
                    for h in (rn.get("hotels", []) or []):
                        name = h.get("name") or ""
                        if name and name not in seen:
                            seen.add(name)
                            merged.append(h)
                cap2 = int(max_price * 3)
                in_budget2 = [h for h in merged if (h.get("lowestPrice") or 0) <= cap2]
                if in_budget2:
                    hotels = sorted(in_budget2, key=lambda h: h.get("lowestPrice") or 0)[:3]
                    return {
                        "ok": True,
                        "hotels": hotels,
                        "message": f"未找到预算（≤{max_price}元/晚）内酒店，以下为略超预算的推荐",
                    }
                return {
                    "ok": True,
                    "hotels": [],
                    "message": f"实时查询暂未匹配到该价位房源（≤{max_price}元/晚，可浮动至{cap}元），建议自行预订经济型连锁酒店",
                }
            hotels = in_budget
        # 数量：在预算范围内尽量多给 2-3 家，让用户有得选
        hotels = sorted(hotels, key=lambda h: h.get("lowestPrice") or 0)[:3]
        return {"ok": True, "hotels": hotels, "message": f"查询到 {len(hotels)} 家推荐酒店"}


# 全局单例
hotel_mcp = HotelMCPService()
