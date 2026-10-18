# -*- coding: utf-8 -*-
# 微信读书: 今日划线书摘 -> 飞书书房群
import json, os, time, urllib.request
from datetime import datetime

COOKIE = os.environ["WEREAD_COOKIE"]
WEBHOOK = os.environ["FEISHU_WEBHOOK_BOOK"]
BASE = "https://weread.qq.com/web"
H = {"Cookie": COOKIE, "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

def get(path):
    req = urllib.request.Request(BASE + path, headers=H)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))

def send(text):
    body = json.dumps({"msg_type": "text", "content": {"text": text}}).encode()
    req = urllib.request.Request(WEBHOOK, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status == 200

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        shelf = get("/shelf")
    except Exception as e:
        send("📚 书房: 微信读书Cookie可能已过期, 请重新抓取\n(%s)" % e)
        return
    books = shelf.get("books") or []
    if not books:
        send("📚 书房: 书架为空或Cookie失效, 请检查")
        return
    lines = []
    for b in books[:20]:
        bid = b.get("bookId")
        title = b.get("title")
        try:
            data = get("/book/bookmarklist?bookId=%s" % bid)
        except Exception:
            continue
        marks = [m for m in (data.get("updated") or [])
                 if time.strftime("%Y-%m-%d", time.localtime(m.get("createTime", 0))) == today
                 and (m.get("markText") or "").strip()]
        for m in marks[:5]:
            lines.append("「%s」\n💭 %s" % (title, m["markText"].strip()))
    if lines:
        text = "📚 今日书摘 (%s)\n\n" % today + "\n\n───\n\n".join(lines[:10])
    else:
        text = "📚 今日书摘 (%s)\n今天没有新划线, 去读两页吧" % today
    ok = send(text)
    print("推送结果:", ok, "| 书摘条数:", len(lines))

if __name__ == "__main__":
    main()
