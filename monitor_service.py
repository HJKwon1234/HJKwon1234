# -*- coding: utf-8 -*-
"""
monitor_service.py — 웹 UI용 백그라운드 모니터링 관리자

web_monitor_drill.py(측정 엔진)의 함수를 **그대로 재사용**한다.
엔진의 CLI main() 루프가 수행하던 핵심 로직(FA01 임계값 경고,
FA02 Down/Recovery 전이, FA03 연속 실패)을 콘솔 출력 대신
스레드 안전한 메모리 상태로 유지하여 웹 API로 노출한다.

엔진 자체는 수정하지 않는다. 여기서는 import 후 호출만 한다.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

import web_monitor_drill as eng

# 차트용 히스토리 보관 개수 (사이트별 최근 N 사이클)
HISTORY_MAXLEN = 600
# 최근 경고/이벤트 보관 개수
ALERTS_MAXLEN = 100
# FA03-A: 연속 실패 CRITICAL 임계값 (엔진과 동일 기본값)
CRITICAL_FAIL_THRESHOLD = eng.CRITICAL_FAIL_THRESHOLD


def _serialize(result: dict) -> dict:
    """엔진 result 딕셔너리를 JSON 직렬화 가능한 레코드로 변환."""
    ts = result.get("Timestamp")
    try:
        ts_iso = ts.strftime("%Y-%m-%dT%H:%M:%S")
        ts_ms = ts.strftime("%H:%M:%S")
    except Exception:
        ts_iso = ts_ms = ""
    err = result.get("_error")
    ok = err is None and result.get("Status") == 200
    rec = {
        "url": result.get("URL"),
        "timestamp": ts_iso,
        "clock": ts_ms,
        "status": result.get("Status"),
        "response_time_ms": round(result.get("Total Response Time (ms)", 0.0), 2),
        "http_version": result.get("HTTP Version"),
        "tls_version": result.get("TLS Version"),
        "ip": result.get("IP"),
        "sni": result.get("SNI"),
        "html_size": result.get("HTML Size (B)", 0),
        "resource_size": result.get("Resource Size (B)", 0),
        "total_size": result.get("Total Size (B)", 0),
        "encoding": result.get("Encoding"),
        "check": result.get("_check_str", ""),
        "error": err,
        "ok": ok,
    }
    # Mode 3 지연 분해 세그먼트 (있을 때만)
    if "TCP Open (ms)" in result:
        rec["breakdown"] = {
            "dns": round(result.get("DNS (ms)", 0.0), 2),
            "tcp": round(result.get("TCP Open (ms)", 0.0), 2),
            "tls": round(result.get("TLS Handshake (ms)", 0.0), 2),
            "resp": round(result.get("Server Response (ms)", 0.0), 2),
            "body": round(result.get("Content Load (ms)", 0.0), 2),
        }
    return rec


class _SiteState:
    """사이트별 상태 + 히스토리 누적 컨테이너."""

    def __init__(self, site: dict):
        self.site = site
        self.url = site["url"]
        self.thresholds = site.get("alert_thresholds", {}) or {}
        self.history = deque(maxlen=HISTORY_MAXLEN)
        self.latest = None
        self.total = 0
        self.ok_count = 0
        self.consec_fail = 0
        self.up = True              # FA02 현재 상태 (True=정상)
        self.down_since = None      # 장애 시작 시각(iso)
        self.last_down_sec = None   # 직전 복구 시의 다운타임(초)
        self.sum_rt = 0.0           # 성공 응답시간 합 (평균용)
        self.max_rt = 0.0

    def ingest(self, result: dict, alerts: deque, events: list):
        rec = _serialize(result)
        self.latest = rec
        self.total += 1
        is_ok = rec["ok"]

        # FA01: 임계값 경고
        if rec["error"] is None and self.thresholds:
            max_ms = self.thresholds.get("max_response_time_ms")
            exp_code = self.thresholds.get("expected_status_code", 200)
            if max_ms and rec["response_time_ms"] > max_ms:
                alerts.appendleft({
                    "level": "ALERT", "url": self.url, "clock": rec["clock"],
                    "msg": f"응답시간 {rec['response_time_ms']:.0f}ms > 임계값 {max_ms}ms",
                })
            if rec["status"] != exp_code:
                alerts.appendleft({
                    "level": "ALERT", "url": self.url, "clock": rec["clock"],
                    "msg": f"상태코드 {rec['status']} != 기대값 {exp_code}",
                })

        # FA02: Down/Recovery 전이
        was_ok = self.up
        if was_ok and not is_ok:
            self.down_since = rec["timestamp"]
            events.append({"url": self.url, "start": rec["timestamp"],
                           "start_clock": rec["clock"], "end": None,
                           "end_clock": None, "down_sec": None})
            alerts.appendleft({"level": "DOWN", "url": self.url,
                               "clock": rec["clock"], "msg": "장애 감지"})
        elif not was_ok and is_ok:
            down_sec = None
            for ev in reversed(events):
                if ev["url"] == self.url and ev["end"] is None:
                    ev["end"] = rec["timestamp"]
                    ev["end_clock"] = rec["clock"]
                    try:
                        import datetime as _dt
                        s = _dt.datetime.strptime(ev["start"], "%Y-%m-%dT%H:%M:%S")
                        e = _dt.datetime.strptime(rec["timestamp"], "%Y-%m-%dT%H:%M:%S")
                        down_sec = (e - s).total_seconds()
                    except Exception:
                        down_sec = None
                    ev["down_sec"] = down_sec
                    break
            self.last_down_sec = down_sec
            self.down_since = None
            alerts.appendleft({"level": "RECOVERY", "url": self.url,
                               "clock": rec["clock"],
                               "msg": f"복구 (다운타임 {down_sec:.1f}초)"
                               if down_sec is not None else "복구"})
        self.up = is_ok

        # FA03-A: 연속 실패 카운터
        if not is_ok:
            self.consec_fail += 1
            if self.consec_fail >= CRITICAL_FAIL_THRESHOLD:
                alerts.appendleft({"level": "CRITICAL", "url": self.url,
                                   "clock": rec["clock"],
                                   "msg": f"{self.consec_fail}회 연속 실패 중"})
        else:
            self.consec_fail = 0
            self.ok_count += 1
            self.sum_rt += rec["response_time_ms"]
            self.max_rt = max(self.max_rt, rec["response_time_ms"])

        self.history.append({
            "clock": rec["clock"], "rt": rec["response_time_ms"],
            "status": rec["status"], "ok": is_ok,
        })

    def summary(self) -> dict:
        succ = (self.ok_count / self.total * 100) if self.total else 0.0
        avg = (self.sum_rt / self.ok_count) if self.ok_count else 0.0
        return {
            "url": self.url,
            "up": self.up,
            "total": self.total,
            "ok": self.ok_count,
            "success_rate": round(succ, 1),
            "avg_rt": round(avg, 1),
            "max_rt": round(self.max_rt, 1),
            "consec_fail": self.consec_fail,
            "down_since": self.down_since,
            "last_down_sec": self.last_down_sec,
            "thresholds": self.thresholds,
            "latest": self.latest,
            "history": list(self.history),
            "ddos_auth": bool(self.site.get("ddos_auth")),
            "http2": self.site.get("http2", True),
            "static_ip": self.site.get("ip", ""),
        }


class MonitorService:
    """단일 모니터링 세션을 관리하는 스레드 안전 서비스."""

    def __init__(self):
        self._lock = threading.Lock()
        self._thread = None
        self._stop_evt = threading.Event()
        self.running = False
        self.interval = 3
        self.mode = 1          # 1=HTML, 2=HTML+리소스, 3=지연 분해
        self.started_at = None
        self.cycle = 0
        self._states = {}      # url -> _SiteState
        self._order = []       # url 순서 유지
        self.alerts = deque(maxlen=ALERTS_MAXLEN)
        self.events = []       # 다운타임 이벤트

    # ---- 제어 ---------------------------------------------------------
    def start(self, sites, interval=3, mode=1):
        """sites: 측정할 site 딕셔너리 리스트. 이미 실행 중이면 False."""
        with self._lock:
            if self.running:
                return False, "이미 모니터링이 실행 중입니다."
            if not sites:
                return False, "선택된 사이트가 없습니다."
            self.interval = max(1, int(interval))
            self.mode = int(mode) if int(mode) in (1, 2, 3) else 1
            self._states = {}
            self._order = []
            for s in sites:
                st = _SiteState(s)
                self._states[st.url] = st
                self._order.append(st.url)
            self.alerts.clear()
            self.events = []
            self.cycle = 0
            self.started_at = eng.now_kst().strftime("%Y-%m-%dT%H:%M:%S")
            self._stop_evt.clear()
            self.running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            return True, "모니터링을 시작했습니다."

    def stop(self):
        with self._lock:
            if not self.running:
                return False, "실행 중인 모니터링이 없습니다."
            self._stop_evt.set()
        t = self._thread
        if t:
            t.join(timeout=self.interval + 10)
        with self._lock:
            self.running = False
        return True, "모니터링을 중지했습니다."

    # ---- 백그라운드 루프 ---------------------------------------------
    def _loop(self):
        # 엔진 전역 모드 설정 (엔진 함수 재사용을 위해 디스패처 변수 지정)
        eng.MONITORING_MODE = 2 if self.mode == 2 else 1
        eng.BREAKDOWN_MODE = (self.mode == 3)

        sites = [self._states[u].site for u in self._order]
        # 워밍업: DNS/TLS 사전 적재 (엔진 함수 재사용, 실패해도 무시)
        try:
            eng._warmup_probe(sites)
        except Exception:
            pass

        num = len(sites)
        while not self._stop_evt.is_set():
            self.cycle += 1
            results = [None] * num
            if num == 1:
                s = sites[0]
                results[0] = eng._measure(
                    s["url"], s.get("check_string", ""),
                    s.get("resource_timeout", 10), s.get("ip", ""),
                    not s.get("http2", True), s.get("ddos_auth", False))
            else:
                with ThreadPoolExecutor(max_workers=min(num, 8)) as pool:
                    futs = {}
                    for idx, s in enumerate(sites):
                        if self._stop_evt.is_set():
                            break
                        f = pool.submit(
                            eng._measure, s["url"], s.get("check_string", ""),
                            s.get("resource_timeout", 10), s.get("ip", ""),
                            not s.get("http2", True), s.get("ddos_auth", False))
                        futs[f] = idx
                    for f in as_completed(futs):
                        try:
                            results[futs[f]] = f.result()
                        except Exception:
                            results[futs[f]] = None

            if self._stop_evt.is_set():
                break

            with self._lock:
                for idx, res in enumerate(results):
                    if res is None:
                        continue
                    url = self._order[idx]
                    self._states[url].ingest(res, self.alerts, self.events)

            # interval 만큼 대기 (중지 신호에 즉시 반응)
            self._stop_evt.wait(self.interval)

    # ---- 조회 ---------------------------------------------------------
    def snapshot(self) -> dict:
        with self._lock:
            sites = [self._states[u].summary() for u in self._order]
            total = sum(s["total"] for s in sites)
            ok = sum(s["ok"] for s in sites)
            up_now = sum(1 for s in sites if s["up"])
            succ = (ok / total * 100) if total else 0.0
            avg = (sum(s["avg_rt"] * s["ok"] for s in sites) / ok) if ok else 0.0
            return {
                "running": self.running,
                "interval": self.interval,
                "mode": self.mode,
                "started_at": self.started_at,
                "cycle": self.cycle,
                "sites": sites,
                "alerts": list(self.alerts),
                "events": self.events,
                "aggregate": {
                    "site_count": len(sites),
                    "up_now": up_now,
                    "total_checks": total,
                    "success_rate": round(succ, 1),
                    "avg_rt": round(avg, 1),
                },
            }
