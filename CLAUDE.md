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
│   ├── portfolio.json           # 보유 종목 스냅샷 — 브리핑 대상의 기준
│   ├── portfolio_report.py      # 보유 종목 집계/비중 리포트
│   └── notify_telegram.py       # 텔레그램 발송 + egress 차단 진단
└── briefing/
    ├── SETUP.md                 # 자동 발송 설정 절차와 현재 차단 상태
    ├── us_market_0900.md        # 미국장 마감 브리핑 프롬프트 (화~토 09:03 KST)
    └── kr_market_1500.md        # 한국장 장중 브리핑 프롬프트 (월~금 15:02 KST)
```

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
| 보유 종목 리포트 | `python3 scripts/portfolio_report.py --market all` |
| 시세 반영 리포트 | `python3 scripts/portfolio_report.py --prices prices.json` |
| 텔레그램 연결 점검 | `python3 scripts/notify_telegram.py --check` |
| 브리핑 수동 발송 | `python3 scripts/notify_telegram.py --text "본문"` |

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

**미해결 제약:** `api.telegram.org` 이 조직 egress 정책에서 차단(CONNECT 403)돼 있어 실제 발송은
아직 불가능하다. 환경의 네트워크 허용 목록에 해당 호스트를 추가해야 한다. 자세한 내용은
`briefing/SETUP.md` 참고. 정책 우회는 시도하지 않는다.

**비밀 값:** 텔레그램 토큰/chat id 는 환경 변수(`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`)로만
주입한다. 저장소에 커밋하지 않는다.
