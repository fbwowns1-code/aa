"""
게시물 하나를 9단계로 실행하고 진행 상태를 모두 automation.db(SQLite)에
기록하는 오케스트레이터.

    RESEARCH → DUPLICATE_CHECK → PLANNING → TITLE → WRITING → FACT_CHECK
    → QUALITY_GATE → IMAGE → NAVER_DRAFT

핵심 설계
---------
- 각 단계의 시작/종료를 core.database.job_steps에 즉시 기록한다. 프로세스가
  중간에 죽어도(정전·강제종료·네트워크 끊김) DB에는 마지막으로 성공한
  단계까지만 SUCCESS로 남으므로, 다음 실행은 first_pending_step()이
  가리키는 단계부터 이어서 시작한다 — 처음부터 다시 하지 않는다.
- OpenAI와의 대화(F목록→제목→본문→이미지 프롬프트)는 Responses API의
  previous_response_id 하나로 서버 쪽에 상태가 남는다. 이 프로세스가
  죽어도 그 id와 지금까지 받은 턴 결과(JSON)를
  output/<post_id>/pipeline_state.json에 같이 적어두므로, 재개할 때 그
  파일을 읽어 같은 대화를 그대로 이어서 쓴다(F목록부터 다시 만들지 않는다).
- NAVER_DRAFT는 posts.naver_draft_completed로 idempotency를 보장한다.
  이미 True면 --force-step NAVER_DRAFT로 명시하지 않는 한 다시 저장하지
  않는다. 저장 버튼 클릭이 실제로 들어간 직후(on_save_clicked 콜백)
  바로 플래그를 세우므로, 그 뒤 확인 대기 중에 죽어도 중복 저장되지 않는다.
- 한 게시물이 실패해도(치명적/시스템적 오류가 아닌 한) 예외를 위로 던지지
  않고 결과 dict로 돌려준다 — 호출자(run_daily_batch)가 다음 게시물을
  계속 진행할 수 있게 하기 위함이다. 로그인 세션 만료처럼 "다음 글에서도
  똑같이 막힐" 오류만 SystemicError로 표시해서 배치 전체를 멈추게 한다.
"""

import json
import re
import time
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from config import PROMPT_PATH as DEFAULT_PROMPT_PATH, IMAGE_PROVIDER
from core import database as db
from core.accounts import (
    get_account, naver_session_file_for, chatgpt_session_file_for, prompt_path_for,
)
from core.account_config import load_account_config
from core.retry_policy import classify_error, backoff_seconds
from core.duplicate_check import check_duplicate
from core.quality_gate import evaluate as quality_evaluate
from core.pipeline import BlogPipeline
from departments import research, planning, writing, design, publishing


# --------------------------------------------------------------- utilities

def _now_ref(obj) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False) if isinstance(obj, (dict, list)) else str(obj)
    except Exception:
        s = str(obj)
    return s[:500]


def _extract_urls(text: str) -> list:
    return re.findall(r"https?://\S+", text or "")


