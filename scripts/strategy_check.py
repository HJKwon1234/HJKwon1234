#!/usr/bin/env python3
"""보유 종목을 원칙(strategy.json)에 비춰 점검한다.

    python3 scripts/strategy_check.py                  # 전체 점검
    python3 scripts/strategy_check.py --section triggers
    python3 scripts/strategy_check.py --prices p.json  # 최신 시세 주입
    python3 scripts/strategy_check.py --fx 1405        # 환율만 갱신

portfolio.json 의 last 는 '마지막으로 확인한 값'이지 실시간 시세가 아니다. 실제 매매
판단 전에는 --prices 로 최신 시세를 넣거나 증권사 화면에서 재확인해야 한다. 이 구분을
흐리지 않으려고 리포트 머리말에 스냅샷 시각을 항상 찍는다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
W = 76


def load(path: pathlib.Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def head(title: str) -> None:
    print(f"\n{'─' * 3} {title} {'─' * max(0, W - len(title) - 5)}")


def key_of(row: dict) -> str:
    return row.get("ticker") or row["name"]


def apply_prices(pf: dict, prices: dict) -> int:
    """시세 파일로 last 를 덮어쓴다. 갱신된 종목 수를 돌려준다."""
    n = 0
    for market in ("domestic", "overseas"):
        for row in pf[market]:
            px = prices.get(key_of(row), prices.get(row["name"]))
            if px is not None:
                row["last"] = px
                n += 1
    return n


def totals(rows: list[dict]) -> tuple[float, float]:
    value = sum(r["qty"] * r["last"] for r in rows)
    cost = sum(r["qty"] * r["avg"] for r in rows)
    return value, cost


def find(pf: dict, name: str) -> dict | None:
    for market in ("domestic", "overseas"):
        for row in pf[market]:
            if row["name"] == name:
                return row
    return None


def sec_summary(pf: dict, fx: float) -> None:
    head("계좌 요약")
    dv, dc = totals(pf["domestic"])
    ov, oc = totals(pf["overseas"])
    for label, v, c, unit in (("국내", dv, dc, "KRW"), ("해외", ov, oc, "USD")):
        pl = v - c
        print(f"  {label}  평가 {v:>12,.2f} {unit}   손익 {pl:>+12,.2f}  ({pl / c * 100:+6.2f}%)")
    total = dv + ov * fx
    print(f"  ── 합계 {total:>12,.0f} 원  (환율 {fx:,.0f} 가정: 국내 {dv / total * 100:.1f}% / 해외 {ov * fx / total * 100:.1f}%)")

    usd_side = sum(r["qty"] * r["last"] for r in pf["domestic"] if "달러자산" in r.get("tags", []))
    exposure = (ov * fx + usd_side) / total * 100
    print(f"  달러 노출 {exposure:.1f}%  (해외 계좌 전액 + 국내 달러자산 ETF {usd_side:,.0f}원)")


def sec_triggers(pf: dict, st: dict) -> None:
    head("활성 트리거")
    fired = []
    for t in st["triggers"]:
        row = find(pf, t["name"])
        if row is None:
            print(f"  ⚠️  {t['id']}: 보유 목록에 '{t['name']}' 없음 — 이미 정리된 종목인지 확인")
            continue
        cur, lvl = row["last"], t["level"]
        hit = cur >= lvl if t["dir"] == "above" else cur <= lvl
        gap = (lvl - cur) / cur * 100
        mark = "🔴 발동" if hit else "  대기"
        print(f"  {mark}  {t['name']:<14} 현재 {cur:>10,.2f} / {t['dir']:<5} {lvl:>10,.2f}  ({gap:+6.2f}%)  {t['action']}")
        if t.get("condition"):
            print(f"          ↳ 조건: {t['condition']}")
        if hit:
            fired.append(t)
    if fired:
        print(f"\n  ※ 발동 {len(fired)}건. 원칙 2-5 에 따라 트리거 도달 시 즉시 실행한다.")
        print("     단 조건부 트리거는 조건까지 충족해야 한다.")


def sec_fx(st: dict, fx: float) -> None:
    head("환율 트리거")
    print(f"  현재 {fx:,.2f} 원")
    active = 0
    for s in st["fx_triggers"]["steps"]:
        hit = fx < s["level"] if s["dir"] == "below" else fx > s["level"]
        if hit:
            active = max(active, s["convert_pct"])
        print(f"    {'✅' if hit else '  '} {s['level']:,} {s['dir']} → {s['convert_pct']}% 전환")
    print(f"  → 현재 전환 단계: {active}%")


def sec_alloc(pf: dict, st: dict) -> None:
    head("목표 비중 대비 현재 (해외 계좌)")
    ov, _ = totals(pf["overseas"])
    dca = st["profile"]["dca"]
    per_day = dca["usd_per_day"] * 1 / len(dca["tickers"])  # 종목당 균등 가정
    need_total = 0.0
    targets = {k: v for k, v in st["allocation_targets"].items() if not k.startswith("_")}
    for tk, (lo, hi) in targets.items():
        row = next((r for r in pf["overseas"] if key_of(r) == tk), None)
        if row is None:
            continue
        v = row["qty"] * row["last"]
        mid = (lo + hi) / 2
        need = ov * mid - v
        need_total += max(0.0, need)
        print(f"  {tk:<6} 현재 {v / ov * 100:5.2f}%   목표 {lo * 100:.0f}~{hi * 100:.0f}%   중간값까지 {need:>+9,.0f} USD")
    if need_total > 0:
        days = need_total / (per_day * len(targets))
        print(f"\n  부족분 합계 ${need_total:,.0f}")
        print(f"  적립식(${dca['usd_per_day']}/일 ÷ {len(dca['tickers'])}종목)만으로 메우면 약 {days:,.0f}일 ({days / 365:.1f}년)")
        if days > 365:
            print("  ⚠️  1년 초과 — 적립식만으로는 도달 불가. 목표 재조정 또는 정예화 대금 배정이 필요하다.")


def sec_principles(pf: dict, st: dict) -> None:
    head("원칙 준수 점검")
    ov, _ = totals(pf["overseas"])
    cc = [r for r in pf["overseas"] if "커버드콜" in r.get("tags", [])]
    cc_v = sum(r["qty"] * r["last"] for r in cc)
    cap = st["principles"]["2-6_기타"]["covered_call_max_pct"]
    pct = cc_v / ov * 100
    print(f"  2-6 커버드콜 {pct:5.2f}%  (상한 {cap}%)  → {'준수' if pct < cap else '🔴 초과'}")
    print(f"      구성: {', '.join(key_of(r) for r in cc)}")
    print("      ※ SCHD 는 배당성장 ETF 로 커버드콜이 아니다. 합산 시 상한 초과로 오판하게 된다.")

    hold = st["principles"]["2-1_영구홀드"]["names"]
    missing = [n for n in hold if find(pf, n) is None]
    print(f"\n  2-1 영구홀드 {len(hold) - len(missing)}/{len(hold)} 보유 중 — 매도·추매 모두 금지")
    if missing:
        print(f"      🔴 목록에 없음: {', '.join(missing)}")

    cand = [r["name"] for m in ("domestic", "overseas") for r in pf[m] if "정예화후보" in r.get("tags", [])]
    print(f"\n  2-6 정예화 후보 {len(cand)}종목: {', '.join(cand)}")


def sec_events(st: dict, today: dt.date) -> None:
    head("다가오는 이벤트")
    dated = [(dt.date.fromisoformat(e["date"]), e) for e in st["events"] if e.get("date")]
    for d, e in sorted(dated):
        if d < today:
            continue
        print(f"  D-{(d - today).days:<3} {d}  [{e['priority']}]  {e['name']}")
    for e in st["events"]:
        if not e.get("date"):
            print(f"  {'미정':<7}          [{e['priority']}]  {e['name']}")


def sec_watch(st: dict) -> None:
    head("감시 목록")
    rt = st["watchlist"]["real_sell_trigger"]
    print(f"  유일한 진짜 매도 트리거: {rt['condition']}")
    print(f"    상태: {rt['status']} — {rt['evidence']}")
    print("\n  신규 감시 항목:")
    for i, item in enumerate(st["watchlist"]["items"], 1):
        print(f"    {i:2}. {item}")


SECTIONS = {
    "summary": sec_summary, "triggers": sec_triggers, "fx": sec_fx,
    "alloc": sec_alloc, "principles": sec_principles, "events": sec_events, "watch": sec_watch,
}


def main() -> None:
    ap = argparse.ArgumentParser(description="원칙·트리거 대비 현재 위치 점검")
    ap.add_argument("--portfolio", type=pathlib.Path, default=HERE / "portfolio.json")
    ap.add_argument("--strategy", type=pathlib.Path, default=HERE / "strategy.json")
    ap.add_argument("--prices", type=pathlib.Path, help="최신 시세 JSON (종목명 또는 티커 → 가격)")
    ap.add_argument("--fx", type=float, help="원달러 환율 (미지정 시 portfolio.json 값)")
    ap.add_argument("--section", choices=sorted(SECTIONS), action="append", help="특정 섹션만 출력")
    args = ap.parse_args()

    pf, st = load(args.portfolio), load(args.strategy)
    stale = "시세 미갱신"
    if args.prices:
        n = apply_prices(pf, load(args.prices))
        stale = f"{n}종목 시세 주입됨"
    fx = args.fx if args.fx else pf.get("fx_usdkrw", 1400.0)
    today = dt.date.today()

    print("=" * W)
    print(f" 포트폴리오 점검  |  스냅샷 {pf['as_of']}  |  실행 {today}")
    print(f" 시세 상태: {stale}  —  매매 실행 전 증권사 화면에서 반드시 재확인할 것")
    print("=" * W)

    for name in (args.section or list(SECTIONS)):
        fn = SECTIONS[name]
        if name in ("summary", "fx"):
            fn(pf, fx) if name == "summary" else fn(st, fx)
        elif name == "events":
            fn(st, today)
        elif name == "watch":
            fn(st)
        else:
            fn(pf, st)
    print()


if __name__ == "__main__":
    main()
