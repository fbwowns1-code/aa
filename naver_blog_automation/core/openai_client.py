import os
from typing import Optional

from openai import OpenAI

from config import OPENAI_MODEL, OPENAI_WEB_SEARCH_TOOL


class ConversationClient:
    """OpenAI Responses API를 감싸는 얇은 래퍼.

    previous_response_id로 서버 쪽에 대화 맥락(F목록, 선택한 제목, 본문 등)을
    유지시켜서, 매 턴마다 이전 내용을 다시 붙여 보낼 필요가 없게 한다.
    instructions(시스템 프롬프트)는 매 호출마다 다시 넘긴다 — Responses API가
    previous_response_id로 이전 instructions까지 자동으로 이어붙여준다는
    보장이 없으므로, 안전하게 매번 명시한다.
    """

    def __init__(self, system_prompt: str, api_key: Optional[str] = None):
        self.client = OpenAI(api_key=api_key or os.environ["OPENAI_API_KEY"])
        self.system_prompt = system_prompt
        self.previous_response_id: Optional[str] = None

    def send(self, user_message: str, use_web_search: bool = True) -> str:
        kwargs = {
            "model": OPENAI_MODEL,
            "instructions": self.system_prompt,
            "input": user_message,
        }
        if self.previous_response_id:
            kwargs["previous_response_id"] = self.previous_response_id
        if use_web_search:
            kwargs["tools"] = [{"type": OPENAI_WEB_SEARCH_TOOL}]

        response = self.client.responses.create(**kwargs)
        self.previous_response_id = response.id
        return response.output_text
