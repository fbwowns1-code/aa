"""
CASE 3: 오류 유형 분류와 exponential backoff, 그리고 재시도 가능 여부
판단(core/retry_policy.py)을 검증한다.
"""

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("OPENAI_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.retry_policy import classify_error, backoff_seconds, should_retry


class RetryPolicyTestCase(unittest.TestCase):
    def test_classify_network_error_is_retryable(self):
        error_type, retryable = classify_error(TimeoutError("Connection timed out"))
        self.assertEqual(error_type, "NETWORK_ERROR")
        self.assertTrue(retryable)

    def test_classify_rate_limit_is_retryable(self):
        error_type, retryable = classify_error(Exception("RateLimitError: 429 Too Many Requests"))
        self.assertEqual(error_type, "RATE_LIMIT")
        self.assertTrue(retryable)

    def test_classify_auth_error_is_not_retryable(self):
        error_type, retryable = classify_error(Exception("AuthenticationError: Incorrect API key provided"))
        self.assertEqual(error_type, "AUTH_ERROR")
        self.assertFalse(retryable)

    def test_classify_session_expired_is_not_retryable(self):
        error_type, retryable = classify_error(RuntimeError("세션 파일(secrets/naver_session.json)이 없습니다"))
        self.assertEqual(error_type, "AUTH_ERROR")
        self.assertFalse(retryable)

    def test_classify_selector_not_found_is_not_retryable(self):
        error_type, retryable = classify_error(RuntimeError("선택자를 찾지 못했습니다: [...]"))
        self.assertEqual(error_type, "NAVER_ERROR")
        self.assertFalse(retryable)

    def test_classify_content_policy_is_not_retryable(self):
        error_type, retryable = classify_error(Exception("content_policy violation: safety"))
        self.assertEqual(error_type, "CONTENT_ERROR")
        self.assertFalse(retryable)

    def test_classify_unknown_defaults_to_retryable(self):
        error_type, retryable = classify_error(Exception("뭔가 알 수 없는 이상한 오류"))
        self.assertEqual(error_type, "UNKNOWN_ERROR")
        self.assertTrue(retryable)

    def test_exponential_backoff_5_15_45(self):
        self.assertEqual(backoff_seconds(1), 5)
        self.assertEqual(backoff_seconds(2), 15)
        self.assertEqual(backoff_seconds(3), 45)

    def test_should_retry_respects_max_attempts(self):
        err = TimeoutError("timeout")
        self.assertTrue(should_retry(err, attempt=1, max_attempts=3))
        self.assertTrue(should_retry(err, attempt=2, max_attempts=3))
        self.assertFalse(should_retry(err, attempt=3, max_attempts=3))

    def test_should_retry_false_for_non_retryable_even_with_attempts_left(self):
        err = Exception("api_key invalid")
        self.assertFalse(should_retry(err, attempt=1, max_attempts=5))


if __name__ == "__main__":
    unittest.main()
