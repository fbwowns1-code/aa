"""
부서별 진행 상태를 파일 하나에 기록하는 아주 단순한 공유 상태 저장소.

manager.py가 부서를 호출할 때마다 여기에 "지금 어느 부서가 뭘 하고 있는지"를
적어두고, 로컬 웹 대시보드(webapp/app.py)가 이 파일을 주기적으로 읽어
화면에 보여준다. CLI로만 쓸 때는 아무도 이 파일을 읽지 않아도 무방하다 —
output/status.json에 계속 덮어쓸 뿐이다.

개인용 로컬 도구라는 전제로, 한 번에 하나의 작업만 진행한다고 가정한다
(여러 계정을 동시에 병렬로 돌리는 상황은 다루지 않는다 — 순서대로 돌린다).
"""

import json
from datetime import datetime
from pathlib import Path
from threading import Lock

STATUS_FILE = Path("output/status.json")
_lock = Lock()

DEPARTMENT_ORDER = ["research", "planning", "writing", "design", "publishing"]
DEPARTMENT_LABELS = {
    "research": "리서치팀",
    "planning": "기획팀",
    "writing": "작성팀",
    "design": "디자인팀",
    "publishing": "발행팀",
}


def _read() -> dict:
    if STATUS_FILE.exists():
        try:
            return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _write(state: dict) -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    STATUS_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def start_batch(total_posts: int, label: str) -> None:
    """새 작업(단발 1건 또는 하루 배치 N건)을 시작할 때 한 번 부른다.
    부서 상태를 전부 "대기"로 초기화한다."""
    with _lock:
        _write({
            "label": label,
            "total_posts": total_posts,
            "current_post": 0,
            "departments": {d: "대기" for d in DEPARTMENT_ORDER},
            "detail": {d: "" for d in DEPARTMENT_ORDER},
            "finished": False,
            "running": True,
            "error": None,
        })


def set_current_post(i: int) -> None:
    with _lock:
        state = _read()
        state["current_post"] = i
        _write(state)


def set_total_posts(n: int) -> None:
    """리서치팀이 글감 개수를 확정한 뒤 total_posts만 갱신한다(부서 상태는
    그대로 둔다 — start_batch처럼 전체를 초기화하지 않는다)."""
    with _lock:
        state = _read()
        state["total_posts"] = n
        _write(state)


def update_department(name: str, state_label: str, detail: str = "") -> None:
    with _lock:
        s = _read()
        s.setdefault("departments", {})[name] = state_label
        s.setdefault("detail", {})[name] = detail
        _write(s)


def mark_finished(error: str = None) -> None:
    with _lock:
        s = _read()
        s["finished"] = True
        s["running"] = False
        s["error"] = error
        _write(s)


def mark_failed(error: str) -> None:
    """지금 "진행중"으로 표시된 부서를 "실패"로 바꾸고 오류 내용을 남긴다.
    배치 전체가 끝났다는 뜻은 아니므로(재시도·다음 건 진행 가능) finished/
    running 값은 건드리지 않는다."""
    with _lock:
        s = _read()
        departments = s.setdefault("departments", {})
        detail = s.setdefault("detail", {})
        for name, label in list(departments.items()):
            if label == "진행중":
                departments[name] = "실패"
                detail[name] = error
        s["error"] = error
        _write(s)


def read() -> dict:
    return _read()
