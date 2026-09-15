"""
작성팀 — 기획팀이 정한 제목을 받아 소제목 구성·본문 작성·팩트체크·다듬기까지
한 번에 처리하고 최종본을 디자인팀·발행팀에 넘긴다. 지침 원문(턴2)의
"제목 선택 → 본문 작성 → 팩트체크 → 최종본" 단계를 담당한다.
"""

from core.pipeline import BlogPipeline


def draft_body(pipeline: BlogPipeline, title_no: int) -> dict:
    """선택된 제목 번호로 본문을 쓰고 팩트체크까지 마친 최종본을 받는다."""
    print(f"[작성팀] {title_no}번 제목으로 본문을 작성하고 팩트체크합니다...")
    turn2 = pipeline.run_turn2(title_no)
    print(f"[작성팀] {turn2.get('factcheck_summary', '')} · 글자수: {turn2.get('char_count', '?')}")
    return turn2


def finalize(pipeline: BlogPipeline, turn2: dict, auto: bool) -> dict:
    """auto=True면 수정 없이 그대로 확정한다. 그렇지 않으면 사람이 자유
    텍스트로 수정을 지시할 수 있고, Enter만 누르면 그대로 확정된다."""
    if auto:
        return turn2

    while True:
        print("\n" + pipeline.human_part())
        answer = input(
            "\n>> [작성팀에게 지시] 본문에 수정할 내용이 있으면 문장으로 입력하세요 "
            "(예: '3번째 소제목에 연비 얘기 추가해줘', '말투를 좀 더 담백하게'). "
            "없으면 그냥 Enter: "
        ).strip()
        if not answer:
            return turn2
        turn2 = pipeline.revise(answer)
