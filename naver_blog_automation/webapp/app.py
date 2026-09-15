"""
네이버 블로그 자동화를 위한 로컬 웹 대시보드.

계정 등록 → 지침 선택 → 실행을 한 화면에서 누르고, 부서별(리서치·기획·
작성·디자인·발행) 진행 상황을 실시간으로 볼 수 있게 한다. 실제 업무
배정은 여전히 manager.py가 한다 — 이 화면은 그걸 누르기 쉽게 감싼
것뿐이다.

이 화면에서 누른 실행은 항상 완전 자동 모드로 돈다(제목 1번 자동 채택,
수정 요청 없음, 저장 전 확인 대기 없음) — 웹 버튼에는 터미널 입력을 받을
방법이 없기 때문이다. 턴마다 대화하면서 고치고 싶으면 터미널에서
main.py를 직접 실행한다(README 참고).

실행 전 준비는 README와 동일하다(.env, 온보딩 등). 실행:
    python webapp/app.py
브라우저에서 http://localhost:5000 접속. 반드시 naver_blog_automation
폴더 안에서(webapp 폴더로 들어가지 말고) 실행해야 prompts/·accounts.json·
output/ 등 상대 경로가 맞게 잡힌다.
"""

import json
import sys
import threading
from pathlib import Path

# webapp/ 밑에서 실행해도 manager·core·departments·config를 그대로
# import할 수 있게 프로젝트 루트를 경로에 넣는다.
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from flask import Flask, jsonify, render_template, request  # noqa: E402

from core import status  # noqa: E402
from core.accounts import load_accounts, ACCOUNTS_FILE  # noqa: E402
from manager import assign_single_post, assign_daily_batch  # noqa: E402

app = Flask(__name__)

PROMPTS_DIR = ROOT_DIR / "prompts"
ACCOUNTS_PATH = ROOT_DIR / ACCOUNTS_FILE

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
            # 매니저가 이미 status.mark_failed를 호출했을 테지만, 예상 밖의
            # 예외(예: 계정/파일 설정 오류로 매니저 진입 전에 터진 경우)도
            # 대시보드에 보이게 한 번 더 남긴다.
            status.mark_finished(error=str(e))
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

    title_strategy = data.get("title_strategy") or "hook_curiosity_mix"

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


@app.route("/api/status", methods=["GET"])
def get_status():
    s = status.read()
    s["is_running"] = _is_running
    s["department_labels"] = status.DEPARTMENT_LABELS
    s["department_order"] = status.DEPARTMENT_ORDER
    return jsonify(s)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
