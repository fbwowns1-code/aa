"""
네이버 블로그 자동화를 위한 로컬 웹 대시보드.

계정 등록 → 지침 선택 → 실행을 한 화면에서 누르고, 오늘 배치의 진행 상황을
automation.db(SQLite)에서 읽어 게시물별 9단계 상태로 실시간으로 볼 수 있게
한다. 실제 업무 배정은 여전히 manager.py(→ core/job_manager.py)가 한다 —
이 화면은 그걸 누르고 지켜보기 쉽게 감싼 것뿐이다.

이 화면에서 누른 실행은 항상 완전 자동 모드로 돈다(제목 1번 자동 채택,
수정 요청 없음, 저장 전 확인 대기 없음) — 웹 버튼에는 터미널 입력을 받을
방법이 없기 때문이다. 턴마다 대화하면서 고치고 싶으면 터미널에서
main.py를 직접 실행한다(README 참고).

게시물이 특정 단계에서 실패/검토 필요 상태면 대시보드에서 "이 단계부터
재시도" 버튼으로 core.job_manager.run_post_job을 force_step과 함께 다시
부를 수 있다. NAVER_DRAFT 재시도도 마찬가지로 가능하지만, 이미 임시저장이
완료된 글은 idempotency 규칙에 따라 NAVER_DRAFT를 명시적으로 재시도할
때만(그 외 단계 재시도로 인한 자동 cascade 포함) 다시 저장된다 — 실수로
중복 저장되지 않는다.

실행 전 준비는 README와 동일하다(.env, 온보딩 등). 실행:
    python webapp/app.py
브라우저에서 http://localhost:5000 접속. 반드시 naver_blog_automation
폴더 안에서(webapp 폴더로 들어가지 말고) 실행해야 prompts/·accounts.json·
output/ 등 상대 경로가 맞게 잡힌다.
"""

import json
import sys
import threading
from datetime import date, datetime
from pathlib import Path

# webapp/ 밑에서 실행해도 manager·core·departments·config를 그대로
# import할 수 있게 프로젝트 루트를 경로에 넣는다.
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from flask import Flask, jsonify, render_template, request  # noqa: E402

from core import database as db  # noqa: E402
from core.accounts import load_accounts, ACCOUNTS_FILE  # noqa: E402
from core.job_manager import run_post_job  # noqa: E402
from core.logger import log_event  # noqa: E402
from manager import assign_single_post, assign_daily_batch  # noqa: E402

app = Flask(__name__)

PROMPTS_DIR = ROOT_DIR / "prompts"
ACCOUNTS_PATH = ROOT_DIR / ACCOUNTS_FILE

# 스케줄러 하트비트(system_status.scheduler_last_seen)가 이보다 오래되면
# "OFFLINE"으로 표시한다(scheduler.py는 20초 주기로 갱신한다).
SCHEDULER_OFFLINE_THRESHOLD_SECONDS = 90

_run_lock = threading.Lock()
_is_running = False


def _save_accounts(accounts: dict) -> None:
    ACCOUNTS_PATH.write_text(json.dumps(accounts, ensure_ascii=False, indent=2), encoding="utf-8")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/accounts", methods=["GET"])
def get_accounts():
    accounts = load_accounts(str(ACCOUNTS_PATH))
    # 비밀번호는 화면에 돌려주지 않는다 — 등록돼 있는지 여부만 알려준다.
    safe = {
        name: {
            "blog_id": info.get("blog_id", ""),
            "naver_id": info.get("naver_id", ""),
            "has_password": bool(info.get("naver_pw")),
            "prompt_path": info.get("prompt_path", ""),
        }
        for name, info in accounts.items()
    }
    return jsonify(safe)


@app.route("/api/accounts", methods=["POST"])
def save_account():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "계정 이름을 입력해주세요."}), 400

    accounts = load_accounts(str(ACCOUNTS_PATH))
    entry = accounts.get(name, {})
    if data.get("blog_id"):
        entry["blog_id"] = data["blog_id"]
    if data.get("naver_id"):
        entry["naver_id"] = data["naver_id"]
    if data.get("naver_pw"):  # 빈 값으로 덮어쓰지 않는다 — 기존 비밀번호 유지
        entry["naver_pw"] = data["naver_pw"]
    accounts[name] = entry
    _save_accounts(accounts)
    return jsonify({"ok": True})


