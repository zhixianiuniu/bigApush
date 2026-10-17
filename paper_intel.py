# -*- coding: utf-8 -*-
import json, time, urllib.request, re, os, sys
from datetime import datetime, timedelta

FEISHU_WEBHOOK = os.environ["FEISHU_WEBHOOK"]
FEISHU_SECRET = os.environ.get("FEISHU_SECRET", "")

KEYWORDS = {
    "P·政策监管": ["证监会", "基金投顾", "投资咨询", "投顾", "网络营销", "管理办法",
                "证券基金", "执业规范", "适当性"],
    "E·经济财富": ["财富管理", "居民存款", "理财", "佣金", "费率", "个人养老金"],
    "S·社会投资者": ["投资者保护", "新开户", "90后", "Z世代", "投资者教育"],
    "T·技术AI": ["智能投顾", "大模型", "AI", "人工智能", "金融科技", "算法",
               "数字员工", "智能客服"],
}

def fetch_roll(lid, num=50, pages=3):
    out = []
    for p in range(1, pages + 1):
        url = ("https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=%s"
               "&k=&num=%d&page=%d" % (lid, num, p))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0",
                                                       "Referer": "https://finance.sina.com.cn"})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read().decode("utf-8"))
            for item in data.get("result", {}).get("data", []):
                if item.get("title"):
                    out.append(item)
        except Exception as e:
            print("feed lid=%s page=%d 失败: %s" % (lid, p, e))
        time.sleep(1)
    return out

def match_group(title):
    for grp, keys in KEYWORDS.items():
        if any(k in title for k in keys):
            return grp
    return None

def main():
    week_ago = (datetime.now() - timedelta(days=7)).timestamp()
    seen, hits = set(), []
    for lid in ("2516",):
        for it in fetch_roll(lid):
            t = it.get("ctime")
            try:
                if t and float(t) < week_ago:
                    continue
            except (TypeError, ValueError):
                pass
            title = re.sub(r"<[^>]+>", "", it["title"]).strip()
            if title in seen or len(title) < 8:
                continue
            seen.add(title)
            grp = match_group(title)
            if grp:
                hits.append({"grp": grp, "title": title,
                             "time": time.strftime("%m-%d", time.localtime(float(t))) if t else ""})
    lines, used = [], {}
    for h in hits:
        if used.get(h["grp"], 0) >= 5 or len(lines) >= 15:
            continue
        used[h["grp"]] = used.get(h["grp"], 0) + 1
        lines.append("• [%s] %s" % (h["time"], h["title"]))
    if not lines:
        lines.append("• 本周未捕获到关键词相关动态(可调宽 KEYWORDS 再试)")
    today = datetime.now().strftime("%Y-%m-%d")
    content = ("【选股信号】📚 论文情报 (近7天 %s)\n\n" % today
               + "\n".join(lines)
               + "\n\n来源: 新浪财经 | 存素材时核对原文日期")
    from daily_news import send_feishu
    ok = send_feishu(FEISHU_WEBHOOK, FEISHU_SECRET, "论文情报", content)
    print("推送结果:", ok)
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
