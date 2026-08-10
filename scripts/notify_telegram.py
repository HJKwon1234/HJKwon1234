#!/usr/bin/env python3
"""텔레그램으로 브리핑 메시지를 보낸다.

사용법:
    python3 scripts/notify_telegram.py --text "본문"
    echo "본문" | python3 scripts/notify_telegram.py
    python3 scripts/notify_telegram.py --check        # 자격증명/연결만 점검

필요한 환경변수:
    TELEGRAM_BOT_TOKEN   @BotFather 에서 발급한 토큰
    TELEGRAM_CHAT_ID     메시지를 받을 chat id

이 컨테이너의 아웃바운드 HTTPS 는 정책 프록시를 통과한다. api.telegram.org 가
조직 egress 정책에서 허용돼 있지 않으면 CONNECT 단계에서 403 이 떨어진다.
그 경우는 코드 문제가 아니므로 우회하지 않고 원인을 그대로 출력한다.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import requests

API = "https://api.telegram.org"
CA_BUNDLE = "/root/.ccr/ca-bundle.crt"
TELEGRAM_LIMIT = 4096  # 텔레그램 sendMessage 본문 최대 길이


def _verify() -> str | bool:
    """프록시가 TLS 를 재종료하므로 사내 CA 번들이 있으면 그걸 신뢰한다."""
    return CA_BUNDLE if os.path.exists(CA_BUNDLE) else True


def _creds() -> tuple[str, str]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    missing = [n for n, v in (("TELEGRAM_BOT_TOKEN", token), ("TELEGRAM_CHAT_ID", chat_id)) if not v]
    if missing:
        sys.exit(
            f"[설정 누락] {', '.join(missing)} 이(가) 없습니다.\n"
            "환경 변수로 등록한 뒤 다시 실행하세요. 토큰은 절대 저장소에 커밋하지 마세요."
        )
    return token, chat_id


def _explain(exc: Exception) -> str:
    """프록시 차단과 일반 네트워크 오류를 구분해서 설명한다."""
    text = str(exc)
    if "403" in text and "CONNECT" in text.upper():
        return (
            "api.telegram.org 이 조직 egress 정책에서 차단돼 있습니다(프록시 CONNECT 403).\n"
            "환경의 네트워크 허용 목록에 api.telegram.org 를 추가해야 합니다. "
            "우회는 정책 위반이라 시도하지 않습니다."
        )
    return f"네트워크 오류: {text}"


def chunks(text: str, size: int = TELEGRAM_LIMIT) -> list[str]:
    """길이 제한을 넘으면 줄 단위로 잘라 여러 통으로 나눈다."""
    if len(text) <= size:
        return [text]
    out, cur = [], ""
    for line in text.splitlines(keepends=True):
        # 한 줄 자체가 제한을 넘으면 강제로 쪼갠다.
        while len(line) > size:
            if cur:
                out.append(cur)
                cur = ""
            out.append(line[:size])
            line = line[size:]
        if len(cur) + len(line) > size:
            out.append(cur)
            cur = line
        else:
            cur += line
    if cur:
        out.append(cur)
    return out


def send(text: str, *, retries: int = 3) -> None:
    token, chat_id = _creds()
    url = f"{API}/bot{token}/sendMessage"
    parts = chunks(text)
    for idx, part in enumerate(parts, 1):
        payload = {
            "chat_id": chat_id,
            "text": part,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        for attempt in range(retries):
            try:
                r = requests.post(url, json=payload, timeout=30, verify=_verify())
            except requests.RequestException as exc:
                if attempt == retries - 1:
                    sys.exit(f"[전송 실패] {_explain(exc)}")
                time.sleep(2 ** attempt)
                continue

            if r.status_code == 200:
                break
            # 429 는 텔레그램 레이트리밋이라 재시도 가치가 있다.
            if r.status_code == 429 and attempt < retries - 1:
                time.sleep(int(r.json().get("parameters", {}).get("retry_after", 2 ** attempt)))
                continue
            sys.exit(f"[전송 실패] HTTP {r.status_code}: {r.text[:300]}")
        print(f"전송 완료 ({idx}/{len(parts)})")


def check() -> None:
    token, _ = _creds()
    try:
        r = requests.get(f"{API}/bot{token}/getMe", timeout=20, verify=_verify())
    except requests.RequestException as exc:
        sys.exit(f"[점검 실패] {_explain(exc)}")
    if r.status_code != 200:
        sys.exit(f"[점검 실패] HTTP {r.status_code}: {r.text[:300]}")
    print("정상:", r.json().get("result", {}).get("username"))


def main() -> None:
    ap = argparse.ArgumentParser(description="텔레그램으로 브리핑 전송")
    ap.add_argument("--text", help="보낼 본문. 생략하면 stdin 에서 읽는다.")
    ap.add_argument("--check", action="store_true", help="자격증명과 연결만 점검")
    args = ap.parse_args()

    if args.check:
        check()
        return

    body = args.text if args.text is not None else sys.stdin.read()
    if not body.strip():
        sys.exit("보낼 본문이 비어 있습니다.")
    send(body)


if __name__ == "__main__":
    main()
