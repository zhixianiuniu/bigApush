# -*- coding: utf-8 -*-
import json, time, urllib.request, urllib.parse, re, os, sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

FEISHU_WEBHOOK = os.environ["FEISHU_WEBHOOK"]
AMINER_API_KEY = os.environ.get("AMINER_API_KEY", "")

KEYWORDS = {
    "P·政策监管": ["证监会", "基金投顾", "投资咨询", "投资顾问", "网络营销", "基金销售",
                "管理办法", "执业规范", "适当性"],
    "E·经济财富": ["财富管理", "券商", "证券公司", "证券行业", "营业部", "佣金", "费率",
                "个人养老金", "理财"],
    "S·社会投资者": ["投资者保护", "新开户", "投资者教育", "新中产"],
    "T·技术AI": ["智能投顾", "智能投研", "大模型", "AI投顾", "AI理财", "AI客服",
               "人工智能", "金融科技"],
}

AMINER_QUERIES = ["智能投顾", "基金投顾", "精准营销 证券", "智能营销 财富管理"]

ARXIV_QUERIES = [
    'all:"robo-advisor" OR all:"robo advisor"',
    'all:"intelligent investment advisory" OR all:"automated investment advice"',
    'all:"digital wealth management" OR all:"online investment recommendation"',
]

NEWS_SOURCES = [
    ("GoogleNews", "https://news.google.com/rss/search?q=%22wealth%20management%22%20AI%20OR%20robo-advisor&hl=en-US&ceid=US:en"),
    ("MarketWatch", "http://feeds.marketwatch.com/marketwatch/topstories/"),
    ("TIME", "https://feeds.feedburner.com/time/topstories"),
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("FT", "https://www.ft.com/rss/home"),
]

TITLE_KEYS = ["robo", "wealth management", "advis", "investment", "asset management",
              "trading", "hedge fund", "artificial intelligence", " etf", "broker"]

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

def fetch_aminer(queries, per=5):
    """AMiner免费接口: GET paper/search; 需控制台生成token且账户已充值激活"""
    if not AMINER_API_KEY:
        return None  # 未配置, 上层降级提示
    out, seen = [], set()
    for q in queries:
        url = ("https://datacenter.aminer.cn/gateway/open_platform/api/paper/search"
               "?page=1&size=%d&title=%s" % (per, urllib.parse.quote(q)))
        try:
            req = urllib.request.Request(url, headers={
                "Authorization": AMINER_API_KEY, "X-Platform": "openclaw"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8"))
            for p in data.get("data", []) or []:
                pid = p.get("id") or p.get("_id") or ""
                t = (p.get("title_zh") or p.get("title") or "").strip()
                if not t or t in seen:
                    continue
                seen.add(t)
                try:
                    year = int(p.get("year") or 0)
                except (TypeError, ValueError):
                    year = 0
                venue = (p.get("venue") or {}).get("name") if isinstance(p.get("venue"), dict) else (p.get("venue") or "")
                out.append({"title": t, "year": year, "venue": venue or "",
                            "url": "https://www.aminer.cn/pub/" + pid if pid else ""})
        except Exception as e:
            print("aminer query=%s 失败: %s" % (q, e))
        time.sleep(1)
    out.sort(key=lambda x: x["year"], reverse=True)
    return out

def fetch_arxiv(queries, per=8):
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out, seen = [], set()
    for q in queries:
        url = ("https://export.arxiv.org/api/query?search_query=%s&start=0&max_results=%d"
               "&sortBy=submittedDate&sortOrder=descending"
               % (urllib.parse.quote(q), per))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "paper-intel/1.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                root = ET.fromstring(r.read())
            for e in root.findall("a:entry", ns):
                t = re.sub(r"\s+", " ", e.findtext("a:title", "", ns)).strip()
                if not t or t in seen:
                    continue
                pub = e.findtext("a:published", "", ns)
                year = int(pub[:4]) if pub[:4].isdigit() else 0
                if year < 2021:
                    continue
                seen.add(t)
                summ = re.sub(r"\s+", " ", e.findtext("a:summary", "", ns)).strip()
                link = ""
                for l in e.findall("a:link", ns):
                    if l.get("rel") == "alternate":
                        link = l.get("href", "")
                out.append({"title": t, "year": year, "abs": summ, "url": link})
        except Exception as ex:
            print("arxiv query 失败: %s" % ex)
        time.sleep(3)
    return out

def fetch_en_news(per_source=3):
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out, seen = [], set()
    for src_name, url in NEWS_SOURCES:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                root = ET.fromstring(r.read())
            items = root.findall(".//item") or root.findall(".//a:entry", ns)
            cnt = 0
            for it in items:
                t_el = it.findtext("title") or it.findtext("a:title", "", ns) or ""
                t = re.sub(r"<!\[CDATA\[|\]\]>", "", t_el).strip()
                if not t or t in seen or len(t) < 15:
                    continue
                if not any(k in t.lower() for k in TITLE_KEYS):
                    continue
                seen.add(t)
                link = (it.findtext("link") or "").strip()
                if not link:
                    l = it.find("a:link", ns)
                    if l is not None:
                        link = l.get("href", "")
                out.append("• [%s] %s\n  %s" % (src_name, t, link))
                cnt += 1
                if cnt >= per_source:
                    break
        except Exception as e:
            print("en news %s 失败: %s" % (src_name, e))
        time.sleep(1)
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

    # --- 中文文献 (AMiner) ---
    cn_papers = fetch_aminer(AMINER_QUERIES)
    if cn_papers is None:
        cn_lines = ["• 未配置 AMINER_API_KEY(去 open.aminer.cn 控制台生成, 存 secrets)"]
    elif not cn_papers:
        cn_lines = ["• AMiner 无新命中(或账户未充值激活, 控制台充任意金额即可)"]
    else:
        cn_lines = []
        for p in cn_papers[:4]:
            cn_lines.append("• %s (%s, %s)\n  %s" % (p["title"], p["year"] or "?", p["venue"], p["url"]))

    # --- 英文文献 (arXiv) ---
    papers = fetch_arxiv(ARXIV_QUERIES)
    papers.sort(key=lambda p: p["year"], reverse=True)
    paper_lines = []
    for p in papers[:4]:
        abs_txt = p["abs"]
        if len(abs_txt) > 90:
            abs_txt = abs_txt[:90] + "…"
        paper_lines.append("• %s (%s)\n  %s\n  %s"
                           % (p["title"], p["year"], abs_txt or "无摘要", p["url"]))
    if not paper_lines:
        paper_lines.append("• arXiv 本周无相关新收录")

    # --- 英文财经杂志 ---
    en_lines = fetch_en_news()
    if not en_lines:
        en_lines.append("• 英文源暂时全部异常(下周自动重试)")

    today = datetime.now().strftime("%Y-%m-%d")
    content = ("【选股信号】📚 论文情报 (近7天 " + today + ")\n\n"
               "🇨🇳 中文动态\n" + "\n".join(lines)
               + "\n\n📚 中文文献 (AMiner)\n" + "\n".join(cn_lines)
               + "\n\n📖 英文文献 (arXiv)\n" + "\n".join(paper_lines)
               + "\n\n🌍 英文财经 (杂志/通讯社)\n" + "\n".join(en_lines)
               + "\n\n💡 本周知网检索式:\n主题=智能投顾 AND 主题=精准营销 AND 年>=2024"
               + "\n\n来源: 新浪 + AMiner + arXiv + GoogleNews 等 | 存素材时核对原文日期")
    from daily_news import send_feishu
    ok = send_feishu(content)
    print("推送结果:", ok)
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
