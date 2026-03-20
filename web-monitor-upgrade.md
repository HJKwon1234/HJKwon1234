# Web Monitor v6.5.5 → v7.0 업그레이드 계획

> DDoS 모의훈련 시 타겟 웹서버 상태 모니터링 관점 개선
> 원칙: 현재 기능 100% 유지 + 단계별 점진적 개선

---

## 현재 기능 목록 (유지 보장)

아래 기능은 모든 단계에서 그대로 동작해야 합니다.

| # | 기능 | 파일/위치 |
|---|------|-----------|
| 1 | Mode 1/2 선택 (HTML 전용 / HTML+리소스) | `select_monitoring_mode()` |
| 2 | sites.json 기반 타겟 설정 | `ConfigManager.load_sites()` |
| 3 | 다중 사이트 선택 모니터링 | `select_targets()` |
| 4 | 매 루프마다 새 TCP/TLS 세션 생성 | `main()` → `Monitor()` 재생성 |
| 5 | DNS 조회 (시스템 DNS + 폴백) | `Monitor.resolve_domain()` |
| 6 | SSL 검증 비활성화 | `NoSSLVerifyAdapter` |
| 7 | PCAP 캡처 (tshark) | `main()` → tshark subprocess |
| 8 | TLS 키로그 (SSLKEYLOGFILE) | 글로벌 설정부 |
| 9 | Wireshark 런처 스크립트 생성 | `generate_wireshark_launcher()` |
| 10 | 엔터 키로 모니터링 시작 | `main()` → `input()` |
| 11 | 콘솔 로그 출력 (한 줄 요약) | 메인 루프 |
| 12 | 세션 리포트 (.txt) 저장 | `save_session_report()` |
| 13 | Excel 리포트 (.xlsx) 저장 | `generate_excel_report()` |
| 14 | 그래프 (Response Time + Success Rate) | `generate_graphs()` |
| 15 | Ctrl+C 종료 및 결과 자동 저장 | `main()` → `finally` 블록 |
| 16 | Windows/Linux 크로스 플랫폼 | 전체 |

---

## Phase 1: 데이터 정확성 개선 (기반 정비)

> 현재 잘못 기록되거나 누락되는 데이터를 정확하게 수집합니다.

### 1-1. TLS 버전 실제 감지

**현재**: 515줄에서 `tls_version = "TLSv1.2"` 하드코딩
**변경**: `requests` 응답의 raw socket에서 실제 TLS 버전 추출

```python
# Monitor.check() 내부, resp 획득 후
def _get_tls_version(self, resp):
    """응답에서 실제 TLS 버전을 추출"""
    try:
        sock = resp.raw._connection.sock
        if hasattr(sock, 'version'):
            return sock.version()  # 예: 'TLSv1.3'
    except Exception:
        pass
    return "N/A"
```

**영향**: 로그/리포트의 TLS Version 컬럼 값이 실제값으로 변경
**호환성**: 출력 형식 동일, 값만 정확해짐

### 1-2. HTTP 버전 감지 수정

**현재**: 523줄 `hasattr(resp, 'h2')` — 항상 `HTTP/1.1` 반환
**변경**: `resp.raw.version` 활용

```python
def _get_http_version(self, resp):
    """응답에서 실제 HTTP 버전을 추출"""
    try:
        raw_version = resp.raw.version
        if raw_version == 11:
            return "HTTP/1.1"
        elif raw_version == 10:
            return "HTTP/1.0"
        elif raw_version == 20:
            return "HTTP/2"
    except Exception:
        pass
    return "HTTP/1.1"
```

**영향**: HTTP Version 컬럼 값이 정확해짐
**호환성**: 출력 형식 동일

### 1-3. DNS 조회 시간 기록

**현재**: `timings['dns_ms']` 계산하지만 `session_data`에 미포함
**변경**: `session_data`에 `DNS Time (ms)` 컬럼 추가

```python
# 메인 루프 session_data.append() 부분에 추가
"DNS Time (ms)": timings.get('dns_ms', 0),
```

