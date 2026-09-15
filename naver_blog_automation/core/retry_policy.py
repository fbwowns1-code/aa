"""
오류를 유형별로 분류하고, 재시도할지·얼마나 기다릴지를 정한다.

모든 오류를 똑같이 재시도하지 않는다 — 네트워크 순단이나 OpenAI rate
limit처럼 "기다리면 풀리는" 문제만 자동 재시도하고, 잘못된 로그인·세션
만료·콘텐츠 정책 위반처럼 "다시 해도 똑같이 막힐" 문제는 재시도하지
않고 바로 FAILED로 기록한다(job_manager가 이 판정을 보고 사람에게
알린다).
"""

import re
from typing import Optional, Tuple

from config import RETRY_MAX_ATTEMPTS, RETRY_BACKOFF_BASE_SECONDS, RETRY_BACKOFF_MULTIPLIER

ERROR_TYPES = (
    "AUTH_ERROR",
    "RATE_LIMIT",
    "NETWORK_ERROR",
    "CONTENT_ERROR",
    "NAVER_ERROR",
    "UNKNOWN_ERROR",
)

# (정규식 패턴, error_type, retryable) 순서대로 검사해서 처음 맞는 것을 쓴다.
_RULES: Tuple[Tuple[str, str, bool], ...] = (
    (r"rate.?limit|429|too many requests", "RATE_LIMIT", True),
    (r"세션 파일|출근 등록|세션이 만료|session expired|unauthorized|401",
     "AUTH_ERROR", False),
    (r"api[_ ]?key|incorrect api key|invalid_api_key|authenticationerror",
     "AUTH_ERROR", False),
    (r"선택자를 찾지 못했습니다", "NAVER_ERROR", False),  # UI 구조 변경 — 재시도 무의미
    (r"blog\.naver\.com|네이버|naver", "NAVER_ERROR", True),
    (r"content_policy|content policy|safety|moderation|정책.*거부|거부.*정책",
     "CONTENT_ERROR", False),
    (r"timeout|timed out|connection|econnreset|network|네트워크|dns",
     "NETWORK_ERROR", True),
)


def classify_error(error: Exception) -> Tuple[str, bool]:
    """(error_type, retryable) 튜플을 돌려준다."""
    text = f"{type(error).__name__}: {error}".lower()
    for pattern, error_type, retryable in _RULES:
        if re.search(pattern, text):
            return error_type, retryable
    # 알 수 없는 오류는 일시적일 가능성이 있으므로 기본은 재시도 허용.
    return "UNKNOWN_ERROR", True


def backoff_seconds(attempt: int) -> int:
    """attempt(1부터 시작)번째 실패 이후 대기 시간(초).
    기본: 1차 5초, 2차 15초, 3차 45초 (5 * 3^(n-1))."""
    if attempt < 1:
        attempt = 1
    return RETRY_BACKOFF_BASE_SECONDS * (RETRY_BACKOFF_MULTIPLIER ** (attempt - 1))


def should_retry(error: Exception, attempt: int, max_attempts: Optional[int] = None) -> bool:
    """attempt(지금까지 시도한 횟수, 1부터)가 최대 재시도 횟수 이내이고,
    오류 유형이 재시도 가능하면 True."""
    max_attempts = max_attempts if max_attempts is not None else RETRY_MAX_ATTEMPTS
    if attempt >= max_attempts:
        return False
    _, retryable = classify_error(error)
    return retryable
