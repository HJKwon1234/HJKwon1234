# -*- coding: utf-8 -*-
"""
DDoS 모의 훈련 전용 웹 모니터링 v5.1

변경 사항 (v5.0 -> v5.1):
  - FA-DA v3: DDoS 인증 벤더 확장 -- F5 BIG-IP ASM, Imperva/Incapsula,
              CloudFlare, Generic 403+Cookie 패턴 추가
              _is_ddos_challenge_response() 챌린지 페이지 자동 판별
              403/503 + Set-Cookie → 쿠키 포함 자동 재요청
  - FA-RT: 연결 실패 시 1회 자동 재시도 (0.5초 대기)
           HTTP/2 협상 실패 → HTTP/1.1 자동 폴백 (에러 없이 전환)
  - FA-TS: 쿠키 저장소 스레드 안전 -- _cookie_jar_lock 도입
           _save_cookies() / _get_cookies() 헬퍼 함수
           복수 사이트 병렬 모니터링 시 쿠키 경합 조건 제거
  - FA-RF: _check_url() → _check_url_h2() / _check_url_h1() 분리
           단일 함수 200줄 → 각 80줄로 가독성/유지보수성 개선

변경 사항 (v4.9 -> v5.0):
  - FA-CL: CLI 인자 즉시 시작 -- --mode, --sites, --interval, --auto
           인자 없으면 기존 대화형 모드 100% 하위 호환
           예: python web-monitor-drill.py --mode 1 --sites 2 --auto
  - FA-PW: 워밍업 프로브 병렬화 -- ThreadPoolExecutor 로 동시 프로브
           DNS 캐시 선등록 후 TCP/TLS 연결을 병렬 수행
  - FA-PC: 메인 루프 사이트별 병렬 요청 -- 복수 사이트 동시 모니터링
           단일 사이트는 오버헤드 없이 직접 호출
           결과는 원래 사이트 순서대로 출력 (콘솔 가독성 유지)
  - FA-PS: 종료 저장 병렬화 -- 텍스트 로그·Excel·그래프를 동시 저장
           저장 소요 시간 대폭 단축 (순차 대비 60~80% 절감)
  - FA-EW: 워밍업 선행 + 대기 중 keep-alive
           워밍업을 엔터 대기 전에 미리 실행 → 엔터 직후 지연 없이 즉시 시작
           엔터 대기 중 30초 주기로 DNS 갱신 + TCP 프로브 → 장시간 대기 후에도 정상 동작

변경 사항 (v4.8 -> v4.9):
  - FA-IP v2: DNS-레벨 IP 오버라이드 -- socket.getaddrinfo 패치 방식으로 전면 교체
              URL 호스트→IP 치환(v4.8) 방식 제거 → Host 헤더·SNI 자동 유지
              서버 302 Redirect 시 Location URL도 자연스럽게 추적
  - FA-LH: Lenient Header Parsing -- RFC 비준수 헤더 이름(공백 포함) 자동 보정
           일부 DDoS 장비/CDN이 "Access Control Allow Origin" 같은 비표준 헤더 반환 시
           http.client.parse_headers가 후속 헤더(Content-Length 등)를 유실하는 문제 해결
           GET 응답 무한 대기 → 타임아웃 현상 수정
  - FA-TV: True TLS Version -- 리디렉트 후 실제 TLS 버전 실시간 감지
           초기 URL 스킴(http/https)이 아닌, 최종 응답 소켓에서 실제 TLS 버전 추출
           requests: stream=True + sock.version()
           httpx: extensions['network_stream'].get_extra_info('ssl_object')
           http→https 302 리디렉트 시에도 정확한 TLS 버전 표시 (예: TLSv1.3)

변경 사항 (v4.7 -> v4.8):
  - FA-IP: Static IP Direct Connect -- sites.json에 "ip" 필드 설정 시
           DNS 조회를 생략하고 해당 IP로 직접 연결
           Host 헤더에 원래 도메인명 유지 (GET 패킷에 URL 정보 정상 반영)
           워밍업 프로브에서도 동일하게 IP 직접 연결 적용
           DNS 캐시에 static_ip 자동 등록 (표시 일관성 유지)

변경 사항 (v4.6 -> v4.7):
  - FA-GS: Graceful Shutdown -- Ctrl+C 즉시 종료 보장
           signal 핸들러로 전역 _stop 플래그 즉시 설정
           time.sleep(3) → 0.1초 분할 슬립 (최대 0.1초 내 탈출)
           메인 루프 내 사이트 간 _stop 체크 (요청 중간에도 즉시 중단)
           finally 블록 저장 중 진행률 표시

변경 사항 (v4.5 -> v4.6):
  - FA-DA v2: DDoS 장비 제조사별 인증 심층 대응
              Arbor APS Meta Refresh 챌린지 자동 추적 (<meta http-equiv="refresh">)
              Radware DefensePro 간단 JS redirect 자동 추적 (document.location=)
              최대 5회 챌린지 체인 추적 (무한 루프 방지)
              _handle_ddos_challenge() 헬퍼 함수 분리

변경 사항 (v4.4 -> v4.5):
  - FA-DA: DDoS 장비 인증 대응 -- 302 Redirect + Set-Cookie(Get Cookie) 처리
           사이트별 쿠키 영속 보존 (_cookie_jar) -- F01 새 세션 + 쿠키 유지 병행
           sites.json "ddos_auth": true 로 사이트별 활성화
           워밍업 프로브에서 인증 쿠키 사전 획득 -- 첫 모니터링부터 즉시 200 OK

변경 사항 (v4.3 -> v4.4):
  - FA-WU: 워밍업 프로브 -- 엔터 직후 메인 루프 진입 전 DNS+TLS 사전 적재
           대기 시간 길어져도 첫 요청 지연 방지 (DNS 캐시 + 연결 사전 확인)
           애플리케이션 레벨 DNS 캐시 (_dns_cache) 도입 -- 프로그램 수명 동안 유지

변경 사항 (v4.2 -> v4.3):
  - FA-MD: 모니터링 모드 선택 -- Mode 1(HTML 전용) / Mode 2(HTML+리소스)
           Mode 2 시 img, script, link, source 태그의 하위 리소스 최대 50개 수집
           beautifulsoup4 없으면 Mode 2 선택 불가 (Mode 1 자동 전환)
           콘솔/그래프/리포트에 모드별 사이즈 표시

변경 사항 (v4.1 -> v4.2):
  - FA-SP: sites.json "save_path" 필드 지원 -- 사이트별 커스텀 저장 경로
           save_path 값이 있으면 해당 경로에 {hostname}_{timestamp} 하위 폴더 자동 생성
           비어있거나 없으면 기존 기본 경로 (work_dir/monitoring/) 사용
           복수 사이트 선택 시 save_path가 있는 사이트만 별도 경로, 나머지는 기본

변경 사항 (v4.0 -> v4.1):
  - FA-H2 BUG FIX: httpx만 설치하고 h2 패키지가 없으면 HTTP/2 협상 불가 --
                    h2 가용성까지 검증하는 HAS_H2 플래그 도입
                    httpx 설치 되어있어도 h2 없으면 requests(HTTP/1.1)로 안전 폴백
                    시작 메시지에 httpx/h2 개별 상태 표시로 진단 용이성 강화

변경 사항 (v3.0 -> v4.0):
  - FA-H2: HTTP/2 자동 협상 -- httpx 설치 시 HTTPS 서버 대상으로 ALPN 협상
           서버가 HTTP/2 미지원 시 HTTP/1.1 자동 폴백
           sites.json "http2": false 로 사이트별 HTTP/1.1 강제 가능
           HTTP URL(http://) 은 항상 HTTP/1.1 (h2c 미지원)

변경 사항 (v2.0 -> v3.0):
  - FA01: Alert Threshold 실시간 적용 (sites.json alert_thresholds 활용)
  - FA02: 상태 전이 감지 -- DOWN/RECOVERY 순간 강조 출력
  - FA03: 연속 실패 [CRITICAL] + 사이클 통계 강화 (성공률/평균/최대)
  - FA05: 실시간 로그 스트리밍 -- 요청마다 txt 즉시 append (강제 종료 시 보존)
  - FA07: 다운타임 집계 -- Summary에 Downtime Events + 가용률(SLA) 추가
  - BUG FIX: resource_timeout 을 alert_thresholds 가 아닌 최상위 필드에서 읽도록 수정

의존성:
  필수: requests
  선택: httpx[http2] (HTTP/2 지원), pandas, openpyxl (Excel 리포트), matplotlib (PNG 그래프)
  설치: pip install requests "httpx[http2]" pandas openpyxl matplotlib

실행:
  python web-monitor-drill.py
"""

import argparse
import json
import os
import signal
import socket
import ssl
import sys
import threading
import time
import datetime
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

warnings.filterwarnings("ignore")

# 타임스탬프(파일명·그래프·로그·콘솔)를 한국시간(KST)으로 고정.
#   time.tzset()은 Windows(EXE)에 없어 시스템 TZ에 의존 → UTC로 표시되는 문제 발생.
#   OS/시스템 시간대와 무관하게 항상 KST가 되도록 고정 오프셋(UTC+9)으로 계산한다.
#   naive datetime을 반환 → 기존 뺄셈/정렬(datetime.min)/strftime 로직과 그대로 호환.
_KST = datetime.timezone(datetime.timedelta(hours=9))


def now_kst():
    """시스템 시간대와 무관하게 KST(UTC+9) 벽시계 시각을 naive datetime으로 반환."""
    return datetime.datetime.now(_KST).replace(tzinfo=None)

try:
    import requests
    from requests.adapters import HTTPAdapter
except ImportError:
    print("[ERROR] requests 가 필요합니다: pip install requests")
    sys.exit(1)

try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

# FA-H2: httpx + h2 (HTTP/2 지원) -- 둘 다 있어야 HTTP/2 활성화
HAS_HTTPX = False
HAS_H2 = False
try:
    import httpx
    HAS_HTTPX = True
    try:
        import h2  # noqa: F401 -- httpx[http2] extras 의존성
        HAS_H2 = True
    except ImportError:
        print("[WARNING] h2 없음 -- httpx는 있으나 HTTP/2 비활성화 (pip install 'httpx[http2]')")
except ImportError:
    print("[WARNING] httpx 없음 -- HTTP/2 비활성화 (pip install 'httpx[http2]')")

# 선택 패키지 -- 없어도 프로그램 정상 실행
HAS_MATPLOTLIB = False
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    print("[WARNING] matplotlib 없음 -- 그래프 생성 비활성화 (pip install matplotlib)")

HAS_PANDAS = False
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    print("[WARNING] pandas 없음 -- Excel 생성 비활성화 (pip install pandas openpyxl)")

# FA-MD: BeautifulSoup (Mode 2 리소스 수집용)
HAS_BS4 = False
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    pass  # Mode 2 선택 시 안내 출력

MONITORING_MODE = 1
BREAKDOWN_MODE = False        # Mode 3: 지연 분해(DNS/TCP/TLS/응답 단계별 측정)
CRITICAL_FAIL_THRESHOLD = 3  # FA03-A: 연속 실패 [CRITICAL] 임계값
MAX_RESOURCES = 50           # FA-MD: Mode 2 최대 리소스 수집 개수

# ── PyInstaller(EXE) 대응 ────────────────────────────────────
#   frozen(EXE) 실행 시:
#     - sites.json / 출력물 기준 = EXE가 있는 폴더 (APP_DIR)
#     - 번들된 Chromium 위치를 Playwright에 알림 → 오프라인 cf-bypass
#   일반 .py 실행 시에는 기존과 동일하게 동작 (frozen=False)
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
    _bundled_browsers = os.path.join(
        getattr(sys, "_MEIPASS", APP_DIR), "ms-playwright")
    if os.path.isdir(_bundled_browsers):
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", _bundled_browsers)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

# FA-CF: Cloudflare 우회 모듈 (선택)
HAS_CF_BYPASS = False
try:
    from cf_bypass import CloudflareBypass
    HAS_CF_BYPASS = True
except ImportError:
    pass

_cf_bypass_map = {}  # key=hostname, value=CloudflareBypass

