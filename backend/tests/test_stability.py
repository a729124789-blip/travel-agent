# -*- coding: utf-8 -*-
"""
稳定性测试：在线调用运行中的后端服务（http://127.0.0.1:8000），验证核心链路。

覆盖用例：
  1. 意图识别 + 信息收集   —— LLM 连通、意图路由、口语化日期（"2天"）解析
  2. 逐天行程生成（SSE）    —— 完整规划链路：中文思考 / 天气 / 车次 / 酒店 / POI / 正文
  3. RAG 差旅政策问答 + 偏好读写 —— 知识检索与记忆闭环

运行方式（后端须已在 8000 端口运行）：
  cd backend
  python tests/test_stability.py
"""
import json
import re
import sys
import time
import requests

BASE = "http://127.0.0.1:8000"
TOTAL_TIMEOUT = 320  # 逐天生成最长等待

results: list = []


def check(name: str, cond: bool, detail: str = ""):
    results.append((name, bool(cond), detail))
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name}" + (f"  -- {detail}" if detail else ""))


def _has_cjk(text: str) -> bool:
    """判断字符串是否包含中文（CJK 统一表意文字）"""
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def test_intent_collection() -> None:
    """用例 1：意图识别 + 信息收集"""
    print("\n===== 用例1：意图识别 + 信息收集 =====")
    try:
        r = requests.post(
            f"{BASE}/api/chat/intent",
            json={
                "user_input": "我想从南京坐火车去上海玩2天，喜欢美食",
                "user_id": "default_user",
                "session_id": "default",
            },
            timeout=60,
        )
        check("intent 接口 200", r.status_code == 200, f"HTTP {r.status_code}")
        data = r.json()
        check("意图包含 itinerary_planning", "itinerary_planning" in data.get("intents", []),
              f"intents={data.get('intents')}")
        check("agent_schedule 非空", bool(data.get("agent_schedule")),
              f"schedule={data.get('agent_schedule')}")
        ents = data.get("key_entities", {})
        check("key_entities 提取目的地=上海", ents.get("destination") == "上海",
              f"destination={ents.get('destination')}")
        check("key_entities 提取出发地=南京", ents.get("origin") == "南京",
              f"origin={ents.get('origin')}")
    except Exception as e:
        check("intent 接口调用", False, str(e))

    # 信息收集：验证口语化日期 "2天" 解析
    try:
        r = requests.post(
            f"{BASE}/api/chat/test/event-collection",
            json={
                "user_input": "我想从南京坐火车去上海玩2天，喜欢美食",
                "context": {
                    "rewritten_query": "我想从南京坐火车去上海玩2天，喜欢美食",
                    "user_preferences": {"transportation_preference": "火车", "last_origin": "南京"},
                },
            },
            timeout=60,
        )
        check("event-collection 接口 200", r.status_code == 200, f"HTTP {r.status_code}")
        ec = r.json()
        check("event 出发地=南京", ec.get("origin") == "南京", f"origin={ec.get('origin')}")
        check("event 目的地=上海", ec.get("destination") == "上海", f"dest={ec.get('destination')}")
        check("event 旅行天数=2", ec.get("duration_days") == 2, f"days={ec.get('duration_days')}")
        check("event 交通=火车", ec.get("transportation") == "火车", f"trans={ec.get('transportation')}")
        check("event 起止日期正确(2天)", ec.get("start_date") and ec.get("end_date"),
              f"{ec.get('start_date')} ~ {ec.get('end_date')}")
    except Exception as e:
        check("event-collection 接口调用", False, str(e))


