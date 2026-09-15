"""core/notify.py: 채널 미설정 시 조용히 넘어가는지, 설정돼 있으면 보내는지,
개별 채널 전송 실패가 notify() 자체를 죽이지 않는지 검증한다."""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("OPENAI_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import notify


class NotifyTestCase(unittest.TestCase):
    def test_no_channels_configured_does_not_raise(self):
        with mock.patch.object(notify, "NOTIFY_SLACK_WEBHOOK_URL", ""), \
             mock.patch.object(notify, "NOTIFY_EMAIL_TO", ""):
            notify.notify("제목", "본문")  # 예외 없이 끝나야 한다

    def test_slack_sent_when_webhook_configured(self):
        with mock.patch.object(notify, "NOTIFY_SLACK_WEBHOOK_URL", "https://hooks.slack.test/x"), \
             mock.patch.object(notify, "NOTIFY_EMAIL_TO", ""), \
             mock.patch("core.notify.urllib.request.urlopen") as mock_urlopen:
            notify.notify("배치 중단", "사유: 테스트")
            self.assertTrue(mock_urlopen.called)
            sent_req = mock_urlopen.call_args[0][0]
            self.assertEqual(sent_req.full_url, "https://hooks.slack.test/x")

    def test_email_sent_when_smtp_configured(self):
        with mock.patch.object(notify, "NOTIFY_SLACK_WEBHOOK_URL", ""), \
             mock.patch.object(notify, "NOTIFY_EMAIL_TO", "me@example.com"), \
             mock.patch.object(notify, "NOTIFY_EMAIL_SMTP_HOST", "smtp.example.com"), \
             mock.patch.object(notify, "NOTIFY_EMAIL_SMTP_USER", "bot@example.com"), \
             mock.patch("core.notify.smtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value.__enter__.return_value
            notify.notify("배치 중단", "사유: 테스트")
            self.assertTrue(instance.send_message.called)

    def test_one_channel_failure_does_not_block_the_other(self):
        with mock.patch.object(notify, "NOTIFY_SLACK_WEBHOOK_URL", "https://hooks.slack.test/x"), \
             mock.patch.object(notify, "NOTIFY_EMAIL_TO", "me@example.com"), \
             mock.patch.object(notify, "NOTIFY_EMAIL_SMTP_HOST", "smtp.example.com"), \
             mock.patch.object(notify, "NOTIFY_EMAIL_SMTP_USER", "bot@example.com"), \
             mock.patch("core.notify.urllib.request.urlopen", side_effect=RuntimeError("네트워크 오류")), \
             mock.patch("core.notify.smtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value.__enter__.return_value
            notify.notify("배치 중단", "사유: 테스트")  # Slack 실패해도 예외 없이 끝나야 한다
            self.assertTrue(instance.send_message.called)


if __name__ == "__main__":
    unittest.main()