**영향**: 리포트에 DNS 조회 시간 컬럼 추가
**호환성**: 기존 컬럼 유지, 신규 컬럼 추가만

### 1-4. 타임아웃 시 응답 시간 기록

**현재**: 에러 발생 시 `total_ms`가 0으로 기록
**변경**: 에러 시에도 경과 시간 기록

```python
# Monitor.check() 수정
total_start = time.time()
try:
    resp = self.session.get(...)
    ...
except requests.exceptions.RequestException as e:
    elapsed_ms = (time.time() - total_start) * 1000
    return {"error": str(e), "total_ms": elapsed_ms}, timings
```

**영향**: 실패 요청도 응답 시간 기록
**호환성**: 에러 딕셔너리에 필드 추가만 (기존 "error" 키 유지)

---

## Phase 2: DDoS 모니터링 핵심 기능 추가

> 공격 상황에서 서버 상태 변화를 감지하고 분류합니다.

### 2-1. 에러 유형 분류

**현재**: 모든 에러가 단일 문자열
**변경**: 에러를 유형별로 분류하여 기록

```python
# Monitor.check() 내부 예외 처리 세분화
except requests.exceptions.ConnectTimeout:
    return {"error": str(e), "error_type": "CONNECT_TIMEOUT", "total_ms": elapsed_ms}, timings
except requests.exceptions.ReadTimeout:
    return {"error": str(e), "error_type": "READ_TIMEOUT", "total_ms": elapsed_ms}, timings
except requests.exceptions.ConnectionError:
    return {"error": str(e), "error_type": "CONNECTION_REFUSED", "total_ms": elapsed_ms}, timings
except requests.exceptions.SSLError:
    return {"error": str(e), "error_type": "SSL_ERROR", "total_ms": elapsed_ms}, timings
except requests.exceptions.RequestException:
    return {"error": str(e), "error_type": "OTHER", "total_ms": elapsed_ms}, timings
```

**session_data에 추가**:
```python
"Error Type": result.get("error_type", ""),
```

**영향**: 리포트에 에러 유형 컬럼 추가 → 공격 영향 분석 가능
**호환성**: 기존 `"error"` 키 유지, `"error_type"` 추가만

### 2-2. alert_thresholds 적용

**현재**: sites.json에 정의만 있고 코드에서 미사용
**변경**: 임계값 초과 시 콘솔 경고 표시

```python
# Target 클래스에 추가
self.max_response_time = config.get("alert_thresholds", {}).get("max_response_time_ms", 5000)
self.expected_status = config.get("alert_thresholds", {}).get("expected_status_code", 200)
```

```python
# 메인 루프 로그 출력 후 경고 체크
if result.get('total_ms', 0) > target.max_response_time:
    print(f"  ⚠ [ALERT] 응답 시간 임계값 초과: {result['total_ms']:.0f}ms > {target.max_response_time}ms")
if result.get('status', -1) != target.expected_status:
    print(f"  ⚠ [ALERT] 상태 코드 불일치: {result.get('status')} (예상: {target.expected_status})")
```

**영향**: 콘솔에 경고 메시지 추가 출력
**호환성**: 기존 로그 형식 유지, 아래에 경고줄만 추가

### 2-3. 서버 상태 변화 감지

**현재**: 없음
**변경**: 연속 실패/복구를 감지하여 알림

```python
# main() 내 상태 추적 변수
server_status = {}  # {url: {"consecutive_fails": 0, "is_down": False, "down_since": None}}
```

