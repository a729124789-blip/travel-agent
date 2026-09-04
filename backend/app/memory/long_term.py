"""
长期记忆：持久化用户信息（偏好、聊天历史、行程历史），JSON 文件存储
"""
from typing import Dict, Any, List
import json
import os
from datetime import datetime
from pathlib import Path
from loguru import logger


class LongTermMemory:
    """按 user_id 隔离的 JSON 文件持久化记忆"""

    def __init__(self, user_id: str, storage_path: str = "data/memory"):
        self.user_id = user_id
        self.storage_path = storage_path
        self.db_path = os.path.join(storage_path, f"{user_id}.json")
        Path(storage_path).mkdir(parents=True, exist_ok=True)
        self.data = self._load()
        logger.info(f"长期记忆已加载: user={user_id}")

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    data = self._migrate_data(data)
                    return data
            except Exception as e:
                logger.error(f"加载长期记忆失败: {e}")
                return self._init_data()
        return self._init_data()

    def _migrate_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """兼容旧格式数据迁移"""
        for field in ["chat_history", "trip_history"]:
            if field not in data:
                data[field] = []
        if "statistics" not in data:
            data["statistics"] = {}
        if "total_messages" not in data.get("statistics", {}):
            data["statistics"]["total_messages"] = 0
        if "preferences" not in data:
            data["preferences"] = []

        # 旧格式：字典 → 列表
        if isinstance(data.get("preferences"), dict):
            old_prefs = data["preferences"]
            new_prefs = [{"type": k, "value": v} for k, v in old_prefs.items() if v is not None]
            data["preferences"] = new_prefs
            logger.info(f"迁移: 偏好字典→列表 ({len(new_prefs)}项)")

        # 修复嵌套 bug
        if isinstance(data.get("preferences"), list):
            fixed = []
            for pref in data["preferences"]:
                if isinstance(pref, dict) and pref.get("type") == "preferences" and isinstance(pref.get("value"), list):
                    for nested in pref["value"]:
                        if isinstance(nested, dict) and "type" in nested:
                            fixed.append({"type": nested["type"], "value": nested["value"]})
                else:
                    fixed.append(pref)
            if fixed != data["preferences"]:
                data["preferences"] = fixed

        self.data = data
        self._save()
        return data

    def _init_data(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "preferences": [],
            "chat_history": [],
            "trip_history": [],
            "statistics": {
                "total_trips": 0,
                "total_messages": 0,
                "frequent_destinations": {}
            }
        }

    def _save(self):
        try:
            self.data["updated_at"] = datetime.now().isoformat()
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存长期记忆失败: {e}")

    # ===== 偏好 =====

    def save_preference(self, pref_type: str, value: Any):
        prefs = self.data["preferences"]
        for pref in prefs:
            if pref.get("type") == pref_type:
                pref["value"] = value
                self._save()
                logger.info(f"更新偏好: {pref_type}={value}")
                return
        prefs.append({"type": pref_type, "value": value})
        self._save()
        logger.info(f"新增偏好: {pref_type}={value}")

    def get_preference(self, pref_type: str = None):
        prefs = self.data["preferences"]
        if pref_type is None:
            return {p.get("type"): p.get("value") for p in prefs}
        for pref in prefs:
            if pref.get("type") == pref_type:
                return pref.get("value")
        return None

    def add_list_preference(self, pref_type: str, value: str):
        """追加型偏好（如酒店品牌、航空公司）"""
        prefs = self.data["preferences"]
        for pref in prefs:
            if pref.get("type") == pref_type:
                if not isinstance(pref["value"], list):
                    pref["value"] = [pref["value"]] if pref["value"] else []
                if value not in pref["value"]:
                    pref["value"].append(value)
                self._save()
                return
        prefs.append({"type": pref_type, "value": [value]})
        self._save()

    # ===== 聊天历史 =====

    def add_chat_message(self, role: str, content: str, session_id: str = None):
        self.data["chat_history"].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id
        })
        self.data["statistics"]["total_messages"] += 1
        self._save()

    def get_chat_history(self, limit: int = None, session_id: str = None) -> List[Dict[str, Any]]:
        messages = self.data["chat_history"]
        if session_id:
            messages = [m for m in messages if m.get("session_id") == session_id]
        return messages[-limit:] if limit else messages

    def delete_chat_messages(self, timestamps: List[str]) -> int:
        """按 timestamp 删除聊天记录（成对的 user/assistant 共享同一 timestamp）。

        Args:
            timestamps: 要删除的消息 timestamp 列表

        Returns:
            实际删除条数
        """
        if not timestamps:
            return 0
        ts_set = set(timestamps)
        before = len(self.data["chat_history"])
        self.data["chat_history"] = [
            m for m in self.data["chat_history"]
            if m.get("timestamp") not in ts_set
        ]
        removed = before - len(self.data["chat_history"])
        # 更新统计
        self.data["statistics"]["total_messages"] = max(
            0, self.data["statistics"].get("total_messages", 0) - removed
        )
        self._save()
        logger.info(f"删除聊天记录: {removed} 条")
        return removed

    def delete_trip_by_id(self, trip_id: str) -> bool:
        """按 trip_id 删除单条行程记录，并同步更新统计与常去目的地。

        Args:
            trip_id: 行程 ID（如 trip_3）

        Returns:
            是否删除成功
        """
        trips = self.data["trip_history"]
        target = next((t for t in trips if t.get("trip_id") == trip_id), None)
        if not target:
            logger.warning(f"删除行程失败: 未找到 trip_id={trip_id}")
            return False
        self.data["trip_history"] = [t for t in trips if t.get("trip_id") != trip_id]
        # 更新统计
        self.data["statistics"]["total_trips"] = max(
            0, self.data["statistics"].get("total_trips", 0) - 1
        )
        dest = target.get("destination")
        if dest:
            freq = self.data["statistics"].get("frequent_destinations", {})
            if dest in freq:
                freq[dest] -= 1
                if freq[dest] <= 0:
                    freq.pop(dest, None)
        self._save()
        logger.info(f"删除行程: {trip_id} ({target.get('origin', '')} → {dest or ''})")
        return True

    # ===== 行程历史 =====

    def save_trip_history(self, trip_info: Dict[str, Any]):
        self.data["trip_history"].append({
            "trip_id": f"trip_{len(self.data['trip_history']) + 1}",
            "timestamp": datetime.now().isoformat(),
            **trip_info
        })
        self.data["statistics"]["total_trips"] += 1
        dest = trip_info.get("destination")
        if dest:
            freq = self.data["statistics"]["frequent_destinations"]
            freq[dest] = freq.get(dest, 0) + 1
        self._save()

    def get_trip_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.data["trip_history"][-limit:] if limit else self.data["trip_history"]

    def get_frequent_destinations(self, top_n: int = 5) -> List[tuple]:
        freq = self.data["statistics"]["frequent_destinations"]
        return sorted(freq.items(), key=lambda x: x[1], reverse=True)[:top_n]

    # ===== 统计与清理 =====

    def get_statistics(self) -> Dict[str, Any]:
        return self.data["statistics"].copy()

    def clear_history(self):
        self.data["chat_history"] = []
        self.data["trip_history"] = []
        self.data["statistics"]["total_trips"] = 0
        self.data["statistics"]["total_messages"] = 0
        self.data["statistics"]["frequent_destinations"] = {}
        self._save()
        logger.info("已清空历史记录（保留偏好）")