def test_day_plan_stream() -> None:
    """用例 2：逐天行程生成（SSE 完整链路）"""
    print("\n===== 用例2：逐天行程生成（SSE） =====")
    try:
        r = requests.post(
            f"{BASE}/api/chat/day-plan/stream",
            json={
                "departure_city": "南京",
                "city": "上海",
                "start_date": "2026-09-04",
                "end_date": "2026-09-05",
                "travel_days": 2,
                "transportation": "火车",
                "accommodation": "经济型",
                "preferences": ["美食"],
                "free_text_input": "喜欢美食，经济实惠",
                "user_id": "default_user",
                "session_id": "default",
                "current_day": 1,
                "previous_days": [],
                "feedback": "",
                "used_poi_names": [],
            },
            stream=True,
            timeout=TOTAL_TIMEOUT,
        )
        check("day-plan 接口 200", r.status_code == 200, f"HTTP {r.status_code}")

        events = {"progress": 0, "reasoning": "", "meta": None, "delta": "",
                  "poi": [], "train": [], "weather": [], "hotel": []}
        done = False
        err = ""
        t0 = time.time()
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            try:
                d = json.loads(line[5:].strip())
            except Exception:
                continue
            t = d.get("type")
            if t == "progress":
                events["progress"] += 1
            elif t == "reasoning":
                events["reasoning"] += d.get("content", "")
            elif t == "meta":
                events["meta"] = d
            elif t == "delta":
                events["delta"] += d.get("content", "")
            elif t in ("poi", "train", "weather", "hotel"):
                events[t] += d.get(t) or d.get("data") or []
            elif t == "done":
                done = True
                break
            elif t == "error":
                err = d.get("message", "")
                break
        elapsed = round(time.time() - t0, 1)

        check("收到 progress 事件", events["progress"] > 0, f"{events['progress']} 条")
        check("收到 reasoning 思考内容", len(events["reasoning"]) > 100,
              f"{len(events['reasoning'])} 字")
        check("reasoning 为中文思考", _has_cjk(events["reasoning"]),
              f"首60字: {events['reasoning'][:60]!r}")
        check("meta 携带 day/total_days", events["meta"] is not None,
              f"meta={events['meta']}")
        check("delta 正文非空", len(events["delta"]) > 200, f"{len(events['delta'])} 字")
        check("天气事件", len(events["weather"]) > 0, f"{len(events['weather'])} 条")
        check("车次事件", len(events["train"]) > 0, f"{len(events['train'])} 条")
        check("酒店事件", len(events["hotel"]) > 0, f"{len(events['hotel'])} 条")
        check("POI 事件", len(events["poi"]) > 0, f"{len(events['poi'])} 条")
        check("done 正常收尾", done, f"elapsed={elapsed}s" + (f" err={err}" if err else ""))
    except Exception as e:
        check("day-plan 接口调用", False, str(e))


def test_rag_prefs() -> None:
    """用例 3：RAG 差旅政策问答 + 偏好读写"""
    print("\n===== 用例3：RAG 问答 + 偏好读写 =====")
    # RAG
    try:
        r = requests.post(
            f"{BASE}/api/chat/test/rag",
            json={
                "user_input": "出差住宿标准是多少？",
                "user_id": "default_user",
                "session_id": "default",
            },
            timeout=90,
        )
        check("RAG 接口 200", r.status_code == 200, f"HTTP {r.status_code}")
        txt = json.dumps(r.json(), ensure_ascii=False)
        check("RAG 返回非空", len(txt) > 50, f"{len(txt)} 字符")
        check("RAG 命中差旅内容(含'住宿'或'标准')",
              ("住宿" in txt or "标准" in txt or "出差" in txt),
              txt[:80])
    except Exception as e:
        check("RAG 接口调用", False, str(e))

    # 偏好读写
    try:
        test_key = f"stability_test_{int(time.time())}"
        r = requests.post(
            f"{BASE}/api/chat/preferences?user_id=default_user&session_id=default",
            json={"type": "transportation_preference", "value": "火车", "action": "replace"},
            timeout=30,
        )
        check("偏好保存 200", r.status_code == 200, f"HTTP {r.status_code}")
        r = requests.get(
            f"{BASE}/api/chat/preferences?user_id=default_user&session_id=default",
            timeout=30,
        )
        check("偏好读取 200", r.status_code == 200, f"HTTP {r.status_code}")
        data = r.json()
        prefs = data.get("preferences") or data
        check("偏好读取包含交通偏好", "火车" in json.dumps(prefs, ensure_ascii=False),
              f"prefs={prefs}")
    except Exception as e:
        check("偏好读写接口调用", False, str(e))


def main() -> None:
    print(f"连接后端: {BASE}")
    try:
        r = requests.get(f"{BASE}/api/chat/llm-status", timeout=15)
        print("LLM 状态:", json.dumps(r.json(), ensure_ascii=False)[:300])
    except Exception as e:
        print("LLM 状态获取失败:", e)

    test_intent_collection()
    test_day_plan_stream()
    test_rag_prefs()

    print("\n" + "=" * 60)
    passed = sum(1 for _, c, _ in results if c)
    print(f"测试结果: {passed}/{len(results)} 通过")
    for name, c, detail in results:
        if not c:
            print(f"  FAIL: {name} {detail}")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
