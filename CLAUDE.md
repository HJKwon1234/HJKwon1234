# CLAUDE.md

This file provides guidance for AI assistants working with this repository.

## Repository Overview

- **Repository**: HJKwon1234/HJKwon1234
- **Status**: New project (initial setup)

## Project Structure

This is a newly initialized repository. As the project grows, document the directory layout here.

```
/
├── CLAUDE.md                    # AI assistant guidance (this file)
├── astf_get_flood_v5_FINAL.py   # L7 HTTP flood traffic generator (unrelated to briefing)
├── scripts/
│   ├── portfolio.json           # 보유 종목 + 매매 이력 — 브리핑 대상의 기준
│   ├── strategy.json            # 원칙·트리거·목표 비중·감시 목록·이벤트
│   ├── strategy_check.py        # 원칙 대비 현재 위치 점검 (트리거 발동 판정)
│   ├── portfolio_report.py      # 보유 종목 집계/비중 리포트
│   └── notify_telegram.py       # 텔레그램 발송 + egress 차단 진단
└── briefing/
    ├── HANDOVER.md              # 원칙의 배경·시장 복기·데이터 신뢰도 (사람이 읽는 문서)
    ├── SETUP.md                 # 자동 발송 설정 절차와 현재 차단 상태
    ├── us_market_0900.md        # 미국장 마감 브리핑 프롬프트 (화~토 09:03 KST)
    └── kr_market_1500.md        # 한국장 장중 브리핑 프롬프트 (월~금 15:02 KST)
```

**데이터와 서술의 분리:** 숫자·규칙처럼 기계가 판정하는 것은 JSON 두 개에, "왜 그 원칙이
생겼는지"는 `briefing/HANDOVER.md` 에 둔다. 시세나 트리거가 바뀌면 JSON 을, 판단의 배경이
바뀌면 HANDOVER 를 고친다.

## Development Setup

<!-- Update this section when a build system, language, or framework is chosen -->

No build system or dependencies have been configured yet. Once the project is set up, document:

- Language and runtime version requirements
- How to install dependencies
- Environment variable configuration

## Common Commands

<!-- Add commands as the project develops -->

| Task | Command |
|------|---------|
| 원칙·트리거 전체 점검 | `python3 scripts/strategy_check.py` |
| 트리거만 확인 (시세 주입) | `python3 scripts/strategy_check.py --prices p.json --fx 1418 --section triggers` |
| 보유 종목 리포트 | `python3 scripts/portfolio_report.py --market all` |
| 텔레그램 연결 점검 | `python3 scripts/notify_telegram.py --check` |
| 브리핑 수동 발송 | `python3 scripts/notify_telegram.py --text "본문"` |

`--prices` 파일은 `{"삼성전자": 231500, "PLTR": 172.15}` 형태로 국내는 종목명, 해외는 티커를
키로 쓴다. `portfolio.json` 의 `last` 는 마지막 확인가일 뿐 실시간 시세가 아니므로, 매매 판단
전에는 항상 최신 시세를 주입하거나 증권사 화면에서 재확인한다.

브리핑 스크립트는 Python 3.11 + `requests` 만 사용한다. 별도 설치 단계는 없다.

## Code Conventions

<!-- Update with project-specific conventions as they emerge -->

- Write clear, descriptive commit messages
- Keep changes focused and atomic
- Follow the existing code style once established

## Testing

No testing framework has been configured yet. Update this section with:

- Test framework and runner
- How to run tests
- Test file naming and location conventions
- Coverage requirements

## Git Workflow

- **Primary branch**: `main` (to be created with first commit)
- Write descriptive commit messages explaining the "why" behind changes
- Keep commits focused on a single logical change

## Architecture Notes

### 시황 브리핑 자동 발송

브리핑 본문은 스크립트가 만들지 않는다. Routine 이 정해진 시각에 새 세션을 띄우고, 그 세션이
`briefing/*.md` 의 지시에 따라 웹 검색으로 시황을 조사한 뒤 본문을 조립한다. 스크립트는
전송(`notify_telegram.py`)과 보유 종목 집계(`portfolio_report.py`)만 담당한다. 시황 해석에는
판단이 필요해 규칙 기반으로 고정하기 어렵기 때문이다.

브리핑 대상 종목은 항상 `scripts/portfolio.json` 에서 읽는다. 매매 후 이 파일을 갱신하지 않으면
브리핑이 더 이상 보유하지 않은 종목을 다루게 된다.

### 투자 원칙은 코드가 판정한다

트리거 발동 여부를 눈대중으로 판단하지 않는다. `strategy_check.py` 가 `strategy.json` 의 규칙과
현재 시세를 대조해 판정하고, 브리핑은 그 출력을 근거로 삼는다. 사람이 표를 보고 어림하면
"+7.5% 남았다"를 "거의 도달"로 읽는 실수가 나기 때문이다.

**조건부 트리거 주의:** 가격 조건만 충족해도 발동이 아닌 항목이 있다. 삼성전자 3차 매수는
"22만원대 이탈"에 더해 "안정화 신호"가 필요하고, 하락 진행 중 매수는 원칙 2-3 위반이다.
스크립트는 가격 조건만 판정하므로 조건문을 함께 출력한다. 최종 판단은 사람이 한다.

**커버드콜 비중 오독 주의:** SCHD 는 배당성장 ETF 이지 커버드콜이 아니다. 합산하면 30% 상한을
넘긴 것처럼 보이지만 실제 커버드콜(JEPI·JEPQ·DIVO·CONY)은 약 11% 로 원칙을 지키고 있다.

**미해결 제약:** `api.telegram.org` 이 조직 egress 정책에서 차단(CONNECT 403)돼 있어 실제 발송은
아직 불가능하다. 환경의 네트워크 허용 목록에 해당 호스트를 추가해야 한다. 자세한 내용은
`briefing/SETUP.md` 참고. 정책 우회는 시도하지 않는다.

**비밀 값:** 텔레그램 토큰/chat id 는 환경 변수(`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`)로만
주입한다. 저장소에 커밋하지 않는다.
