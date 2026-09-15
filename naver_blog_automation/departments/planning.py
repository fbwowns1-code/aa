"""
기획팀 — 리서치팀이 넘긴 키워드·참고자료를 받아 F목록(사실 목록)과 제목
45/50개 후보를 뽑고, 그중 하나를 골라 작성팀에 넘긴다. 지침 원문(턴1)의
"입력 판정 → 정보 수집 → 제목 생성" 단계를 담당한다.

기획팀·작성팀·디자인팀은 core.pipeline.BlogPipeline이라는 하나의 사내
업무 스레드(대화 맥락)를 순서대로 이어받아 쓴다 — 매니저가 부서마다 새
스레드를 만드는 게 아니라, 같은 스레드를 넘겨가며 일한다.
"""

from core.pipeline import BlogPipeline

# 지침 원문(턴1 1-5절)의 카테고리 이름과 정확히 같아야 매칭된다.
HOOK_CATEGORY = "후킹/클릭 유도형"       # 6~10번
CURIOSITY_CATEGORY = "궁금증 폭발형"     # 21~25번


def _choose_first(titles: list) -> int:
    """가장 기본적인 채택 방식 — SEO 최적화형 1번을 그대로 쓴다."""
    return titles[0]["no"]


def _choose_hook_curiosity_short(titles: list) -> int:
    """후킹/클릭 유도형과 궁금증 폭발형을 섞은 후보(총 10개) 중에서
    가장 짧은 제목을 고른다. 두 카테고리 다 후킹 장치가 강해서 길어지기
    쉬운데, 그중 짧고 간결한 쪽을 우선해서 제목이 늘어지지 않게 한다."""
    candidates = [t for t in titles if t.get("category") in (HOOK_CATEGORY, CURIOSITY_CATEGORY)]
    if not candidates:
        return _choose_first(titles)
    shortest = min(candidates, key=lambda t: len(t.get("text", "")))
    return shortest["no"]


TITLE_STRATEGIES = {
    "first": _choose_first,
    "hook_curiosity_mix": _choose_hook_curiosity_short,
}
DEFAULT_TITLE_STRATEGY = "hook_curiosity_mix"


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
                  title_strategy: str = DEFAULT_TITLE_STRATEGY) -> int:
    """제목 번호를 정한다.

    title_index가 있으면 그 번호를 그대로 쓴다. auto=True면 title_strategy에
    따라 자동으로 고른다 — "hook_curiosity_mix"(기본값)는 후킹/클릭
    유도형(6~10번)과 궁금증 폭발형(21~25번)을 섞어 그중 가장 짧은 제목을,
    "first"는 예전처럼 SEO 최적화형 1번을 그대로 쓴다. auto가 아니면 사람이
    번호를 고르거나 자유 텍스트로 재작업을 지시할 수 있다."""
    titles = turn1["titles"]
    if title_index:
        return title_index
    if auto:
        strategy_fn = TITLE_STRATEGIES.get(title_strategy, _choose_first)
        return strategy_fn(titles)

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
