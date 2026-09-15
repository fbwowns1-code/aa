"""
총괄 매니저 — main.py/daily_batch.py/scheduler.py가 그대로 부르는 창구다.
함수 이름(assign_single_post/assign_daily_batch)과 인자는 기존과 최대한
동일하게 유지했다 — 실제 실행·재시도·중단 후 재개·중복 저장 방지는 이제
core/job_manager.py + automation.db(SQLite)가 전담한다(README 리팩터링
섹션 참고). 이 파일은 그 앞단의 얇은 호환 계층일 뿐이다.

  리서치팀(departments.research)   : 오늘의 글감 조사
  기획팀(departments.planning)     : 제목 후보 뽑고 확정
  작성팀(departments.writing)      : 본문 작성·팩트체크
  디자인팀(departments.design)     : 인포그래픽 썸네일 제작
  발행팀(departments.publishing)   : 네이버 블로그 임시저장

옛 manager.py는 core/status.py(진행률 JSON)와 output/<날짜>/<계정>/
batch_state.json으로 상태를 관리했다. 이제 모든 상태는 automation.db 하나에
기록되고, 웹 대시보드(webapp/app.py)도 거기서 읽는다.
"""

from typing import Optional

from core.job_manager import run_daily_batch, run_single_post
from departments import planning


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
    infographic_via_chatgpt: Optional[bool] = None,
    prompt_path: Optional[str] = None,
    title_strategy: str = planning.DEFAULT_TITLE_STRATEGY,
    force_step: Optional[str] = None,
) -> dict:
    """글 한 편을 기획→작성→팩트체크→품질검사→디자인→발행 순서로 만들어
    네이버에 임시저장한다(core/job_manager.run_single_post의 얇은 창구).

    title_strategy는 auto=True일 때 기획팀이 제목을 어떻게 자동으로 고를지
    정한다 — "ai_click_appeal"(기본값)은 후킹/클릭 유도형+궁금증 폭발형
    후보를 놓고 웹에서 반응 좋은 실제 제목 사례를 찾아본 뒤 그 패턴에
    맞는 제목을 AI가 직접 판단해서 고르고, "hook_curiosity_mix"는 같은
    후보 중 가장 짧은 제목을 기계적으로, "first"는 SEO 최적화형 1번을
    그대로 쓴다(departments/planning.py 참고).

    여러 계정을 운영한다면 account에 accounts.json의 계정 이름을 주면
    blog_id와 로그인 세션 파일을 그 계정 것으로 자동으로 고른다.

    infographic_via_chatgpt를 생략(None)하면 계정 설정
    (configs/accounts/<계정>.yaml의 images.provider) 또는 .env의
    기본값(IMAGE_PROVIDER, 기본 openai_api)을 따른다. True/False를 명시하면
    그 값이 우선한다.

    force_step: 이미 성공한 단계라도 강제로 다시 실행하고 싶을 때 단계
    이름(RESEARCH/DUPLICATE_CHECK/PLANNING/TITLE/WRITING/FACT_CHECK/
    QUALITY_GATE/IMAGE/NAVER_DRAFT)을 준다. NAVER_DRAFT를 강제 지정하면
    이미 임시저장된 글이라도 예외적으로 다시 저장한다(중복 방지 규칙의
    유일한 예외).

    이 함수는 매번 automation.db에 새 post_id(YYYYMMDD_계정_NNN)를 만들어
    실행한다 — 중단 후 재개는 같은 post_id로 다시 부르는
    core.job_manager.run_post_job()이 처리하며, 배치(assign_daily_batch)
    안에서는 이미 그렇게 동작한다.

    반환값: {"post_id", "status", "keyword", "title", "char_count", "image_count"}
    status가 "FAILED"면 예외를 던진다(automation.db의 errors 테이블에
    자세한 원인이 남아 있다).
    """
    result = run_single_post(
        keyword=keyword, blog_id=blog_id, account=account, reference=reference,
        extra=extra, title_index=title_index, out_dir=out_dir, headless=headless,
        pause_before_save=pause_before_save, auto=auto,
        infographic_via_chatgpt=infographic_via_chatgpt, prompt_path=prompt_path,
        title_strategy=title_strategy, force_step=force_step,
    )
    if result.get("status") == "FAILED":
        raise RuntimeError(
            f"{result.get('step', '어느 단계인지 알 수 없음')} 단계에서 실패했습니다"
            f"(post_id={result.get('post_id')}): {result.get('error', '알 수 없는 오류')}. "
            "automation.db의 errors 테이블 또는 output/<post_id>/를 확인하세요."
        )
    return result