@app.route("/api/prompts", methods=["GET"])
def list_prompts():
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(p.name for p in PROMPTS_DIR.glob("*.txt"))
    return jsonify({"files": files})


@app.route("/api/prompts/<filename>", methods=["GET"])
def get_prompt(filename):
    path = (PROMPTS_DIR / filename).resolve()
    if PROMPTS_DIR.resolve() not in path.parents or not path.exists():
        return jsonify({"error": "파일을 찾을 수 없습니다."}), 404
    return jsonify({"filename": filename, "content": path.read_text(encoding="utf-8")})


@app.route("/api/prompts", methods=["POST"])
def save_prompt():
    data = request.get_json(force=True) or {}
    filename = (data.get("filename") or "").strip()
    content = data.get("content", "")
    if not filename:
        return jsonify({"error": "파일 이름을 입력해주세요."}), 400
    if not filename.endswith(".txt"):
        filename += ".txt"
    if "/" in filename or "\\" in filename or ".." in filename:
        return jsonify({"error": "파일 이름에 경로 문자를 쓸 수 없습니다."}), 400

    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    (PROMPTS_DIR / filename).write_text(content, encoding="utf-8")
    return jsonify({"ok": True, "filename": filename})


@app.route("/api/prompts/select", methods=["POST"])
def select_prompt():
    data = request.get_json(force=True) or {}
    account_name = data.get("account")
    filename = data.get("filename")
    if not account_name or not filename:
        return jsonify({"error": "계정과 지침 파일을 모두 선택해주세요."}), 400

    accounts = load_accounts(str(ACCOUNTS_PATH))
    if account_name not in accounts:
        return jsonify({"error": f"'{account_name}' 계정이 없습니다. 먼저 계정을 등록해주세요."}), 400

    accounts[account_name]["prompt_path"] = f"prompts/{filename}"
    _save_accounts(accounts)
    return jsonify({"ok": True})


def _run_in_background(fn, kwargs: dict) -> bool:
    global _is_running

    with _run_lock:
        if _is_running:
            return False
        _is_running = True

    def _target():
        global _is_running
        try:
            fn(**kwargs)
        except Exception as e:
            # 게시물/단계별 실패는 이미 automation.db(posts.status, errors
            # 테이블)에 남아 대시보드가 그대로 보여준다. 여기서는 계정/파일
            # 설정 오류처럼 job_manager 진입 전에 터진, DB에 남지 않는
            # 예외만 평문 로그로 한 번 더 남긴다.
            log_event(kwargs.get("account") or kwargs.get("account_id"),
                       kwargs.get("post_id"), "WEBAPP_RUN", "ERROR", str(e))
        finally:
            with _run_lock:
                _is_running = False

    threading.Thread(target=_target, daemon=True).start()
    return True


@app.route("/api/run", methods=["POST"])
def run():
    data = request.get_json(force=True) or {}
    mode = data.get("mode")
    account = data.get("account")
    if not account:
        return jsonify({"error": "계정을 선택해주세요."}), 400

    title_strategy = data.get("title_strategy") or "ai_click_appeal"

    if mode == "single":
        keyword = (data.get("keyword") or "").strip()
        if not keyword:
            return jsonify({"error": "키워드를 입력해주세요."}), 400
        started = _run_in_background(assign_single_post, dict(
            keyword=keyword,
            account=account,
            reference=data.get("reference", ""),
            headless=True,
            pause_before_save=False,
            auto=True,
            title_strategy=title_strategy,
        ))
    elif mode == "daily":
        count = int(data.get("count") or 8)
        started = _run_in_background(assign_daily_batch, dict(
            account=account,
            count=count,
            headless=True,
            title_strategy=title_strategy,
        ))
    else:
        return jsonify({"error": "mode는 'single' 또는 'daily'여야 합니다."}), 400

    if not started:
        return jsonify({"error": "이미 다른 작업이 진행 중입니다. 끝난 뒤 다시 시도해주세요."}), 409
    return jsonify({"ok": True})


def _scheduler_status() -> dict:
    last_seen = db.get_system_status("scheduler_last_seen")
    if not last_seen:
        return {"last_seen": None, "online": False, "seconds_ago": None}
    try:
        seconds_ago = (datetime.now() - datetime.fromisoformat(last_seen)).total_seconds()
    except ValueError:
        return {"last_seen": last_seen, "online": False, "seconds_ago": None}
    return {
        "last_seen": last_seen,
        "online": seconds_ago <= SCHEDULER_OFFLINE_THRESHOLD_SECONDS,
        "seconds_ago": int(seconds_ago),
    }