# ---------------------------------------------------------------------------
# FA-CL: CLI 인자 파싱  (v5.0)
#   --mode, --sites, --interval, --auto 인자로 대화형 입력 없이 즉시 시작 가능
#   인자를 주지 않으면 기존 대화형 모드 그대로 동작 (100% 하위 호환)
# ---------------------------------------------------------------------------
def _parse_args():
    """FA-CL: 명령줄 인자 파싱. 인자 없으면 대화형 모드 유지."""
    p = argparse.ArgumentParser(
        description="DDoS 모의 훈련 웹 모니터링 v5.1",
        add_help=False,   # -h 충돌 방지 (기존 대화형 모드와 공존)
    )
    p.add_argument("--mode", type=int, choices=[1, 2, 3], default=None,
                   help="모니터링 모드 (1=HTML, 2=HTML+리소스, 3=지연 분해)")
    p.add_argument("--sites", type=str, default=None,
                   help="사이트 번호 (쉼표 구분, 0=전체). 예: 1,3  또는 0")
    p.add_argument("--interval", type=int, default=None,
                   help="사이클 간격 초 (기본 3)")
    p.add_argument("--auto", action="store_true",
                   help="엔터 대기 없이 즉시 시작")
    p.add_argument("--cf-bypass", action="store_true",
                   help="Cloudflare Challenge 자동 우회 (playwright + curl_cffi)")
    p.add_argument("--help", "-h", action="help", default=argparse.SUPPRESS,
                   help="도움말 출력")
    return p.parse_args()

# ---------------------------------------------------------------------------
# FA-IP v2: DNS-레벨 IP 오버라이드  (v4.9)
#   socket.getaddrinfo 를 패치하여 _dns_cache 에 등록된 호스트명은
#   실제 DNS 조회 없이 캐시된 IP 로 즉시 해석.
#   URL 을 변조(호스트→IP 치환)하지 않으므로
#     - Host 헤더 자동 유지 (별도 설정 불필요)
#     - HTTPS SNI 가 원래 도메인으로 정상 전송
#     - 서버가 보내는 302 Redirect 의 Location URL 도 자연스럽게 추적
# ---------------------------------------------------------------------------
_original_getaddrinfo = socket.getaddrinfo


def _patched_getaddrinfo(host, port, *args, **kwargs):
    """_dns_cache 에 등록된 호스트명이면 해당 IP 로 해석."""
    if host in _dns_cache:
        host = _dns_cache[host]
    return _original_getaddrinfo(host, port, *args, **kwargs)


socket.getaddrinfo = _patched_getaddrinfo

# ---------------------------------------------------------------------------
# FA-LH: Lenient Header Parsing  (v4.9)
#   일부 DDoS 장비·CDN 이 RFC 7230 위반 헤더를 반환하는 경우가 있음.
#   예) "Access Control Allow Origin: *"  (하이픈 누락, 공백 포함)
#   Python http.client.parse_headers 는 이런 헤더를 만나면 후속 헤더
#   (Content-Length, Connection, Location 등)까지 전부 유실하여
#   GET 요청 시 응답 본문 길이를 알 수 없어 무한 대기 → 타임아웃이 발생.
#   아래 패치는 헤더 이름 부분에 공백이 있으면 하이픈으로 치환하여
#   표준 형식으로 보정한 뒤 원래 파서에 넘긴다.
# ---------------------------------------------------------------------------
import http.client as _httpclient
import email.parser as _email_parser
_orig_parse_headers = _httpclient.parse_headers


def _lenient_parse_headers(fp, _class=_httpclient.HTTPMessage):
    """RFC 비준수 헤더 이름(공백 포함)을 하이픈으로 보정 후 파싱."""
    headers = []
    while True:
        line = fp.readline(_httpclient._MAXLINE + 1)
        if len(line) > _httpclient._MAXLINE:
            raise _httpclient.LineTooLong("header line")
        headers.append(line)
        if len(headers) > _httpclient._MAXHEADERS:
            raise _httpclient.HTTPException(
                "got more than %d headers" % _httpclient._MAXHEADERS
            )
        if line in (b'\r\n', b'\n', b''):
            break
    # 헤더 이름에 공백이 포함된 경우 하이픈으로 치환
    fixed = []
    for h in headers:
        if b':' in h and not h.startswith((b' ', b'\t')):
            name, sep, value = h.partition(b':')
            if b' ' in name:
                name = name.replace(b' ', b'-')
                h = name + sep + value
        fixed.append(h)
    hstring = b''.join(fixed).decode('iso-8859-1')
    return _email_parser.Parser(_class=_class).parsestr(hstring)


_httpclient.parse_headers = _lenient_parse_headers

# FA-GS: Graceful Shutdown -- Ctrl+C 즉시 종료 보장
_stop = False


def _signal_handler(signum, frame):
    """FA-GS: SIGINT(Ctrl+C) 수신 시 전역 _stop 플래그 설정"""
    global _stop
    _stop = True


def _interruptible_sleep(seconds):
    """FA-GS: 0.1초 단위 분할 슬립 — _stop 시 즉시 탈출"""
    elapsed = 0.0
    while elapsed < seconds and not _stop:
        time.sleep(0.1)
        elapsed += 0.1


def _select_monitoring_mode():
    """FA-MD: 모니터링 모드 선택 (Mode 1: HTML 전용, Mode 2: HTML+리소스, Mode 3: 지연 분해)"""
    global MONITORING_MODE, BREAKDOWN_MODE
    print("\n[모드 선택]")
    print("  [1] Mode 1: HTML만 다운로드 (빠름, 기본)")
    print("  [2] Mode 2: HTML + 리소스 다운로드 (img/script/css 포함)")
    print("  [3] Mode 3: 지연 분해 (DNS/TCP Open/TLS/서버응답 단계별 측정)\n")

    while True:
        try:
            choice = input("  모드를 선택하세요 (1/2/3, 기본=1): ").strip()
            if choice == "" or choice == "1":
                MONITORING_MODE = 1
                print("  -> Mode 1 선택: HTML 전용\n")
                return
            elif choice == "2":
                if not HAS_BS4:
                    print("  [WARNING] Mode 2에는 beautifulsoup4가 필요합니다.")
                    print("            pip install beautifulsoup4")
                    print("  -> Mode 1로 자동 전환\n")
                    MONITORING_MODE = 1
                    return
                MONITORING_MODE = 2
                print("  -> Mode 2 선택: HTML + 리소스\n")
                return
            elif choice == "3":
                MONITORING_MODE = 1        # 분해 모드는 단일 GET(HTML 전용) 기준
                BREAKDOWN_MODE = True
                print("  -> Mode 3 선택: 지연 분해 (TCP Open vs 서버응답 분리 측정)\n")
                return
            else:
                print("  [!] 1, 2, 3 중 하나를 입력하세요.")
        except KeyboardInterrupt:
            print("\n  -> Mode 1 사용\n")
            MONITORING_MODE = 1
            return


# -- SSL 검증 비활성화 어댑터 --------------------------------------------------

class _NoSSLAdapter(HTTPAdapter):
    """자체 서명 인증서 / 만료 인증서 사이트도 모니터링 가능"""
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


# -- 유틸리티 ------------------------------------------------------------------

