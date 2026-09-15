import os

from dotenv import load_dotenv

load_dotenv()

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
OPENAI_WEB_SEARCH_TOOL = os.getenv("OPENAI_WEB_SEARCH_TOOL", "web_search_preview")
NAVER_SESSION_FILE = os.getenv("NAVER_SESSION_FILE", "secrets/naver_session.json")
CHATGPT_SESSION_FILE = os.getenv("CHATGPT_SESSION_FILE", "secrets/chatgpt_session.json")
PROMPT_PATH = os.getenv("PROMPT_PATH", "prompts/system_prompt.txt")

# 이미지 생성 기본 경로. "openai_api"(기본, 공식 API 우선) 또는
# "chatgpt_web"(레거시 — core/legacy/chatgpt_image.py, 브라우저 자동화).
IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "openai_api")

# 재시도 정책 (core/retry_policy.py)
RETRY_MAX_ATTEMPTS = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))
RETRY_BACKOFF_BASE_SECONDS = int(os.getenv("RETRY_BACKOFF_BASE_SECONDS", "5"))
RETRY_BACKOFF_MULTIPLIER = int(os.getenv("RETRY_BACKOFF_MULTIPLIER", "3"))

# QUALITY_GATE 기준점 (core/quality_gate.py)
QUALITY_GATE_PASS_SCORE = int(os.getenv("QUALITY_GATE_PASS_SCORE", "85"))
QUALITY_GATE_REVIEW_SCORE = int(os.getenv("QUALITY_GATE_REVIEW_SCORE", "70"))

# 중복 주제 탐지 (core/duplicate_check.py)
DUPLICATE_CHECK_WINDOW_DAYS = int(os.getenv("DUPLICATE_CHECK_WINDOW_DAYS", "30"))
DUPLICATE_SIMILARITY_THRESHOLD = float(os.getenv("DUPLICATE_SIMILARITY_THRESHOLD", "0.85"))
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
