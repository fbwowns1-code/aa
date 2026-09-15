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
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from core.pipeline import BlogPipeline
from core.accounts import get_account, naver_session_file_for, chatgpt_session_file_for
from departments import research, planning, writing, design, publishing

# 배치 중 이 문구가 오류 메시지에 들어 있으면 "재시도해도 소용없는" 치명적
# 문제로 보고, 남은 글감을 전부 건너뛰는 대신 배치를 즉시 멈추고 대기한다.
# (로그인 세션 만료, UI 구조 변경 등 — 다음 글에서도 똑같이 실패할 문제들)
CRITICAL_ERROR_MARKERS = [
    "세션 파일",              # 네이버/챗지피티 로그인 세션이 없음
    "출근 등록",               # 온보딩(로그인) 안 함
    "선택자를 찾지 못했습니다",   # 네이버/챗지피티 UI 구조가 바뀜
    "api_key",
    "API key",
    "AuthenticationError",
    "RateLimitError",
]


def _is_critical(error: Exception) -> bool:
    text = f"{type(error).__name__}: {error}"
    return any(marker in text for marker in CRITICAL_ERROR_MARKERS)


def _state_path(out_dir: str, report_date: str, account: Optional[str] = None) -> Path:
    # account별로 폴더를 나눠야 여러 계정을 같은 날 동시에 배치 돌려도
    # batch_state.json이 서로 덮어써지지 않는다.
    return Path(out_dir) / report_date / (account or "default") / "batch_state.json"


def _load_state(path: Path) -> Optional[dict]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_system_prompt(prompt_path: str) -> str:
    return Path(prompt_path).read_text(encoding="utf-8")


