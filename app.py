# -*- coding: utf-8 -*-
"""
app.py — DDoS 모의 훈련 웹 모니터링 : 웹 UI 서버 (Flask)

측정 엔진(web_monitor_drill.py)의 함수를 그대로 재사용하고,
브라우저에서 사이트를 선택/편집하고 실시간 모니터링 결과를 보는
대시보드와 REST API를 제공한다.

실행:
    python app.py                      # http://127.0.0.1:5000
    HOST=0.0.0.0 PORT=8080 python app.py
환경변수:
    SITES_FILE   기본 sites.json 경로 (기본값: 스크립트 폴더의 sites.json)
    HOST, PORT   바인드 주소/포트
"""
from __future__ import annotations

import json
import os
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request

import web_monitor_drill as eng
from monitor_service import MonitorService

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SITES_FILE = os.environ.get("SITES_FILE", os.path.join(APP_DIR, "sites.json"))

app = Flask(__name__)
service = MonitorService()


# --------------------------------------------------------------------------
# sites.json 입출력
# --------------------------------------------------------------------------
def load_sites():
    if not os.path.exists(SITES_FILE):
        return []
    try:
        return eng._load_sites(SITES_FILE)  # 엔진 로더 재사용
    except Exception:
        return []


def save_sites(sites):
    with open(SITES_FILE, "w", encoding="utf-8") as f:
        json.dump(sites, f, ensure_ascii=False, indent=2)


def _normalize_site(raw: dict) -> dict:
    """UI/API에서 들어온 사이트 항목을 엔진이 기대하는 형태로 정규화."""
    url = (raw.get("url") or "").strip()
    if not url:
        raise ValueError("url은 필수입니다.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"올바른 URL이 아닙니다: {url}")

    site = {
        "url": url,
        "ip": (raw.get("ip") or "").strip(),
        "ddos_auth": bool(raw.get("ddos_auth", False)),
        "http2": bool(raw.get("http2", True)),
    }
    if raw.get("check_string"):
        site["check_string"] = str(raw["check_string"])
    if raw.get("impersonate"):
        site["impersonate"] = str(raw["impersonate"])
    if raw.get("resource_timeout"):
        try:
            site["resource_timeout"] = int(raw["resource_timeout"])
        except (TypeError, ValueError):
            pass
    if raw.get("save_path"):
        site["save_path"] = str(raw["save_path"])

    thr = raw.get("alert_thresholds") or {}
    max_ms = thr.get("max_response_time_ms")
    exp = thr.get("expected_status_code")
    norm_thr = {}
    if max_ms not in (None, "", 0):
        norm_thr["max_response_time_ms"] = int(max_ms)
    if exp not in (None, ""):
        norm_thr["expected_status_code"] = int(exp)
    if norm_thr:
        site["alert_thresholds"] = norm_thr
    return site


# --------------------------------------------------------------------------
# 페이지
# --------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


# --------------------------------------------------------------------------
# 사이트 설정 API (sites.json CRUD)
# --------------------------------------------------------------------------
@app.get("/api/sites")
def api_sites_get():
    return jsonify({"sites": load_sites(), "path": SITES_FILE})


@app.post("/api/sites")
def api_sites_save():
    """전체 사이트 목록을 교체 저장. body: {"sites": [...]}"""
    data = request.get_json(silent=True) or {}
    raw_sites = data.get("sites")
    if not isinstance(raw_sites, list):
        return jsonify({"ok": False, "error": "sites 배열이 필요합니다."}), 400
    try:
        normalized = [_normalize_site(s) for s in raw_sites]
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    save_sites(normalized)
    return jsonify({"ok": True, "sites": normalized})


# --------------------------------------------------------------------------
# 모니터링 제어 API
# --------------------------------------------------------------------------
@app.post("/api/monitor/start")
def api_monitor_start():
    """
    body: {
      "urls": ["https://..."],   # 선택한 사이트 URL 목록 (없으면 전체)
      "interval": 3,
      "mode": 1
    }
    선택된 URL은 저장된 sites.json 설정을 사용한다.
    sites.json에 없는 URL이면 기본 설정으로 임시 구성한다.
    """
    data = request.get_json(silent=True) or {}
    interval = data.get("interval", 3)
    mode = data.get("mode", 1)
    urls = data.get("urls")

    all_sites = load_sites()
    by_url = {s["url"]: s for s in all_sites}

    if urls:
        chosen = []
        for u in urls:
            if u in by_url:
                chosen.append(by_url[u])
            else:
                try:
                    chosen.append(_normalize_site({"url": u}))
                except ValueError as e:
                    return jsonify({"ok": False, "error": str(e)}), 400
    else:
        chosen = all_sites

    ok, msg = service.start(chosen, interval=interval, mode=mode)
    status = 200 if ok else 409
    return jsonify({"ok": ok, "message": msg}), status


@app.post("/api/monitor/stop")
def api_monitor_stop():
    ok, msg = service.stop()
    return jsonify({"ok": ok, "message": msg})


@app.get("/api/monitor/status")
def api_monitor_status():
    return jsonify(service.snapshot())


# --------------------------------------------------------------------------
# 엔진 진단 정보
# --------------------------------------------------------------------------
@app.get("/api/engine")
def api_engine():
    return jsonify({
        "version": "v5.1",
        "http2": eng.HAS_H2,
        "httpx": eng.HAS_HTTPX,
        "matplotlib": eng.HAS_MATPLOTLIB,
        "pandas": eng.HAS_PANDAS,
        "bs4": eng.HAS_BS4,
    })


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    print("=" * 70)
    print("  DDoS 모의 훈련 웹 모니터링 — 웹 UI")
    print(f"  http://{host}:{port}")
    print(f"  sites.json: {SITES_FILE}")
    print("=" * 70)
    app.run(host=host, port=port, threaded=True)
