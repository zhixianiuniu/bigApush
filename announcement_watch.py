# -*- coding: utf-8 -*-
# 持仓公告监控: 巨潮轮询 -> 新公告推飞书 -> 状态回写去重
import json, time, urllib.request, urllib.parse, os
from datetime import datetime, timedelta

FEISHU_WEBHOOK = os.environ["FEISHU_WEBHOOK"]
STATE_FILE = "announcements_state.json"

STOCKS = [
    ("002266", "szse", "浙富控股"),
    ("601991", "sse", "大唐发电"),
]

def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def http_post(url, payload, timeout=20):
    req = urllib.request.Request(url, data=payload.encode(),
        headers={"User-Agent": "Mozilla/5.0",
                 "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def get_org_id(code):
    try:
        data = http_get("http://www.cninfo.com.cn/new/information/topSearch/query?keyWord=%s&maxNum=10" % code)
        for item in data if isinstance(data, list) else []:
            if item.get("code") == code:
                return item.get("orgId")
    except Exception as e:
        print("orgId 查询失败 %s: %s" % (code, e))
    return None

def fetch_announcements(code, org_id, column):
    today = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    payload = {
        "pageNum": "1", "pageSize": "20", "column": column, "tabName": "fulltext",
        "plate": "", "stock": "%s,%s" % (code, org_id), "searchkey": "", "secid": "",
        "category": "", "trade": "", "seDate": "%s~%s" % (start, today),
        "sortName": "", "sortType": "", "isHLtitle": "true",
    }
    try:
        data = http_post("http://www.cninfo.com.cn/new/hisAnnouncement/query",
                         urllib.parse.urlencode(payload))
        return data.get("announcements") or []
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
    for code, column, name in STOCKS:
        org_id = get_org_id(code)
        if not org_id:
            print("拿不到 orgId: %s" % code)
            continue
        seen = set(state["seen"].get(code, []))
        for a in fetch_announcements(code, org_id, column):
            aid = str(a.get("announcementId"))
            if aid in seen:
                continue
            seen.add(aid)
            ts = a.get("announcementTime") or 0
            tstr = time.strftime("%m-%d %H:%M", time.localtime(ts / 1000)) if ts else ""
            title = (a.get("announcementTitle") or "").replace("<em>", "").replace("</em>", "")
            link = "https://static.cninfo.com.cn/" + (a.get("adjunctUrl") or "")
            new_items.append((ts, name, tstr, title, link))
        state["seen"][code] = list(seen)[-80:]
    if not state["initialized"]:
        print("首次运行: 建立基线(不推送), 下次起只推增量")
        state["initialized"] = True
    elif not new_items:
        print("无新公告")
    else:
        new_items.sort()
        msgs = ["🔔 %s | %s\n%s\n%s" % (name, tstr, title, link)
                for ts, name, tstr, title, link in new_items]
        ok = send_feishu("【选股信号】📢 持仓公告 (%d条新)\n\n" % len(msgs) + "\n\n".join(msgs))
        print("推送 %d 条新公告, 结果: %s" % (len(msgs), ok))
    json.dump(state, open(STATE_FILE, "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
