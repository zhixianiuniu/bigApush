# -*- coding: utf-8 -*-
# 淘股吧博客监控: 行鱼复盘更新 -> 飞书秒推
import json, re, os, urllib.request

FEISHU_WEBHOOK = os.environ["FEISHU_WEBHOOK"]
STATE_FILE = "tgb_state.json"
BLOG_URL = "https://m.tgb.cn/blog/563404"
BLOG_NAME = "行鱼复盘"

def get_latest():
    req = urllib.request.Request(BLOG_URL, headers={
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode("utf-8")
    m = re.findall(r'<a class="contentTitle" href="(/a/[A-Za-z0-9]+)">([^<]+)</a>', html)
    return [(aid, title.strip()) for aid, title in m[:5]]

def send_feishu(text):
    body = json.dumps({"msg_type": "text", "content": {"text": text}}).encode()
    req = urllib.request.Request(FEISHU_WEBHOOK, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status == 200

def main():
    try:
        latest = get_latest()
    except Exception as e:
        print("抓取失败: %s" % e)
        return
    if not latest:
        print("未解析到文章, 页面结构可能变了")
        return
    state = {}
    if os.path.exists(STATE_FILE):
        try:
            state = json.load(open(STATE_FILE))
        except Exception:
            pass
    latest_id = latest[0][0]
    if not state.get("initialized"):
        state = {"initialized": True, "last_id": latest_id}
        json.dump(state, open(STATE_FILE, "w"))
        print("首次运行: 基线=%s %s(不推送)" % (latest_id, latest[0][1]))
        return
    new_items = [(aid, t) for aid, t in latest if aid != state.get("last_id")][:3]
    if not new_items:
        print("无更新")
        return
    msgs = ["🔥 %s\nhttps://www.tgb.cn%s" % (t, aid) for aid, t in reversed(new_items)]
    ok = send_feishu("【选股信号】📝 %s更新 (%d篇)\n\n" % (BLOG_NAME, len(msgs)) + "\n\n".join(msgs))
    print("推送 %d 篇, 结果: %s" % (len(msgs), ok))
    state["last_id"] = latest_id
    json.dump(state, open(STATE_FILE, "w"))

if __name__ == "__main__":
    main()