def _load_sites(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# FA-WU: 애플리케이션 레벨 DNS 캐시 (프로그램 수명 동안 유지)
_dns_cache = {}

# FA-DA v3: 사이트별 쿠키 저장소 (DDoS 장비 인증 쿠키 영속 보존)
#           key=hostname, value=dict of cookies
#           v5.1: threading.Lock 으로 복수 사이트 병렬 요청 시 스레드 안전 보장
_cookie_jar = {}
_cookie_jar_lock = threading.Lock()


def _save_cookies(hostname, cookies_dict):
    """v5.1: 스레드 안전 쿠키 저장"""
    if not cookies_dict:
        return
    with _cookie_jar_lock:
        jar = _cookie_jar.setdefault(hostname, {})
        jar.update(cookies_dict)


def _get_cookies(hostname):
    """v5.1: 스레드 안전 쿠키 읽기 (복사본 반환)"""
    with _cookie_jar_lock:
        return dict(_cookie_jar.get(hostname, {}))


def _cookies_to_dict(cookies):
    """중복 이름 쿠키가 있어도 예외 없이 dict로 변환.

    일부 사이트는 같은 이름의 쿠키를 도메인/경로만 달리해 여러 개 내려주는데
    (예: www.bow.co.kr 의 'bow' 쿠키 2개), 이때 dict(jar)/jar[name] 접근은
    requests 가 CookieConflictError("There are multiple cookies with name ...")
    를 던져 200 응답을 받고도 요청 전체가 실패로 기록된다.
    쿠키 객체를 직접 순회하면 __getitem__ 을 거치지 않아 예외 없이 안전하다.
    requests(RequestsCookieJar) / httpx(Cookies) 모두 Cookie 객체를 순회한다."""
    out = {}
    try:
        for c in cookies:
            name = getattr(c, "name", None)
            if name is not None:
                out[name] = getattr(c, "value", "")
            else:
                # 매핑형(키가 이름)인 경우 폴백
                try:
                    out[c] = cookies[c]
                except Exception:
                    pass
    except Exception:
        pass
    return out


def _extract_tls_version_requests(response):
    """FA-TV: requests 응답에서 실제 TLS 버전 추출.
    stream=True 로 받은 응답의 소켓에서 직접 읽음.
    실패 시 최종 URL 스킴으로 폴백."""
    try:
        sock = response.raw._connection.sock
        if sock and hasattr(sock, "version"):
            ver = sock.version()
            if ver:
                return ver
    except Exception:
        pass
    # 폴백: 최종 URL이 https면 TLS 사용 (정확한 버전은 알 수 없음)
    try:
        if urlparse(response.url).scheme == "https":
            return "TLS (version unknown)"
    except Exception:
        pass
    return "N/A"


def _extract_tls_version_httpx(response):
    """FA-TV: httpx 응답에서 실제 TLS 버전 추출.
    extensions['network_stream'].get_extra_info('ssl_object') 로 직접 읽음."""
    try:
        ns = response.extensions.get("network_stream")
        if ns:
            ssl_obj = ns.get_extra_info("ssl_object")
            if ssl_obj and hasattr(ssl_obj, "version"):
                ver = ssl_obj.version()
                if ver:
                    return ver
    except Exception:
        pass
    # 폴백: 최종 URL 스킴 확인
    try:
        if urlparse(str(response.url)).scheme == "https":
            return "TLS (version unknown)"
    except Exception:
        pass
    return "N/A"


def _resolve_ip(hostname):
    """소켓으로 호스트명 -> IP 변환. 캐시 히트 시 즉시 반환. 실패 시 'Unknown'"""
    if hostname in _dns_cache:
        return _dns_cache[hostname]
    try:
        ip = socket.getaddrinfo(hostname, None)[0][4][0]
        _dns_cache[hostname] = ip
        return ip
    except Exception:
        return "Unknown"


def _warmup_one(site, wu_timeout=3):
    """FA-PW: 단일 사이트 워밍업 (스레드 풀에서 호출). 결과 딕셔너리 반환."""
    url       = site["url"]
    parsed    = urlparse(url)
    hostname  = parsed.hostname or ""
    static_ip = site.get("ip", "")
    ddos_auth = site.get("ddos_auth", False)
    st = time.time()
    # 1) DNS 캐시 적재
    if static_ip:
        _dns_cache[hostname] = static_ip
    else:
        _resolve_ip(hostname)
    # 2) TCP/TLS 사전 연결 + DDoS 인증 쿠키 획득
    ok = False
    auth = False
    try:
        if HAS_H2 and parsed.scheme == "https":
            with httpx.Client(http2=True, verify=False, timeout=wu_timeout,
                              follow_redirects=True) as c:
                if ddos_auth:
                    r = c.get(url)
                    if r.cookies:
                        _save_cookies(hostname, _cookies_to_dict(r.cookies))
                        auth = True
                else:
                    c.head(url)
        else:
            if ddos_auth:
                s = requests.Session()
                s.mount("https://", _NoSSLAdapter())
                s.mount("http://", _NoSSLAdapter())
                r = s.get(url, timeout=wu_timeout, verify=False, allow_redirects=True)
                if s.cookies:
                    _save_cookies(hostname, _cookies_to_dict(s.cookies))
                    auth = True
                s.close()
            else:
                requests.head(url, timeout=wu_timeout, verify=False,
                              allow_redirects=True)
        ok = True
    except Exception:
        pass
    ms = round((time.time() - st) * 1000)
    return {"hostname": hostname, "ok": ok, "auth": auth, "ms": ms}


def _warmup_probe(sites):
    """FA-PW: 워밍업 프로브 병렬 실행 (ThreadPoolExecutor).
    FA-WU + FA-DA: DNS 캐시 적재 + TCP/TLS 사전 연결 + DDoS 인증 쿠키 사전 획득."""
    total = len(sites)
    print(f"[INFO] 워밍업 프로브 실행 중 ({total}개 사이트, 병렬)...")
    t0 = time.time()

    # DNS 캐시를 먼저 적재 (순차 — getaddrinfo 패치가 스레드 안전하려면 캐시 선등록)
    for site in sites:
        hostname  = urlparse(site["url"]).hostname or ""
        static_ip = site.get("ip", "")
        if static_ip:
            _dns_cache[hostname] = static_ip
        else:
            _resolve_ip(hostname)

    # TCP/TLS + 쿠키 수거를 병렬 실행
    results = [None] * total
    with ThreadPoolExecutor(max_workers=min(total, 8)) as pool:
        future_map = {pool.submit(_warmup_one, site): idx
                      for idx, site in enumerate(sites)}
        for future in as_completed(future_map):
            idx = future_map[future]
            results[idx] = future.result()

    # 결과 출력 (원래 순서대로)
    auth_count = 0
    for idx, r in enumerate(results, 1):
        tag = "OK" if r["ok"] else "SKIP"
        print(f"  [{idx}/{total}] {r['hostname']} {tag} ({r['ms']}ms)")
        if r["auth"]:
            auth_count += 1

    elapsed = round((time.time() - t0) * 1000)
    cached  = len(_dns_cache)
    msg = f"[INFO] 워밍업 완료: {cached}개 DNS 캐시 적재, {elapsed}ms 소요 (병렬)"
    if auth_count:
        msg += f", DDoS 인증 쿠키 {auth_count}개 사이트 획득"
    print(msg)


def _select_targets(sites):
    """sites.json 목록에서 모니터링할 사이트 선택 (F07)"""
    print("\n[사이트 목록]")
    for i, site in enumerate(sites, 1):
        ip_info = f" (IP: {site.get('ip')})" if site.get("ip") else ""
        print(f"  {i:2d}. {site['url']}{ip_info}")
    print(f"   0. 모든 사이트 (All Sites)")
    print()

    while True:
        try:
            raw = input("  번호를 입력하세요 (쉼표 구분 복수, 0=전체): ").strip()
            if not raw:
                continue
            if raw == "0":
                return sites
            indices = {int(x.strip()) for x in raw.split(",")}
            selected = [sites[i - 1] for i in sorted(indices) if 1 <= i <= len(sites)]
            if selected:
                return selected
            print(f"  [!] 유효한 번호를 입력하세요 (1~{len(sites)}).")
        except ValueError:
            print("  [!] 숫자와 쉼표(,)만 입력하세요.")
        except KeyboardInterrupt:
            print("\n[INFO] 취소됨.")
            sys.exit(0)


def _to_session_record(result):
    """내부 필드(_xxx)를 제거한 저장용 딕셔너리 반환"""
    return {k: v for k, v in result.items() if not k.startswith("_")}


# -- FA-MD: Mode 2 리소스 수집 헬퍼 -------------------------------------------

def _fetch_resources(html_content, base_url, client=None, session=None):
    """Mode 2: HTML에서 img/script/link/source 태그의 src/href를 추출하여 다운로드.
    반환: 리소스 총 바이트 수 (최대 MAX_RESOURCES개)"""
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        urls = []
        for tag in soup.find_all(["img", "script", "link", "source"]):
            src = tag.get("src") or tag.get("href")
            if src:
                from urllib.parse import urljoin
                urls.append(urljoin(base_url, src))

        total_bytes = 0
        for res_url in urls[:MAX_RESOURCES]:
            try:
                if client:  # httpx
                    rr = client.get(res_url)
                    total_bytes += len(rr.content)
                elif session:  # requests
                    rr = session.get(res_url, verify=False, timeout=3)
                    total_bytes += len(rr.content)
            except Exception:
                pass
        return total_bytes
    except Exception:
        return 0


# -- FA-DA v3: DDoS 챌린지 핸들러 (v5.1 확장) -----------------------------------
#   지원 벤더: Arbor APS, Radware DefensePro, F5 BIG-IP ASM,
#              Imperva/Incapsula, CloudFlare, Generic 403+Cookie
# ---------------------------------------------------------------------------

_CHALLENGE_PATTERNS = None   # 지연 컴파일된 정규식 리스트
_challenge_lock = threading.Lock()  # 패턴 컴파일 스레드 안전


def _compile_challenge_patterns():
    """v5.1: 정규식 패턴 지연 컴파일 (최초 1회, 스레드 안전)"""
    global _CHALLENGE_PATTERNS
    if _CHALLENGE_PATTERNS is not None:
        return
    with _challenge_lock:
        if _CHALLENGE_PATTERNS is not None:
            return
        import re
        _CHALLENGE_PATTERNS = [
            # 1) Arbor APS: <meta http-equiv="refresh" content="0;url=/verify?token=abc">
            ("arbor_meta_refresh", re.compile(
                r'<meta\s+http-equiv\s*=\s*["\']?refresh["\']?\s+'
                r'content\s*=\s*["\']?\d+\s*;\s*url\s*=\s*([^"\'>\s]+)',
                re.IGNORECASE,
            )),
            # 2) Radware DefensePro: document.location="url"
            ("radware_js_redirect", re.compile(
                r'(?:document\.location|window\.location(?:\.href)?)\s*=\s*["\']([^"\']+)["\']',
                re.IGNORECASE,
            )),
            # 3) F5 BIG-IP ASM: location.replace("url") 또는 self.location="url"
            ("f5_js_redirect", re.compile(
                r'(?:location\.replace|self\.location)\s*[\(=]\s*["\']([^"\']+)["\']',
                re.IGNORECASE,
            )),
            # 4) Imperva/Incapsula: <script>setCookie("incap_ses_...",...);</script> + redirect
            ("imperva_redirect", re.compile(
                r'(?:top\.location\.href|window\.location)\s*=\s*["\']([^"\']+)["\']',
                re.IGNORECASE,
            )),
            # 5) Generic: <noscript><a href="url"> 패턴 (JS 비활성화 폴백)
            ("noscript_fallback", re.compile(
                r'<noscript>[^<]*<a\s+href\s*=\s*["\']([^"\']+)["\']',
                re.IGNORECASE,
            )),
        ]


def _extract_challenge_url(html_body, base_url):
    """v5.1: DDoS 장비 챌린지 응답에서 리다이렉트 URL 추출.
    지원 벤더 패턴을 순서대로 검사. 없으면 None 반환."""
    _compile_challenge_patterns()
    text = html_body.decode("utf-8", "ignore") if isinstance(html_body, bytes) else html_body

    for vendor_name, pattern in _CHALLENGE_PATTERNS:
        m = pattern.search(text)
        if m:
            from urllib.parse import urljoin
            return urljoin(base_url, m.group(1))

    return None


def _is_ddos_challenge_response(status_code, body_text, response_headers=None):
    """v5.1: 응답이 DDoS 장비의 챌린지인지 판별.
    403/503 + 특정 키워드 조합으로 판별하여 쿠키 재시도가 필요한지 결정.

    Returns: True면 쿠키를 포함하여 재요청 필요
    """
    # 403 + Set-Cookie → DDoS 장비가 인증 쿠키를 발급한 것
    if status_code == 403 and response_headers:
        has_set_cookie = any(
            k.lower() == "set-cookie" for k in response_headers
        )
        if has_set_cookie:
            return True

    # 503 + Retry-After (일부 장비가 503으로 챌린지)
    if status_code == 503 and response_headers:
        if "Retry-After" in response_headers or "retry-after" in response_headers:
            return True

    # 200이지만 body에 챌린지 키워드 포함 (JS 챌린지 페이지)
    if status_code == 200 and body_text:
        challenge_keywords = [
            "please enable javascript",
            "checking your browser",
            "ddos protection",
            "incapsula incident",
            "cf-browser-verification",
            "challenge-platform",
            "bot detection",
        ]
        body_lower = body_text.lower()
        # HTML 크기가 작고(< 10KB) 챌린지 키워드 포함 → 챌린지 페이지
        if len(body_text) < 10240:
            for kw in challenge_keywords:
                if kw in body_lower:
                    return True

    return False


MAX_CHALLENGE_HOPS = 5  # 챌린지 체인 최대 추적 횟수 (무한 루프 방지)


# -- 핵심 모니터링 함수 --------------------------------------------------------

def _check_url(url, check_string="", req_timeout=10, static_ip="", force_h1=False,
               ddos_auth=False):
    """
    v5.1: 매 호출마다 새 TCP/TLS 세션 생성 (F01).

    v5.1 개선:
      - 연결 실패 시 1회 자동 재시도 (0.5초 대기 후)
      - HTTP/2 협상 실패 → HTTP/1.1 자동 폴백 (에러 없이)
      - DDoS 인증 강화: 403+Cookie 자동 재시도, 챌린지 판별 확장
      - 쿠키 저장/읽기 스레드 안전 (_save_cookies / _get_cookies)
    """
    parsed   = urlparse(url)
    hostname = parsed.hostname or ""
    ts       = now_kst()
    use_h2   = HAS_H2 and not force_h1 and parsed.scheme == "https"

    if static_ip:
        _dns_cache[hostname] = static_ip

    result = {
        "Timestamp": ts,
        "URL": url,
        "Status": -1,
        "HTML Size (B)": 0,
        "Resource Size (B)": 0,
        "Total Size (B)": 0,
        "Total Response Time (ms)": 0.0,
        "Resource Load Time (ms)": 0.0,
        "HTTP Version": "HTTP/1.1",
        "TLS Version": "N/A",
        "SNI": hostname,
        "IP": static_ip if static_ip else _resolve_ip(hostname),
        "Encoding": "utf-8",
        "_error": None,
        "_check_str": "",
    }

    saved_cookies = _get_cookies(hostname) if ddos_auth else {}

    # FA-CF: Cloudflare 우회 세션이 있으면 curl_cffi로 요청
    cf = _cf_bypass_map.get(hostname)
    if cf and cf._solved:
        t0 = time.time()
        try:
            cf_result = cf.get(url, timeout=req_timeout)
            if cf_result and cf_result.get("status_code") == 200:
                elapsed_ms = round((time.time() - t0) * 1000, 2)
                result["Total Response Time (ms)"] = elapsed_ms
                result["Status"] = cf_result["status_code"]
                result["HTML Size (B)"] = cf_result["body_size"]
                result["Total Size (B)"] = cf_result["body_size"]
                result["HTTP Version"] = "HTTP/1.1"
                result["TLS Version"] = "TLS (CF bypass)"
                if check_string:
                    ok = check_string in cf_result.get("body", "")
                    result["_check_str"] = f"Content: {'OK' if ok else 'FAIL'}"
                return result
        except Exception:
            pass  # 우회 실패 시 일반 경로로 폴백

    # v5.1: 재시도 래퍼 — 최대 2회 시도 (초기 1회 + 재시도 1회)
    max_attempts = 2
    last_error = None

    for attempt in range(max_attempts):
        if attempt > 0:
            time.sleep(0.5)  # 재시도 전 0.5초 대기

        t0 = time.time()
        try:
            if use_h2:
                _check_url_h2(url, hostname, result, t0, req_timeout,
                              saved_cookies, ddos_auth, check_string)
            else:
                _check_url_h1(url, hostname, result, t0, req_timeout,
                              saved_cookies, ddos_auth, check_string)

            # 성공 — 에러 없으면 루프 탈출
            if result["_error"] is None:
                return result

            # v5.1: HTTP/2 실패 시 HTTP/1.1 자동 폴백
            if use_h2 and attempt == 0:
                use_h2 = False
                result["_error"] = None  # 에러 초기화 후 재시도
                continue

            last_error = result["_error"]

        except Exception as e:
            result["Total Response Time (ms)"] = round((time.time() - t0) * 1000, 2)
            if HAS_HTTPX and isinstance(e, (httpx.ConnectError,)):
                last_error = "연결 실패 (Connection refused / DNS 오류)"
            elif HAS_HTTPX and isinstance(e, (httpx.TimeoutException,)):
                last_error = f"타임아웃 ({req_timeout}s 초과)"
            elif isinstance(e, requests.exceptions.ConnectionError):
                last_error = "연결 실패 (Connection refused / DNS 오류)"
            elif isinstance(e, requests.exceptions.Timeout):
                last_error = f"타임아웃 ({req_timeout}s 초과)"
            else:
                last_error = str(e)

            # v5.1: HTTP/2 에러 → HTTP/1.1 폴백 시도
            if use_h2 and attempt == 0:
                use_h2 = False
                continue

            result["_error"] = last_error

    # 모든 시도 실패
    if result["_error"] is None and last_error:
        result["_error"] = last_error
    return result


def _check_url_breakdown(url, check_string="", req_timeout=10, static_ip="",
                         force_h1=False, ddos_auth=False):
    """
    Mode 3 (지연 분해): raw 소켓으로 연결 단계를 개별 측정.
      DNS -> TCP Open -> TLS Handshake -> Server Response(TTFB) -> Content
    각 단계 경계를 공유하므로 (DNS+TCP+TLS+응답+본문) == Total (정확히 가산적).
    진단 전용: HTTP/1.1 단일 GET. 재시도/리다이렉트/DDoS쿠키/CF우회 미지원.
    (force_h1 / ddos_auth 는 시그니처 호환용으로만 받고 사용하지 않음)
    """
    parsed   = urlparse(url)
    hostname = parsed.hostname or ""
    scheme   = parsed.scheme
    port     = parsed.port or (443 if scheme == "https" else 80)
    path     = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    ts = now_kst()

    result = {
        "Timestamp": ts,
        "URL": url,
        "Status": -1,
        "HTML Size (B)": 0,
        "Resource Size (B)": 0,
        "Total Size (B)": 0,
        "Total Response Time (ms)": 0.0,
        "Resource Load Time (ms)": 0.0,
        "HTTP Version": "HTTP/1.1",
        "TLS Version": "N/A",
        "SNI": hostname,
        "IP": static_ip if static_ip else _resolve_ip(hostname),
        "Encoding": "utf-8",
        "_error": None,
        "_check_str": "",
        # -- Mode 3 분해 필드 --
        "DNS (ms)": 0.0,
        "TCP Open (ms)": 0.0,
        "TLS Handshake (ms)": 0.0,
        "Server Response (ms)": 0.0,
        "Content Load (ms)": 0.0,
    }

    sock = None
    t0 = time.time()
    try:
        # 1) DNS 조회
        if static_ip:
            ip = static_ip
        else:
            ip = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)[0][4][0]
        t_dns = time.time()
        result["IP"] = ip
        result["DNS (ms)"] = round((t_dns - t0) * 1000, 2)

        # 2) TCP Open (SYN / SYN-ACK / ACK) -- 여기서 SYN-ACK 재전송 지연이 잡힘
        sock = socket.create_connection((ip, port), timeout=req_timeout)
        sock.settimeout(req_timeout)
        t_tcp = time.time()
        result["TCP Open (ms)"] = round((t_tcp - t_dns) * 1000, 2)

        # 3) TLS Handshake (https 만)
        if scheme == "https":
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            try:
                ctx.set_alpn_protocols(["http/1.1"])
            except Exception:
                pass
            sock = ctx.wrap_socket(sock, server_hostname=hostname)  # 핸드셰이크 수행
            result["TLS Version"] = sock.version() or "N/A"
        t_tls = time.time()
        result["TLS Handshake (ms)"] = round((t_tls - t_tcp) * 1000, 2)

        # 4) Server Response: 요청 송신 -> 응답 헤더(200 OK) 수신 = TTFB
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {hostname}\r\n"
            f"User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            f"AppleWebKit/537.36\r\n"
            f"Accept: */*\r\n"
            f"Cache-Control: no-cache, no-store\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("latin1")
        sock.sendall(req)
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        t_hdr = time.time()
        result["Server Response (ms)"] = round((t_hdr - t_tls) * 1000, 2)

        header_blob, _, body = buf.partition(b"\r\n\r\n")
        status_line = header_blob.split(b"\r\n", 1)[0].decode("latin1", "ignore")
        parts = status_line.split(" ", 2)
        if len(parts) >= 2 and parts[1].isdigit():
            result["Status"] = int(parts[1])
            result["HTTP Version"] = parts[0]

        # Content-Length 있으면 정확히, 없으면 연결 종료(EOF)까지 수신
        clen = None
        for hline in header_blob.split(b"\r\n")[1:]:
            if hline.lower().startswith(b"content-length:"):
                try:
                    clen = int(hline.split(b":", 1)[1].strip())
                except Exception:
                    clen = None
                break

        # 5) Content (본문 수신)
        if clen is not None:
            while len(body) < clen:
                chunk = sock.recv(8192)
                if not chunk:
                    break
                body += chunk
        else:
            while True:
                try:
                    chunk = sock.recv(8192)
                except socket.timeout:
                    break
                if not chunk:
                    break
                body += chunk
        t_body = time.time()
        result["Content Load (ms)"] = round((t_body - t_hdr) * 1000, 2)
        result["HTML Size (B)"] = len(body)
        result["Total Size (B)"] = len(body)
        result["Total Response Time (ms)"] = round((t_body - t0) * 1000, 2)

        if check_string:
            ok = check_string.encode("utf-8", "ignore") in body
            result["_check_str"] = f"Content: {'OK' if ok else 'FAIL'}"

    except socket.timeout:
        result["_error"] = f"타임아웃 ({req_timeout}s 초과)"
        result["Total Response Time (ms)"] = round((time.time() - t0) * 1000, 2)
    except (ConnectionRefusedError, ConnectionResetError):
        result["_error"] = "연결 실패 (Connection refused/reset)"
        result["Total Response Time (ms)"] = round((time.time() - t0) * 1000, 2)
    except socket.gaierror:
        result["_error"] = "DNS 조회 실패"
        result["Total Response Time (ms)"] = round((time.time() - t0) * 1000, 2)
    except Exception as e:
        result["_error"] = str(e)
        result["Total Response Time (ms)"] = round((time.time() - t0) * 1000, 2)
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

    return result