def _read_prompt(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _post_dir(out_dir: str, post_id: str) -> Path:
    return Path(out_dir) / post_id


def _pipeline_state_path(out_dir: str, post_id: str) -> Path:
    return _post_dir(out_dir, post_id) / "pipeline_state.json"


def _save_pipeline_state(out_dir: str, post_id: str, state: dict) -> None:
    path = _pipeline_state_path(out_dir, post_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_pipeline_state(out_dir: str, post_id: str) -> dict:
    path = _pipeline_state_path(out_dir, post_id)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


class SystemicError(Exception):
    """배치 전체를 멈춰야 하는 오류(로그인 세션 만료, UI 구조 변경 등 —
    다음 게시물에서도 똑같이 막힐 문제)를 감싼다."""

    def __init__(self, original: Exception, error_type: str):
        super().__init__(str(original))
        self.original = original
        self.error_type = error_type


def _is_systemic(error_type: str, retryable: bool) -> bool:
    if error_type == "AUTH_ERROR":
        return True
    if error_type == "NAVER_ERROR" and not retryable:
        return True
    return False


def _run_step(post_id: str, job_id: str, account_id: str, step_name: str, fn,
              max_attempts: int, db_path: str = db.DB_PATH):
    """fn()을 실행한다. 성공하면 (result, None). 재시도까지 다 써도
    실패하면 (None, exception). 시스템적 오류면 SystemicError로 감싸서
    돌려준다."""
    attempt = 0
    last_error = None
    while attempt < max_attempts:
        attempt += 1
        db.start_step(post_id, job_id, step_name, db_path=db_path)
        try:
            result = fn()
            db.complete_step(post_id, step_name, result_ref=_now_ref(result), db_path=db_path)
            return result, None
        except Exception as e:
            last_error = e
            error_type, retryable = classify_error(e)
            db.log_error(post_id, account_id, step_name, error_type, str(e),
                         traceback.format_exc(), db_path=db_path)
            if _is_systemic(error_type, retryable):
                db.fail_step(post_id, step_name, str(e), retry=False, db_path=db_path)
                return None, SystemicError(e, error_type)
            if retryable and attempt < max_attempts:
                db.fail_step(post_id, step_name, str(e), retry=True, db_path=db_path)
                wait = backoff_seconds(attempt)
                print(f"[JobManager] {post_id} {step_name} 실패({error_type}) — "
                      f"{wait}초 대기 후 재시도합니다 ({attempt}/{max_attempts}).")
                time.sleep(wait)
                continue
            db.fail_step(post_id, step_name, str(e), retry=False, db_path=db_path)
            return None, last_error
    db.fail_step(post_id, step_name, str(last_error), retry=False, db_path=db_path)
    return None, last_error


def _fatal_result(post_id: str, job_id: str, step_name: str, err: Exception, db_path: str) -> dict:
    db.update_job_status(job_id, "FAILED", db_path=db_path)
    db.update_post(post_id, db_path=db_path, status="FAILED")
    return {
        "post_id": post_id,
        "status": "FAILED",
        "step": step_name,
        "error": str(err),
        "systemic": isinstance(err, SystemicError),
    }


# ----------------------------------------------------------------- 핵심 실행

def run_post_job(
    post_id: str,
    account_id: str,
    blog_id: str,
    keyword: str,
    reference: str = "",
    extra: str = "",
    account_info: Optional[dict] = None,
    out_dir: str = "output",
    headless: bool = False,
    pause_before_save: bool = True,
    auto: bool = False,
    title_index: Optional[int] = None,
    title_strategy: str = planning.DEFAULT_TITLE_STRATEGY,
    prompt_path: Optional[str] = None,
    infographic_via_chatgpt: Optional[bool] = None,
    force_step: Optional[str] = None,
    is_batch_research: bool = False,
    db_path: str = db.DB_PATH,
) -> dict:
    """게시물 한 건을 9단계로 실행한다(또는 중단된 지점부터 이어서 실행한다).

    반환값: {"post_id", "status": "COMPLETED"|"REVIEW"|"FAILED",
             "title", "char_count", "image_count", ...}
    """
    acc_config = load_account_config(account_id)
    naver_session_file = naver_session_file_for(account_id, account_info)
    chatgpt_session_file = chatgpt_session_file_for(account_id, account_info)
    resolved_prompt_path = prompt_path or prompt_path_for(account_info) or DEFAULT_PROMPT_PATH
    max_attempts = acc_config.get("retry", {}).get("max_attempts", 3)

    if infographic_via_chatgpt is None:
        via_chatgpt = acc_config.get("images", {}).get("provider", IMAGE_PROVIDER) == "chatgpt_web"
    else:
        via_chatgpt = infographic_via_chatgpt

    db.upsert_account(account_id, blog_id=blog_id,
                      category=acc_config.get("blog", {}).get("category", ""), db_path=db_path)
    db.create_post(post_id, account_id, topic=keyword, db_path=db_path)
    job_id = db.create_job(post_id, db_path=db_path)
    db.init_steps_for_post(job_id, post_id, db_path=db_path)

    if force_step:
        print(f"[JobManager] {post_id}: {force_step} 단계부터 강제로 다시 실행합니다.")
        db.reset_step(post_id, force_step, db_path=db_path)

    # 상태를 RUNNING으로 바꾸기 전에 먼저 "이미 다 끝났는지"부터 확인한다 —
    # 순서를 바꾸면(RUNNING으로 먼저 덮어쓰면) 이 조기 반환이 실제 posts.status
    # (COMPLETED/REVIEW 등)를 RUNNING으로 잘못 보고하게 된다.
    if db.first_pending_step(post_id, db_path=db_path) is None:
        print(f"[JobManager] {post_id}는 이미 모든 단계가 끝나 있습니다.")
        post = db.get_post(post_id, db_path=db_path)
        return {"post_id": post_id, "status": post.get("status", "COMPLETED"),
                "title": post.get("title", ""), "keyword": keyword}

    db.update_job_status(job_id, "RUNNING", db_path=db_path)
    db.update_post(post_id, db_path=db_path, status="RUNNING")

    state = _load_pipeline_state(out_dir, post_id)
    pipeline_holder = {"p": None}
    turn1 = state.get("turn1")
    turn2 = state.get("turn2")
    turn3 = state.get("turn3")
    chosen_no = state.get("chosen_no")
    duplicate_result = state.get("duplicate_result")
    quality_result = state.get("quality_result")
    images = state.get("images") or []

    def _ensure_pipeline() -> BlogPipeline:
        if pipeline_holder["p"] is None:
            if state.get("previous_response_id"):
                pipeline_holder["p"] = BlogPipeline.resume(
                    _read_prompt(resolved_prompt_path),
                    state["previous_response_id"],
                    state.get("current_raw", ""),
                )
                print(f"[JobManager] {post_id}: 이전 OpenAI 대화를 이어서 씁니다.")
            else:
                pipeline_holder["p"] = BlogPipeline(_read_prompt(resolved_prompt_path))
        return pipeline_holder["p"]

    def _persist_state():
        p = pipeline_holder["p"]
        state.update({
            "post_id": post_id,
            "previous_response_id": p.client.previous_response_id if p else state.get("previous_response_id"),
            "current_raw": p.current_raw if p else state.get("current_raw", ""),
            "turn1": turn1, "turn2": turn2, "turn3": turn3,
            "chosen_no": chosen_no,
            "duplicate_result": duplicate_result,
            "quality_result": quality_result,
            "images": images,
        })
        _save_pipeline_state(out_dir, post_id, state)

    steps = db.get_steps(post_id, db_path=db_path)

    # ---------------------------------------------------------- RESEARCH
    if steps.get("RESEARCH", {}).get("status") not in ("SUCCESS", "SKIPPED"):
        if is_batch_research:
            db.start_step(post_id, job_id, "RESEARCH", db_path=db_path)
            db.complete_step(post_id, "RESEARCH", result_ref="배치 공용 리서치 결과 재사용", db_path=db_path)
        else:
            db.skip_step(post_id, "RESEARCH", reason="단발 실행은 리서치 단계를 거치지 않음", db_path=db_path)
        steps = db.get_steps(post_id, db_path=db_path)

    # ------------------------------------------------------ DUPLICATE_CHECK
    if steps.get("DUPLICATE_CHECK", {}).get("status") not in ("SUCCESS", "SKIPPED"):
        def _dup():
            return check_duplicate(account_id, f"{keyword}\n{reference}", db_path=db_path)

        duplicate_result, err = _run_step(post_id, job_id, account_id, "DUPLICATE_CHECK",
                                           _dup, max_attempts, db_path)
        if err:
            return _fatal_result(post_id, job_id, "DUPLICATE_CHECK", err, db_path)
        if duplicate_result and duplicate_result.get("is_duplicate"):
            db.update_post(post_id, db_path=db_path, status="DUPLICATE_WARNING")
            best = duplicate_result.get("best_match") or {}
            print(f"[JobManager] {post_id}: 최근 게시물과 유사도 높음"
                  f"(score={duplicate_result.get('score', 0):.2f}, 기존 글={best.get('post_id', '?')})"
                  " — 업데이트 관점으로 작성하도록 기획팀에 안내합니다.")
        _persist_state()
    steps = db.get_steps(post_id, db_path=db_path)

    # ------------------------------------------------------------ PLANNING
    if steps.get("PLANNING", {}).get("status") not in ("SUCCESS", "SKIPPED"):
        dup_note = ""
        if duplicate_result and duplicate_result.get("is_duplicate"):
            best = duplicate_result.get("best_match") or {}
            dup_note = (
                f"\n\n참고: 최근에 '{best.get('title', '')}' 라는 비슷한 주제를 이미 다뤘다. "
                "단순 재탕이 아니라 그 이후 새로 나온 정보(가격, 사전계약, 출시일 확정 등) 위주로 "
                "'업데이트' 관점에서 쓰고, 무엇이 새로 달라졌는지 본문에 명시해라."
            )

        def _plan():
            p = _ensure_pipeline()
            return planning.propose_titles(p, keyword, reference, extra + dup_note)

        turn1, err = _run_step(post_id, job_id, account_id, "PLANNING", _plan, max_attempts, db_path)
        if err:
            return _fatal_result(post_id, job_id, "PLANNING", err, db_path)
        _persist_state()
    steps = db.get_steps(post_id, db_path=db_path)

    # --------------------------------------------------------------- TITLE
    if steps.get("TITLE", {}).get("status") not in ("SUCCESS", "SKIPPED"):
        def _title():
            p = _ensure_pipeline()
            return planning.select_title(p, turn1, auto, title_index, title_strategy, keyword)

        chosen_no, err = _run_step(post_id, job_id, account_id, "TITLE", _title, max_attempts, db_path)
        if err:
            return _fatal_result(post_id, job_id, "TITLE", err, db_path)
        _persist_state()
    steps = db.get_steps(post_id, db_path=db_path)

    chosen_title = next((t["text"] for t in turn1["titles"] if t["no"] == chosen_no), "")
    db.update_post(post_id, db_path=db_path, title=chosen_title)

    # ------------------------------------------------------------- WRITING
    if steps.get("WRITING", {}).get("status") not in ("SUCCESS", "SKIPPED"):
        def _write():
            p = _ensure_pipeline()
            t2 = writing.draft_body(p, chosen_no)
            return writing.finalize(p, t2, auto)

        turn2, err = _run_step(post_id, job_id, account_id, "WRITING", _write, max_attempts, db_path)
        if err:
            return _fatal_result(post_id, job_id, "WRITING", err, db_path)
        _persist_state()
    steps = db.get_steps(post_id, db_path=db_path)

    # ----------------------------------------------------------- FACT_CHECK
    # 턴2 자체가 지침에 따라 F목록 대조 팩트체크까지 마친 최종본을 내므로,
    # 별도 API 호출 없이 그 결과(factcheck_summary)를 이 단계 기록으로 남긴다.
    if steps.get("FACT_CHECK", {}).get("status") not in ("SUCCESS", "SKIPPED"):
        db.start_step(post_id, job_id, "FACT_CHECK", db_path=db_path)
        db.complete_step(post_id, "FACT_CHECK",
                         result_ref=turn2.get("factcheck_summary", ""), db_path=db_path)
    steps = db.get_steps(post_id, db_path=db_path)

    # --------------------------------------------------------- QUALITY_GATE
    if steps.get("QUALITY_GATE", {}).get("status") not in ("SUCCESS", "SKIPPED"):
        def _qgate():
            nonlocal turn3
            p = _ensure_pipeline()
            t3 = design.propose_visuals(p)
            t3 = design.finalize(p, t3, auto)
            turn3 = t3
            wcfg = acc_config.get("writing", {})
            qcfg = acc_config.get("quality_gate", {})
            return quality_evaluate(
                title=chosen_title,
                sections=turn2.get("sections", []),
                char_count=turn2.get("char_count", 0) or 0,
                factcheck_summary=turn2.get("factcheck_summary", ""),
                min_chars=wcfg.get("min_chars", 1200),
                max_chars=wcfg.get("max_chars", 1500),
                headings_target=wcfg.get("headings", 5),
                has_image_prompts=bool(t3.get("infographic_prompts")),
                duplicate_result=duplicate_result,
                pass_score=qcfg.get("pass_score", 85),
                review_score=qcfg.get("review_score", 70),
            )

        quality_result, err = _run_step(post_id, job_id, account_id, "QUALITY_GATE",
                                         _qgate, max_attempts, db_path)
        if err:
            return _fatal_result(post_id, job_id, "QUALITY_GATE", err, db_path)
        _persist_state()

        print(f"[JobManager] {post_id}: 품질 점수 {quality_result['score']}점 "
              f"({quality_result['verdict']})" +
              (f" — {'; '.join(quality_result['findings'])}" if quality_result['findings'] else ""))

        if quality_result["verdict"] == "FAILED":
            db.update_post(post_id, db_path=db_path, status="FAILED")
            db.update_job_status(job_id, "FAILED", db_path=db_path)
            db.skip_step(post_id, "IMAGE", reason="품질 게이트 미달로 건너뜀", db_path=db_path)
            db.skip_step(post_id, "NAVER_DRAFT", reason="품질 게이트 미달로 건너뜀", db_path=db_path)
            return {"post_id": post_id, "status": "FAILED", "title": chosen_title,
                    "quality": quality_result, "keyword": keyword}
        if quality_result["verdict"] == "REVIEW":
            db.update_post(post_id, db_path=db_path, status="REVIEW")
    steps = db.get_steps(post_id, db_path=db_path)

    # -------------------------------------------------------------- IMAGE
    if steps.get("IMAGE", {}).get("status") not in ("SUCCESS", "SKIPPED"):
        def _image():
            imgs = design.produce_images(
                turn3, str(_post_dir(out_dir, post_id) / "images"),
                via_chatgpt=via_chatgpt, headless=headless,
                chatgpt_session_file=chatgpt_session_file,
            )
            provider = "chatgpt_web" if via_chatgpt else "openai_api"
            for img in imgs:
                db.add_image(post_id, img.get("subheading", ""), img.get("prompt", ""),
                            img.get("file_path", ""), provider, db_path=db_path)
            return imgs

        images, err = _run_step(post_id, job_id, account_id, "IMAGE", _image, max_attempts, db_path)
        if err:
            return _fatal_result(post_id, job_id, "IMAGE", err, db_path)
        _persist_state()
    steps = db.get_steps(post_id, db_path=db_path)

    # --------------------------------------------------------- NAVER_DRAFT
    if db.is_naver_draft_completed(post_id, db_path=db_path) and force_step != "NAVER_DRAFT":
        db.skip_step(post_id, "NAVER_DRAFT", reason="이미 임시저장 완료(중복 방지)", db_path=db_path)
    elif steps.get("NAVER_DRAFT", {}).get("status") not in ("SUCCESS", "SKIPPED"):
        def _publish():
            # _run_step이 재시도 루프 안에서 이 함수를 여러 번 부를 수 있다.
            # 직전 시도에서 저장 버튼 클릭까지는 성공했는데 그 뒤(확인 대기
            # 등)에서 예외가 나서 재시도로 넘어온 경우, 여기서 바로 멈춰야
            # 한다 — 안 그러면 같은 글이 재시도마다 또 저장된다.
            if db.is_naver_draft_completed(post_id, db_path=db_path):
                return {"title": chosen_title, "already_saved": True}

            def _on_saved():
                db.mark_naver_draft_completed(post_id, db_path=db_path)

            publishing.publish_draft(
                blog_id=blog_id, title=chosen_title, sections=turn2["sections"],
                tags=turn2.get("tags", []), images=images, headless=headless,
                pause_before_save=pause_before_save, session_file=naver_session_file,
                on_save_clicked=_on_saved,
                post_id=post_id, account_id=account_id,
            )
            return {"title": chosen_title}

        _, err = _run_step(post_id, job_id, account_id, "NAVER_DRAFT", _publish, max_attempts, db_path)
        if err:
            return _fatal_result(post_id, job_id, "NAVER_DRAFT", err, db_path)

    post = db.get_post(post_id, db_path=db_path)
    final_status = post.get("status")
    if final_status not in ("REVIEW", "DUPLICATE_WARNING"):
        final_status = "COMPLETED"
    db.update_post(post_id, db_path=db_path, status=final_status,
                   completed_at=datetime.now().isoformat(timespec="seconds"))
    db.update_job_status(job_id, "SUCCESS", db_path=db_path)

    db.add_published_topic(
        account_id, post_id, topic=keyword, title=chosen_title, keywords=[keyword],
        embedding=(duplicate_result or {}).get("embedding"),
        source_urls=_extract_urls(reference), db_path=db_path,
    )

    return {
        "post_id": post_id,
        "status": final_status,
        "keyword": keyword,
        "title": chosen_title,
        "char_count": turn2.get("char_count"),
        "image_count": len(images),
        "quality": quality_result,
    }


# ------------------------------------------------------------- 상위 진입점

def _resolve_account(blog_id: Optional[str], account: Optional[str]):
    account_info = get_account(account) if account else None
    resolved_blog_id = blog_id or (account_info or {}).get("blog_id")
    if not resolved_blog_id:
        raise ValueError("blog_id가 없습니다. --blog-id를 직접 주거나, "
                          "--account로 blog_id가 등록된 계정을 지정하세요.")
    account_id = account or resolved_blog_id
    return account_id, resolved_blog_id, account_info


def run_single_post(
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
    db_path: str = db.DB_PATH,
) -> dict:
    account_id, resolved_blog_id, account_info = _resolve_account(blog_id, account)
    post_id = db.next_post_id(account_id, db_path=db_path)
    return run_post_job(
        post_id=post_id, account_id=account_id, blog_id=resolved_blog_id,
        keyword=keyword, reference=reference, extra=extra, account_info=account_info,
        out_dir=out_dir, headless=headless, pause_before_save=pause_before_save, auto=auto,
        title_index=title_index, title_strategy=title_strategy, prompt_path=prompt_path,
        infographic_via_chatgpt=infographic_via_chatgpt, force_step=force_step,
        is_batch_research=False, db_path=db_path,
    )


def run_daily_batch(
    blog_id: Optional[str] = None,
    account: Optional[str] = None,
    count: int = 8,
    out_dir: str = "output",
    reports_dir: str = "reports",
    headless: bool = True,
    infographic_via_chatgpt: Optional[bool] = None,
    prompt_path: Optional[str] = None,
    title_strategy: str = planning.DEFAULT_TITLE_STRATEGY,
    force_rerun: bool = False,
    force_step: Optional[str] = None,
    db_path: str = db.DB_PATH,
) -> dict:
    """오늘의 글감을 조사해 count건을 순서대로 처리한다. 하나가 실패해도
    (시스템적 오류가 아닌 한) 나머지는 계속 진행한다.

    반환값: {"report_date", "posts": [...], "summary": {"total","completed",
             "failed","review","paused"}}
    """
    account_id, resolved_blog_id, account_info = _resolve_account(blog_id, account)
    today = date.today().strftime("%Y%m%d")

    existing_posts = db.list_posts(account_id, report_date=today, db_path=db_path)
    if existing_posts and not force_rerun:
        unfinished = [p for p in existing_posts if p["status"] in ("PENDING", "RUNNING")]
        if not unfinished:
            print(f"[JobManager] 오늘({today}) {account_id} 배치는 이미 끝까지 처리되어 있습니다. "
                  "다시 돌리려면 force_rerun=True로 호출하세요.")
            return _summarize(today, existing_posts)
        print(f"[JobManager] 오늘 진행 중이던 배치를 이어서 진행합니다({len(unfinished)}건 남음).")
        topics_by_post = {p["post_id"]: db.get_daily_topic_by_post(p["post_id"], db_path=db_path)
                          for p in unfinished}
        post_ids = [p["post_id"] for p in unfinished]
    else:
        account_reports_dir = str(Path(reports_dir) / account_id)
        report = research.investigate(save_dir=account_reports_dir)
        report_date = report.get("report_date", today)
        topics = report.get("selected_topics", [])[:count]
        if not topics:
            print("[JobManager] 리서치팀이 선정한 글감이 없어서 오늘 배치는 종료합니다.")
            return {"report_date": report_date, "posts": [],
                    "summary": {"total": 0, "completed": 0, "failed": 0, "review": 0}}

        post_ids = []
        topics_by_post = {}
        for topic in topics:
            post_id = db.next_post_id(account_id, report_date=today, db_path=db_path)
            keyword = topic.get("keyword", "")
            reference = topic.get("reference", "")
            db.add_daily_topic(account_id, today, keyword, reference, selected=True,
                               post_id=post_id, db_path=db_path)
            db.create_post(post_id, account_id, topic=keyword, db_path=db_path)
            post_ids.append(post_id)
            topics_by_post[post_id] = {"keyword": keyword, "reference": reference}

    results = []
    for i, post_id in enumerate(post_ids, 1):
        topic = topics_by_post[post_id]
        keyword = topic.get("keyword", "")
        reference = topic.get("reference", "")
        print(f"\n===== [JobManager] {i}/{len(post_ids)}번째 건: {post_id} ({keyword}) =====")

        result = run_post_job(
            post_id=post_id, account_id=account_id, blog_id=resolved_blog_id,
            keyword=keyword, reference=reference, account_info=account_info,
            out_dir=out_dir, headless=headless, pause_before_save=False, auto=True,
            title_strategy=title_strategy, prompt_path=prompt_path,
            infographic_via_chatgpt=infographic_via_chatgpt,
            force_step=force_step if i == 1 else None,  # force는 첫 건에만 적용
            is_batch_research=True, db_path=db_path,
        )
        results.append(result)

        if result.get("systemic"):
            print(f"[JobManager] {post_id}에서 시스템적 오류가 발생해 배치를 멈춥니다: "
                  f"{result.get('error')}")
            print(f"[JobManager] 남은 {len(post_ids) - i}건은 건드리지 않았습니다. "
                  "문제를 해결한 뒤(재로그인 등) 같은 명령을 다시 실행하면 이어서 진행됩니다.")
            break

    all_posts = db.list_posts(account_id, report_date=today, db_path=db_path)
    return _summarize(today, all_posts)


def _summarize(report_date: str, posts: list) -> dict:
    summary = {
        "total": len(posts),
        "completed": sum(1 for p in posts if p["status"] == "COMPLETED"),
        "failed": sum(1 for p in posts if p["status"] == "FAILED"),
        "review": sum(1 for p in posts if p["status"] in ("REVIEW", "DUPLICATE_WARNING")),
    }
    print(f"\n[JobManager] 오늘 배치 요약 — 전체 {summary['total']}건 / "
          f"완료 {summary['completed']}건 / 실패 {summary['failed']}건 / "
          f"검토 필요 {summary['review']}건")
    return {"report_date": report_date, "posts": posts, "summary": summary}
