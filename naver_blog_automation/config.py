import os

from dotenv import load_dotenv

load_dotenv()

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
OPENAI_WEB_SEARCH_TOOL = os.getenv("OPENAI_WEB_SEARCH_TOOL", "web_search_preview")
NAVER_SESSION_FILE = os.getenv("NAVER_SESSION_FILE", "naver_session.json")
CHATGPT_SESSION_FILE = os.getenv("CHATGPT_SESSION_FILE", "chatgpt_session.json")
PROMPT_PATH = os.getenv("PROMPT_PATH", "prompts/system_prompt.txt")
