import json
import re

from src.openai_client import ConversationClient

AUTOMATION_MARKER = "---AUTOMATION-JSON---"


def _extract_automation_json(text: str) -> dict:
    if AUTOMATION_MARKER not in text:
        raise ValueError(
            "응답에 자동화 JSON 블록(---AUTOMATION-JSON---)이 없습니다. "
            "모델이 지침의 어댑터 섹션을 따르지 않은 것으로 보입니다. "
            "응답 마지막 부분:\n" + text[-2000:]
        )
    tail = text.split(AUTOMATION_MARKER, 1)[1]
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", tail, re.DOTALL)
    if not match:
        raise ValueError("자동화 JSON 코드블록을 찾지 못했습니다:\n" + tail[:2000])
    return json.loads(match.group(1))


class BlogPipeline:
    """지침의 3턴(제목 → 본문/팩트체크 → 이미지 프롬프트) 흐름을
    OpenAI Responses API 대화 하나로 실행한다.

    각 턴 사이에 사용자가 자유 텍스트로 수정 요청을 넣을 수 있도록
    revise()를 제공한다 — 지침 원문의 "제목 번호를 골라달라" /
    "수정할 곳이 있으면 말해달라" 지점을 그대로 살린 것이다.
    """

    def __init__(self, system_prompt: str):
        self.client = ConversationClient(system_prompt)
        self.current_raw = None  # 가장 최근 모델 응답 원문(사람이 읽는 부분 + JSON)

    def _send(self, message: str, use_web_search: bool = True) -> dict:
        self.current_raw = self.client.send(message, use_web_search=use_web_search)
        return _extract_automation_json(self.current_raw)

    def run_turn1(self, keyword: str, reference_text: str = "", image_mode: str = "둘다",
                  extra_request: str = "") -> dict:
        user_message = (
            f"키워드 또는 제목: {keyword}\n"
            f"참고 본문: {reference_text or '(없음)'}\n"
            f"이미지 모드: {image_mode}\n"
            f"레퍼런스 썸네일: (없음)"
        )
        if extra_request:
            user_message += f"\n\n위 입력에 추가로 반영해줄 요청사항: {extra_request}"
        return self._send(user_message)

    def run_turn2(self, title_no) -> dict:
        return self._send(str(title_no))

    def run_turn3(self) -> dict:
        return self._send("이미지")

    def revise(self, message: str) -> dict:
        """현재 턴(제목 목록/본문/이미지 프롬프트 중 방금 받은 것)에 대해
        자유 텍스트로 수정을 요청하고, 같은 형식의 자동화 JSON을 다시 받는다."""
        return self._send(message)

    def human_part(self) -> str:
        """가장 최근 응답에서 사람이 읽는 부분만 돌려준다(자동화 JSON 블록 제외)."""
        if not self.current_raw:
            return ""
        return self.current_raw.split(AUTOMATION_MARKER, 1)[0].strip()
