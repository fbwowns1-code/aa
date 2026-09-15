"""
야간 무인 배치가 시스템적 오류로 멈추거나(로그인 세션 만료, 네이버 UI
구조 변경 등) 스케줄러 프로세스 자체가 예상치 못하게 죽었을 때, 다음날
아침까지 아무도 모르고 지나가지 않도록 사람에게 알리는 모듈.

.env에 아무 것도 설정하지 않으면(기본값) 콘솔/logs/automation_*.log에만
남기고 조용히 넘어간다 — 선택 기능이라 설정 안 해도 기존처럼 동작한다.
아래 중 하나 이상을 .env에 채우면 그 경로로도 알림을 보낸다.

  NOTIFY_SLACK_WEBHOOK_URL                                  — Slack Incoming Webhook
  NOTIFY_EMAIL_TO + NOTIFY_EMAIL_SMTP_HOST/_USER/_PASSWORD  — 이메일(SMTP)

알림 전송 자체가 실패해도(네트워크 오류, 잘못된 웹훅 URL 등) 예외를 절대
위로 던지지 않는다 — 알림 실패가 배치 실행을 막으면 안 되기 때문이다.
"""

import json
import smtplib
import urllib.request
from email.mime.text import MIMEText
from typing import Optional

from config import (
    NOTIFY_EMAIL_SMTP_HOST,
    NOTIFY_EMAIL_SMTP_PASSWORD,
    NOTIFY_EMAIL_SMTP_PORT,
    NOTIFY_EMAIL_SMTP_USER,
    NOTIFY_EMAIL_TO,
    NOTIFY_SLACK_WEBHOOK_URL,
)
from core.logger import log_event


def _send_slack(subject: str, message: str) -> None:
    if not NOTIFY_SLACK_WEBHOOK_URL:
        return
    payload = json.dumps({"text": f"*{subject}*\n{message}"}).encode("utf-8")
    req = urllib.request.Request(
        NOTIFY_SLACK_WEBHOOK_URL, data=payload,
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=10)


def _send_email(subject: str, message: str) -> None:
    if not (NOTIFY_EMAIL_TO and NOTIFY_EMAIL_SMTP_HOST and NOTIFY_EMAIL_SMTP_USER):
        return
    msg = MIMEText(message)
    msg["Subject"] = subject
    msg["From"] = NOTIFY_EMAIL_SMTP_USER
    msg["To"] = NOTIFY_EMAIL_TO
    with smtplib.SMTP(NOTIFY_EMAIL_SMTP_HOST, NOTIFY_EMAIL_SMTP_PORT, timeout=15) as smtp:
        smtp.starttls()
        smtp.login(NOTIFY_EMAIL_SMTP_USER, NOTIFY_EMAIL_SMTP_PASSWORD)
        smtp.send_message(msg)


_CHANNELS = ((_send_slack, "Slack"), (_send_email, "이메일"))


def notify(subject: str, message: str, account_id: Optional[str] = None,
           post_id: Optional[str] = None, step: Optional[str] = None) -> None:
    """설정된 채널(Slack/이메일)로 알림을 보낸다. 채널이 하나도 설정 안 돼
    있으면 로그만 남기고 조용히 넘어간다. 개별 채널 전송 실패는 서로
    독립적으로 무시한다(예: 이메일 설정이 틀려도 Slack은 정상 발송)."""
    log_event(account_id, post_id, step or "NOTIFY", "ERROR", f"{subject}: {message}")
    for sender, name in _CHANNELS:
        try:
            sender(subject, message)
        except Exception as e:
            log_event(account_id, post_id, step or "NOTIFY", "WARNING",
                      f"{name} 알림 전송 실패(무시하고 계속): {e}")