```python
# 각 요청 후 상태 업데이트
if "error" in result or result.get("status", -1) != target.expected_status:
    status["consecutive_fails"] += 1
    if status["consecutive_fails"] >= 3 and not status["is_down"]:
        status["is_down"] = True
        status["down_since"] = now
        print(f"\n{'!'*60}")
        print(f"  🔴 [DOWN] 서버 다운 감지: {target.url}")
        print(f"  연속 {status['consecutive_fails']}회 실패 | 시각: {now.strftime('%H:%M:%S')}")
        print(f"{'!'*60}\n")
else:
    if status["is_down"]:
        downtime = (now - status["down_since"]).total_seconds()
        print(f"\n{'='*60}")
        print(f"  🟢 [RECOVERY] 서버 복구 감지: {target.url}")
        print(f"  다운타임: {downtime:.1f}초 | 복구 시각: {now.strftime('%H:%M:%S')}")
        print(f"{'='*60}\n")
    status["consecutive_fails"] = 0
    status["is_down"] = False
    status["down_since"] = None
```

**영향**: 상태 변화 시 강조된 알림 메시지 추가
**호환성**: 기존 로그 출력 유지, 알림은 별도 줄로 추가

---

## Phase 3: 운영 편의성 개선

> 모니터링 운영 시 유연성과 가시성을 높입니다.

### 3-1. 모니터링 주기 설정

**현재**: `time.sleep(3)` 하드코딩
**변경**: 시작 시 사용자 입력으로 설정

```python
# select_monitoring_mode() 이후 추가
def select_monitoring_interval():
    """모니터링 주기 설정"""
    global MONITORING_INTERVAL
    print("[INPUT] 모니터링 주기를 입력하세요 (초 단위, 기본값 3): ", end="")
    try:
        val = input().strip()
        MONITORING_INTERVAL = int(val) if val else 3
        if MONITORING_INTERVAL < 1:
            MONITORING_INTERVAL = 1
    except (ValueError, KeyboardInterrupt):
        MONITORING_INTERVAL = 3
    print(f"[✓] 모니터링 주기: {MONITORING_INTERVAL}초\n")
```

```python
# 메인 루프 sleep 변경
time.sleep(MONITORING_INTERVAL)  # 기존: time.sleep(3)
```

**영향**: 시작 시 주기 입력 프롬프트 추가
**호환성**: 기본값 3초 유지 (엔터만 누르면 동일 동작)

### 3-2. 실시간 상태 요약 (N회마다)

**현재**: 매 요청마다 한 줄 로그만 출력
**변경**: 10회마다 요약 통계 출력

```python
# 메인 루프 카운터 추가
loop_count = 0

# 루프 내부
loop_count += 1
if loop_count % 10 == 0:
    for url, data in session_data.items():
        recent = data[-10:]  # 최근 10회
        success = len([d for d in recent if d.get('Status') == 200])
        avg_time = sum(d.get('Total Response Time (ms)', 0) for d in recent) / max(len(recent), 1)
        print(f"\n--- [{url}] 최근 10회 요약: 성공률 {success}/10 ({success*10}%) | 평균 응답시간 {avg_time:.1f}ms ---\n")
```

**영향**: 10회마다 요약줄 추가
**호환성**: 기존 로그 사이에 요약 삽입, 형식 변경 없음

### 3-3. PCAP BPF 필터 개선

**현재**: `host {hostname}` — 호스트명을 BPF에 직접 사용
**변경**: DNS resolve된 IP 주소를 사용

```python
# PCAP 캡처 필터 생성 시
all_ips = []
temp_monitor = Monitor()
for t in targets:
    if t.ip:
        all_ips.append(t.ip)
    else:
        resolved = temp_monitor.resolve_domain(t.host)
        all_ips.extend(resolved)
temp_monitor.session.close()

capture_filter = " or ".join([f"host {ip}" for ip in set(all_ips)]) if all_ips else ""
```

**영향**: PCAP 캡처 필터가 IP 기반으로 변경
**호환성**: 캡처되는 패킷 내용 동일, 필터 안정성 향상

### 3-4. sites.json 미사용 필드 연결

**현재**: `load_resources`, `verify_ssl`, `resource_timeout`, `max_resources` 무시
**변경**: Target 클래스에서 읽어오되 글로벌 모드가 우선

