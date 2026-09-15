"""
기획팀 — 리서치팀이 넘긴 키워드·참고자료를 받아 F목록(사실 목록)과 제목
45/50개 후보를 뽑고, 그중 하나를 골라 작성팀에 넘긴다. 지침 원문(턴1)의
"입력 판정 → 정보 수집 → 제목 생성" 단계를 담당한다.

기획팀·작성팀·디자인팀은 core.pipeline.BlogPipeline이라는 하나의 사내
업무 스레드(대화 맥락)를 순서대로 이어받아 쓴다 — 매니저가 부서마다 새
스레드를 만드는 게 아니라, 같은 스레드를 넘겨가며 일한다.
"""

from core.pipeline import BlogPipeline


def propose_titles(pipeline: BlogPipeline, keyword: str, reference: str = "",
                    extra: str = "", image_mode: str = "인포") -> dict:
    """키워드(+참고자료)를 받아 F목록과 제목 후보 목록을 만든다."""
    print(f"[기획팀] '{keyword}' 관련 자료를 조사하고 제목 후보를 뽑습니다...")
    turn1 = pipeline.run_turn1(keyword, reference, image_mode, extra)
    if not turn1.get("titles"):
        raise RuntimeError("기획팀이 제목을 하나도 만들지 못했습니다. 원본 응답:\n" + pipeline.current_raw)
    print(f"[기획팀] 제목 후보 {len(turn1['titles'])}개를 보고합니다.")
    return turn1


def select_title(pipeline: BlogPipeline, turn1: dict, auto: bool, title_index: int = None) -> int:
    """제목 번호를 정한다. auto=True면 1번을 그대로 채택하고,
    그렇지 않으면 사람이 번호를 고르거나 자유 텍스트로 재작업을 지시할 수 있다."""
    titles = turn1["titles"]
    if title_index:
        return title_index
    if auto:
        return titles[0]["no"]

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