def assign_daily_batch(
    blog_id: Optional[str] = None,
    account: Optional[str] = None,
    count: int = 8,
    out_dir: str = "output",
    reports_dir: str = "reports",
    headless: bool = True,
    infographic_via_chatgpt: Optional[bool] = None,
    prompt_path: Optional[str] = None,
    title_strategy: str = planning.DEFAULT_TITLE_STRATEGY,
    max_retries: int = 1,
    retry_wait_seconds: int = 60,
    consecutive_failure_limit: int = 2,
    force_rerun: bool = False,
    force_step: Optional[str] = None,
) -> dict:
    """리서치팀에게 오늘의 글감을 조사하게 하고, count개를 순서대로 나머지
    부서에 넘겨 완전 무인으로 처리한다(core/job_manager.run_daily_batch의
    얇은 창구).

    진행 상황·재시도·이어서 하기는 이제 output/<날짜>/<계정>/batch_state.json
    이 아니라 automation.db(SQLite)에 post_id별 9단계로 기록된다. 게시물
    한 건이 실패해도(로그인 세션 만료 등 "다음 글에서도 똑같이 막힐"
    시스템적 오류가 아닌 한) 배치를 멈추지 않고 나머지 건을 계속 진행한다
    — 이전처럼 "치명적 오류 감지 시 배치 전체 정지"가 필요한 경우에만
    멈춘다.

    max_retries/retry_wait_seconds/consecutive_failure_limit는 더 정교한
    새 재시도 체계(core/retry_policy.py의 오류 유형별 자동 재시도·지수
    백오프, 계정별 configs/accounts/<계정>.yaml의 retry.max_attempts)로
    대체되었다 — 기존 CLI 옵션과의 호환을 위해 인자는 남겨두었지만 더 이상
    쓰이지 않는다.

    force_step: assign_single_post와 같되, 배치의 "이어서 진행되는 첫
    건"에만 적용된다(재개 시 이미 끝난 나머지 건까지 전부 강제로 다시
    돌리지 않기 위함).

    다시 돌리려면(오늘 이미 끝까지 완료됐어도) force_rerun=True로 준다.

    반환값: {"report_date", "posts": [...], "summary": {...},
             "paused": bool, "paused_reason": str|None}
    (paused/paused_reason은 옛 scheduler.py와의 호환을 위해 posts 상태에서
    유추해 채운다 — 처리되지 못한(PENDING) 글이 남아 있으면 True)
    """
    result = run_daily_batch(
        blog_id=blog_id, account=account, count=count, out_dir=out_dir,
        reports_dir=reports_dir, headless=headless,
        infographic_via_chatgpt=infographic_via_chatgpt, prompt_path=prompt_path,
        title_strategy=title_strategy, force_rerun=force_rerun, force_step=force_step,
    )

    summary = result.get("summary", {})
    total = summary.get("total", 0)
    processed = summary.get("completed", 0) + summary.get("failed", 0) + summary.get("review", 0)
    paused = total > 0 and processed < total
    result["paused"] = paused
    if paused:
        left = total - processed
        result["paused_reason"] = (
            f"{left}건을 처리하지 못한 채 배치가 멈췄습니다. automation.db의 errors "
            "테이블에서 마지막 오류를 확인하세요(로그인 세션 만료, UI 구조 변경 등 "
            "시스템적 오류로 배치가 멈췄을 가능성이 있습니다)."
        )
    else:
        result["paused_reason"] = None
    return result
