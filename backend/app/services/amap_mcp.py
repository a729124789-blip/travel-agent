"""
高德地图 MCP 客户端封装（Streamable HTTP / JSON-RPC）

通过高德官方 MCP endpoint（https://mcp.amap.com/mcp?key=xxx）调用 15 个地图工具：
  - maps_text_search     关键字搜索 POI（景点/美食/酒店等，返回 name/address/photo 等）
  - maps_search_detail   查询 POI 详情（经纬度 location / 图片 photo / 评分 rating / 营业时间 / 级别）
  - maps_weather         城市天气
  - maps_geo / maps_regeocode / maps_direction_* / maps_distance 等（路线/坐标）

零额外依赖：直接用 httpx 发 JSON-RPC（协议已验证可用 2025-03-26）。
"""
import json
import re
from loguru import logger
import httpx

from app.config import settings

MCP_URL_TEMPLATE = "https://mcp.amap.com/mcp?key={key}"


class AmapMCPService:
    """高德 MCP 服务封装"""

    def __init__(self, api_key: str = ""):
        self.api_key = (api_key or "").strip()
        self.url = MCP_URL_TEMPLATE.format(key=self.api_key) if self.api_key else ""
        self.protocol_version = "2025-03-26"
        self._seq = 0

    # ---------- 基础 ----------

    @property
    def enabled(self) -> bool:
        """是否已配置 key 可用"""
        return bool(self.api_key and self.url)

    async def _rpc(self, method: str, params: dict) -> dict:
        """发送 JSON-RPC 请求，返回 result 部分"""
        if not self.enabled:
            raise RuntimeError("高德 MCP 未配置（AMAP_KEY 为空）")
        self._seq += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._seq,
            "method": method,
            "params": params,
        }
        headers = {
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": self.protocol_version,
        }
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.post(self.url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        if "error" in data:
            raise RuntimeError(f"高德MCP错误: {data['error']}")
        return data.get("result", {})

    @staticmethod
    def _extract_text(result: dict) -> str:
        """提取 MCP result 中的文本内容"""
        content = result.get("content", [])
        for item in content:
            if item.get("type") == "text":
                return item.get("text", "")
        return ""

    # ---------- 工具调用 ----------

    async def text_search(self, keywords: str, city: str = "") -> list[dict]:
        """关键字搜索 POI，返回结构化列表（含 name/address/photo 等）"""
        args: dict = {"keywords": keywords}
        if city:
            args["city"] = city
            args["citylimit"] = "true"
        result = await self._rpc("tools/call", {"name": "maps_text_search", "arguments": args})
        text = self._extract_text(result)
        try:
            data = json.loads(text)
            return data.get("pois", [])
        except Exception as e:
            # 高德 MCP 偶发返回非 JSON 文本（如空或错误提示），重试一次
            logger.debug(f"高德 text_search 解析失败 {keywords}（重试一次）: {e}")
            try:
                result = await self._rpc("tools/call", {"name": "maps_text_search", "arguments": args})
                text = self._extract_text(result)
                data = json.loads(text)
                return data.get("pois", [])
            except Exception as e2:
                logger.debug(f"高德 text_search 重试仍失败 {keywords}: {e2}")
                return []

    async def search_detail(self, poi_id: str) -> dict:
        """查询 POI 详情（经纬度/图片/评分/营业时间/级别）"""
        result = await self._rpc("tools/call", {"name": "maps_search_detail", "arguments": {"id": poi_id}})
        text = self._extract_text(result)
        try:
            return json.loads(text)
        except Exception as e:
            logger.debug(f"高德 search_detail 解析失败 {poi_id}: {e}")
            return {}

    async def weather(self, city: str) -> dict:
        """查询城市天气"""
        result = await self._rpc("tools/call", {"name": "maps_weather", "arguments": {"city": city}})
        text = self._extract_text(result)
        try:
            return json.loads(text)
        except Exception as e:
            logger.debug(f"高德 weather 解析失败 {city}: {e}")
            return {}

    async def geo(self, address: str) -> dict:
        """地址/地标转经纬度"""
        result = await self._rpc("tools/call", {"name": "maps_geo", "arguments": {"address": address}})
        text = self._extract_text(result)
        try:
            return json.loads(text)
        except Exception as e:
            logger.debug(f"高德 geo 解析失败 {address}: {e}")
            return {}

    # ---------- 行程增强 ----------

    @staticmethod
    def _categorize_poi(raw_type: str) -> str:
        """根据高德 POI 原始 type 字段归一化为类别：attraction / food / hotel / shopping / other"""
        t = (raw_type or "").lower()
        if any(k in t for k in ("酒店", "住宿", "宾馆", "旅馆", "民宿", "客栈", "招待所", "公寓")):
            return "hotel"
        if any(k in t for k in ("餐饮", "餐厅", "美食", "小吃", "咖啡", "甜品", "茶馆", "酒楼", "食府", "面馆")):
            return "food"
        if any(k in t for k in ("购物", "商场", "超市", "市场", "商店", "百货")):
            return "shopping"
        if any(k in t for k in ("风景", "公园", "景点", "名胜", "古迹", "景区", "游乐", "展馆", "博物馆", "美术馆", "动物园", "植物园", "寺庙", "纪念馆", "广场", "街区")):
            return "attraction"
        return "other"

    async def enrich_attractions(self, names: list, city: str = "", cities: list | None = None) -> list[dict]:
        """
        对一组景点/餐厅名，逐个搜索并补充真实 POI 信息（图片/经纬度/评分/营业时间）。

        city/cities：候选城市列表。跨城行程（如第1天白天在出发地、晚上到目的地）时，
        POI 可能分布在多个城市，逐城市尝试搜索（优先精确匹配）；候选城市都搜不到时
        回退为全国搜索（不带 citylimit），避免把"南京夫子庙"错配成"上海文庙"。

        返回列表，每项：
          { name, poi_name, address, photo, location, rating, open_time, level, poi_id, type, category }
        其中 category 由高德 type 归一化：attraction / food / hotel / shopping / other。
        搜索不到时该项会被跳过（不阻塞主流程）。
        """
        if not self.enabled:
            return []
        # 归一化候选城市列表
        city_list: list[str] = []
        if isinstance(city, str) and city:
            city_list.append(city)
        for c in (cities or []):
            c = (c or "").strip()
            if c and c not in city_list:
                city_list.append(c)
        enriched = []
        for name in names:
            name = (name or "").strip()
            # 过滤掉过长的/疑似整句描述的条目（如"XX路美食街"之类当关键词搜不准，交给详细搜索）
            if not name or len(name) > 20:
                continue
            try:
                # 搜索策略（跨城行程 POI 可能分布多个城市，如第1天白天在出发地、晚上到目的地）：
                # 无括号名称（纯景点/街区，如"夫子庙秦淮风光带"）：全国搜索完整名取第一个
                #   ——高德默认按相关度排序最可信（实测全国搜"夫子庙秦淮风光带"→南京夫子庙）；
                #   结果地址命中候选城市时优先，否则按候选城市兜底。
                # 带括号名称（分店/品牌店，如"南京大牌档(夫子庙平江府店)"）：全名搜索会被括号内容
                #   干扰（误命中无关 POI），改用"核心名(去括号)"全国+候选城市搜索，
                #   用 相似度打分(核心名+3 / 分支关键词+2 / 候选城市+1) 挑选全局最优分店。
                search_kw = re.split(r"[（(]", name)[0].strip() or name
                search_kw = search_kw[:12]
                branch_kw = ""
                m = re.search(r"[（(]([^（）()]*?)[）)]", name)
                if m:
                    branch_kw = m.group(1).strip()
                has_branch = bool(branch_kw)

                if not has_branch:
                    # 无括号：全国搜索完整名，地址命中候选城市优先，否则取第一个
                    pois = await self.text_search(search_kw)
                    poi = None
                    if pois:
                        if city_list:
                            for p in pois:
                                s = (p.get("address", "") or "") + (p.get("adname", "") or "")
                                if any(c and c in s for c in city_list):
                                    poi = p
                                    break
                        if poi is None:
                            poi = pois[0]
                    if poi is None and city_list:
                        for c in city_list:
                            pois = await self.text_search(search_kw, city=c)
                            if pois:
                                poi = pois[0]
                                break
                    if poi is None:
                        continue
                else:
                    # 带括号分店：核心名搜索 + 打分选最优
                    # 城市搜索的结果属于候选城市（城市可信），统一 +10 基础加成，
                    # 确保正确城市的店永远覆盖全国搜索（如"南京大牌档"全国搜会返回北京店）——
                    # 再叠加 核心名+3 / 分支关键词+2 / 地址含城市+1 区分具体分店。
                    def _score(p: dict, cities: list, base: int = 0) -> int:
                        s = (p.get("name", "") or "") + (p.get("address", "") or "") + (p.get("adname", "") or "")
                        sc = base
                        if search_kw and (search_kw in s):
                            sc += 3
                        if branch_kw:
                            if branch_kw in s:
                                sc += 2
                            elif branch_kw[:2] in s:
                                sc += 1
                        if cities and any(c and c in s for c in cities):
                            sc += 1
                        return sc

                    best_poi = None
                    best_score = -1
                    # 阶段1：逐候选城市搜索（优先，+10 城市可信加成）
                    for c in city_list:
                        pois = await self.text_search(search_kw, city=c)
                        for p in pois:
                            sc = _score(p, [c], base=10)
                            if sc > best_score:
                                best_poi, best_score = p, sc
                    # 阶段2：候选城市全空 → 回退全国搜索（不加成）
                    if best_poi is None:
                        pois = await self.text_search(search_kw)
                        for p in pois:
                            sc = _score(p, city_list)
                            if sc > best_score:
                                best_poi, best_score = p, sc
                    if best_poi is None:
                        continue
                    poi = best_poi
                poi_id = poi.get("id", "")
                detail = {}
                if poi_id:
                    detail = await self.search_detail(poi_id)
                raw_type = detail.get("type") or poi.get("type") or ""
                enriched.append({
                    "name": name,
                    "poi_name": detail.get("name") or poi.get("name", ""),
                    "address": detail.get("address") or poi.get("address", ""),
                    "photo": detail.get("photo") or poi.get("photo", ""),
                    "location": detail.get("location") or "",
                    "rating": detail.get("rating") or "",
                    "open_time": detail.get("open_time") or detail.get("opentime2", ""),
                    "level": detail.get("level") or "",
                    "poi_id": poi_id,
                    "type": raw_type,
                    "category": self._categorize_poi(raw_type),
                })
                logger.info(f"高德补充POI成功: {name} -> {enriched[-1]['poi_name']} [{enriched[-1]['category']}] @{enriched[-1]['location']}")
            except Exception as e:
                logger.debug(f"高德补充POI失败 {name}: {e}")
                continue
        return enriched

    async def hot_attractions(self, city: str, exclude_names: list | None = None, limit: int = 4) -> list[dict]:
        """
        搜索某城市的热门景点（不在行程规划中也推荐），用于丰富"景点推荐"栏。

        返回与 enrich_attractions 相同的结构（仅 category=attraction 的 POI），
        并过滤掉已出现在行程中的景点（exclude_names）。
        """
        if not self.enabled or not city:
            return []
        exclude = {str(n).strip() for n in (exclude_names or []) if str(n).strip()}
        results = []
        keywords = [f"{city}热门景点", f"{city}景点", f"{city}著名景点"]
        for kw in keywords:
            if len(results) >= limit:
                break
            try:
                pois = await self.text_search(kw, city=city)
                for poi in pois:
                    if len(results) >= limit:
                        break
                    name = (poi.get("name", "") or "").strip()
                    if not name or name in exclude:
                        continue
                    poi_id = poi.get("id", "")
                    detail = {}
                    if poi_id:
                        detail = await self.search_detail(poi_id)
                    # 注意：搜索列表项顶层没有 type 字段（只有 typecode），
                    # 必须用详情接口返回的中文 type 判断类别，否则全部被误过滤
                    raw_type = detail.get("type") or poi.get("type") or ""
                    if self._categorize_poi(raw_type) != "attraction":
                        continue
                    results.append({
                        "name": name,
                        "poi_name": detail.get("name") or poi.get("name", name),
                        "address": detail.get("address") or poi.get("address", ""),
                        "photo": detail.get("photo") or poi.get("photo", ""),
                        "location": detail.get("location") or "",
                        "rating": detail.get("rating") or "",
                        "open_time": detail.get("open_time") or "",
                        "level": detail.get("level") or "",
                        "poi_id": poi_id,
                        "type": raw_type,
                        "category": "attraction",
                    })
                    exclude.add(name)
            except Exception as e:
                logger.debug(f"热门景点搜索失败 {kw}: {e}")
                continue
        if results:
            logger.info(f"热门景点补充: {city} 共{len(results)}个")
        return results


# 全局单例
amap_mcp = AmapMCPService(api_key=settings.amap_key)
