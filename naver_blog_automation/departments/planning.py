"""
기획팀 — 리서치팀이 넘긴 키워드·참고자료를 받아 F목록(사실 목록)과 제목
45/50개 후보를 뽑고, 그중 하나를 골라 작성팀에 넘긴다. 지침 원문(턴1)의
"입력 판정 → 정보 수집 → 제목 생성" 단계를 담당한다.

기획팀·작성팀·디자인팀은 core.pipeline.BlogPipeline이라는 하나의 사내
업무 스레드(대화 맥락)를 순서대로 이어받아 쓴다 — 매니저가 부서마다 새
스레드를 만드는 게 아니라, 같은 스레드를 넘겨가며 일한다.

단, "클릭을 잘 유도하는 제목을 AI가 스스로 판단해서 고르는" 전략만은
예외로 별도의 짧은 대화를 새로 연다(core.openai_client) — 지침 원문이
정해둔 턴1/턴2/턴3의 고정된 흐름 안에 "어떤 제목이 반응이 좋을지 조사·
판단"하는 절차가 없어서, 그걸 기존 대화에 억지로 끼워 넣으면 다음
턴(제목 번호 선택)이 지침이 기대하는 형식과 어긋날 수 있기 때문이다.
"""

import json
import os
import re

from openai import OpenAI

from config import OPENAI_MODEL, OPENAI_WEB_SEARCH_TOOL
from core.pipeline import BlogPipeline

# 지침 원문(턴1 1-5절)의 카테고리 이름과 정확히 같아야 매칭된다.
HOOK_CATEGORY = "후킹/클릭 유도형"       # 6~10번
CURIOSITY_CATEGORY = "궁금증 폭발형"     # 21~25번

CLICK_APPEAL_INSTRUCTIONS = """당신은 네이버 블로그 홈판 클릭률(CTR) 전문가다.
입력으로 키워드와, 이미 만들어진 블로그 제목 후보 목록(번호·카테고리·
제목)을 받는다.

먼저 웹 검색으로 같은 키워드나 비슷한 주제를 다룬 실제 게시물 중 반응
(조회수·댓글·공유·좋아요)이 좋았던 제목 사례를 찾는다 — 네이버 블로그
인기글, 커뮤니티 인기글, 유튜브 썸네일 문구, 뉴스 헤드라인 등 클릭을
유도하는 데 실제로 효과가 검증된 제목의 공통 패턴(어떤 단어·구조·톤이
반응을 끌어냈는지)을 참고한다.

그다음 후보 목록 중에서, 그렇게 확인한 검증된 패턴과 가장 잘 맞아서
사람들이 클릭할 수밖에 없게 만드는 제목을 하나 고른다. 후보 목록에 없는
제목을 새로 만들거나 후보를 고쳐 쓰지 않는다 — 반드시 후보 중 하나의
번호를 그대로 고른다.

다음 JSON 형식으로만 답하라. 다른 텍스트나 코드블록 표시 없이 JSON 객체
하나만 출력한다.

{"selected_no": 번호, "reason": "이 제목이 왜 클릭을 유도하는지, 어떤 실제
사례의 패턴을 참고했는지 한두 문장"}
"""


def _choose_first(titles: list, keyword: str = "") -> int:
    """가장 기본적인 채택 방식 — SEO 최적화형 1번을 그대로 쓴다."""
    return titles[0]["no"]


def _hook_curiosity_candidates(titles: list) -> list:
    candidates = [t for t in titles if t.get("category") in (HOOK_CATEGORY, CURIOSITY_CATEGORY)]
    return candidates or titles


def _choose_hook_curiosity_short(titles: list, keyword: str = "") -> int:
    """후킹/클릭 유도형과 궁금증 폭발형을 섞은 후보(총 10개) 중에서
    가장 짧은 제목을 고른다. AI 판단(ai_click_appeal)이 실패했을 때의
    대체 방식으로도 쓰인다."""
    candidates = _hook_curiosity_candidates(titles)
    shortest = min(candidates, key=lambda t: len(t.get("text", "")))
    return shortest["no"]