```python
# Target 클래스에 추가
self.load_resources = config.get("load_resources", False)
self.verify_ssl = config.get("verify_ssl", False)
self.resource_timeout = config.get("resource_timeout", 3)
self.max_resources = config.get("max_resources", 50)
```

```python
# Monitor.check() 리소스 다운로드 부분에서 사용
for res_url in resources[:target.max_resources]:
    res_resp = self.session.get(res_url, verify=False, timeout=target.resource_timeout)
```

**영향**: sites.json의 per-site 설정이 실제로 적용됨
**호환성**: 기본값이 현재 하드코딩 값과 동일 (timeout=3, max=50)

---

## Phase 4: 리포트 강화

> DDoS 훈련 결과 보고서에 필요한 분석 데이터를 추가합니다.

### 4-1. 리포트에 에러 유형 통계 추가

**변경 파일**: `save_session_report()`, `generate_excel_report()`

```
Summary Statistics 섹션에 추가:
 - Connection Timeout: 5회
 - Read Timeout: 12회
 - Connection Refused: 3회
 - SSL Error: 0회
 - Other: 1회
```

### 4-2. 리포트에 다운타임 구간 기록

```
Downtime Events:
 [1] 14:23:15 ~ 14:25:42 (다운타임: 147초, 연속 실패 49회)
 [2] 14:30:01 ~ 14:30:31 (다운타임: 30초, 연속 실패 10회)
 총 다운타임: 177초
```

### 4-3. 그래프 강화

**변경 파일**: `generate_graphs()`

- 기존 2개 그래프 유지 (Response Time + Success Rate)
- 3번째 그래프 추가: **타임라인 기반 상태 히트맵** (시간축 기준 초록/빨강)
- 4번째 그래프 추가 (Phase 2 적용 시): **에러 유형별 분포**

```python
fig, axes = plt.subplots(2, 2, figsize=(20, 14))
# axes[0,0]: Response Time Trend (기존)
# axes[0,1]: Success Rate Pie (기존)
# axes[1,0]: 상태 타임라인 히트맵 (신규)
# axes[1,1]: 에러 유형 분포 (신규)
```

---

## 구현 순서 요약

```
Phase 1 (데이터 정확성) ← 우선 구현, 기존 동작 최소 변경
  └─ 1-1. TLS 버전 실제 감지
  └─ 1-2. HTTP 버전 감지 수정
  └─ 1-3. DNS 조회 시간 기록
  └─ 1-4. 타임아웃 시 응답 시간 기록

Phase 2 (DDoS 핵심) ← 가장 중요한 가치 추가
  └─ 2-1. 에러 유형 분류
  └─ 2-2. alert_thresholds 적용
  └─ 2-3. 서버 상태 변화 감지

Phase 3 (운영 편의성) ← 사용성 개선
  └─ 3-1. 모니터링 주기 설정
  └─ 3-2. 실시간 상태 요약
  └─ 3-3. PCAP BPF 필터 개선
  └─ 3-4. sites.json 미사용 필드 연결

Phase 4 (리포트 강화) ← 훈련 보고서 품질 향상
  └─ 4-1. 에러 유형 통계
  └─ 4-2. 다운타임 구간 기록
  └─ 4-3. 그래프 강화
```

---

## 파일 변경 범위

| 파일 | 변경 유형 |
|------|-----------|
| `web-monitor-v6.5-5-final-single-plus.py` | 기존 파일 수정 (신규 파일 생성 안함) |
| `sites.json` | 변경 없음 (기존 필드 활용만) |

---

## 주의사항

1. **모든 Phase는 독립적** — Phase 1만 적용해도 정상 동작
2. **기존 출력 형식 유지** — 로그, 리포트, 엑셀의 기존 컬럼/포맷 변경 없음
3. **새 기능은 추가만** — 기존 필드 삭제 안함, 새 컬럼/메시지 추가만
4. **기본값 = 현재 동작** — 새 설정의 기본값은 현재 하드코딩된 값과 동일
5. **외부 의존성 추가 없음** — 현재 사용 중인 라이브러리만 활용
