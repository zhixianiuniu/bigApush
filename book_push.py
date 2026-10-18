# -*- coding: utf-8 -*-
# 书房推送: 每日诗词(古诗文网) + 周日豆瓣周榜 -> 飞书房群 (零登录, 永不过期)
import json, os, re, urllib.request
from datetime import datetime

WEBHOOK = os.environ["FEISHU_WEBHOOK_BOOK"]
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"

def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8")

def send(text):
    body = json.dumps({"msg_type": "text", "content": {"text": text}}).encode()
    req = urllib.request.Request(WEBHOOK, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status == 200

def daily_quote():
    try:
        html = http_get("https://www.gushiwen.cn/")
    except Exception as e:
        return None, str(e)
    pairs = re.findall(r'<a[^>]*>([^<]{8,90})</a>\s*<a[^>]*>([^<]{2,50}《[^<]{2,40})</a>', html)
    if pairs:
        q, src = pairs[0]
        return "📖 %s\n—— %s" % (q.strip(), src.strip()), None
    return None, "未解析到推荐句"

def douban_chart():
    try:
        html = http_get("https://book.douban.com/chart")
    except Exception as e:
        return None, str(e)
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
        return "📚 豆瓣周榜 Top10\n\n" + "\n\n".join(lines), None
    return None, "未解析到榜单"

def main():
    today = datetime.now()
    sections = []
    q, err = daily_quote()
    sections.append(q or "📖 (每日推荐抓取失败: %s)" % err)
    if today.weekday() == 6:
        c, err = douban_chart()
        sections.append(c or "📚 (豆瓣榜抓取失败: %s)" % err)
    text = "【选股信号】书房 · %s\n\n" % today.strftime("%Y-%m-%d") + "\n\n".join(sections)
    ok = send(text)
    print("推送:", ok)

if __name__ == "__main__":
    main()