def assign_single_post(
    keyword: str,
    blog_id: Optional[str] = None,
    account: Optional[str] = None,
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

    여러 계정을 운영한다면 account에 accounts.json의 계정 이름을 주면
    blog_id와 로그인 세션 파일을 그 계정 것으로 자동으로 고른다(blog_id를
    같이 주면 account의 blog_id보다 그 값이 우선한다). 계정이 하나뿐이면
    account 없이 blog_id만 줘도 기존처럼 동작한다.

    반환값: {"keyword", "title", "char_count", "image_count"}
    """
    account_info = get_account(account) if account else None
    blog_id = blog_id or (account_info or {}).get("blog_id")
    if not blog_id:
        raise ValueError("blog_id가 없습니다. --blog-id를 직접 주거나, "
                          "--account로 blog_id가 등록된 계정을 지정하세요.")
    naver_session_file = naver_session_file_for(account, account_info)
    chatgpt_session_file = chatgpt_session_file_for(account, account_info)

    who = f"'{account}' 계정" if account else f"블로그 {blog_id}"
    print(f"\n[매니저] {who}로 '{keyword}' 건을 접수해서 기획팀에 넘깁니다.")
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
        chatgpt_session_file=chatgpt_session_file,
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
        session_file=naver_session_file,
    )

    return {
        "keyword": keyword,
        "title": turn2["title"],
        "char_count": turn2.get("char_count"),
        "image_count": len(images),
    }


def _attempt_post(keyword, blog_id, account, reference, post_out_dir, headless,
                   infographic_via_chatgpt, prompt_path, max_retries, retry_wait_seconds):
    """한 건을 최대 (1 + max_retries)번 시도한다. 치명적 오류로 보이면
    재시도 없이 바로 실패로 반환한다(재시도해도 똑같이 막힐 문제이므로)."""
    attempt = 0
    last_error = None
    while attempt <= max_retries:
        try:
            result = assign_single_post(
                keyword=keyword,
                blog_id=blog_id,
                account=account,
                reference=reference,
                out_dir=post_out_dir,
                headless=headless,
                pause_before_save=False,  # 야간 무인 실행 — 확인 대기 없음
                auto=True,  # 기획팀 1번 제목 자동 채택, 재작업 지시 없음
                infographic_via_chatgpt=infographic_via_chatgpt,
                prompt_path=prompt_path,
            )
            return result, None
        except Exception as e:
            last_error = e
            if _is_critical(e):
                return None, e
            attempt += 1
            if attempt <= max_retries:
                print(f"[매니저] 실패({e}) — {retry_wait_seconds}초 대기 후 재시도합니다 "
                      f"({attempt}/{max_retries})...")
                time.sleep(retry_wait_seconds)
    return None, last_error


def assign_daily_batch(
    blog_id: Optional[str] = None,
    account: Optional[str] = None,
    count: int = 8,
    out_dir: str = "output",
    reports_dir: str = "reports",
    headless: bool = True,
    infographic_via_chatgpt: bool = True,
    prompt_path: str = "prompts/system_prompt.txt",
    max_retries: int = 1,
    retry_wait_seconds: int = 60,
    consecutive_failure_limit: int = 2,
    force_rerun: bool = False,
) -> dict:
    """리서치팀에게 오늘의 글감을 조사하게 하고, count개를 순서대로 나머지
    부서에 넘겨 완전 무인으로 처리한다.

    여러 계정을 운영한다면 account에 accounts.json의 계정 이름을 주면
    blog_id·로그인 세션을 그 계정 것으로 자동으로 고르고, 리포트·진행
    상태도 계정별 폴더(reports/<account>/, output/<날짜>/<account>/)에
    따로 저장한다 — 같은 날 여러 계정을 각각 배치 돌려도 서로 덮어쓰지
    않는다. 계정이 하나뿐이면 account 없이 blog_id만 줘도 된다.

    진행 상황은 매 건마다 output/<날짜>/<account 또는 default>/batch_state.json에 저장한다.

    - 한 건이 실패하면 retry_wait_seconds만큼 기다렸다가 최대 max_retries번
      재시도한다(웹 검색 타임아웃 같은 일시적인 변수를 견디기 위함).
    - 그래도 실패했는데 로그인 세션 만료·UI 변경처럼 "재시도해도 똑같이
      막힐" 치명적 오류로 보이거나, consecutive_failure_limit번 연속으로
      실패하면 — 남은 글감을 억지로 더 실패시키지 않고 배치를 멈추고
      상태를 저장한 채 대기한다(state["paused"] = True).
    - 중단된 배치가 있는 상태에서 다시 부르면(force_rerun=False, 기본값),
      새로 리서치를 돌리지 않고 멈췄던 글감부터 이어서 진행한다. 오늘 배치가
      이미 끝까지 완료돼 있으면 그대로 결과를 돌려주고 아무 일도 하지 않는다
      (force_rerun=True면 오늘 분량을 새로 조사해서 처음부터 다시 돈다).
    """
    account_info = get_account(account) if account else None
    blog_id = blog_id or (account_info or {}).get("blog_id")
    if not blog_id:
        raise ValueError("blog_id가 없습니다. --blog-id를 직접 주거나, "
                          "--account로 blog_id가 등록된 계정을 지정하세요.")

    today = date.today().isoformat()
    existing = None if force_rerun else _load_state(_state_path(out_dir, today, account))

    if existing and not existing.get("paused") and existing.get("topics_total", 0) > 0 \
            and len(existing.get("results", [])) >= existing["topics_total"]:
        print(f"[매니저] 오늘({today}) 배치는 이미 끝까지 완료되어 있습니다. "
              "다시 돌리려면 force_rerun=True로 호출하세요.")
        return existing

    if existing:
        print(f"[매니저] 이전에 중단된 배치를 이어서 진행합니다 — 중단 사유: {existing.get('paused_reason')}")
        state = existing
        state["paused"] = False
        state["paused_reason"] = None
    else:
        # 계정별로 리포트 폴더를 나눠야 같은 날 여러 계정을 배치 돌려도
        # reports/<날짜>.json이 서로 덮어써지지 않는다.
        account_reports_dir = str(Path(reports_dir) / account) if account else reports_dir
        report = research.investigate(save_dir=account_reports_dir)
        report_date = report.get("report_date", today)
        topics = report.get("selected_topics", [])[:count]
        state = {
            "report_date": report_date,
            "account": account,
            "blog_id": blog_id,
            "topics": topics,
            "topics_total": len(topics),
            "results": [],
            "paused": False,
            "paused_reason": None,
        }
        if not topics:
            print("[매니저] 리서치팀이 선정한 글감이 없어서 오늘 배치는 종료합니다.")
            return state

    state_path = _state_path(out_dir, state["report_date"], account)
    today_out_dir = Path(out_dir) / state["report_date"] / (account or "default")
    topics = state["topics"]
    results = state["results"]
    consecutive_failures = 0

    for i in range(len(results), len(topics)):
        topic = topics[i]
        keyword = topic.get("keyword", "")
        reference = topic.get("reference", "")
        print(f"\n===== [매니저] {i + 1}/{len(topics)}번째 건 배정: {keyword} =====")

        result, error = _attempt_post(
            keyword, blog_id, account, reference, str(today_out_dir / f"post_{i + 1:02d}"),
            headless, infographic_via_chatgpt, prompt_path, max_retries, retry_wait_seconds,
        )

        if error is None:
            consecutive_failures = 0
            result["status"] = "ok"
            results.append(result)
            print(f"[매니저] {i + 1}번째 건 완료: {result['title']}")
            _save_state(state_path, state)
            continue

        results.append({"keyword": keyword, "status": "failed", "error": str(error)})
        consecutive_failures += 1 if not _is_critical(error) else consecutive_failure_limit

        if _is_critical(error) or consecutive_failures >= consecutive_failure_limit:
            reason = (
                f"치명적인 오류로 판단해 배치를 멈춥니다: {error}"
                if _is_critical(error) else
                f"{consecutive_failures}건이 연속으로 실패했습니다(마지막 오류: {error}). "
                "네이버/챗지피티 로그인, API 키, 네트워크 상태를 확인해주세요."
            )
            print(f"[매니저] {reason}")
            print(f"[매니저] 남은 {len(topics) - i - 1}건은 건드리지 않고 대기합니다. "
                  "문제를 해결한 뒤 같은 명령을 다시 실행하면 이어서 진행됩니다.")
            state["paused"] = True
            state["paused_reason"] = reason
            state["paused_at"] = datetime.now().isoformat(timespec="seconds")
            _save_state(state_path, state)
            return state

        _save_state(state_path, state)

    ok = sum(1 for r in results if r.get("status") == "ok")
    print(f"\n[매니저] 오늘 배치 완료: {ok}/{len(results)}건 성공. 기록: {state_path}")
    _save_state(state_path, state)
    return state
