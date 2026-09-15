"""
FACT_CHECK 다음, IMAGE 전에 실행하는 품질 게이트. 0~100점을 매겨서

  85점 이상       → 자동 통과(PASS)
  70~84점        → REVIEW (임시저장은 진행하되 사람이 한 번 봐야 함)
  69점 이하       → FAILED (이 게시물은 여기서 멈추고, 다른 게시물은 계속 진행)

기준점은 config.QUALITY_GATE_PASS_SCORE / QUALITY_GATE_REVIEW_SCORE
(계정별로는 account_config의 quality_gate.pass_score/review_score)로
조정할 수 있다.

점수는 두 부분을 합친다:
  - 휴리스틱 점수(글자수·소제목 수·금지어·문장 반복·중복 주제 등 코드로
    바로 셀 수 있는 것들)
  - AI 판정 점수(제목-본문 사실 일치, 과장 정도, 출처 없는 단정, 과도한
    AI 문체 — 코드로 세기 어려운 것들을 GPT에게 한 번 더 물어본다)
AI 판정 호출이 실패하면(네트워크 등) 휴리스틱 점수만으로 판단한다 —
이 단계 때문에 파이프라인 전체가 멈추면 안 되기 때문이다.
"""

import json
import os
import re
from typing import Optional

from openai import OpenAI

from config import OPENAI_MODEL, QUALITY_GATE_PASS_SCORE, QUALITY_GATE_REVIEW_SCORE

BANNED_WORDS = ["대박", "레전드", "미쳤다", "ㄹㅇ", "핵꿀팁"]

AI_JUDGE_INSTRUCTIONS = """당신은 네이버 블로그 글의 품질 검수자다. 제목과
본문, 이미 통과한 팩트체크 요약을 받는다.

다음 항목을 각각 점검한다:
1. 제목과 본문의 사실관계가 일치하는가(제목만 보고 낚였다는 느낌이 없는가)
2. 제목이 본문 내용에 비해 과장됐는가
3. 팩트체크 요약에 없는 수치·고유명사를 단정적으로 말하는 곳이 있는가
   (있다면 "~로 알려졌다" 같은 완곡한 표현으로 바뀌어야 한다)
4. 기계가 쓴 듯한 어색하거나 반복적인 문체가 심한가

0~100점으로 종합 점수를 매기고, 감점 사유를 findings에 짧게 나열하라.
다음 JSON 형식으로만 답하라:
{"score": 0-100, "findings": ["사유1", "사유2"]}
"""


def _heuristic_checks(title: str, body_text: str, char_count: int, min_chars: int,
                       max_chars: int, section_count: int, headings_target: int,
                       has_image_prompts: bool, duplicate_result: Optional[dict]) -> tuple:
    """(점수 0~100, findings 리스트)를 돌려준다. 100점에서 위반마다 감점한다."""
    score = 100
    findings = []

    if char_count < min_chars:
        score -= 15
        findings.append(f"글자수 부족: {char_count}자 (최소 {min_chars}자)")
    elif char_count > max_chars:
        score -= 10
        findings.append(f"글자수 초과: {char_count}자 (최대 {max_chars}자)")

    if section_count < max(2, headings_target - 3):
        score -= 10
        findings.append(f"소제목 수 부족: {section_count}개 (목표 {headings_target}개 안팎)")

    for word in BANNED_WORDS:
        if word in title or word in body_text:
            score -= 10
            findings.append(f"금지어 포함: '{word}'")

    sentences = [s.strip() for s in re.split(r"[.!?。]\s*", body_text) if len(s.strip()) > 10]
    if sentences:
        duplicated = len(sentences) - len(set(sentences))
        if duplicated > 0:
            score -= min(20, duplicated * 5)
            findings.append(f"동일/유사 문장 반복 {duplicated}건")

    if not has_image_prompts:
        score -= 15
        findings.append("이미지 생성 프롬프트가 없음")

    if duplicate_result and duplicate_result.get("is_duplicate"):
        best = duplicate_result.get("best_match") or {}
        score -= 15
        findings.append(
            f"최근 게시물과 유사도 높음(score={duplicate_result.get('score', 0):.2f}, "
            f"기존 글: {best.get('post_id', '?')}) — 새로운 정보 위주로 작성됐는지 확인 필요"
        )

    return max(0, score), findings


def _ai_judge(title: str, body_text: str, factcheck_summary: str) -> Optional[dict]:
    try:
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        response = client.responses.create(
            model=OPENAI_MODEL,
            instructions=AI_JUDGE_INSTRUCTIONS,
            input=f"제목: {title}\n\n팩트체크 요약: {factcheck_summary}\n\n본문:\n{body_text}",
        )
        match = re.search(r"\{.*\}", response.output_text, re.DOTALL)
        return json.loads(match.group(0)) if match else None
    except Exception as e:
        print(f"[품질게이트] AI 판정 실패({e}) — 휴리스틱 점수만으로 평가합니다.")
        return None


def evaluate(
    title: str,
    sections: list,
    char_count: int,
    factcheck_summary: str = "",
    min_chars: int = 1200,
    max_chars: int = 1500,
    headings_target: int = 5,
    has_image_prompts: bool = True,
    duplicate_result: Optional[dict] = None,
    pass_score: int = QUALITY_GATE_PASS_SCORE,
    review_score: int = QUALITY_GATE_REVIEW_SCORE,
) -> dict:
    """반환값: {"score": int, "verdict": "PASS"|"REVIEW"|"FAILED", "findings": [...]}"""
    body_text = "\n".join(
        p for s in sections for p in s.get("paragraphs", [])
    )
    heuristic_score, findings = _heuristic_checks(
        title, body_text, char_count, min_chars, max_chars,
        len(sections), headings_target, has_image_prompts, duplicate_result,
    )

    ai_result = _ai_judge(title, body_text, factcheck_summary)
    if ai_result and isinstance(ai_result.get("score"), (int, float)):
        ai_score = max(0, min(100, int(ai_result["score"])))
        findings.extend(ai_result.get("findings", []))
        final_score = round(heuristic_score * 0.6 + ai_score * 0.4)
    else:
        final_score = heuristic_score

    if final_score >= pass_score:
        verdict = "PASS"
    elif final_score >= review_score:
        verdict = "REVIEW"
    else:
        verdict = "FAILED"

    return {"score": final_score, "verdict": verdict, "findings": findings}
