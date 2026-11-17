# -*- coding: utf-8 -*-
"""
smoke_test.py — 로컬 HTTP 서버를 띄우고 웹 UI 전체 흐름을 검증한다.

- 엔진(web_monitor_drill) import
- Flask 테스트 클라이언트로 /api/* 엔드포인트 호출
- 로컬 서버를 대상으로 실제 모니터링을 1~2 사이클 수행 → 200 응답 확인
- 모니터링 중지

외부 네트워크가 필요 없으므로 CI/샌드박스 어디서나 동작한다.
종료 코드 0 = 성공, 1 = 실패.
"""
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

# 리포지토리 루트를 import 경로에 추가
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"<html><body>ok smoke test</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *a):
        pass


def _fail(msg):
    print(f"[FAIL] {msg}")
    sys.exit(1)


def main():
    # 1) 로컬 테스트 서버 기동
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{port}/"
    print(f"[i] 로컬 테스트 서버: {base}")

    # 2) 앱 import (SITES_FILE을 임시 파일로 지정하여 저장소 sites.json 보호)
    tmp_sites = os.path.join(ROOT, "tests", "_tmp_sites.json")
    with open(tmp_sites, "w", encoding="utf-8") as f:
        f.write("[]")
    os.environ["SITES_FILE"] = tmp_sites
    import app as webapp
    client = webapp.app.test_client()

    try:
        # 3) 엔진 진단
        r = client.get("/api/engine")
        assert r.status_code == 200, r.status_code
        print("[OK] /api/engine ->", r.get_json())

        # 4) 사이트 저장 (로컬 서버 대상)
        r = client.post("/api/sites", json={"sites": [
            {"url": base, "ddos_auth": False, "http2": True,
             "alert_thresholds": {"max_response_time_ms": 5000, "expected_status_code": 200}}
        ]})
        assert r.status_code == 200 and r.get_json()["ok"], r.get_data(as_text=True)
        print("[OK] /api/sites 저장")

        r = client.get("/api/sites")
        assert len(r.get_json()["sites"]) == 1
        print("[OK] /api/sites 조회")

        # 5) 모니터링 시작 (http → force_h1 자동)
        r = client.post("/api/monitor/start",
                        json={"urls": [base], "interval": 1, "mode": 1})
        assert r.status_code == 200 and r.get_json()["ok"], r.get_data(as_text=True)
        print("[OK] /api/monitor/start")

        # 6) 몇 사이클 대기 후 상태 확인
        got_ok = False
        last = None
        for _ in range(12):
            time.sleep(0.5)
            snap = client.get("/api/monitor/status").get_json()
            last = snap
            if snap["sites"] and snap["sites"][0]["total"] > 0:
                lt = snap["sites"][0]["latest"]
                if lt and lt["status"] == 200 and lt["ok"]:
                    got_ok = True
                    break
        if not got_ok:
            _fail(f"로컬 서버 200 응답을 받지 못함: {last}")
        s0 = last["sites"][0]
        print(f"[OK] 모니터링 측정 성공: status={s0['latest']['status']} "
              f"rt={s0['latest']['response_time_ms']}ms "
              f"ver={s0['latest']['http_version']} 성공률={s0['success_rate']}%")
        assert last["running"] is True
        assert last["aggregate"]["site_count"] == 1

        # 7) 중지
        r = client.post("/api/monitor/stop")
        assert r.status_code == 200 and r.get_json()["ok"], r.get_data(as_text=True)
        time.sleep(0.3)
        snap = client.get("/api/monitor/status").get_json()
        assert snap["running"] is False
        print("[OK] /api/monitor/stop")

        # 8) 인덱스 페이지 렌더
        r = client.get("/")
        assert r.status_code == 200 and b"DDoS" in r.get_data()
        print("[OK] / (대시보드 렌더)")

        print("\n[PASS] 전체 스모크 테스트 통과")
    finally:
        try:
            webapp.service.stop()
        except Exception:
            pass
        srv.shutdown()
        if os.path.exists(tmp_sites):
            os.remove(tmp_sites)


if __name__ == "__main__":
    main()
