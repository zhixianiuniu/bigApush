# -*- coding: utf-8 -*-
# 书房推送 v4: 每天北京09:00 诗词+金句+新书速递, 周日加周榜 -> 飞书房群
import json, os, re, urllib.request
from datetime import datetime, timedelta

WEBHOOK = os.environ["FEISHU_WEBHOOK_BOOK"]
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"

def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")

def send(text):
    body = json.dumps({"msg_type": "text", "content": {"text": text}}).encode()
    req = urllib.request.Request(WEBHOOK, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status == 200

def daily_quote():
    try:
        html = http_get("https://www.gushiwen.cn/")
    except Exception:
        return None
    m = re.search(r'<textarea[^>]*id="txtare\d+"[^>]*>([^<]{20,})</textarea>', html)
    if m:
        content = m.group(1)
        poem, _, rest = content.partition("——")
        src = rest.split("http")[0].strip()
        poem = poem.strip()
        if len(poem) > 400:
            poem = poem[:400] + "…"
        return "📖 %s\n—— %s" % (poem, src)
    return None

def hitokoto():
    try:
        d = json.loads(http_get("https://v1.hitokoto.cn/?c=d&c=i&c=k", timeout=10))
        who = d.get("from_who") or ""
        frm = d.get("from") or ""
        src = " ".join(x for x in [who, "《%s》" % frm if frm else ""] if x)
        return "💬 %s%s" % (d.get("hitokoto", "").strip(), ("\n—— " + src) if src else "")
    except Exception:
        return None

def latest_books():
    try:
        html = http_get("https://book.douban.com/latest")
    except Exception:
        return None
    items = re.findall(r'href="(https://book.douban.com/subject/\d+/)"[^>]*>([^<]+)</a>', html)
    seen, lines = set(), []
    for link, t in items:
        t = t.strip()
        if t and t not in seen and len(t) > 1:
            seen.add(t)
            lines.append("• %s\n  %s" % (t, link))
        if len(lines) >= 5:
            break
    if lines:
        return "📕 豆瓣新书速递\n\n" + "\n\n".join(lines)
    return None

def douban_chart():
    try:
        html = http_get("https://book.douban.com/chart")
    except Exception:
        return None
    items = re.findall(r'href="(https://book.douban.com/subject/\d+/)"[^>]*>([^<]+)</a>', html)
    seen, lines = set(), []
    for link, t in items:
        t = t.strip()
        if t and t not in seen and len(t) > 1:
            seen.add(t)
            lines.append("• %s\n  %s" % (t, link))
        if len(lines) >= 10:
            break
    if lines:
        return "📚 豆瓣周榜 Top10\n\n" + "\n\n".join(lines)
    return None

def main():
    utc = datetime.utcnow()
    bj = utc + timedelta(hours=8)
    sections = []
    for fn in (daily_quote, hitokoto, latest_books):
        r = fn()
        if r: sections.append(r)
    if utc.weekday() == 6:
        c = douban_chart()
        if c: sections.append(c)
    if not sections:
        sections.append("📖 (内容暂不可用)")
    text = "【选股信号】书房 · %s\n\n" % bj.strftime("%Y-%m-%d") + "\n\n".join(sections)
    ok = send(text)
    print("推送:", ok)

if __name__ == "__main__":
    main()
