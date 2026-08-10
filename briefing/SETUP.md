# 브리핑 자동 발송 설정

매일 두 번, 보유 종목 기준 시황 브리핑을 텔레그램으로 받기 위한 설정이다.

| 브리핑 | 발송 시각 (KST) | 대상 | 프롬프트 |
|---|---|---|---|
| 미국장 마감 | 화~토 09:03 | 해외 보유 종목 | `briefing/us_market_0900.md` |
| 한국장 장중 | 월~금 15:02 | 국내 보유 종목 | `briefing/kr_market_1500.md` |

미국장 브리핑이 **화~토**인 이유: 미국 정규장은 한국시간 새벽에 끝난다. 금요일 미국장은
토요일 새벽에 마감되므로, 토요일 아침 브리핑까지 있어야 한 주가 빠짐없이 덮인다.

정각(:00)을 피해 :02, :03 으로 둔 건 스케줄러 부하가 정각에 몰리는 걸 피하기 위해서다.
체감 차이는 없다.

## 선행 조건 1 — 네트워크 허용 (현재 막혀 있음)

이 실행 환경의 아웃바운드는 정책 프록시를 통과한다. 확인 결과 **`api.telegram.org` 이
차단**되어 있다.

```
$ curl -sS https://api.telegram.org/bot<...>/getMe
curl: (56) CONNECT tunnel failed, response 403
```

프록시 상태에도 거부 기록이 남는다.

```
"recentRelayFailures": [
  { "kind": "connect_rejected",
    "detail": "gateway answered 403 to CONNECT (policy denial or upstream failure)",
    "host": "api.telegram.org:443" }
]
```

이건 코드 문제가 아니라 조직 egress 정책이다. **환경의 네트워크 허용 목록에
`api.telegram.org` 를 추가**해야 발송이 된다. 환경 설정 방법은
<https://code.claude.com/docs/en/claude-code-on-the-web> 참고. 정책 우회는 시도하지 않는다.

## 선행 조건 2 — 텔레그램 자격증명

1. 텔레그램에서 [@BotFather](https://t.me/BotFather) 에게 `/newbot` → 봇 토큰 발급
2. 생성한 봇과 대화방을 열고 아무 메시지나 전송
3. chat id 확인:
   `https://api.telegram.org/bot<토큰>/getUpdates` → `result[0].message.chat.id`
4. 두 값을 **환경 변수로** 등록한다 (환경 설정의 environment variables).

```
TELEGRAM_BOT_TOKEN=123456:AA...
TELEGRAM_CHAT_ID=987654321
```

> 토큰은 저장소에 커밋하지 않는다. 이 리포지토리에는 코드만 두고 값은 환경 변수로만 넘긴다.
> 토큰이 유출되면 BotFather 에서 `/revoke` 로 즉시 폐기할 것.

## 동작 확인

```bash
python3 scripts/notify_telegram.py --check          # 자격증명 + 연결 점검
python3 scripts/notify_telegram.py --text "테스트"  # 실제 발송
```

`--check` 가 통과해야 Routine 을 등록할 의미가 있다.

## Routine 등록

두 선행 조건이 끝나면 아래 두 개를 등록한다. cron 은 **UTC 기준**이다(KST = UTC+9).

| 브리핑 | cron (UTC) | 의미 |
|---|---|---|
| 미국장 마감 | `3 0 * * 2-6` | 화~토 09:03 KST |
| 한국장 장중 | `2 6 * * 1-5` | 월~금 15:02 KST |

각 Routine 의 프롬프트에는 해당 `briefing/*.md` 의 지시문을 그대로 넣는다. Routine 은
매 실행마다 새 세션을 띄우므로 프롬프트가 자기완결적이어야 한다.

## 보유 종목 갱신

브리핑은 `scripts/portfolio.json` 을 기준으로 종목을 고른다. 매매 후에는 이 파일을 고쳐야
브리핑 대상이 맞게 유지된다.

```bash
python3 scripts/portfolio_report.py --market all
```