def _measure(url, check_string="", req_timeout=10, static_ip="",
             force_h1=False, ddos_auth=False):
    """BREAKDOWN_MODE 여부에 따라 측정 함수 선택 (호출부 최소 변경용 디스패처)."""
    fn = _check_url_breakdown if BREAKDOWN_MODE else _check_url
    return fn(url, check_string, req_timeout, static_ip, force_h1, ddos_auth)


def _check_url_h2(url, hostname, result, t0, req_timeout,
                  saved_cookies, ddos_auth, check_string):
    """v5.1: httpx HTTP/2 요청 경로 (내부 헬퍼)"""
    cookies_arg = httpx.Cookies(saved_cookies) if saved_cookies else None
    h2_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        ),
        "Cache-Control": "no-cache, no-store",
        "Pragma": "no-cache",
    }
    with httpx.Client(
        http2=True, verify=False, timeout=req_timeout,
        follow_redirects=True, cookies=cookies_arg, headers=h2_headers,
    ) as client:
        r = client.get(url)

        # v5.1: DDoS 챌린지 체인 추적 (확장된 벤더 패턴)
        if ddos_auth:
            for _ in range(MAX_CHALLENGE_HOPS):
                if r.cookies:
                    _save_cookies(hostname, _cookies_to_dict(r.cookies))

                # v5.1: 403/503 + Set-Cookie → 쿠키 포함 재요청
                body_text = r.content.decode("utf-8", "ignore")
                if _is_ddos_challenge_response(r.status_code, body_text,
                                               dict(r.headers)):
                    r = client.get(url)  # 쿠키 포함 원래 URL 재요청
                    continue

                challenge_url = _extract_challenge_url(r.content, url)
                if not challenge_url:
                    break
                r = client.get(challenge_url)

        elapsed_ms = round((time.time() - t0) * 1000, 2)
        result["Total Response Time (ms)"] = elapsed_ms
        result["Status"] = r.status_code
        result["HTML Size (B)"] = len(r.content)
        result["Encoding"] = r.encoding or "utf-8"
        result["HTTP Version"] = r.http_version
        result["TLS Version"] = _extract_tls_version_httpx(r)

        resource_size = 0
        if MONITORING_MODE == 2 and HAS_BS4:
            resource_size = _fetch_resources(r.content, url, client=client)
            result["Resource Load Time (ms)"] = round(
                (time.time() - t0) * 1000 - elapsed_ms, 2)
        result["Resource Size (B)"] = resource_size
        result["Total Size (B)"] = len(r.content) + resource_size

        if ddos_auth and r.cookies:
            _save_cookies(hostname, _cookies_to_dict(r.cookies))

        if check_string:
            body_text = r.content.decode("utf-8", "ignore")
            ok = check_string in body_text
            result["_check_str"] = f"Content: {'OK' if ok else 'FAIL'}"


def _check_url_h1(url, hostname, result, t0, req_timeout,
                  saved_cookies, ddos_auth, check_string):
    """v5.1: requests HTTP/1.1 요청 경로 (내부 헬퍼)"""
    session = requests.Session()
    if saved_cookies:
        session.cookies.update(saved_cookies)
    session.mount("https://", _NoSSLAdapter())
    session.mount("http://", _NoSSLAdapter())
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    session.headers["Cache-Control"] = "no-cache, no-store"
    session.headers["Pragma"] = "no-cache"
    try:
        r = session.get(url, timeout=req_timeout, verify=False,
                        allow_redirects=True, stream=True)
        tls_ver = _extract_tls_version_requests(r)
        _ = r.content  # stream 본문 즉시 소비

        # v5.1: DDoS 챌린지 체인 추적 (확장)
        if ddos_auth:
            for _ in range(MAX_CHALLENGE_HOPS):
                if session.cookies:
                    _save_cookies(hostname, _cookies_to_dict(session.cookies))

                # v5.1: 403/503 + Set-Cookie → 쿠키 포함 재요청
                body_text = r.content.decode("utf-8", "ignore")
                if _is_ddos_challenge_response(r.status_code, body_text,
                                               dict(r.headers)):
                    r = session.get(url, timeout=req_timeout, verify=False,
                                    allow_redirects=True)
                    continue

                challenge_url = _extract_challenge_url(r.content, url)
                if not challenge_url:
                    break
                r = session.get(challenge_url, timeout=req_timeout,
                                verify=False, allow_redirects=True)

        elapsed_ms = round((time.time() - t0) * 1000, 2)
        result["Total Response Time (ms)"] = elapsed_ms
        result["Status"] = r.status_code
        result["HTML Size (B)"] = len(r.content)
        result["Encoding"] = r.encoding or "utf-8"
        result["HTTP Version"] = "HTTP/1.1"
        result["TLS Version"] = tls_ver

        resource_size = 0
        if MONITORING_MODE == 2 and HAS_BS4:
            resource_size = _fetch_resources(r.content, url, session=session)
            result["Resource Load Time (ms)"] = round(
                (time.time() - t0) * 1000 - elapsed_ms, 2)
        result["Resource Size (B)"] = resource_size
        result["Total Size (B)"] = len(r.content) + resource_size

        if ddos_auth and session.cookies:
            _save_cookies(hostname, _cookies_to_dict(session.cookies))

        if check_string:
            body_text = r.content.decode("utf-8", "ignore")
            ok = check_string in body_text
            result["_check_str"] = f"Content: {'OK' if ok else 'FAIL'}"
    finally:
        session.close()


