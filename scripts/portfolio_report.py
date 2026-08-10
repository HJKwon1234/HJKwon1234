#!/usr/bin/env python3
"""보유 종목을 집계해 브리핑에 쓸 형태로 출력한다.

    python3 scripts/portfolio_report.py --market kr      # 국내 보유 목록
    python3 scripts/portfolio_report.py --market us      # 해외 보유 목록
    python3 scripts/portfolio_report.py --prices p.json  # 시세를 주면 평가금/손익까지

시세 파일(p.json)은 {"삼성전자": 231500, "PLTR": 172.15} 형태로, 국내는 종목명,
해외는 티커를 키로 쓴다. 시세가 없는 종목은 조용히 건너뛰지 않고 목록 끝에 표시한다.
"""

from __future__ import annotations

import argparse
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_PF = HERE / "portfolio.json"


def load(path: pathlib.Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def key_of(row: dict, market: str) -> str:
    return row["ticker"] if market == "us" and "ticker" in row else row["name"]


def report(rows: list[dict], market: str, prices: dict, unit: str) -> None:
    priced, missing = [], []
    for row in rows:
        px = prices.get(key_of(row, market))
        if px is None:
            missing.append(row)
            continue
        cost = row["qty"] * row["avg"]
        value = row["qty"] * px
        priced.append((row, cost, value))

    if not priced:
        # 시세가 하나도 없으면 보유 목록만 출력한다.
        for row in rows:
            print(f"  {row['name']:<28} {row['qty']:>12,.6f}주  평단 {row['avg']:,.2f} {unit}")
        return

    total_v = sum(v for _, _, v in priced)
    total_c = sum(c for _, c, _ in priced)
    priced.sort(key=lambda t: -t[2])

    print(f"{'종목':<28} {'비중':>7} {'평가금':>14} {'손익':>14} {'수익률':>9}")
    for row, cost, value in priced:
        pl = value - cost
        pct = pl / cost * 100 if cost else 0.0
        print(f"{row['name']:<28} {value / total_v * 100:6.1f}% {value:>14,.2f} {pl:>+14,.2f} {pct:>+8.2f}%")

    pl = total_v - total_c
    print("-" * 78)
    print(f"{'합계':<28} {'100.0%':>7} {total_v:>14,.2f} {pl:>+14,.2f} "
          f"{(pl / total_c * 100 if total_c else 0):>+8.2f}%  [{unit}]")
    if missing:
        print("\n시세 없음:", ", ".join(r["name"] for r in missing))


def main() -> None:
    ap = argparse.ArgumentParser(description="보유 종목 집계 리포트")
    ap.add_argument("--portfolio", type=pathlib.Path, default=DEFAULT_PF)
    ap.add_argument("--market", choices=["kr", "us", "all"], default="all")
    ap.add_argument("--prices", type=pathlib.Path, help="시세 JSON 파일")
    args = ap.parse_args()

    pf = load(args.portfolio)
    prices = load(args.prices) if args.prices else {}

    print(f"기준 스냅샷: {pf.get('as_of', '알 수 없음')}\n")
    if args.market in ("kr", "all"):
        print("=== 국내 ===")
        report(pf["domestic"], "kr", prices, "KRW")
        print()
    if args.market in ("us", "all"):
        print("=== 해외 ===")
        report(pf["overseas"], "us", prices, "USD")


if __name__ == "__main__":
    main()
