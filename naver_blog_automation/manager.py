"""
총괄 매니저 — 회사의 다섯 부서(리서치팀·기획팀·작성팀·디자인팀·발행팀)에게
순서대로 일을 시키고 보고를 받아 다음 부서에 넘긴다.

  리서치팀(departments.research)   : 오늘의 글감 조사
  기획팀(departments.planning)     : 제목 후보 뽑고 확정
  작성팀(departments.writing)      : 본문 작성·팩트체크
  디자인팀(departments.design)     : 인포그래픽 썸네일 제작
  발행팀(departments.publishing)   : 네이버 블로그 임시저장

main.py(단발 지시)와 daily_batch.py(하루 배치 지시)는 이 매니저의
assign_single_post() / assign_daily_batch()를 부르는 창구일 뿐이고,
실제 업무 지시·보고 취합은 여기서 한다.
"""

import json
import traceback
from datetime import date
from pathlib import Path
from typing import Optional

from core.pipeline import BlogPipeline
from departments import research, planning, writing, design, publishing


def load_system_prompt(prompt_path: str) -> str:
    return Path(prompt_path).read_text(encoding="utf-8")


def assign_single_post(
    keyword: str,
    blog_id: str,
    reference: str = "",
    extra: str = "",
    title_index: Optional[int] = None,
    out_dir: str = "output",
    headless: bool = False,
    pause_before_save: bool = True,
    auto: bool = False,
    infographic_via_chatgpt: bool = True,
    prompt_path: str = "prompts/system_prompt.txt",
) -> dict:
    """글 한 편을 기획→작성→디자인→발행 순서로 만들어 네이버에 임시저장한다.

    반환값: {"keyword", "title", "char_count", "image_count"}
    """
    print(f"\n[매니저] '{keyword}' 건을 접수해서 기획팀에 넘깁니다.")
    pipeline = BlogPipeline(load_system_prompt(prompt_path))

    turn1 = planning.propose_titles(pipeline, keyword, reference, extra)
    chosen_no = planning.select_title(pipeline, turn1, auto, title_index)
    chosen = next(t for t in turn1["titles"] if t["no"] == chosen_no)
    print(f"[매니저] 기획팀 결과 확정: {chosen_no}번 «{chosen['text']}» → 작성팀에 넘깁니다.")

    turn2 = writing.draft_body(pipeline, chosen_no)
    turn2 = writing.finalize(pipeline, turn2, auto)
    print("[매니저] 작성팀 최종본을 넘겨받아 디자인팀에 전달합니다.")

    turn3 = design.propose_visuals(pipeline)
    turn3 = design.finalize(pipeline, turn3, auto)
    images = design.produce_images(
        turn3, out_dir, via_chatgpt=infographic_via_chatgpt, headless=headless,
    )
    print(f"[매니저] 디자인팀 이미지 {len(images)}장을 넘겨받아 발행팀에 전달합니다.")

    publishing.publish_draft(
        blog_id=blog_id,
        title=turn2["title"],
        sections=turn2["sections"],
        tags=turn2["tags"],
        images=images,
        headless=headless,
        pause_before_save=pause_before_save,
    )

    return {
        "keyword": keyword,
        "title": turn2["title"],
        "char_count": turn2.get("char_count"),
        "image_count": len(images),
    }


def assign_daily_batch(
    blog_id: str,
    count: int = 8,
    out_dir: str = "output",
    reports_dir: str = "reports",
    headless: bool = True,
    infographic_via_chatgpt: bool = True,
    prompt_path: str = "prompts/system_prompt.txt",
) -> list:
    """리서치팀에게 오늘의 글감을 조사하게 하고, 그중 count개를 순서대로
    나머지 부서에 넘겨 완전 무인으로 처리한다. 실패한 건이 있어도 나머지는
    계속 진행하고, 마지막에 성공/실패 요약을 output/<날짜>/batch_summary.json에
    남긴다."""
    report = research.investigate(save_dir=reports_dir)
    report_date = report.get("report_date", date.today().isoformat())
    topics = report.get("selected_topics", [])[:count]

    if not topics:
        print("[매니저] 리서치팀이 선정한 글감이 없어서 오늘 배치는 종료합니다.")
        return []

    today_out_dir = Path(out_dir) / report_date
    results = []

    for i, topic in enumerate(topics, 1):
        keyword = topic.get("keyword", "")
        reference = topic.get("reference", "")
        print(f"\n===== [매니저] {i}/{len(topics)}번째 건 배정: {keyword} =====")
        try:
            result = assign_single_post(
                keyword=keyword,
                blog_id=blog_id,
                reference=reference,
                out_dir=str(today_out_dir / f"post_{i:02d}"),
                headless=headless,
                pause_before_save=False,  # 야간 무인 실행 — 확인 대기 없음
                auto=True,  # 기획팀 1번 제목 자동 채택, 재작업 지시 없음
                infographic_via_chatgpt=infographic_via_chatgpt,
                prompt_path=prompt_path,
            )
            result["status"] = "ok"
            results.append(result)
            print(f"[매니저] {i}번째 건 완료: {result['title']}")
        except Exception as e:
            print(f"[매니저] {i}번째 건 처리 중 문제가 생겨 건너뜁니다 — {keyword}: {e}")
            traceback.print_exc()
            results.append({"keyword": keyword, "status": "failed", "error": str(e)})
            continue

    today_out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = today_out_dir / "batch_summary.json"
    summary_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = sum(1 for r in results if r.get("status") == "ok")
    print(f"\n[매니저] 오늘 배치 완료: {ok}/{len(results)}건 성공. 요약: {summary_path}")
    return results
