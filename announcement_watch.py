# -*- coding: utf-8 -*-
# 持仓公告监控: 东方财富公告接口 -> 新公告推飞书 -> 状态回写去重
import json, time, urllib.request, os
from datetime import datetime

FEISHU_WEBHOOK = os.environ["FEISHU_WEBHOOK"]
STATE_FILE = "announcements_state.json"

STOCKS = [
    ("002266", "浙富控股"),
    ("601991", "大唐发电"),
    ("600690", "海尔智家"),
]

def fetch_announcements(code):
    url = ("https://np-anotice-stock.eastmoney.com/api/security/ann"
           "?sr=-1&page_size=10&page_index=1&ann_type=A&client_source=web&stock_list=%s" % code)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        return (data.get("data") or {}).get("list") or []
    except Exception as e:
        print("公告查询失败 %s: %s" % (code, e))
        return []

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            return json.load(open(STATE_FILE))
        except Exception:
            pass
    return {"seen": {}, "initialized": False}

def send_feishu(text):
    body = json.dumps({"msg_type": "text", "content": {"text": text}}).encode()
    req = urllib.request.Request(FEISHU_WEBHOOK, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status == 200

def main():
    state = load_state()
    new_items = []
    for code, name in STOCKS:
        seen = set(state["seen"].get(code, []))
        for a in fetch_announcements(code):
            aid = str(a.get("art_code") or "")
            if not aid or aid in seen:
                continue
            seen.add(aid)
            date_str = (a.get("notice_date") or "")[:10]
            title = (a.get("title") or "").strip()
            link = "https://data.eastmoney.com/notices/detail/%s/%s.html" % (code, aid)
            new_items.append((date_str, name, title, link))
        state["seen"][code] = list(seen)[-60:]
    if not state["initialized"]:
        print("首次运行: 建立基线(不推送), 下次起只推增量")
        state["initialized"] = True
    elif not new_items:
        print("无新公告")
    else:
        try:
            new_items.sort()
            msgs = ["🔔 %s | %s\n%s\n%s" % (name, d, t, link)
                    for d, name, t, link in new_items]
            ok = send_feishu("【选股信号】📢 持仓公告 (%d条新)\n\n" % len(msgs) + "\n\n".join(msgs))
            print("推送 %d 条新公告, 结果: %s" % (len(msgs), ok))
        except Exception as e:
            print("推送失败(不影响状态保存): %s" % e)
    json.dump(state, open(STATE_FILE, "w"), ensure_ascii=False, indent=1)
    print("状态已保存")

if __name__ == "__main__":
    main()
