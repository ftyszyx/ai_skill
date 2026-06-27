#!/usr/bin/env python3
"""
Scan A-share stocks for a 605186-style flat-base breakout.

The pattern this script looks for:
1. A quiet 20-30 trading day base with narrow price range and low close volatility.
2. A sudden strong up day with volume expansion.
3. Optional next-day confirmation with much heavier turnover/volume.

Data source: Eastmoney public quote and daily kline endpoints.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import datetime as dt
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import requests


EASTMONEY_QUOTE_URL = "https://push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"


@dataclasses.dataclass(frozen=True)
class Stock:
    code: str
    name: str
    market: int

    @property
    def secid(self) -> str:
        return f"{self.market}.{self.code}"


@dataclasses.dataclass(frozen=True)
class Bar:
    date: str
    open: float
    close: float
    high: float
    low: float
    volume: float
    amount: float
    amp_pct: float
    pct: float
    chg: float
    turnover_pct: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan A-shares for flat-base breakout candidates."
    )
    parser.add_argument("--date", help="Signal date, YYYY-MM-DD. Defaults to latest kline date.")
    parser.add_argument("--lookback", type=int, default=30, help="Base lookback trading days.")
    parser.add_argument("--min-base-days", type=int, default=20, help="Minimum available base days.")
    parser.add_argument("--max-base-range-pct", type=float, default=13.0)
    parser.add_argument("--max-close-cv-pct", type=float, default=3.0)
    parser.add_argument("--min-breakout-pct", type=float, default=7.0)
    parser.add_argument("--min-volume-ratio", type=float, default=2.0)
    parser.add_argument("--min-turnover-pct", type=float, default=2.0)
    parser.add_argument("--max-prev-volume-ratio", type=float, default=2.2)
    parser.add_argument("--max-prev-big-up-days", type=int, default=2)
    parser.add_argument("--min-amount-yuan", type=float, default=80_000_000)
    parser.add_argument("--max-results", type=int, default=80)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument(
        "--universe-file",
        default="auto",
        help="A-share universe JSON. Defaults to latest a_share_*_all*.json; use 'none' to fetch from Eastmoney.",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        help="Limit number of stocks for quick testing. 0 scans all.",
    )
    parser.add_argument(
        "--include-star",
        action="store_true",
        help="Include 科创板 688/689 stocks. They have 20% limits and noisier signals.",
    )
    parser.add_argument(
        "--include-bj",
        action="store_true",
        help="Include 北交所 stocks. They have 30% limits and noisier signals.",
    )
    parser.add_argument(
        "--watch",
        nargs="*",
        default=[],
        help="Always evaluate these stock codes, e.g. --watch 605186 603xxx.",
    )
    parser.add_argument("--out-dir", default="output/breakout_scan")
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Only write JSON and skip Markdown report.",
    )
    return parser.parse_args()


def request_json(
    session: requests.Session,
    url: str,
    params: dict[str, Any],
    timeout: float,
    retries: int,
) -> dict[str, Any] | None:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001 - network retries are intentionally broad.
            last_error = exc
            if attempt < retries:
                time.sleep(0.25 * (attempt + 1))
    print(f"request failed: {url} params={params} error={last_error}", file=sys.stderr)
    return None


def load_market_stocks(
    session: requests.Session,
    timeout: float,
    retries: int,
    include_star: bool,
    include_bj: bool,
) -> list[Stock]:
    stocks: list[Stock] = []
    page = 1
    page_size = 100
    while True:
        params = {
            "pn": page,
            "pz": page_size,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
            "fields": "f12,f13,f14",
        }
        payload = request_json(session, EASTMONEY_QUOTE_URL, params, timeout, retries)
        diff = ((payload or {}).get("data") or {}).get("diff") or []
        if not diff:
            break
        for item in diff:
            code = str(item.get("f12") or "").strip()
            name = str(item.get("f14") or "").strip()
            market = int(item.get("f13") or 0)
            if not code or not name:
                continue
            if name.startswith(("ST", "*ST", "退市")) or "退" in name:
                continue
            if not include_star and code.startswith(("688", "689")):
                continue
            if not include_bj and code.startswith(("8", "4")):
                continue
            stocks.append(Stock(code=code, name=name, market=market))
        if len(diff) < page_size:
            break
        page += 1
    return stocks


def stock_from_local_item(item: dict[str, Any]) -> Stock | None:
    code = str(item.get("code") or item.get("f12") or "").strip()
    name = str(item.get("name") or item.get("f14") or "").strip()
    if not code or not name:
        return None
    qcode = str(item.get("qcode") or "").strip().lower()
    market_hint = item.get("market_hint")
    if qcode.startswith("sh"):
        market = 1
    elif qcode.startswith(("sz", "bj")):
        market = 0
    elif market_hint in (0, 1):
        market = int(market_hint)
    else:
        market = infer_market(code)
    return Stock(code=code, name=name, market=market)


def find_latest_universe_file() -> Path | None:
    files = sorted(
        Path(".").glob("a_share_*_all*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def load_local_universe(
    universe_file: str,
    include_star: bool,
    include_bj: bool,
) -> list[Stock]:
    if universe_file.lower() == "none":
        return []
    path = find_latest_universe_file() if universe_file == "auto" else Path(universe_file)
    if not path or not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - local universe is an optional convenience.
        print(f"failed to read universe file {path}: {exc}", file=sys.stderr)
        return []

    stocks: list[Stock] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        stock = stock_from_local_item(item)
        if not stock or stock.code in seen:
            continue
        if stock.name.startswith(("ST", "*ST", "退市")) or "退" in stock.name:
            continue
        if not include_star and stock.code.startswith(("688", "689")):
            continue
        if not include_bj and stock.code.startswith(("8", "4", "920")):
            continue
        seen.add(stock.code)
        stocks.append(stock)
    print(f"Loaded {len(stocks)} stocks from {path}", file=sys.stderr)
    return stocks


def infer_market(code: str) -> int:
    if code.startswith(("6", "9")):
        return 1
    return 0


def fetch_bars(
    session: requests.Session,
    stock: Stock,
    timeout: float,
    retries: int,
    beg: str,
    end: str,
) -> list[Bar]:
    params = {
        "secid": stock.secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "1",
        "beg": beg,
        "end": end,
    }
    payload = request_json(session, EASTMONEY_KLINE_URL, params, timeout, retries)
    rows = ((payload or {}).get("data") or {}).get("klines") or []
    bars: list[Bar] = []
    for row in rows:
        fields = row.split(",")
        if len(fields) < 11:
            continue
        try:
            bars.append(
                Bar(
                    date=fields[0],
                    open=float(fields[1]),
                    close=float(fields[2]),
                    high=float(fields[3]),
                    low=float(fields[4]),
                    volume=float(fields[5]),
                    amount=float(fields[6]),
                    amp_pct=float(fields[7]),
                    pct=float(fields[8]),
                    chg=float(fields[9]),
                    turnover_pct=float(fields[10]),
                )
            )
        except ValueError:
            continue
    return bars


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def pct(value: float) -> float:
    return value * 100.0


def safe_ratio(num: float, den: float) -> float:
    return num / den if den else 0.0


def evaluate_signal(
    stock: Stock,
    bars: list[Bar],
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    if len(bars) < args.min_base_days + 2:
        return None

    if args.date:
        idx = next((i for i, bar in enumerate(bars) if bar.date == args.date), None)
        if idx is None:
            return None
    else:
        idx = len(bars) - 1

    if idx < args.min_base_days:
        return None

    today = bars[idx]
    base_start = max(0, idx - args.lookback)
    base = bars[base_start:idx]
    if len(base) < args.min_base_days:
        return None

    prev20 = bars[max(0, idx - 20) : idx]
    prev60 = bars[max(0, idx - 60) : idx]
    closes = [bar.close for bar in base]
    volumes = [bar.volume for bar in base]
    highs = [bar.high for bar in base]
    lows = [bar.low for bar in base]

    base_high = max(highs)
    base_low = min(lows)
    close_mean = mean(closes)
    close_cv_pct = pct(statistics.pstdev(closes) / close_mean) if close_mean else 0.0
    base_range_pct = pct(base_high / base_low - 1.0) if base_low else 0.0
    volume_mean = mean(volumes)
    volume20_mean = mean(bar.volume for bar in prev20)
    volume60_mean = mean(bar.volume for bar in prev60)
    turnover20 = mean(bar.turnover_pct for bar in prev20)
    amount20 = mean(bar.amount for bar in prev20)

    prev_big_up_days = sum(1 for bar in base if bar.pct >= 5.0)
    prev_volume_ratio = safe_ratio(max(volumes), volume_mean)
    volume_ratio = safe_ratio(today.volume, volume_mean)
    volume20_ratio = safe_ratio(today.volume, volume20_mean)
    amount_ratio = safe_ratio(today.amount, amount20)
    close_vs_base_high_pct = pct(today.close / base_high - 1.0) if base_high else 0.0
    high_vs_base_high_pct = pct(today.high / base_high - 1.0) if base_high else 0.0
    close_position = (today.close - today.low) / (today.high - today.low) if today.high > today.low else 1.0

    # A 605186-like trigger can either close above the short platform,
    # or hit a limit/near-limit day from a very tight base.
    strong_up = today.pct >= args.min_breakout_pct
    platform_break = today.close >= base_high * 0.995 or today.high >= base_high * 1.01
    near_limit_from_tight_base = today.pct >= 9.0 and base_range_pct <= args.max_base_range_pct

    passes = (
        base_range_pct <= args.max_base_range_pct
        and close_cv_pct <= args.max_close_cv_pct
        and prev_volume_ratio <= args.max_prev_volume_ratio
        and prev_big_up_days <= args.max_prev_big_up_days
        and strong_up
        and volume_ratio >= args.min_volume_ratio
        and today.turnover_pct >= args.min_turnover_pct
        and today.amount >= args.min_amount_yuan
        and (platform_break or near_limit_from_tight_base)
    )

    if not passes:
        return None

    prev_close = bars[idx - 1].close if idx > 0 else today.close
    ma20 = mean(bar.close for bar in prev20)
    ma60 = mean(bar.close for bar in prev60)

    confirm = None
    if idx + 1 < len(bars):
        nxt = bars[idx + 1]
        next_prev20 = bars[max(0, idx + 1 - 20) : idx + 1]
        next_vol20 = mean(bar.volume for bar in next_prev20)
        confirm = {
            "date": nxt.date,
            "pct": round(nxt.pct, 2),
            "close": round(nxt.close, 2),
            "volume_ratio_20": round(safe_ratio(nxt.volume, next_vol20), 2),
            "turnover_pct": round(nxt.turnover_pct, 2),
            "holds_breakout": nxt.close >= today.close * 0.97,
            "high_extends": nxt.high > today.high,
            "giant_volume": safe_ratio(nxt.volume, next_vol20) >= 3.0,
        }

    # Scoring favors tight bases, big volume, strong close, and follow-through.
    score = 0.0
    score += max(0.0, (args.max_base_range_pct - base_range_pct) * 1.7)
    score += max(0.0, (args.max_close_cv_pct - close_cv_pct) * 5.0)
    score += min(35.0, volume20_ratio * 4.0)
    score += min(20.0, max(0.0, today.pct) * 1.3)
    score += min(15.0, max(0.0, high_vs_base_high_pct + 3.0) * 1.8)
    score += min(8.0, today.turnover_pct * 0.8)
    score += 5.0 if close_position >= 0.75 else 0.0
    if confirm:
        score += 8.0 if confirm["holds_breakout"] else -8.0
        score += 6.0 if confirm["high_extends"] else 0.0
        score += 8.0 if confirm["giant_volume"] else 0.0

    return {
        "code": stock.code,
        "name": stock.name,
        "date": today.date,
        "signal": "day1_breakout",
        "score": round(score, 1),
        "close": round(today.close, 2),
        "pct": round(today.pct, 2),
        "amount_yuan": round(today.amount, 0),
        "turnover_pct": round(today.turnover_pct, 2),
        "base_days": len(base),
        "base_range_pct": round(base_range_pct, 2),
        "close_cv_pct": round(close_cv_pct, 2),
        "base_high": round(base_high, 2),
        "base_low": round(base_low, 2),
        "close_vs_base_high_pct": round(close_vs_base_high_pct, 2),
        "high_vs_base_high_pct": round(high_vs_base_high_pct, 2),
        "volume_ratio": round(volume_ratio, 2),
        "volume_ratio_20": round(volume20_ratio, 2),
        "volume_ratio_60": round(safe_ratio(today.volume, volume60_mean), 2),
        "amount_ratio_20": round(amount_ratio, 2),
        "prev_volume_ratio": round(prev_volume_ratio, 2),
        "prev_big_up_days": prev_big_up_days,
        "close_position": round(close_position, 2),
        "prev_close": round(prev_close, 2),
        "ma20": round(ma20, 2),
        "ma60": round(ma60, 2),
        "ma20_vs_ma60_pct": round(pct(ma20 / ma60 - 1.0), 2) if ma60 else 0.0,
        "next_day": confirm,
    }


def evaluate_confirmation(
    stock: Stock,
    bars: list[Bar],
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    if len(bars) < args.min_base_days + 3:
        return None

    if args.date:
        idx = next((i for i, bar in enumerate(bars) if bar.date == args.date), None)
        if idx is None or idx == 0:
            return None
    else:
        idx = len(bars) - 1

    # Re-evaluate yesterday with the same rules and then test today's confirmation.
    y_args = argparse.Namespace(**vars(args))
    y_args.date = bars[idx - 1].date
    day1 = evaluate_signal(stock, bars, y_args)
    if not day1:
        return None

    today = bars[idx]
    prev20 = bars[max(0, idx - 20) : idx]
    volume20_ratio = safe_ratio(today.volume, mean(bar.volume for bar in prev20))
    held = today.close >= day1["close"] * 0.97
    extended = today.high > day1["close"] * 1.02 or today.close > day1["close"]
    active = volume20_ratio >= 2.5 or today.turnover_pct >= 8.0
    if not (held and extended and active):
        return None

    score = day1["score"] + min(25.0, volume20_ratio * 3.0) + max(0.0, today.pct) * 1.2
    return {
        **day1,
        "date": today.date,
        "signal": "day2_confirmed",
        "score": round(score, 1),
        "close": round(today.close, 2),
        "pct": round(today.pct, 2),
        "amount_yuan": round(today.amount, 0),
        "turnover_pct": round(today.turnover_pct, 2),
        "day1_date": day1["date"],
        "day1_close": day1["close"],
        "day1_pct": day1["pct"],
        "day2_volume_ratio_20": round(volume20_ratio, 2),
        "day2_holds_day1": held,
        "day2_extends": extended,
    }


def scan_stock(stock: Stock, args: argparse.Namespace, beg: str, end: str) -> list[dict[str, Any]]:
    session = requests.Session()
    bars = fetch_bars(session, stock, args.timeout, args.retries, beg, end)
    if not bars:
        return []
    signals = []
    signal = evaluate_signal(stock, bars, args)
    if signal:
        signals.append(signal)
    confirmation = evaluate_confirmation(stock, bars, args)
    if confirmation:
        signals.append(confirmation)
    return signals


def today_yyyymmdd() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


def calc_beg(args: argparse.Namespace) -> str:
    if args.date:
        signal_date = dt.datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        signal_date = dt.date.today()
    beg = signal_date - dt.timedelta(days=max(220, args.lookback * 5))
    return beg.strftime("%Y%m%d")


def build_report(results: list[dict[str, Any]], args: argparse.Namespace) -> str:
    generated_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title_date = args.date or "latest"
    lines = [
        f"# Flat-Base Breakout Scan {title_date}",
        "",
        f"Generated: {generated_at}",
        "",
        "Rules:",
        f"- Base: {args.lookback} trading days, range <= {args.max_base_range_pct}%, close CV <= {args.max_close_cv_pct}%.",
        f"- Breakout: pct >= {args.min_breakout_pct}%, volume/base >= {args.min_volume_ratio}x, turnover >= {args.min_turnover_pct}%, amount >= {args.min_amount_yuan:,.0f}.",
        "- Signals: day1_breakout is the first launch; day2_confirmed means the next day held and traded actively.",
        "",
    ]
    if not results:
        lines.append("No candidates matched.")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "| Rank | Code | Name | Signal | Date | Score | Close | Pct | Turnover | Vol20x | BaseRange | BaseHighGap | Next/Day2 |",
            "|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for rank, row in enumerate(results, 1):
        next_text = ""
        if row.get("signal") == "day2_confirmed":
            next_text = f"day1 {row.get('day1_date')} +{row.get('day1_pct')}%"
            vol20 = row.get("day2_volume_ratio_20", row.get("volume_ratio_20", ""))
        else:
            nd = row.get("next_day") or {}
            if nd:
                tags = []
                if nd.get("holds_breakout"):
                    tags.append("held")
                if nd.get("high_extends"):
                    tags.append("extend")
                if nd.get("giant_volume"):
                    tags.append("huge vol")
                next_text = f"{nd.get('date')} {nd.get('pct')}% {'/'.join(tags)}".strip()
            vol20 = row.get("volume_ratio_20", "")
        lines.append(
            "| {rank} | {code} | {name} | {signal} | {date} | {score} | {close} | {pct}% | {turnover}% | {vol20} | {base_range}% | {gap}% | {next_text} |".format(
                rank=rank,
                code=row.get("code", ""),
                name=row.get("name", ""),
                signal=row.get("signal", ""),
                date=row.get("date", ""),
                score=row.get("score", ""),
                close=row.get("close", ""),
                pct=row.get("pct", ""),
                turnover=row.get("turnover_pct", ""),
                vol20=vol20,
                base_range=row.get("base_range_pct", ""),
                gap=row.get("close_vs_base_high_pct", ""),
                next_text=next_text,
            )
        )

    lines.extend(
        [
            "",
            "Notes:",
            "- This is a technical alert list, not a buy list. Review theme, news, fundamentals, liquidity, and next-day price action before trading.",
            "- Very loose parameters raise recall but also false positives. Tighten range/volume/turnover after a few weeks of observation.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(results: list[dict[str, Any]], args: argparse.Namespace) -> tuple[Path, Path | None]:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = (args.date or dt.date.today().strftime("%Y-%m-%d")).replace("-", "")
    json_path = out_dir / f"flat_breakouts_{suffix}.json"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path: Path | None = None
    if not args.json_only:
        md_path = out_dir / f"flat_breakouts_{suffix}.md"
        md_path.write_text(build_report(results, args), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    args = parse_args()
    session = requests.Session()
    stocks = load_local_universe(args.universe_file, args.include_star, args.include_bj)
    if not stocks:
        stocks = load_market_stocks(
            session,
            timeout=args.timeout,
            retries=args.retries,
            include_star=args.include_star,
            include_bj=args.include_bj,
        )
        print(f"Loaded {len(stocks)} stocks from Eastmoney quote list", file=sys.stderr)
    watched = {code.strip() for code in args.watch if code.strip()}
    existing = {stock.code for stock in stocks}
    for code in sorted(watched - existing):
        stocks.append(Stock(code=code, name=code, market=infer_market(code)))

    if args.sample:
        watch_stocks = [stock for stock in stocks if stock.code in watched]
        others = [stock for stock in stocks if stock.code not in watched]
        stocks = (watch_stocks + others)[: args.sample]

    beg = calc_beg(args)
    end = today_yyyymmdd()
    all_signals: list[dict[str, Any]] = []
    total = len(stocks)
    print(f"Scanning {total} stocks from {beg} to {end}...", file=sys.stderr)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(scan_stock, stock, args, beg, end): stock for stock in stocks
        }
        for done, future in enumerate(concurrent.futures.as_completed(futures), 1):
            try:
                all_signals.extend(future.result())
            except Exception as exc:  # noqa: BLE001 - keep scanning after one bad symbol.
                stock = futures[future]
                print(f"scan failed {stock.code} {stock.name}: {exc}", file=sys.stderr)
            if done % 300 == 0 or done == total:
                print(f"  {done}/{total} done, signals={len(all_signals)}", file=sys.stderr)

    all_signals.sort(key=lambda row: (row.get("score", 0.0), row.get("amount_yuan", 0.0)), reverse=True)
    results = all_signals[: args.max_results]
    json_path, md_path = write_outputs(results, args)
    print(f"Wrote {json_path}")
    if md_path:
        print(f"Wrote {md_path}")
    for row in results[:20]:
        vol_key = "day2_volume_ratio_20" if row.get("signal") == "day2_confirmed" else "volume_ratio_20"
        print(
            f"{row['code']} {row['name']} {row['signal']} {row['date']} "
            f"score={row['score']} pct={row['pct']}% vol20x={row.get(vol_key)} "
            f"base={row['base_range_pct']}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
