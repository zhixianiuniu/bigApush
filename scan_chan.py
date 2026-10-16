#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scan_chan.py — 缠论盘后扫描（分型/笔/中枢/背驰）
规则: 统一放 ~/monitor/；系统 python3 零依赖(urllib+腾讯fqkline接口)可跑内置引擎；
      chan.py 引擎走独立 venv(需 Python3.11+)，缺省 auto=能 import 就用，失败自动降级内置。
日志: ~/monitor/logs/scan_chan.log / chan_state.json(增量事件判定)
"""
import json, os, sys, time, datetime, traceback
import urllib.request

# ===================== WATCHLIST 区（自填） =====================
# 格式: ("sz002266", "浙富控股", "备注")   代码可只写6位数字，脚本自动补 sh/sz/bj
WATCHLIST = [
    ("002266", "浙富控股", ""),
    ("600690", "海尔智家", ""),
    ("601991", "大唐发电", ""),
    ("000858", "五粮液",   ""),
    ("301197", "工大科雅", ""),
    ("300758", "七彩化学", ""),
    ("002714", "牧原股份", ""),
    ("600584", "长电科技", ""),
    ("sh000001", "上证指数", ""),
    ("sh000905", "中证500", ""),
]
ENGINE   = os.environ.get("SCAN_ENGINE", "auto")   # auto | builtin | chanpy
CHANPY_DIR = os.path.expanduser("~/monitor/chan.py")
LOOKBACK = 260             # 拉取日线根数
ZS_MIN_WIDTH = 0.10        # 中枢最小宽度(元)，过滤分分钱假中枢
DIVERGE_RATIO = 0.8        # 背驰: 后段面积 <= 前段*0.8
HOME = os.path.expanduser(os.environ.get("SCAN_HOME", "~/monitor"))
LOG_DIR = os.path.join(HOME, "logs")
STATE_FILE = os.environ.get("STATE_FILE", os.path.join(LOG_DIR, "chan_state.json"))
os.makedirs(LOG_DIR, exist_ok=True)

def _load_webhook():
    """读取优先级: 环境变量 FEISHU_WEBHOOK(GitHub Secrets) > 本地 chan_config.json(不进仓库) > 空"""
    if os.environ.get("FEISHU_WEBHOOK"):
        return os.environ["FEISHU_WEBHOOK"]
    try:
        with open(os.path.join(HOME, "chan_config.json"), encoding="utf-8") as f:
            return json.load(f).get("feishu_webhook", "")
    except Exception:
        return ""
FEISHU_WEBHOOK = _load_webhook()

def log(msg):
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    with open(os.path.join(LOG_DIR, "scan_chan.log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")

def norm_code(c):
    c = c.strip().lower()
    if len(c) == 6 and c.isdigit():
        if c[0] in "56": return "sh" + c
        if c[0] in "034": return "sz" + c
        if c[0] in "48": return "bj" + c
    return c

# ---------------- 取数: 腾讯前复权日线 ----------------
def fetch_kline(code, n=LOOKBACK):
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,{n},qfq"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        j = json.loads(r.read().decode("utf-8"))
    d = j["data"][code]
    rows = d.get("qfqday") or d.get("day") or []
    out = []
    for row in rows:
        # 腾讯返回: [date, open, close, high, low, volume] —— 注意 close 在 high 前
        out.append({"date": row[0], "open": float(row[1]), "close": float(row[2]),
                    "high": float(row[3]), "low": float(row[4]), "volume": float(row[5])})
    return out

# ---------------- 内置缠论引擎（已用 002266 真实数据回测） ----------------
def ema(vals, n):
    k = 2.0 / (n + 1); out = []; e = vals[0]
    for v in vals:
        e = v * k + e * (1 - k); out.append(e)
    return out

def merge_bars(bars):
    mb = []
    for i, b in enumerate(bars):
        h, l = b["high"], b["low"]
        if not mb:
            mb.append({"h": h, "l": l, "dir": 1, "i0": i, "i1": i}); continue
        p = mb[-1]
        if (h <= p["h"] and l >= p["l"]) or (h >= p["h"] and l <= p["l"]):
            if p["dir"] == 1: p["h"], p["l"] = max(p["h"], h), max(p["l"], l)
            else:             p["h"], p["l"] = min(p["h"], h), min(p["l"], l)
            p["i1"] = i
            if h > p["h"] and l > p["l"]: p["dir"] = 1
            elif h < p["h"] and l < p["l"]: p["dir"] = -1
        else:
            mb.append({"h": h, "l": l, "dir": 1 if h > p["h"] else -1, "i0": i, "i1": i})
    return mb

def find_fractals(mb):
    fx = []
    for i in range(1, len(mb) - 1):
        if mb[i]["h"] > mb[i-1]["h"] and mb[i]["h"] > mb[i+1]["h"]:
            fx.append([i, "top", mb[i]["h"]])
        elif mb[i]["l"] < mb[i-1]["l"] and mb[i]["l"] < mb[i+1]["l"]:
            fx.append([i, "bot", mb[i]["l"]])
    return fx

def alternate(fx):
    out = []
    for f in fx:
        if out and f[1] == out[-1][1]:
            if (f[1] == "top" and f[2] >= out[-1][2]) or (f[1] == "bot" and f[2] <= out[-1][2]):
                out[-1] = f
        else:
            out.append(f)
    return out

def build_strokes(fx0, min_gap=4):
    fx = alternate(fx0); changed = True
    while changed:
        changed = False
        for i in range(len(fx) - 1):
            if fx[i+1][0] - fx[i][0] < min_gap:
                s_keep_i   = abs(fx[i][2] - fx[i-1][2]) if i > 0 else float("inf")
                s_keep_ip1 = abs(fx[i+2][2] - fx[i+1][2]) if i + 2 < len(fx) else float("inf")
                if s_keep_i >= s_keep_ip1:
                    del fx[i+1]
                else:
                    del fx[i]
                changed = True; break
    return alternate(fx)

def find_zhongshu(strokes, min_width=ZS_MIN_WIDTH):
    out = []; j = 0
    while j <= len(strokes) - 3:
        zg = min(max(s["f0"][2], s["f1"][2]) for s in strokes[j:j+3])
        zd = max(min(s["f0"][2], s["f1"][2]) for s in strokes[j:j+3])
        if zg - zd >= min_width:
            end = j + 2; m = end + 1
            while m < len(strokes):
                h = max(strokes[m]["f0"][2], strokes[m]["f1"][2])
                l = min(strokes[m]["f0"][2], strokes[m]["f1"][2])
                if l <= zg and h >= zd: end = m; m += 1
                else: break
            out.append({"start": j, "end": end, "zg": zg, "zd": zd})
            j = end + 1
        else:
            j += 1
    return out

def analyze(bars):
    """输入: [{'date','open','close','high','low','volume'}...] 返回结构 dict"""
    closes = [b["close"] for b in bars]
    e12, e26 = ema(closes, 12), ema(closes, 26)
    dif = [a - b for a, b in zip(e12, e26)]
    dea = ema(dif, 9)
    macd = [2 * (a - b) for a, b in zip(dif, dea)]
    mb = merge_bars(bars)
    fx = build_strokes(find_fractals(mb))
    strokes = [{"f0": fx[i], "f1": fx[i+1]} for i in range(len(fx) - 1)]
    zs = find_zhongshu(strokes)
    def bi_i(f): return mb[f[0]]["i1"]
    # 背驰 + 买卖点
    buy1 = sell1 = buy2 = None; divs = []
    downs = [s for s in strokes if s["f0"][1] == "top"]
    ups   = [s for s in strokes if s["f0"][1] == "bot"]
    for a_, b_ in zip(downs, downs[1:]):
        i1, i2 = bi_i(a_["f1"]), bi_i(b_["f1"])
        ar1 = sum(v for v in macd[bi_i(a_["f0"]):i1+1] if v < 0)
        ar2 = sum(v for v in macd[bi_i(b_["f0"]):i2+1] if v < 0)
        if b_["f1"][2] <= a_["f1"][2] and abs(ar1) > 0.05 and abs(ar2) <= abs(ar1) * DIVERGE_RATIO:
            buy1 = {"date": bars[i2]["date"], "price": b_["f1"][2], "area1": round(ar1,2), "area2": round(ar2,2)}
            divs.append({"type": "底背驰(一买)", **{k: buy1[k] for k in ("date","price")}})
            # 二买: 一买后下一个底分型不创新低
            ti = fx.index(b_["f1"])
            if ti + 2 < len(fx) and fx[ti+2][1] == "bot" and fx[ti+2][2] > b_["f1"][2] * 1.005:
                buy2 = {"date": bars[mb[fx[ti+2][0]]["i1"]]["date"], "price": fx[ti+2][2]}
                divs.append({"type": "二买", **{k: buy2[k] for k in ("date","price")}})
    for a_, b_ in zip(ups, ups[1:]):
        ar1 = sum(v for v in macd[bi_i(a_["f0"]):bi_i(a_["f1"])+1] if v > 0)
        ar2 = sum(v for v in macd[bi_i(b_["f0"]):bi_i(b_["f1"])+1] if v > 0)
        if b_["f1"][2] >= a_["f1"][2] and ar1 > 0.05 and ar2 <= ar1 * DIVERGE_RATIO:
            sell1 = {"date": bars[bi_i(b_["f1"])]["date"], "price": b_["f1"][2]}
            divs.append({"type": "顶背驰(卖点)", **{k: sell1[k] for k in ("date","price")}})
    # 当前状态
    last = bars[-1]; cur_zs = zs[-1] if zs else None
    pos = "无中枢"
    if cur_zs:
        zd, zg = cur_zs["zd"], cur_zs["zg"]
        if last["close"] > zg: pos = f"中枢上方(>{zg:.2f})"
        elif last["close"] < zd: pos = f"跌破中枢下沿{zd:.2f},向下离开"
        elif last["close"] > zg * 0.99: pos = "中枢上沿附近"
        elif last["close"] < zd * 1.01: pos = "中枢下沿附近"
        else: pos = "中枢内部"
    break_buy1 = bool(buy1 and last["close"] < buy1["price"] * 0.995)
    tops = [f[2] for f in fx if f[1] == "top"]
    weak_tops = len(tops) >= 3 and tops[-1] < tops[-2] < tops[-3]
    return {"last_date": last["date"], "close": last["close"], "fx": fx, "mb": mb,
            "n_stroke": len(strokes), "zhongshu": zs, "buy1": buy1, "buy2": buy2, "sell1": sell1,
            "divs": divs, "pos": pos, "break_buy1": break_buy1, "weak_tops": weak_tops,
            "last_fractal": {"date": bars[bi_i(fx[-1])]["date"], "type": fx[-1][1], "price": fx[-1][2]} if fx else None}

# ---------------- chan.py 引擎（best-effort，失败降级） ----------------
def analyze_chanpy(code):
    sys.path.insert(0, CHANPY_DIR)
    from Chan import CChan
    from ChanConfig import CChanConfig
    from Common.CEnum import DATA_SRC, AUTYPE, KL_TYPE
    chan = CChan(code=code[-6:], begin_time="2025-01-01", data_src=DATA_SRC.AKSHARE,
                 lv_list=[KL_TYPE.K_DAY], config=CChanConfig({}), autype=AUTYPE.QFQ)
    bsp = list(chan.get_bsp())
    return {"engine": "chanpy", "bsp_count": len(bsp),
            "bsp": [{"date": str(b.klu.time), "type": int(b.type2)} for b in bsp[-5:]]}

# ---------------- 飞书推送 ----------------
def push_feishu(text):
    if not FEISHU_WEBHOOK: return
    try:
        body = json.dumps({"msg_type": "text", "content": {"text": text}}).encode("utf-8")
        req = urllib.request.Request(FEISHU_WEBHOOK, data=body,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        log("飞书推送失败:\n" + traceback.format_exc())

# ---------------- 主流程 ----------------
def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f: return json.load(f)
    except Exception: return {}

def save_state(st):
    with open(STATE_FILE, "w", encoding="utf-8") as f: json.dump(st, f, ensure_ascii=False, indent=1)

def main():
    state = load_state(); events_all = []; rows = []
    for code, name, note in WATCHLIST:
        code = norm_code(code)
        try:
            bars = fetch_kline(code)
            if len(bars) < 40:
                log(f"{name} 数据不足({len(bars)}根)，跳过"); continue
            use_chanpy = ENGINE in ("auto", "chanpy")
            if use_chanpy:
                try:
                    r = analyze_chanpy(code)
                    log(f"{name} [chanpy] bsp={r['bsp_count']}")
                except Exception:
                    if ENGINE == "chanpy":
                        log(f"{name} chanpy 引擎失败，降级内置: {traceback.format_exc(limit=1)}")
                    r = analyze(bars)
            else:
                r = analyze(bars)
            cur_zs = r["zhongshu"][-1] if r["zhongshu"] else None
            zs_txt = f"[{cur_zs['zd']:.2f},{cur_zs['zg']:.2f}]" if cur_zs else "-"
            sig = []
            if r["buy1"]: sig.append(f"一买{r['buy1']['date']}@{r['buy1']['price']:.2f}")
            if r["buy2"]: sig.append(f"二买{r['buy2']['date']}@{r['buy2']['price']:.2f}")
            if r["sell1"]: sig.append(f"顶背驰{r['sell1']['date']}@{r['sell1']['price']:.2f}")
            if r["break_buy1"] and r["buy1"]: sig.append(f"!!跌破一买低点{r['buy1']['price']:.2f}")
            if r["weak_tops"]: sig.append("高点递降(弱)")
            rows.append((name, code, r["last_date"], r["close"], zs_txt, r["n_stroke"], r["pos"], " ".join(sig) or "-"))
            # 增量事件
            prev = state.get(code, {})
            ev = []
            lf = r["last_fractal"]
            if lf and prev.get("last_fractal") and lf != prev["last_fractal"]:
                ev.append(f"新分型: {lf['type']}@{lf['price']:.2f}({lf['date']})")
            elif lf and not prev.get("last_fractal"):
                ev.append(f"初始化分型: {lf['type']}@{lf['price']:.2f}")
            if r["buy1"] and prev.get("buy1", {}).get("date") != r["buy1"]["date"]:
                ev.append(f"底背驰一买 {r['buy1']['date']} @{r['buy1']['price']:.2f} 面积{r['buy1']['area1']}→{r['buy1']['area2']}")
            if r["break_buy1"] and not prev.get("break_buy1") and r["buy1"]:
                ev.append(f"收盘跌破一买低点 {r['buy1']['price']:.2f}，结构破坏")
            if r["sell1"] and prev.get("sell1", {}).get("date") != r["sell1"]["date"]:
                ev.append(f"顶背驰卖点 {r['sell1']['date']} @{r['sell1']['price']:.2f}")
            if cur_zs and prev.get("zs") and (abs(prev["zs"][0]-cur_zs["zd"])>1e-6 or abs(prev["zs"][1]-cur_zs["zg"])>1e-6):
                ev.append(f"中枢变为 [{cur_zs['zd']:.2f},{cur_zs['zg']:.2f}]")
            if ev:
                events_all.append(f"◆ {name}({code}):\n  " + "\n  ".join(ev))
            state[code] = {"last_fractal": lf, "buy1": r["buy1"], "sell1": r["sell1"],
                           "break_buy1": r["break_buy1"],
                           "zs": [cur_zs["zd"], cur_zs["zg"]] if cur_zs else None}
        except Exception:
            log(f"{name}({code}) 扫描失败:\n{traceback.format_exc()}")
    save_state(state)
    # 表格输出
    w = [10,9,11,7,14,5,22,40]
    header = ("名称","代码","数据日期","收盘","最新中枢","笔数","位置","信号")
    line1 = "  ".join(h.ljust(wi) for h,wi in zip(header,w))
    print("\n" + line1 + "\n" + "-" * len(line1))
    for row in rows:
        print("  ".join(str(c).ljust(wi) for c,wi in zip(row,w)))
    log(f"扫描完成 {len(rows)} 只，事件 {len(events_all)} 条")
    if events_all:
        txt = "【选股信号｜缠论扫描触发】\n" + "\n".join(events_all)
        print("\n" + txt)
        push_feishu(txt)

if __name__ == "__main__":
    main()
    if sys.stdin.isatty() and os.environ.get("SCAN_NO_PAUSE") != "1":
        try: input("\n按回车退出...")
        except EOFError: pass