def _post_with_steps(post: dict) -> dict:
    steps_raw = db.get_steps(post["post_id"])
    steps = {}
    for name in db.STEP_NAMES:
        row = steps_raw.get(name)
        steps[name] = {
            "status": row["status"] if row else "PENDING",
            "attempt": row["attempt"] if row else 0,
            "last_error": row["last_error"] if row else None,
            "started_at": row["started_at"] if row else None,
            "completed_at": row["completed_at"] if row else None,
        }
    return {
        "post_id": post["post_id"],
        "account_id": post["account_id"],
        "topic": post.get("topic", ""),
        "title": post.get("title", ""),
        "status": post.get("status", "PENDING"),
        "naver_draft_completed": bool(post.get("naver_draft_completed")),
        "created_at": post.get("created_at"),
        "updated_at": post.get("updated_at"),
        "completed_at": post.get("completed_at"),
        "steps": steps,
    }


def _summarize_posts(posts: list) -> dict:
    return {
        "total": len(posts),
        "completed": sum(1 for p in posts if p["status"] == "COMPLETED"),
        "in_progress": sum(1 for p in posts if p["status"] in ("PENDING", "RUNNING")),
        "failed": sum(1 for p in posts if p["status"] == "FAILED"),
        "review": sum(1 for p in posts if p["status"] in ("REVIEW", "DUPLICATE_WARNING")),
    }


@app.route("/api/status", methods=["GET"])
def get_status():
    """오늘(today) 배치의 전체/계정별/게시물별(9단계) 진행 상황을
    automation.db에서 읽어 돌려준다. 예전에는 output/status.json 하나에
    "지금 실행 중인 작업"만 보여줬지만, 이제는 여러 계정을 같은 날 각자
    배치 돌려도 DB에 전부 남으므로 계정별로 묶어서 보여준다."""
    today = date.today().strftime("%Y%m%d")
    posts = [_post_with_steps(p) for p in db.list_posts(report_date=today)]

    by_account: dict = {}
    for p in posts:
        by_account.setdefault(p["account_id"], []).append(p)

    return jsonify({
        "today": today,
        "is_running": _is_running,
        "scheduler": _scheduler_status(),
        "summary": _summarize_posts(posts),
        "step_names": list(db.STEP_NAMES),
        "step_labels": db.STEP_LABELS,
        "accounts": [
            {"account_id": account_id, "summary": _summarize_posts(items), "posts": items}
            for account_id, items in sorted(by_account.items())
        ],
    })


@app.route("/api/retry", methods=["POST"])
def retry():
    """게시물 하나를 지정한 단계부터 강제로 다시 실행한다(그 단계와 그
    이후 모든 단계가 PENDING으로 cascade 초기화된다 — core.database.reset_step).
    NAVER_DRAFT는 이미 임시저장이 끝났어도 이 경로로 명시적으로 지정했을
    때만 예외적으로 다시 저장된다(idempotency 규칙의 유일한 예외)."""
    data = request.get_json(force=True) or {}
    post_id = (data.get("post_id") or "").strip()
    step = (data.get("step") or "").strip().upper()
    if not post_id or not step:
        return jsonify({"error": "post_id와 step을 모두 지정해주세요."}), 400
    if step not in db.STEP_NAMES:
        return jsonify({"error": f"알 수 없는 단계입니다: {step}"}), 400

    post = db.get_post(post_id)
    if not post:
        return jsonify({"error": f"{post_id} 게시물을 찾을 수 없습니다."}), 404

    account_id = post["account_id"]
    accounts = load_accounts(str(ACCOUNTS_PATH))
    account_info = accounts.get(account_id)
    blog_id = (account_info or {}).get("blog_id") or account_id
    keyword = post.get("topic") or post.get("title") or ""

    started = _run_in_background(run_post_job, dict(
        post_id=post_id, account_id=account_id, blog_id=blog_id, keyword=keyword,
        account_info=account_info, headless=True, pause_before_save=False, auto=True,
        force_step=step, is_batch_research=False,
    ))
    if not started:
        return jsonify({"error": "이미 다른 작업이 진행 중입니다. 끝난 뒤 다시 시도해주세요."}), 409
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