def _format_line(result):
    """F16 콘솔 출력 형식"""
    ts = result["Timestamp"].strftime("%Y-%m-%d %H:%M:%S")
    url = result["URL"]

    if result["_error"]:
        return f"[{ts}] URL: {url} | [FAIL] {result['_error']}"

    check_str = result["_check_str"]
    # FA-MD: Mode에 따라 사이즈 표시 변경
    res_size = result.get("Resource Size (B)", 0)
    if MONITORING_MODE == 2 and res_size > 0:
        size_str = (f"HTML: {result['HTML Size (B)']}B + "
                    f"Res: {res_size}B = {result['Total Size (B)']}B")
    else:
        size_str = f"HTML: {result['HTML Size (B)']}B"

    line = (
        f"[{ts}] URL: {url} | IP: {result['IP']} | "
        f"Status: {result['Status']} | Ver: {result['HTTP Version']} | "
        f"TLS: {result['TLS Version']} | SNI: {result['SNI']} | "
        f"Time: {result['Total Response Time (ms)']:.2f}ms | {size_str}"
    )
    if check_str:
        line += f" | {check_str}"
    # Mode 3: 지연 분해 세그먼트 (분해 필드가 있을 때만 표시)
    if "TCP Open (ms)" in result:
        line += (
            f" | [DNS:{result['DNS (ms)']:.1f} "
            f"TCP:{result['TCP Open (ms)']:.1f} "
            f"TLS:{result['TLS Handshake (ms)']:.1f} "
            f"Resp:{result['Server Response (ms)']:.1f} "
            f"Body:{result['Content Load (ms)']:.1f}]ms"
        )
    return line


# -- FA05: 실시간 로그 스트리밍 -----------------------------------------------

def _init_live_log(log_file, url):
    """FA05: 모니터링 시작 시 로그 파일 헤더 + Detailed Log 섹션 초기화"""
    try:
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write(f"Web Monitoring Report - {url}\n")
            f.write(f"Started: {now_kst().strftime('%Y-%m-%d %H:%M:%S')}\n")
            if BREAKDOWN_MODE:
                _mode_str = "지연 분해 (Mode 3: DNS/TCP/TLS/응답 단계별)"
            elif MONITORING_MODE == 1:
                _mode_str = "HTML 전용 (Mode 1)"
            else:
                _mode_str = "HTML+리소스 (Mode 2)"
            f.write(f"Mode: {_mode_str} [LIVE]\n")
            f.write("=" * 80 + "\n\n")
            f.write("Detailed Log\n")
            f.write("-" * 80 + "\n")
    except Exception as e:
        print(f"[WARNING] 라이브 로그 초기화 실패: {e}")


def _append_live_log(entry, log_file, index):
    """FA05: 요청 1건을 즉시 파일에 append (모니터링 중 강제 종료 시 데이터 보존)"""
    try:
        ts_val = entry.get("Timestamp", "")
        if isinstance(ts_val, datetime.datetime):
            ts_val = ts_val.strftime("%Y-%m-%d %H:%M:%S.%f")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n[{index}] {ts_val}\n")
            f.write(f" URL: {entry.get('URL', 'N/A')}\n")
            f.write(f" Status: {entry.get('Status', -1)}\n")
            f.write(f" Response Time: {entry.get('Total Response Time (ms)', 0):.2f}ms\n")
            f.write(f" HTML Size: {entry.get('HTML Size (B)', 0)}B\n")
            f.write(f" Resource Size: {entry.get('Resource Size (B)', 0)}B\n")
            f.write(f" Total Size: {entry.get('Total Size (B)', 0)}B\n")
            f.write(f" HTTP Version: {entry.get('HTTP Version', 'HTTP/1.1')}\n")
            f.write(f" TLS Version: {entry.get('TLS Version', 'N/A')}\n")
            f.write(f" SNI: {entry.get('SNI', 'N/A')}\n")
            f.write(f" IP: {entry.get('IP', 'Unknown')}\n")
            # Mode 3: 지연 분해 (분해 필드가 있을 때만)
            if "TCP Open (ms)" in entry:
                f.write(" -- Latency Breakdown --\n")
                f.write(f"   DNS: {entry.get('DNS (ms)', 0):.2f}ms\n")
                f.write(f"   TCP Open: {entry.get('TCP Open (ms)', 0):.2f}ms\n")
                f.write(f"   TLS Handshake: {entry.get('TLS Handshake (ms)', 0):.2f}ms\n")
                f.write(f"   Server Response: {entry.get('Server Response (ms)', 0):.2f}ms\n")
                f.write(f"   Content Load: {entry.get('Content Load (ms)', 0):.2f}ms\n")
    except Exception:
        pass  # 스트리밍 실패는 무시 -- 메인 루프 중단 없음


# -- 저장 함수 -----------------------------------------------------------------

def _write_detailed_log(f, session_data):
    """상세 로그 섹션 전체 작성 헬퍼 (FA05 폴백 또는 비-FA05 경로)"""
    f.write("Detailed Log\n")
    f.write("-" * 80 + "\n")
    for i, entry in enumerate(session_data, 1):
        ts_val = entry.get("Timestamp", "")
        if isinstance(ts_val, datetime.datetime):
            ts_val = ts_val.strftime("%Y-%m-%d %H:%M:%S.%f")
        f.write(f"\n[{i}] {ts_val}\n")
        f.write(f" URL: {entry.get('URL', 'N/A')}\n")
        f.write(f" Status: {entry.get('Status', -1)}\n")
        f.write(f" Response Time: {entry.get('Total Response Time (ms)', 0):.2f}ms\n")
        f.write(f" HTML Size: {entry.get('HTML Size (B)', 0)}B\n")
        f.write(f" Resource Size: {entry.get('Resource Size (B)', 0)}B\n")
        f.write(f" Total Size: {entry.get('Total Size (B)', 0)}B\n")
        f.write(f" HTTP Version: {entry.get('HTTP Version', 'HTTP/1.1')}\n")
        f.write(f" TLS Version: {entry.get('TLS Version', 'N/A')}\n")
        f.write(f" SNI: {entry.get('SNI', 'N/A')}\n")
        f.write(f" IP: {entry.get('IP', 'Unknown')}\n")
    f.write("\n" + "=" * 80 + "\n")


def save_session_report(session_data, save_path, url,
                        live_log_file=None, downtime_events=None, start_time=None):
    """
    v6.5.5 동일 형식 텍스트 리포트 저장 (F11)
    FA05: live_log_file 이 있으면 기존 상세 로그에 Summary 를 앞에 재기록
    FA07: downtime_events 있으면 Summary 에 다운타임 집계 + 가용률 추가
    """
    try:
        # FA05: 라이브 로그 파일 재사용 or 새 파일 생성
        if live_log_file and os.path.exists(live_log_file):
            log_file = live_log_file
            with open(log_file, "r", encoding="utf-8") as f:
                existing_content = f.read()
        else:
            timestamp = now_kst().strftime("%Y%m%d_%H%M%S")
            hostname = urlparse(url).hostname or url
            log_file = os.path.join(save_path, f"monitor_log_{hostname}_{timestamp}.txt")
            existing_content = None

        with open(log_file, "w", encoding="utf-8") as f:
            # --- 헤더 ---
            f.write("=" * 80 + "\n")
            f.write(f"Web Monitoring Report - {url}\n")
            f.write(f"Generated: {now_kst().strftime('%Y-%m-%d %H:%M:%S')}\n")
            if BREAKDOWN_MODE:
                _mode_str = "지연 분해 (Mode 3: DNS/TCP/TLS/응답 단계별)"
            elif MONITORING_MODE == 1:
                _mode_str = "HTML 전용 (Mode 1)"
            else:
                _mode_str = "HTML+리소스 (Mode 2)"
            f.write(f"Mode: {_mode_str}\n")
            f.write("=" * 80 + "\n\n")

            if not session_data:
                f.write("[INFO] 데이터 없음\n")
                return log_file

            total = len(session_data)
            successes = [d for d in session_data if d.get("Status") == 200]
            failures = total - len(successes)
            avg_time = (
                sum(d.get("Total Response Time (ms)", 0) for d in successes) / len(successes)
                if successes else 0
            )
            total_html = sum(d.get("HTML Size (B)", 0) for d in session_data)
            total_res  = sum(d.get("Resource Size (B)", 0) for d in session_data)
            total_size = total_html + total_res

            # --- Summary Statistics ---
            f.write("Summary Statistics\n")
            f.write(f" - Total Requests: {total}\n")
            f.write(f" - Successful: {len(successes)} ({len(successes)/total*100:.1f}%)\n")
            f.write(f" - Failed: {failures}\n")
            f.write(f" - Average Response Time: {avg_time:.2f}ms\n")
            # Mode 3: 평균 단계별 지연 (분해 데이터가 있을 때만)
            _bd = [d for d in successes if "TCP Open (ms)" in d]
            if _bd:
                _avg = lambda k: sum(d.get(k, 0) for d in _bd) / len(_bd)
                f.write(
                    "   (Breakdown avg) "
                    f"DNS: {_avg('DNS (ms)'):.2f}ms | "
                    f"TCP Open: {_avg('TCP Open (ms)'):.2f}ms | "
                    f"TLS: {_avg('TLS Handshake (ms)'):.2f}ms | "
                    f"Server Response: {_avg('Server Response (ms)'):.2f}ms | "
                    f"Content: {_avg('Content Load (ms)'):.2f}ms\n"
                )
            f.write("\n")
            f.write("Total Download Size\n")
            f.write(f" - HTML: {total_html / 1024:.2f} KB\n")
            f.write(f" - Resources: {total_res / 1024:.2f} KB\n")
            f.write(f" - Total: {total_size / 1024:.2f} KB\n")

            # --- FA07: 다운타임 집계 ---
            if downtime_events is not None:
                url_events = [e for e in downtime_events if e["url"] == url]
                if url_events:
                    f.write("\nDowntime Events\n")
                    total_down_sec = 0.0
                    for i, ev in enumerate(url_events, 1):
                        start_str = ev["start"].strftime("%H:%M:%S.%f")[:-3]
                        if ev["end"]:
                            end_str = ev["end"].strftime("%H:%M:%S.%f")[:-3]
                            dur = (ev["end"] - ev["start"]).total_seconds()
                            total_down_sec += dur
                            f.write(f" - [{i}] {start_str} ~ {end_str}  ({dur:.1f}s)\n")
                        else:
                            f.write(f" - [{i}] {start_str} ~ (미복구)\n")
                            if start_time:
                                total_down_sec += (
                                    now_kst() - ev["start"]
                                ).total_seconds()
                    if start_time:
                        monitor_dur = (
                            now_kst() - start_time
                        ).total_seconds()
                        avail = (
                            (1 - total_down_sec / monitor_dur) * 100
                            if monitor_dur > 0 else 100.0
                        )
                        f.write(f" Total Downtime : {total_down_sec:.1f}s\n")
                        f.write(f" 모니터링 시간  : {monitor_dur:.0f}s\n")
                        f.write(f" 가용률 (SLA)   : {avail:.2f}%\n")

            f.write("\n" + "=" * 80 + "\n\n")

            # --- Detailed Log ---
            if existing_content:
                # FA05: 기존 상세 로그에서 "Detailed Log" 마커 이후 내용 재활용
                detail_marker = "Detailed Log\n" + "-" * 80
                idx = existing_content.find(detail_marker)
                if idx != -1:
                    f.write(existing_content[idx:])
                    f.write("\n" + "=" * 80 + "\n")
                else:
                    _write_detailed_log(f, session_data)
            else:
                _write_detailed_log(f, session_data)

        print(f"[+] 텍스트 로그: {log_file}")
        return log_file
    except Exception as e:
        print(f"[ERROR] 텍스트 로그 저장 실패: {e}")
        return None


