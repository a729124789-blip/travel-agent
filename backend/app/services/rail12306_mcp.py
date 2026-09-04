"""
12306 火车票 MCP 客户端封装（streamable_http / JSON-RPC）

通过魔搭 ModelScope 托管的 12306 MCP（https://mcp.api-inference.modelscope.net/<UUID>/mcp）调用：
  - get-current-date            获取当前日期（Asia/Shanghai）
  - get-station-code-of-citys   城市 -> 代表车站 code（如 南京 -> NJH）
  - get-stations-code-in-city   城市 -> 该城市所有车站
  - get-station-code-by-names   具体车站名 -> station_code
  - get-tickets                 查询 12306 余票（车次/出发到达时间/历时/票价/余票）
  - get-interline-tickets       查询中转余票（前10条）
  - get-train-route-stations    车次经停站详情

与高德 MCP 同样的调用方式：httpx + JSON-RPC，零额外依赖。
"""
import json
from loguru import logger
import httpx

from app.config import settings

# 12306 MCP URL 从环境变量读取（含用户专属 UUID，不硬编码）
RAIL_MCP_URL = settings.rail_mcp_url


class Rail12306MCPService:
    """12306 MCP 服务封装"""

    def __init__(self, url: str = RAIL_MCP_URL):
        self.url = url
        self.protocol_version = "2025-03-26"
        self._seq = 0

    # ---------- 基础 ----------

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    async def _rpc(self, method: str, params: dict) -> dict:
        """发送 JSON-RPC 请求，返回 result 部分"""
        self._seq += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._seq,
            "method": method,
            "params": params,
        }
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": self.protocol_version,
        }
        async with httpx.AsyncClient(timeout=40) as client:
            resp = await client.post(self.url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        if "error" in data:
            raise RuntimeError(f"12306MCP错误: {data['error']}")
        return data.get("result", {})

    @staticmethod
    def _extract_text(result: dict) -> str:
        """提取 MCP result 中的文本内容"""
        content = result.get("content", [])
        return "".join(i.get("text", "") for i in content if i.get("type") == "text")

    # ---------- 工具调用 ----------

    async def current_date(self) -> str:
        """获取当前日期 yyyy-MM-dd"""
        try:
            result = await self._rpc("tools/call", {"name": "get-current-date", "arguments": {}})
            return self._extract_text(result).strip()
        except Exception as e:
            logger.debug(f"12306 current_date 失败: {e}")
            return ""

    async def station_codes(self, cities: str) -> dict:
        """城市名(可|分隔多个) -> {城市: {station_code, station_name}}"""
        try:
            result = await self._rpc(
                "tools/call",
                {"name": "get-station-code-of-citys", "arguments": {"citys": cities}},
            )
            text = self._extract_text(result).strip()
            data = json.loads(text)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.debug(f"12306 station_codes 失败: {e}")
            return {}

    async def tickets(self, date: str, from_station: str, to_station: str) -> list[dict]:
        """查询余票，返回结构化车次列表

        返回每项：{ train_no, from_to, dep_time, arr_time, duration, seats: [ {type, price, left} ] }
        失败时返回 []。
        """
        try:
            result = await self._rpc(
                "tools/call",
                {
                    "name": "get-tickets",
                    "arguments": {"date": date, "fromStation": from_station, "toStation": to_station},
                },
            )
            text = self._extract_text(result).strip()
            return self._parse_tickets(text)
        except Exception as e:
            logger.warning(f"12306 余票查询失败 {from_station}->{to_station} {date}: {e}")
            return []

    @staticmethod
    def _parse_tickets(text: str) -> list[dict]:
        """解析 12306 MCP 返回的车次文本为结构化列表"""
        trains = []
        current = None
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            # 车次行: "Z175 南京(telecode:NJH) -> 上海松江(telecode:IMH) 00:08 -> 04:01 历时：03:53"
            if line[0:1].isalpha() and "->" in line and "车次" not in line and "出发站" not in line:
                if current:
                    trains.append(current)
                # 解析
                parts = line.split()
                train_no = parts[0]
                # 找 出发 -> 到达 时间
                import re
                m = re.search(r"(\d{2}:\d{2})\s*->\s*(\d{2}:\d{2})", line)
                dep = m.group(1) if m else ""
                arr = m.group(2) if m else ""
                dm = re.search(r"历时[：:]\s*([\d:]+)", line)
                duration = dm.group(1) if dm else ""
                current = {"train_no": train_no, "dep_time": dep, "arr_time": arr, "duration": duration, "seats": []}
            elif current and ("张票" in line or "有票" in line or "无票" in line):
                # 座位行: "- 硬座: 剩余1张票 50.5元"
                sm = re.match(r"-\s*([^:：]+)[:：]\s*(.+)", line)
                if sm:
                    seat_type = sm.group(1).strip()
                    info = sm.group(2).strip()
                    pm = re.search(r"([\d.]+)\s*元", info)
                    price = pm.group(1) if pm else ""
                    current["seats"].append({"type": seat_type, "price": price, "info": info})
        if current:
            trains.append(current)
        return trains

    @staticmethod
    def _is_normal_train(train_no: str) -> bool:
        """是否普速列车：车次号以数字/K/T/Z/L/Y/N 开头（高铁动车为 G/D/C）"""
        if not train_no:
            return False
        c = train_no[0].upper()
        return c.isdigit() or c in "KTZLYNX"

    # ---------- 行程增强 ----------

    async def enrich_train_plan(
        self,
        date: str,
        from_city: str,
        to_city: str,
        max_trains: int = 3,
        prefer_type: str | None = None,
    ) -> dict:
        """
        为某一天的城市间移动补充真实车次/票价/余票信息。

        prefer_type:
          - "train"      用户指定火车 → 优先普速 K/T/Z/数字 车次；无普速时回退高铁并说明
          - "high_speed" 用户指定高铁/动车 → 优先 G/D/C
          - None         不指定 → 按白天时段排序返回全部

        返回：{ "ok": bool, "message": str, "trains": [...] }
        """
        if not self.enabled:
            return {"ok": False, "message": "12306 MCP 未配置", "trains": []}
        if not date or not from_city or not to_city or from_city == to_city:
            return {"ok": False, "message": "缺少出发/到达城市或日期", "trains": []}
        try:
            codes = await self.station_codes(f"{from_city}|{to_city}")
            from_code = codes.get(from_city, {}).get("station_code", from_city)
            to_code = codes.get(to_city, {}).get("station_code", to_city)
            trains = await self.tickets(date, from_code, to_code)
            if not trains:
                return {"ok": False, "message": f"未查询到 {from_city}->{to_city} 的车次", "trains": []}

            # 按出发时间排序，优先白天车次（06:00-23:59），凌晨夜车放最后
            def _sort_key(t):
                dep = t.get("dep_time", "")
                try:
                    hh, mm = dep.split(":")
                    v = int(hh) * 60 + int(mm)
                except Exception:
                    v = 24 * 60
                # 凌晨(00:00-05:59)视为不适用的夜车，排到最末
                if v < 6 * 60:
                    return v + 48 * 60
                return v

            trains = sorted(trains, key=_sort_key)
            note = ""
            if prefer_type == "train":
                normal = [t for t in trains if self._is_normal_train(t.get("train_no", ""))]
                if normal:
                    trains = normal
                else:
                    note = "当日暂无普速（K/T/Z）车次，已为您展示高铁/动车备选；如仍希望乘坐普速火车，可换乘或调整日期。"
            elif prefer_type == "high_speed":
                hs = [t for t in trains if not self._is_normal_train(t.get("train_no", ""))]
                if hs:
                    trains = hs
                else:
                    note = "当日暂无高铁/动车车次，已为您展示普速列车备选。"
            message = f"查询到 {len(trains)} 个车次"
            if note:
                message = note
            return {
                "ok": True,
                "message": message,
                "trains": trains[:max_trains],
            }
        except Exception as e:
            logger.warning(f"12306 行程增强失败: {e}")
            return {"ok": False, "message": str(e), "trains": []}


# 全局单例
rail_mcp = Rail12306MCPService()
