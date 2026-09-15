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
    OpenAI Responses API 대화 하나로 자동 실행한다."""

    def __init__(self, system_prompt: str):
        self.client = ConversationClient(system_prompt)
        self.turn1_raw = None
        self.turn2_raw = None
        self.turn3_raw = None

    def run_turn1(self, keyword: str, reference_text: str = "", image_mode: str = "둘다") -> dict:
        user_message = (
            f"키워드 또는 제목: {keyword}\n"
            f"참고 본문: {reference_text or '(없음)'}\n"
            f"이미지 모드: {image_mode}\n"
            f"레퍼런스 썸네일: (없음)"
        )
        self.turn1_raw = self.client.send(user_message)
        return _extract_automation_json(self.turn1_raw)

    def run_turn2(self, title_no: int) -> dict:
        self.turn2_raw = self.client.send(str(title_no))
        return _extract_automation_json(self.turn2_raw)

    def run_turn3(self) -> dict:
        self.turn3_raw = self.client.send("이미지")
        return _extract_automation_json(self.turn3_raw)