def generate_excel_report(session_data, save_path, url):
    """v6.5.5 동일 형식 Excel 리포트 생성 (F12)"""
    if not HAS_PANDAS:
        print("[WARNING] pandas/openpyxl 없음 -- Excel 리포트 생성 건너뜀")
        return None
    try:
        timestamp = now_kst().strftime("%Y%m%d_%H%M%S")
        hostname = urlparse(url).hostname or url
        excel_file = os.path.join(save_path, f"monitor_report_{hostname}_{timestamp}.xlsx")

        df = pd.DataFrame(session_data)
        if "Timestamp" in df.columns:
            df["Timestamp"] = df["Timestamp"].astype(str)

        with pd.ExcelWriter(excel_file, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Data", index=False)

            success_count = len(df[df["Status"] == 200]) if "Status" in df.columns else 0
            total = len(df)
            avg_rt = (
                df[df["Status"] == 200]["Total Response Time (ms)"].mean()
                if success_count > 0 else 0
            )
            stats_data = {
                "Metric": [
                    "Total Requests", "Successful (200)", "Failed", "Success Rate (%)",
                    "Avg Response Time (ms)", "Total HTML Size (B)",
                    "Total Resource Size (B)", "Total Size (B)", "Monitoring Mode",
                ],
                "Value": [
                    total,
                    success_count,
                    total - success_count,
                    success_count / total * 100 if total > 0 else 0,
                    avg_rt,
                    df["HTML Size (B)"].sum() if "HTML Size (B)" in df.columns else 0,
                    df["Resource Size (B)"].sum() if "Resource Size (B)" in df.columns else 0,
                    df["Total Size (B)"].sum() if "Total Size (B)" in df.columns else 0,
                    "Mode 1: HTML only" if MONITORING_MODE == 1 else "Mode 2: HTML+Resources",
                ],
            }
            pd.DataFrame(stats_data).to_excel(writer, sheet_name="Statistics", index=False)

        print(f"[+] Excel 리포트: {excel_file}")
        return excel_file
    except Exception as e:
        print(f"[ERROR] Excel 리포트 생성 실패: {e}")
        return None


def generate_graphs(session_data, save_path):
    """v4.2 개선 PNG 그래프 — Response Time Trend + Success Rate (F13)"""
    if not HAS_MATPLOTLIB:
        print("[WARNING] matplotlib 없음 -- 그래프 생성 건너뜀")
        return False
    try:
        from matplotlib.gridspec import GridSpec
        import matplotlib.patheffects as pe

        # ── 색상 팔레트 ───────────────────────────────────────────────
        C_BG       = "#F7F9FC"          # 전체 배경
        C_CARD     = "#FFFFFF"          # 카드(축) 배경
        C_PRIMARY  = "#0EA5E9"          # 메인 라인 (스카이 블루)
        C_FILL     = "#0EA5E9"          # 라인 아래 그라데이션
        C_AVG      = "#F97316"          # 평균선 (오렌지)
        C_MAX      = "#EF4444"          # 최대값 마커 (빨강)
        C_MIN      = "#10B981"          # 최소값 마커 (초록)
        C_SUCCESS  = "#10B981"          # 성공 (초록)
        C_FAIL     = "#EF4444"          # 실패 (빨강)
        C_GRID     = "#E2E8F0"          # 그리드
        C_TEXT     = "#1E293B"          # 텍스트
        C_SUBTEXT  = "#64748B"          # 보조 텍스트

        # ── 대상 URL 추출 ─────────────────────────────────────────────
        urls = list({d.get("URL", "") for d in session_data})
        target_url = urls[0] if len(urls) == 1 else f"{len(urls)} sites"

        # ── 레이아웃 (2행: 헤더 + 차트 2개) ───────────────────────────
        fig = plt.figure(figsize=(20, 9), facecolor=C_BG)
        gs  = GridSpec(2, 2, figure=fig, height_ratios=[0.08, 1],
                       hspace=0.18, wspace=0.28,
                       left=0.06, right=0.96, top=0.95, bottom=0.08)

        # ── 헤더 영역 ────────────────────────────────────────────────
        ax_header = fig.add_subplot(gs[0, :])
        ax_header.set_xlim(0, 1)
        ax_header.set_ylim(0, 1)
        ax_header.axis("off")
        ax_header.text(
            0.5, 0.5, "Web Monitoring Report",
            fontsize=24, fontweight="bold", color=C_TEXT,
            ha="center", va="center",
            fontfamily="sans-serif",
        )
        ax_header.text(
            0.5, -0.3,
            f"Target: {target_url}  |  "
            + ("Mode 3: Latency Breakdown" if BREAKDOWN_MODE
               else ("Mode 1: HTML only" if MONITORING_MODE == 1
                     else "Mode 2: HTML+Resources")),
            fontsize=12, color=C_SUBTEXT,
            ha="center", va="center",
            fontfamily="sans-serif",
        )

        # ── 1) Response Time Trend ────────────────────────────────────
        ax1 = fig.add_subplot(gs[1, 0])
        ax1.set_facecolor(C_CARD)
        for spine in ax1.spines.values():
            spine.set_visible(False)

        # 전체 데이터를 시계열로 정렬 (성공+실패 모두 포함)
        all_entries = sorted(session_data, key=lambda d: d.get("Timestamp", datetime.datetime.min))
        all_timestamps = [d.get("Timestamp") for d in all_entries]

        # 성공/실패 분류 (X축은 전체 시계열 인덱스 기준)
        ok_x, ok_times, ok_tcp = [], [], []
        fail_x, fail_timestamps_list = [], []
        for i, d in enumerate(all_entries):
            if d.get("Status") == 200:
                ok_x.append(i)
                ok_times.append(d.get("Total Response Time (ms)", 0))
                ok_tcp.append(d.get("TCP Open (ms)"))  # 분해 데이터 (없으면 None)
            else:
                fail_x.append(i)
                fail_timestamps_list.append(d.get("Timestamp"))
        # Mode 3: TCP Open 분해 데이터 존재 여부
        has_bd = any(v is not None for v in ok_tcp)

        if ok_times or fail_x:
            # 성공 데이터 — 라인 + 그라데이션 영역
            if ok_times:
                ax1.plot(ok_x, ok_times, marker="o", linestyle="-",
                         color=C_PRIMARY, linewidth=2.5, markersize=6,
                         markerfacecolor="white", markeredgecolor=C_PRIMARY,
                         markeredgewidth=2, zorder=4, label="Response Time")
                ax1.fill_between(ok_x, ok_times, alpha=0.08, color=C_FILL)

                # Mode 3: TCP Open 오버레이 (Total 급증이 연결 단계 때문임을 시각화)
                if has_bd:
                    tcp_vals = [v if v is not None else 0 for v in ok_tcp]
                    ax1.plot(ok_x, tcp_vals, marker="o", linestyle="--",
                             color=C_AVG, linewidth=2, markersize=4,
                             markerfacecolor="white", markeredgecolor=C_AVG,
                             markeredgewidth=1.5, zorder=5, label="TCP Open")

            # 실패 시점 — 빨간 X 마커 + 세로 음영으로 표시
            if fail_x:
                # Y축 범위 결정을 위한 기준값
                y_top = max(ok_times) * 1.1 if ok_times else 100
                # 실패 위치에 빨간 X 마커
                ax1.scatter(fail_x, [y_top * 0.85] * len(fail_x),
                            s=150, c=C_FAIL, marker="X",
                            zorder=7, edgecolors="white", linewidth=1.5,
                            label="FAIL")
                # 실패 구간 세로 음영 (연한 빨강)
                for fx in fail_x:
                    ax1.axvspan(fx - 0.4, fx + 0.4,
                                alpha=0.12, color=C_FAIL, zorder=1)
                # 실패 시간 레이블 (최대 5개까지 표시, 과밀 방지)
                shown = 0
                for j, fx in enumerate(fail_x):
                    if shown >= 5:
                        break
                    # 이전 실패와 너무 가까우면 스킵 (3칸 이내)
                    if j > 0 and fx - fail_x[j - 1] < 3:
                        continue
                    ts_label = ""
                    if fail_timestamps_list[j] and isinstance(fail_timestamps_list[j], datetime.datetime):
                        ts_label = fail_timestamps_list[j].strftime("%H:%M:%S")
                    ax1.annotate(
                        f"FAIL\n{ts_label}", xy=(fx, y_top * 0.85),
                        xytext=(0, 16), textcoords="offset points",
                        fontsize=8, fontweight="bold", color=C_FAIL,
                        ha="center", va="bottom",
                    )
                    shown += 1

            # 평균선 (성공 데이터 기준)
            if ok_times:
                avg_time = sum(ok_times) / len(ok_times)
                ax1.axhline(y=avg_time, color=C_AVG, linestyle="--", linewidth=2,
                            alpha=0.85, zorder=3)
                ax1.text(len(all_entries) - 0.5, avg_time, f"  Avg {avg_time:.0f}ms",
                         color=C_AVG, fontsize=11, fontweight="bold",
                         va="bottom", ha="left", zorder=5)

                # 최대/최소 마커 + 주석
                max_time = max(ok_times)
                min_time = min(ok_times)
                max_idx  = ok_x[ok_times.index(max_time)]
                min_idx  = ok_x[ok_times.index(min_time)]

                ax1.scatter([max_idx], [max_time], s=120, c=C_MAX, marker="D",
                            zorder=6, edgecolors="white", linewidth=2)
                ax1.annotate(
                    f"Max {max_time:.0f}ms", xy=(max_idx, max_time),
                    xytext=(0, 16), textcoords="offset points",
                    fontsize=10, fontweight="bold", color=C_MAX,
                    ha="center", va="bottom",
                    arrowprops=dict(arrowstyle="-", color=C_MAX, lw=1),
                )
                ax1.scatter([min_idx], [min_time], s=120, c=C_MIN, marker="D",
                            zorder=6, edgecolors="white", linewidth=2)
                ax1.annotate(
                    f"Min {min_time:.0f}ms", xy=(min_idx, min_time),
                    xytext=(0, -18), textcoords="offset points",
                    fontsize=10, fontweight="bold", color=C_MIN,
                    ha="center", va="top",
                    arrowprops=dict(arrowstyle="-", color=C_MIN, lw=1),
                )

            # 그리드
            ax1.grid(axis="y", color=C_GRID, linewidth=0.8, alpha=0.7)
            ax1.grid(axis="x", visible=False)

            # 제목 / 축
            ax1.set_title("Response Time Trend", fontsize=16, fontweight="bold",
                          color=C_TEXT, pad=16, loc="left")
            ax1.set_xlabel("Time", fontsize=11, color=C_SUBTEXT, labelpad=8)
            ax1.set_ylabel("Response Time (ms)", fontsize=11, color=C_SUBTEXT, labelpad=8)
            ax1.tick_params(axis="both", colors=C_SUBTEXT, labelsize=10)

            # Y축 여백 (분해 모드에선 TCP Open 라인이 보이도록 0부터 시작)
            if ok_times:
                y_margin = (max_time - min_time) * 0.25 if max_time != min_time else max_time * 0.3
                y_lo = 0 if has_bd else max(0, min_time - y_margin)
                ax1.set_ylim(y_lo, max_time + y_margin * 2)
            else:
                ax1.set_ylim(0, 100)

            # 범례 (실패가 있거나 분해 오버레이가 있을 때)
            if fail_x or has_bd:
                ax1.legend(loc="upper right", fontsize=9, framealpha=0.9)

            # X축 시간 레이블 (전체 시계열 기준, 균등 분배, 최대 8개)
            timestamps = all_timestamps
            max_labels = min(8, len(timestamps))
            if timestamps and isinstance(timestamps[0], datetime.datetime) and max_labels > 1:
                step = max(1, (len(timestamps) - 1) // (max_labels - 1))
                positions = list(range(0, len(timestamps), step))
                if positions[-1] != len(timestamps) - 1:
                    positions.append(len(timestamps) - 1)
                labels = [timestamps[p].strftime("%H:%M:%S") for p in positions]
                ax1.set_xticks(positions)
                ax1.set_xticklabels(labels, rotation=30, ha="right", fontsize=9)
            elif timestamps and isinstance(timestamps[0], datetime.datetime):
                ax1.set_xticks([0])
                ax1.set_xticklabels([timestamps[0].strftime("%H:%M:%S")], fontsize=9)

            # 통계 박스 (좌하단)
            if ok_times:
                avg_time = sum(ok_times) / len(ok_times)
                max_time = max(ok_times)
                min_time = min(ok_times)
            else:
                avg_time = max_time = min_time = 0
            fail_text = f"   Fail: {len(fail_x)}" if fail_x else ""
            stats_text = (
                f"Requests: {len(ok_times)}   "
                f"Avg: {avg_time:.0f}ms   "
                f"Max: {max_time:.0f}ms   "
                f"Min: {min_time:.0f}ms"
                f"{fail_text}"
            )
            ax1.text(0.01, -0.12, stats_text, transform=ax1.transAxes,
                     fontsize=9, color=C_SUBTEXT, va="top",
                     fontfamily="sans-serif",
                     bbox=dict(boxstyle="round,pad=0.4", facecolor="#F1F5F9",
                               edgecolor=C_GRID, alpha=0.9))

        # ── 2) Success Rate (도넛 차트) ───────────────────────────────
        ax2 = fig.add_subplot(gs[1, 1])
        ax2.set_facecolor(C_CARD)
        for spine in ax2.spines.values():
            spine.set_visible(False)

        success_count = len([d for d in session_data if d.get("Status") == 200])
        fail_count    = len(session_data) - success_count
        total         = len(session_data)

        if total > 0:
            success_pct = success_count / total * 100
            fail_pct    = fail_count / total * 100

            sizes  = [success_count, fail_count] if fail_count > 0 else [success_count]
            colors = [C_SUCCESS, C_FAIL] if fail_count > 0 else [C_SUCCESS]

            wedges, _ = ax2.pie(
                sizes,
                labels=None,
                colors=colors,
                startangle=90,
                counterclock=False,
                wedgeprops=dict(width=0.35, edgecolor="white", linewidth=3),
                pctdistance=0.82,
            )

            # 도넛 중앙 텍스트 (성공률)
            centre_label = f"{success_pct:.1f}%"
            ax2.text(0, 0.06, centre_label, ha="center", va="center",
                     fontsize=36, fontweight="bold", color=C_SUCCESS if success_pct >= 80 else C_FAIL,
                     fontfamily="sans-serif",
                     path_effects=[pe.withStroke(linewidth=3, foreground="white")])
            ax2.text(0, -0.14, "Success Rate", ha="center", va="center",
                     fontsize=12, color=C_SUBTEXT, fontfamily="sans-serif")

            # 범례 (하단)
            legend_labels = [
                f"  Success: {success_count} ({success_pct:.1f}%)",
                f"  Failed:  {fail_count} ({fail_pct:.1f}%)",
            ]
            legend_handles = [
                plt.Line2D([0], [0], marker="s", color="w", markerfacecolor=C_SUCCESS,
                           markersize=12, markeredgecolor="none"),
                plt.Line2D([0], [0], marker="s", color="w", markerfacecolor=C_FAIL,
                           markersize=12, markeredgecolor="none"),
            ]
            leg = ax2.legend(
                legend_handles, legend_labels,
                loc="lower center", fontsize=11,
                frameon=True, framealpha=0.9,
                fancybox=True, shadow=False,
                edgecolor=C_GRID,
                bbox_to_anchor=(0.5, -0.06),
                ncol=2, handletextpad=0.3, columnspacing=2,
            )
            leg.get_frame().set_facecolor("#F1F5F9")

            ax2.set_title("Success Rate", fontsize=16, fontweight="bold",
                          color=C_TEXT, pad=16, loc="left")

            # 총 요청 수 텍스트
            ax2.text(0.5, -0.12, f"Total Requests: {total}", transform=ax2.transAxes,
                     fontsize=9, color=C_SUBTEXT, ha="center", va="top",
                     fontfamily="sans-serif",
                     bbox=dict(boxstyle="round,pad=0.4", facecolor="#F1F5F9",
                               edgecolor=C_GRID, alpha=0.9))

        # ── 저장 ──────────────────────────────────────────────────────
        ts_str     = now_kst().strftime("%Y%m%d_%H%M%S")
        graph_file = os.path.join(save_path, f"monitor_graph_{ts_str}.png")
        plt.savefig(graph_file, dpi=180, bbox_inches="tight",
                    facecolor=C_BG, edgecolor="none")
        plt.close()

        print(f"[+] 그래프 (Response Time + Success Rate): {graph_file}")
        return True
    except Exception as e:
        print(f"[ERROR] 그래프 생성 실패: {e}")
        return False


def _print_summary(all_results, start_time):
    """콘솔 요약 출력 (all_results: 내부 필드 포함 원본 리스트)"""
    if not all_results:
        print("\n[INFO] 수집된 데이터 없음")
        return

    elapsed     = (now_kst() - start_time).total_seconds()
    ok_list     = [r for r in all_results if not r["_error"]]
    fail_list   = [r for r in all_results if r["_error"]]
    success_rate = len(ok_list) / len(all_results) * 100

    print("\n" + "=" * 80)
    print("  모니터링 결과 요약")
    print("=" * 80)
    print(f"  모니터링 시간  : {elapsed:.0f}초")
    print(f"  총 요청 수     : {len(all_results)}건")
    print(f"  성공           : {len(ok_list)}건  ({success_rate:.1f}%)")
    print(f"  실패           : {len(fail_list)}건")

    if ok_list:
        times = [r["Total Response Time (ms)"] for r in ok_list]
        print(f"\n  응답 시간 통계:")
        print(f"    평균 : {sum(times)/len(times):.1f}ms")
        print(f"    최소 : {min(times):.1f}ms")
        print(f"    최대 : {max(times):.1f}ms")

    urls = list(dict.fromkeys(r["URL"] for r in all_results))
    print(f"\n  사이트별 결과:")
    for url in urls:
        url_all = [r for r in all_results if r["URL"] == url]
        url_ok  = [r for r in url_all if not r["_error"]]
        pct     = len(url_ok) / len(url_all) * 100
        avg_ms  = (
            sum(r["Total Response Time (ms)"] for r in url_ok) / len(url_ok)
            if url_ok else 0.0
        )
        status = "정상" if pct == 100 else ("경고" if pct >= 50 else "장애")
        print(f"    [{status}] {url}")
        print(f"           성공률 {pct:.0f}% | 평균 응답 {avg_ms:.1f}ms | {len(url_all)}회 측정")

    if fail_list:
        seen = set()
        print(f"\n  실패 상세:")
        for r in fail_list:
            key = (r["URL"], r["_error"])
            if key not in seen:
                print(f"    {r['URL']}  ->  {r['_error']}")
                seen.add(key)


# -- 메인 ----------------------------------------------------------------------

def main():
    global _stop, MONITORING_MODE, BREAKDOWN_MODE
    # FA-CL: CLI 인자 파싱 (인자 없으면 기존 대화형 모드)
    args = _parse_args()

    work_dir   = os.getcwd()
    script_dir = APP_DIR   # frozen(EXE)이면 EXE 폴더, 아니면 스크립트 폴더
    # sites.json 탐색: EXE 폴더 → _internal(_MEIPASS) → 현재 디렉토리 순 (견고성)
    _sj_candidates = [
        os.path.join(script_dir, "sites.json"),
        os.path.join(getattr(sys, "_MEIPASS", script_dir), "sites.json"),
        os.path.join(work_dir, "sites.json"),
    ]
    sites_path = next((p for p in _sj_candidates if os.path.exists(p)), _sj_candidates[0])

    print("=" * 80)
    signal.signal(signal.SIGINT, _signal_handler)

    print("  DDoS 모의 훈련 웹 모니터링  v5.1")
    print("=" * 80)

    # FA-MD + FA-CL: 모니터링 모드 — CLI 인자 우선, 없으면 대화형
    if args.mode is not None:
        if args.mode == 3:
            MONITORING_MODE = 1        # 분해 모드는 단일 GET(HTML 전용) 기준
            BREAKDOWN_MODE = True
            print("\n  -> Mode 3 선택: 지연 분해 (TCP Open vs 서버응답 분리) (CLI)\n")
        else:
            MONITORING_MODE = args.mode
            if MONITORING_MODE == 2 and not HAS_BS4:
                print("  [WARNING] Mode 2에는 beautifulsoup4가 필요합니다. Mode 1로 전환")
                MONITORING_MODE = 1
            label = "HTML 전용" if MONITORING_MODE == 1 else "HTML + 리소스"
            print(f"\n  -> Mode {MONITORING_MODE} 선택: {label} (CLI)\n")
    else:
        _select_monitoring_mode()

    # sites.json 로드 (F15)
    if not os.path.exists(sites_path):
        print(f"[ERROR] sites.json 없음: {sites_path}")
        sys.exit(1)
    try:
        all_sites = _load_sites(sites_path)
    except json.JSONDecodeError as e:
        print(f"[ERROR] sites.json 파싱 실패: {e}")
        sys.exit(1)
    if not all_sites:
        print("[ERROR] sites.json에 사이트가 없습니다.")
        sys.exit(1)

    # F07 + FA-CL: 사이트 선택 — CLI 인자 우선, 없으면 대화형
    if args.sites is not None:
        if args.sites.strip() == "0":
            selected_sites = all_sites
        else:
            try:
                indices = {int(x.strip()) for x in args.sites.split(",")}
                selected_sites = [all_sites[i - 1] for i in sorted(indices)
                                  if 1 <= i <= len(all_sites)]
            except (ValueError, IndexError):
                print(f"[ERROR] --sites 값 오류: {args.sites}")
                sys.exit(1)
        if not selected_sites:
            print("[ERROR] 선택된 사이트가 없습니다.")
            sys.exit(1)
        print(f"\n[사이트 목록]")
        for i, site in enumerate(all_sites, 1):
            ip_info = f" (IP: {site.get('ip')})" if site.get("ip") else ""
            marker = " *" if site in selected_sites else ""
            print(f"  {i:2d}. {site['url']}{ip_info}{marker}")
        print(f"  -> {len(selected_sites)}개 선택 (CLI)\n")
    else:
        selected_sites = _select_targets(all_sites)

    # 저장 경로 준비 (엔터 전에 완료 -- F08)
    # FA-SP: sites.json "save_path" → 사이트별 커스텀 저장 경로 지원
    first_host = urlparse(selected_sites[0]["url"]).hostname or "unknown"
    ts_str     = now_kst().strftime("%Y%m%d_%H%M%S")
    default_save_dir = os.path.join(work_dir, "monitoring", f"{first_host}_{ts_str}")
    os.makedirs(default_save_dir, exist_ok=True)

    # 사이트별 저장 경로 매핑: save_path가 있으면 그 안에 {host}_{ts} 폴더 생성
    site_save_dirs = {}
    for s in selected_sites:
        url      = s["url"]
        hostname = urlparse(url).hostname or "unknown"
        custom   = s.get("save_path", "").strip()
        if custom:
            site_dir = os.path.join(custom, f"{hostname}_{ts_str}")
            os.makedirs(site_dir, exist_ok=True)
            site_save_dirs[url] = site_dir
        else:
            site_save_dirs[url] = default_save_dir

    # FA-CL: 사이클 간격 — CLI 인자 우선, 없으면 기본 3초
    interval = args.interval if args.interval is not None else 3

    print(f"\n[+] 모니터링 대상: {len(selected_sites)}개 사이트")
    for s in selected_sites:
        url = s["url"]
        sd  = site_save_dirs[url]
        if sd != default_save_dir:
            print(f"    - {url}  -> {sd}")
        else:
            print(f"    - {url}")
    print(f"[+] 기본 저장 경로: {default_save_dir}")
    custom_dirs = {v for v in site_save_dirs.values() if v != default_save_dir}
    if custom_dirs:
        for cd in sorted(custom_dirs):
            print(f"[+] 커스텀 경로  : {cd}")
    print(f"[+] 사이클 간격: {interval}초")
    # FA-MD: 모드 출력
    if BREAKDOWN_MODE:
        mode_label = "Mode 3: 지연 분해 (TCP Open/TLS/서버응답 분리)"
    elif MONITORING_MODE == 1:
        mode_label = "Mode 1: HTML 전용"
    else:
        mode_label = "Mode 2: HTML+리소스"
    print(f"[+] 모니터링 모드: {mode_label}")
    # FA-H2: HTTP/2 지원 여부 출력 (v4.1: httpx + h2 개별 상태 진단)
    if HAS_H2:
        print(f"[+] HTTP/2     : 활성화 (httpx + h2) -- HTTPS 서버 자동 협상")
    elif HAS_HTTPX:
        print(f"[+] HTTP/2     : 비활성화 -- httpx O, h2 X (pip install 'httpx[http2]')")
    else:
        print(f"[+] HTTP/2     : 비활성화 -- HTTP/1.1 고정 (pip install 'httpx[http2]')")
    # FA-DA: DDoS 인증 대응 사이트 출력
    da_sites = [s for s in selected_sites if s.get("ddos_auth")]
    if da_sites:
        print(f"[+] DDoS 인증  : {len(da_sites)}개 사이트 (302+Cookie 자동 처리)")
        for s in da_sites:
            print(f"    - {s['url']}")
    # FA01: 임계값 미리 출력
    has_threshold = any(s.get("alert_thresholds") for s in selected_sites)
    if has_threshold:
        print(f"[+] FA01 경고 임계값:")
        for s in selected_sites:
            thr = s.get("alert_thresholds", {})
            if thr:
                max_ms   = thr.get("max_response_time_ms", "N/A")
                exp_code = thr.get("expected_status_code", "N/A")
                print(f"    - {s['url']}: 응답시간 {max_ms}ms | 상태코드 {exp_code}")
    print(f"[i]  중지       : Ctrl+C  ->  자동 저장 후 종료")
    print()

    # 상태 변수 초기화 (finally 블록 접근 위해 try 밖에서 선언)
    all_results    = []
    session_data   = {}
    cycle          = 0
    start_time     = None
    live_log_files = {}

    # FA02 / FA03 / FA07 상태 변수
    site_state      = {s["url"]: True for s in selected_sites}  # True=정상
    consec_fail     = {s["url"]: 0 for s in selected_sites}     # FA03-A 연속 실패 카운터
    down_times      = {}                                         # FA02 다운 시작 시각
    downtime_events = []                                         # FA07 다운타임 이벤트 목록

    # ── FA-CF: Cloudflare 우회 초기화 (--cf-bypass) ─────────────
    if args.cf_bypass and HAS_CF_BYPASS:
        print(f"\n[CF_BYPASS] Cloudflare 우회 초기화 ({len(selected_sites)}개 사이트)...")
        for site in selected_sites:
            url = site["url"]
            hostname = urlparse(url).hostname or ""
            cf = CloudflareBypass(url)
            if cf.available and cf.solve():
                _cf_bypass_map[hostname] = cf
                print(f"  [OK] {hostname}: 쿠키 {len(cf.get_cookies())}개")
            else:
                print(f"  [SKIP] {hostname}: 우회 실패 — 일반 모드")
        if _cf_bypass_map:
            print(f"[CF_BYPASS] {len(_cf_bypass_map)}개 사이트 우회 활성화\n")
    elif args.cf_bypass and not HAS_CF_BYPASS:
        print("[WARNING] --cf-bypass: cf_bypass.py 모듈 없음, playwright/curl_cffi 설치 필요")

    # ── FA-EW: 워밍업을 엔터 대기 **전**에 미리 실행 ─────────────
    #    엔터 입력 직후 지연 없이 즉시 모니터링 시작 가능
    _warmup_probe(selected_sites)

    # F08 + FA-CL: 엔터 대기 — --auto 시 즉시 시작
    print("=" * 80)

    # FA-EW: 엔터 대기 중 백그라운드 keep-alive (30초마다 DNS 재확인)
    #        대기가 길어져도 DNS 캐시가 stale하지 않도록 유지
    _keep_alive_stop = threading.Event()

    def _keep_alive_loop():
        """FA-EW: 엔터 대기 중 30초 주기로 DNS 캐시 갱신 + TCP 프로브."""
        while not _keep_alive_stop.is_set():
            _keep_alive_stop.wait(30)
            if _keep_alive_stop.is_set():
                break
            for site in selected_sites:
                parsed    = urlparse(site["url"])
                hostname  = parsed.hostname or ""
                static_ip = site.get("ip", "")
                # DNS 캐시 갱신 (static_ip 사이트는 갱신 불필요)
                if not static_ip:
                    try:
                        ip = socket.getaddrinfo(hostname, None)[0][4][0]
                        _dns_cache[hostname] = ip
                    except Exception:
                        pass
                # 경량 HEAD 프로브 (TCP 연결 유효성 확인)
                try:
                    requests.head(site["url"], timeout=3, verify=False,
                                  allow_redirects=True)
                except Exception:
                    pass

    if args.auto:
        print("[INFO] --auto: 즉시 시작")
    else:
        # 백그라운드 keep-alive 스레드 시작
        ka_thread = threading.Thread(target=_keep_alive_loop, daemon=True)
        ka_thread.start()
        try:
            input("[INFO] 엔터 키를 입력하면 모니터링을 시작합니다 (중지: Ctrl+C)")
        except KeyboardInterrupt:
            _keep_alive_stop.set()
            print("\n모니터링이 취소되었습니다.")
            return
        # keep-alive 중지
        _keep_alive_stop.set()

    start_time = now_kst()

    # FA05: 라이브 로그 파일 초기화 (엔터 직후, 루프 시작 전)
    ts_log = start_time.strftime("%Y%m%d_%H%M%S")
    for site in selected_sites:
        url      = site["url"]
        hostname = urlparse(url).hostname or "unknown"
        log_file = os.path.join(site_save_dirs[url], f"monitor_log_{hostname}_{ts_log}.txt")
        _init_live_log(log_file, url)
        live_log_files[url] = {"path": log_file, "count": 0}

    print("=" * 80)
    print(f"[START] {start_time.strftime('%Y-%m-%d %H:%M:%S')}  모니터링 시작")
    print("=" * 80 + "\n")

    # FA-PC: 메인 루프 — 복수 사이트 병렬 요청 (F01: 매 호출 새 Session 유지)
    num_sites = len(selected_sites)
    try:
        while not _stop:
            cycle += 1

            # ── FA-PC: 병렬 요청 (1사이트면 순차와 동일) ─────────────
            if num_sites == 1:
                # 단일 사이트 — 스레드 풀 오버헤드 없이 직접 호출
                site = selected_sites[0]
                cycle_results = [_measure(
                    site["url"], site.get("check_string", ""),
                    site.get("resource_timeout", 10), site.get("ip", ""),
                    not site.get("http2", True), site.get("ddos_auth", False),
                )]
            else:
                # 복수 사이트 — ThreadPoolExecutor 병렬 요청
                cycle_results = [None] * num_sites
                with ThreadPoolExecutor(max_workers=min(num_sites, 8)) as pool:
                    futures = {}
                    for idx, site in enumerate(selected_sites):
                        if _stop:
                            break
                        f = pool.submit(
                            _measure,
                            site["url"], site.get("check_string", ""),
                            site.get("resource_timeout", 10), site.get("ip", ""),
                            not site.get("http2", True), site.get("ddos_auth", False),
                        )
                        futures[f] = idx
                    for f in as_completed(futures):
                        cycle_results[futures[f]] = f.result()

            if _stop:
                break

            # ── 결과 처리 (순서 보장 — sites 순서대로 출력) ───────────
            for idx, result in enumerate(cycle_results):
                if result is None:
                    continue
                site       = selected_sites[idx]
                url        = site["url"]
                thresholds = site.get("alert_thresholds", {})
                all_results.append(result)

                # F16: 콘솔 실시간 출력
                print(_format_line(result))

                # ── FA01: Alert Threshold 체크 ────────────────────────
                if not result["_error"] and thresholds:
                    max_ms   = thresholds.get("max_response_time_ms")
                    exp_code = thresholds.get("expected_status_code", 200)
                    if max_ms and result["Total Response Time (ms)"] > max_ms:
                        print(
                            f"  [ALERT] 응답시간 {result['Total Response Time (ms)']:.0f}ms"
                            f" > 임계값 {max_ms}ms"
                        )
                    if result["Status"] != exp_code:
                        print(
                            f"  [ALERT] 상태코드 {result['Status']}"
                            f" != 기대값 {exp_code}"
                        )

                # ── FA02: 상태 전이 감지 (Down / Recovery) ────────────
                is_ok  = (result["_error"] is None and result["Status"] == 200)
                was_ok = site_state.get(url, True)

                if was_ok and not is_ok:
                    down_times[url] = result["Timestamp"]
                    downtime_events.append(
                        {"url": url, "start": result["Timestamp"], "end": None}
                    )
                    bar = "#" * 60
                    print(bar)
                    print(f"  [DOWN] {url}")
                    print(f"  장애 감지: {result['Timestamp'].strftime('%H:%M:%S.%f')[:-3]}")
                    print(bar)

                elif not was_ok and is_ok:
                    down_start   = down_times.pop(url, result["Timestamp"])
                    downtime_sec = (result["Timestamp"] - down_start).total_seconds()
                    for ev in reversed(downtime_events):
                        if ev["url"] == url and ev["end"] is None:
                            ev["end"] = result["Timestamp"]
                            break
                    bar2 = "=" * 60
                    print(bar2)
                    print(f"  [RECOVERY] {url}")
                    print(f"  복구 확인: {result['Timestamp'].strftime('%H:%M:%S.%f')[:-3]}")
                    print(f"  다운타임: {downtime_sec:.1f}초")
                    print(bar2)

                site_state[url] = is_ok

                # ── FA03-A: 연속 실패 카운터 ──────────────────────────
                if not is_ok:
                    consec_fail[url] = consec_fail.get(url, 0) + 1
                    if consec_fail[url] >= CRITICAL_FAIL_THRESHOLD:
                        print(
                            f"  [CRITICAL] {url}"
                            f" -- {consec_fail[url]}회 연속 실패 중"
                        )
                else:
                    consec_fail[url] = 0

                # 세션 데이터 누적
                if url not in session_data:
                    session_data[url] = []
                record = _to_session_record(result)
                session_data[url].append(record)

                # ── FA05: 라이브 로그 즉시 append ─────────────────────
                if url in live_log_files:
                    live_log_files[url]["count"] += 1
                    _append_live_log(
                        record,
                        live_log_files[url]["path"],
                        live_log_files[url]["count"],
                    )

            # ── FA03-B: 사이클 통계 강화 ──────────────────────────────
            ok_so_far = [r for r in all_results if not r["_error"]]
            pct       = len(ok_so_far) / len(all_results) * 100 if all_results else 0.0
            avg_rt    = (
                sum(r["Total Response Time (ms)"] for r in ok_so_far) / len(ok_so_far)
                if ok_so_far else 0.0
            )
            max_rt = max(
                (r["Total Response Time (ms)"] for r in ok_so_far), default=0.0
            )
            print(
                f"  -- 사이클 {cycle:03d} 완료  "
                f"{now_kst().strftime('%H:%M:%S')} | "
                f"성공률: {pct:.1f}% | "
                f"평균: {avg_rt:.0f}ms | "
                f"최대: {max_rt:.0f}ms --"
            )
            _interruptible_sleep(interval)

    except KeyboardInterrupt:
        _stop = True

    # F14: finally 보장 -- 모든 종료 경로에서 실행
    finally:
        if _stop:
            stop_time = now_kst()
            print(
                f"\n\n[STOP]  Ctrl+C  --  "
                f"{stop_time.strftime('%H:%M:%S')}  사이클 {cycle}회 완료"
            )
        # FA-GS: 저장 중 두 번째 Ctrl+C 방지 (시그널 무시)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        total_sites = len(session_data) if session_data else 0
        print(f"\n[INFO] 데이터 저장 중... ({total_sites}개 사이트, 병렬)")
        if session_data:
            # FA-PS: 텍스트 로그 + Excel + 그래프 저장을 모두 병렬 실행
            save_tasks = []
            for url, data in session_data.items():
                url_save_dir = site_save_dirs.get(url, default_save_dir)
                lf = live_log_files.get(url, {}).get("path")
                # 텍스트 로그 저장 태스크
                save_tasks.append(("txt", url, lambda u=url, d=data, sd=url_save_dir, l=lf:
                    save_session_report(d, sd, u, live_log_file=l,
                                        downtime_events=downtime_events,
                                        start_time=start_time)))
                # Excel 리포트 저장 태스크
                save_tasks.append(("xlsx", url, lambda u=url, d=data, sd=url_save_dir:
                    generate_excel_report(d, sd, u)))

            # 그래프: 저장 경로별 그룹핑
            dir_data = {}
            for url, data in session_data.items():
                sd = site_save_dirs.get(url, default_save_dir)
                dir_data.setdefault(sd, []).extend(data)
            for sd, data in dir_data.items():
                if data:
                    save_tasks.append(("png", sd, lambda s=sd, d=data:
                        generate_graphs(d, s)))

            # 병렬 실행
            t_save = time.time()
            with ThreadPoolExecutor(max_workers=min(len(save_tasks), 6)) as pool:
                futures = {pool.submit(task_fn): (ftype, label)
                           for ftype, label, task_fn in save_tasks}
                for f in as_completed(futures):
                    ftype, label = futures[f]
                    try:
                        f.result()
                    except Exception as e:
                        print(f"  [WARNING] {ftype} 저장 실패 ({label}): {e}")
            save_ms = round((time.time() - t_save) * 1000)
            print(f"[INFO] 저장 완료: {len(save_tasks)}개 작업, {save_ms}ms (병렬)")

            if start_time:
                _print_summary(all_results, start_time)
        else:
            print("[INFO] 저장할 데이터가 없습니다.")

        print("\n[완료] 모니터링 종료")


if __name__ == "__main__":
    main()
