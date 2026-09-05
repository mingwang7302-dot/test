"""Official Taiwan market data adapters and transparent regime rules."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json


TWSE_SPOT_URL = "https://www.twse.com.tw/rwd/zh/fund/BFI82U"
TWSE_MARGIN_URL = "https://www.twse.com.tw/exchangeReport/MI_MARGN"
TAIFEX_FUTURES_URL = (
    "https://openapi.taifex.com.tw/v1/"
    "MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (TaiwanMarketDashboard/1.0)",
    "Accept": "application/json",
}


class MarketDataError(RuntimeError):
    pass


def number(value) -> float:
    if value is None:
        raise MarketDataError("官方資料缺少必要數值")
    cleaned = str(value).replace(",", "").replace("+", "").strip()
    if cleaned in {"", "--", "-"}:
        raise MarketDataError(f"無法解析數值：{value!r}")
    return float(cleaned)


def _request_json(url: str, *, params=None, timeout: int = 15):
    if params:
        url = f"{url}?{urlencode(params)}"
    request = Request(url, headers=HEADERS)
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _latest_twse_table(url: str, table_parser: Callable, lookback_days: int = 10):
    day = datetime.now()
    last_error = None
    for _ in range(lookback_days):
        query_date = day.strftime("%Y%m%d")
        try:
            payload = _request_json(
                url,
                params={"response": "json", "date": query_date, "selectType": "ALL"},
            )
            if payload.get("stat") == "OK":
                return query_date, table_parser(payload)
        except (OSError, ValueError, MarketDataError) as exc:
            last_error = exc
        day -= timedelta(days=1)
    raise MarketDataError(f"最近 {lookback_days} 日查無證交所資料：{last_error or '非交易日'}")


def _parse_spot(payload) -> float:
    fields = payload.get("fields", [])
    rows = payload.get("data", [])
    net_index = next((i for i, name in enumerate(fields) if "買賣差額" in name), -1)
    if net_index < 0:
        net_index = len(fields) - 1
    for row in rows:
        label = str(row[0]).replace(" ", "")
        if "外資及陸資" in label:
            return number(row[net_index])
    raise MarketDataError("證交所法人資料找不到外資及陸資列")


def _parse_margin(payload) -> float:
    tables = payload.get("tables", [])
    if not tables:
        raise MarketDataError("證交所融資資料缺少彙總表")
    summary = tables[0]
    fields = summary.get("fields", [])
    rows = summary.get("data", [])
    balance_index = next((i for i, name in enumerate(fields) if "今日餘額" in name), -1)
    if balance_index < 0:
        balance_index = len(fields) - 1
    for row in rows:
        if "融資金額" in str(row[0]):
            # TWSE publishes this row in thousands of TWD; dashboard stores TWD.
            return number(row[balance_index]) * 1_000
    raise MarketDataError("證交所融資彙總找不到融資金額列")


def fetch_foreign_spot():
    date, net_twd = _latest_twse_table(TWSE_SPOT_URL, _parse_spot)
    return {"date": date, "foreign_spot_net_twd": net_twd}


def fetch_margin_balance():
    date, balance_twd = _latest_twse_table(TWSE_MARGIN_URL, _parse_margin)
    return {"date": date, "margin_balance_twd": balance_twd}


def fetch_foreign_futures():
    try:
        data = _request_json(TAIFEX_FUTURES_URL)
    except (OSError, ValueError) as exc:
        raise MarketDataError(f"期交所資料取得失敗：{exc}") from exc
    if not isinstance(data, list):
        raise MarketDataError("期交所回傳格式異常")
    for item in data:
        contract = str(item.get("ContractCode", "")).replace(" ", "")
        investor = str(item.get("Item", "")).replace(" ", "")
        if "臺股期貨" in contract and "外資" in investor:
            return {
                "date": str(item.get("Date", "")).replace("/", "").replace("-", ""),
                "foreign_futures_long": int(number(item.get("OpenInterest(Long)"))),
                "foreign_futures_short": int(number(item.get("OpenInterest(Short)"))),
                "foreign_futures_net": int(number(item.get("OpenInterest(Net)"))),
            }
    raise MarketDataError("期交所資料找不到臺股期貨外資未平倉列")


def fetch_taiex_trend():
    import yfinance as yf

    hist = yf.Ticker("^TWII").history(period="3mo", auto_adjust=False)
    if hist.empty or len(hist) < 20:
        raise MarketDataError("加權指數資料不足 20 個交易日")
    close = hist["Close"].dropna()
    latest = float(close.iloc[-1])
    return {
        "taiex_close": latest,
        "taiex_ma20": float(close.tail(20).mean()),
        "taiex_new_20d_low": latest <= float(close.tail(20).min()),
    }


def collect_snapshot():
    spot = fetch_foreign_spot()
    margin = fetch_margin_balance()
    futures = fetch_foreign_futures()
    trend = fetch_taiex_trend()
    source_dates = {"spot": spot["date"], "margin": margin["date"], "futures": futures["date"]}
    dates = {value for value in source_dates.values() if value}
    if len(dates) != 1:
        raise MarketDataError(f"官方資料日期尚未同步：{source_dates}")
    return {**spot, **margin, **futures, **trend, "date": dates.pop(), "source_dates": source_dates}


def _values(history: Iterable, attr: str, limit: int):
    return [float(getattr(row, attr)) for row in list(history)[-limit:]]


def evaluate_regime(snapshot, history=()):
    """Apply the user's established absolute-level + recent-change rules."""
    history = list(history)
    futures_net = int(snapshot.foreign_futures_net)
    spot = float(snapshot.foreign_spot_net_twd)
    margin = float(snapshot.margin_balance_twd)
    close = float(snapshot.taiex_close)
    ma20 = float(snapshot.taiex_ma20)

    prior_futures = _values(history, "foreign_futures_net", 3)
    prior_spot = _values(history, "foreign_spot_net_twd", 5)
    prior_margin = _values(history, "margin_balance_twd", 1)
    futures_3d_change = futures_net - prior_futures[0] if len(prior_futures) >= 3 else None
    spot_3d = sum((prior_spot + [spot])[-3:]) if len(prior_spot) >= 2 else None
    spot_5d = sum((prior_spot + [spot])[-5:]) if len(prior_spot) >= 4 else None
    three_buy_days = len(prior_spot) >= 2 and all(v > 0 for v in (prior_spot + [spot])[-3:])
    margin_change = margin - prior_margin[-1] if prior_margin else None

    if futures_net < -80_000:
        futures_label, futures_score = "高避險／明顯偏空", -2
    elif futures_net < -65_000:
        futures_label, futures_score = "偏空改善中", -1
    elif futures_net < -50_000:
        futures_label, futures_score = "反轉觀察區", 0
    elif futures_net < -40_000:
        futures_label, futures_score = "反轉形成", 1
    elif futures_net < -30_000:
        futures_label, futures_score = "明確反轉", 2
    else:
        futures_label, futures_score = "強勢反轉", 3
    if futures_3d_change is not None and futures_3d_change > 15_000:
        futures_score += 1
        futures_label += "，近3日大幅減空"

    spot_score = -2 if spot <= -30_000_000_000 else (-1 if spot < 0 else 1)
    if spot_3d is not None and spot_3d > 0:
        spot_score += 1
    if spot_5d is not None and spot_5d > 0:
        spot_score += 1
    if three_buy_days:
        spot_score += 1

    if margin > 530_000_000_000:
        margin_score, margin_label = -2, "槓桿偏高"
    elif margin > 520_000_000_000:
        margin_score, margin_label = -1, "槓桿仍高"
    elif margin > 500_000_000_000:
        margin_score, margin_label = 1, "籌碼改善"
    else:
        margin_score, margin_label = 2, "籌碼乾淨"
    if margin_change is not None and margin_change < 0:
        margin_score += 1
        margin_label += "，融資下降"

    price_score = -2 if snapshot.taiex_new_20d_low else (1 if close >= ma20 else 0)
    score = futures_score + spot_score + margin_score + price_score

    reversal_gate = (
        futures_net >= -50_000
        and spot_3d is not None and spot_3d > 0
        and close >= ma20
        and (margin_change is None or margin_change <= 0)
    )
    strong_gate = reversal_gate and futures_net >= -30_000 and spot_5d is not None and spot_5d > 0
    bearish_gate = futures_net < -50_000 and spot <= -30_000_000_000 and (
        margin > 530_000_000_000 or snapshot.taiex_new_20d_low
    )

    if strong_gate and score >= 6:
        regime = "強多頭"
    elif reversal_gate and score >= 3:
        regime = "反轉形成"
    elif bearish_gate:
        regime = "偏空"
    elif not snapshot.taiex_new_20d_low and spot > -30_000_000_000:
        regime = "反彈確認"
    else:
        regime = "築底"

    reasons = [
        f"外資台指期淨部位 {futures_net:,} 口：{futures_label}",
        f"外資現貨單日 {spot / 100_000_000:+,.1f} 億元",
        f"融資餘額 {margin / 100_000_000:,.1f} 億元：{margin_label}",
        f"加權指數 {'站上' if close >= ma20 else '尚未站上'} 20日均線",
    ]
    watch = []
    if len(prior_spot) < 4:
        watch.append("累積至少5個交易日後，才可完整確認外資連買與5日合計")
    if futures_net < -50_000:
        watch.append("外資期貨淨空單需回到 -50,000 口以內")
    if spot_3d is None or spot_3d <= 0:
        watch.append("外資現貨3日累計需轉正")
    if close < ma20:
        watch.append("指數需站回20日均線且回測不破")

    return {
        "regime": regime,
        "score": score,
        "reasons": reasons,
        "watch": watch,
        "calculations": {
            "futures_3d_change": futures_3d_change,
            "spot_3d_twd": spot_3d,
            "spot_5d_twd": spot_5d,
            "margin_change_twd": margin_change,
        },
    }