def _choose_ai_click_appeal(titles: list, keyword: str = "") -> int:
    """후킹/클릭 유도형 + 궁금증 폭발형 후보를 놓고, 실제 반응 좋은 제목
    사례를 웹에서 찾아본 뒤 그 패턴에 가장 잘 맞는 제목을 AI가 골라준다.
    조사·판단에 실패하면(네트워크 문제, 응답 형식 오류 등) 가장 짧은
    제목을 고르는 방식으로 조용히 대체한다."""
    candidates = _hook_curiosity_candidates(titles)
    candidate_lines = "\n".join(
        f"{t['no']}. [{t.get('category', '')}] {t.get('text', '')}" for t in candidates
    )
    user_message = (
        f"키워드: {keyword}\n\n"
        f"후보 제목 목록:\n{candidate_lines}\n\n"
        "이 중에서 실제로 클릭을 가장 잘 유도할 제목 하나를 골라줘."
    )

    try:
        print("[기획팀] 반응 좋은 제목 사례를 웹에서 찾아보고 클릭 유도력을 판단합니다...")
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        response = client.responses.create(
            model=OPENAI_MODEL,
            instructions=CLICK_APPEAL_INSTRUCTIONS,
            input=user_message,
            tools=[{"type": OPENAI_WEB_SEARCH_TOOL}],
        )
        match = re.search(r"\{.*\}", response.output_text, re.DOTALL)
        result = json.loads(match.group(0))
        selected_no = int(result["selected_no"])
        if any(t["no"] == selected_no for t in candidates):
            print(f"[기획팀] 클릭 유도 판단: {selected_no}번 채택 — {result.get('reason', '')}")
            return selected_no
        print(f"[기획팀] AI가 후보 목록에 없는 번호({selected_no})를 골라서 대체 방식을 씁니다.")
    except Exception as e:
        print(f"[기획팀] 클릭 유도 판단에 실패했습니다({e}) — 가장 짧은 제목으로 대체합니다.")

    return _choose_hook_curiosity_short(titles, keyword)


TITLE_STRATEGIES = {
    "first": _choose_first,
    "hook_curiosity_mix": _choose_hook_curiosity_short,
    "ai_click_appeal": _choose_ai_click_appeal,
}
DEFAULT_TITLE_STRATEGY = "ai_click_appeal"


def propose_titles(pipeline: BlogPipeline, keyword: str, reference: str = "",
                    extra: str = "", image_mode: str = "인포") -> dict:
    """키워드(+참고자료)를 받아 F목록과 제목 후보 목록을 만든다."""
    print(f"[기획팀] '{keyword}' 관련 자료를 조사하고 제목 후보를 뽑습니다...")
    turn1 = pipeline.run_turn1(keyword, reference, image_mode, extra)
    if not turn1.get("titles"):
        raise RuntimeError("기획팀이 제목을 하나도 만들지 못했습니다. 원본 응답:\n" + pipeline.current_raw)
    print(f"[기획팀] 제목 후보 {len(turn1['titles'])}개를 보고합니다.")
    return turn1


def select_title(pipeline: BlogPipeline, turn1: dict, auto: bool, title_index: int = None,
                  title_strategy: str = DEFAULT_TITLE_STRATEGY, keyword: str = "") -> int:
    """제목 번호를 정한다.

    title_index가 있으면 그 번호를 그대로 쓴다. auto=True면 title_strategy에
    따라 자동으로 고른다:
      - "ai_click_appeal"(기본값): 후킹/클릭 유도형+궁금증 폭발형 후보를
        놓고, 웹에서 반응 좋은 실제 제목 사례를 찾아본 뒤 그 패턴에 맞는
        제목을 AI가 직접 판단해서 고른다.
      - "hook_curiosity_mix": 같은 후보 중 가장 짧은 제목을 기계적으로 고른다.
      - "first": 예전처럼 SEO 최적화형 1번을 그대로 쓴다.
    auto가 아니면 사람이 번호를 고르거나 자유 텍스트로 재작업을 지시할 수 있다."""
    titles = turn1["titles"]
    if title_index:
        return title_index
    if auto:
        strategy_fn = TITLE_STRATEGIES.get(title_strategy, _choose_first)
        return strategy_fn(titles, keyword)

    while True:
        print("\n" + pipeline.human_part())
        answer = input(
            "\n>> [기획팀에게 지시] 마음에 드는 제목 번호를 입력하세요.\n"
            "   재작업을 지시하려면 문장으로 입력하세요 (예: '오너 감정형 위주로 5개만 다시', "
            "'가격 정보를 제목에 넣어줘'): "
        ).strip()
        if not answer:
            continue
        if answer.isdigit():
            title_no = int(answer)
            if any(t["no"] == title_no for t in titles):
                return title_no
            print(f"[기획팀] {title_no}번은 목록에 없습니다. 다시 골라주세요.")
            continue
        # 숫자가 아니면 재작업 지시로 간주해서 그대로 모델에 전달한다.
        turn1 = pipeline.revise(answer)
        titles = turn1["titles"]
