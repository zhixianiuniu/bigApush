# -*- coding: utf-8 -*-
import json, time, urllib.request, urllib.parse, re, os, sys
from datetime import datetime, timedelta

FEISHU_WEBHOOK = os.environ["FEISHU_WEBHOOK"]
FEISHU_SECRET = os.environ.get("FEISHU_SECRET", "")

KEYWORDS = {
    "P·政策监管": ["证监会", "基金投顾", "投资咨询", "投资顾问", "网络营销", "基金销售",
                "管理办法", "执业规范", "适当性"],
    "E·经济财富": ["财富管理", "券商", "证券公司", "证券行业", "营业部", "佣金", "费率",
                "个人养老金", "理财"],
    "S·社会投资者": ["投资者保护", "新开户", "投资者教育", "新中产"],
    "T·技术AI": ["智能投顾", "智能投研", "大模型", "AI投顾", "AI理财", "AI客服",
               "人工智能", "金融科技"],
}

SCHOLAR_QUERIES = [
    "robo-advisor marketing",
    "intelligent investment advisory personalization",
    "securities wealth management digital marketing",
]

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

def fetch_scholar(queries, per=8):
    """Semantic Scholar 免费API, 无需注册; 匿名限流~1次/秒"""
    out, seen = [], set()
    for q in queries:
        url = ("https://api.semanticscholar.org/graph/v1/paper/search"
               "?query=%s&limit=%d&fields=title,abstract,url,year"
               % (urllib.parse.quote(q), per))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "paper-intel/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8"))
            for p in data.get("data", []):
                t = (p.get("title") or "").strip()
                if t and t not in seen and (p.get("year") or 0) >= 2021:
                    seen.add(t)
                    out.append(p)
        except Exception as e:
            print("scholar query=%s 失败: %s" % (q, e))
        time.sleep(1.5)
    return out

def match_group(title):
    for grp, keys in KEYWORDS.items():
        if any(k in title for k in keys):
            return grp
    return None

def main():
    # --- 中文动态 ---
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
    order = {"P·政策监管": 0, "E·经济财富": 1, "S·社会投资者": 2, "T·技术AI": 3}
    hits.sort(key=lambda h: (order.get(h["grp"], 9), h["time"]))
    lines, used = [], {}
    for h in hits:
        if used.get(h["grp"], 0) >= 5 or len(lines) >= 12:
            continue
        used[h["grp"]] = used.get(h["grp"], 0) + 1
        lines.append("• [%s] %s" % (h["time"], h["title"]))
    if not lines:
        lines.append("• 本周未捕获到关键词相关动态")

    # --- 英文文献 ---
    papers = fetch_scholar(SCHOLAR_QUERIES)
    papers.sort(key=lambda p: p.get("year") or 0, reverse=True)
    paper_lines = []
    for p in papers[:5]:
        abs_txt = re.sub(r"\s+", " ", p.get("abstract") or "").strip()
        if len(abs_txt) > 90:
            abs_txt = abs_txt[:90] + "…"
        paper_lines.append("• %s (%s)\n  %s\n  %s"
                           % (p["title"], p.get("year") or "?",
                              abs_txt or "无摘要", p.get("url") or ""))
    if not paper_lines:
        paper_lines.append("• 本周无新收录")

    today = datetime.now().strftime("%Y-%m-%d")
    content = ("【选股信号】📚 论文情报 (近7天 %s)\n\n"
               "🇨🇳 中文动态\n" + "\n".join(lines)
               + "\n\n📖 英文文献 (Semantic Scholar, 近5年)\n" + "\n".join(paper_lines)
               + "\n\n💡 本周知网检索式:\n主题=智能投顾 AND 主题=精准营销 AND 年>=2024"
               + "\n\n来源: 新浪财经 + Semantic Scholar | 存素材时核对原文日期")
    from daily_news import send_feishu
    ok = send_feishu(content)
    print("推送结果:", ok)
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
