"""
automation.db (SQLite) 연결·스키마·CRUD 헬퍼.

이 프로젝트의 모든 실행 상태(게시물, 작업 단계, 이미지, 오류, 일일 글감,
발행된 주제, 시스템 상태)는 이 모듈을 통해서만 읽고 쓴다. 예전에는
output/status.json과 output/<날짜>/<계정>/batch_state.json에 흩어져
있던 정보를 여기 하나로 모은 것이다 — 프로그램이 중간에 죽어도(정전,
강제종료, 네트워크 끊김) 마지막으로 SUCCESS를 기록한 단계 다음부터
재개할 수 있게 하기 위함이다.

동시성 모델: 개인용 로컬 도구이므로 한 번에 하나의 파이프라인만 돈다고
가정한다. 그래도 웹 대시보드가 동시에 읽을 수 있으므로 매 호출마다
짧게 연결을 열고 닫는다(커넥션을 오래 들고 있지 않는다).
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

DB_PATH = "automation.db"

STEP_NAMES = (
    "RESEARCH",
    "DUPLICATE_CHECK",
    "PLANNING",
    "TITLE",
    "WRITING",
    "FACT_CHECK",
    "QUALITY_GATE",
    "IMAGE",
    "NAVER_DRAFT",
)
STEP_STATUSES = ("PENDING", "RUNNING", "SUCCESS", "FAILED", "RETRY", "SKIPPED")

POST_STATUSES = (
    "PENDING", "RUNNING", "COMPLETED", "FAILED", "REVIEW", "DUPLICATE_WARNING",
)

# 대시보드(webapp)가 단계 이름을 한글로 보여줄 때 쓰는 라벨.
STEP_LABELS = {
    "RESEARCH": "리서치",
    "DUPLICATE_CHECK": "중복확인",
    "PLANNING": "기획",
    "TITLE": "제목",
    "WRITING": "작성",
    "FACT_CHECK": "팩트체크",
    "QUALITY_GATE": "품질검사",
    "IMAGE": "이미지",
    "NAVER_DRAFT": "네이버 임시저장",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id   TEXT PRIMARY KEY,
    blog_id      TEXT,
    category     TEXT,
    config_path  TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    post_id                TEXT PRIMARY KEY,
    account_id             TEXT NOT NULL,
    topic                  TEXT,
    title                  TEXT,
    status                 TEXT NOT NULL DEFAULT 'PENDING',
    naver_draft_completed  INTEGER NOT NULL DEFAULT 0,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL,
    completed_at           TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id      TEXT PRIMARY KEY,
    post_id     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'PENDING',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    FOREIGN KEY (post_id) REFERENCES posts(post_id)
);

CREATE TABLE IF NOT EXISTS job_steps (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id        TEXT NOT NULL,
    post_id       TEXT NOT NULL,
    step_name     TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'PENDING',
    started_at    TEXT,
    completed_at  TEXT,
    attempt       INTEGER NOT NULL DEFAULT 0,
    last_error    TEXT,
    result_ref    TEXT,
    UNIQUE(post_id, step_name),
    FOREIGN KEY (post_id) REFERENCES posts(post_id)
);

CREATE TABLE IF NOT EXISTS images (
    image_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id     TEXT NOT NULL,
    subheading  TEXT,
    prompt      TEXT,
    file_path   TEXT,
    provider    TEXT,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (post_id) REFERENCES posts(post_id)
);

CREATE TABLE IF NOT EXISTS errors (
    error_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id        TEXT,
    account_id     TEXT,
    step           TEXT,
    error_type     TEXT,
    error_message  TEXT,
    traceback      TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_topics (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id   TEXT NOT NULL,
    report_date  TEXT NOT NULL,
    post_id      TEXT,
    keyword      TEXT,
    reference    TEXT,
    selected     INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS published_topics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    TEXT NOT NULL,
    post_id       TEXT NOT NULL,
    topic         TEXT,
    title         TEXT,
    keywords      TEXT,
    embedding     TEXT,
    published_at  TEXT NOT NULL,
    source_urls   TEXT
);

CREATE TABLE IF NOT EXISTS system_status (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_posts_account ON posts(account_id);
CREATE INDEX IF NOT EXISTS idx_job_steps_post ON job_steps(post_id);
CREATE INDEX IF NOT EXISTS idx_published_topics_account_date
    ON published_topics(account_id, published_at);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


_initialized_paths = set()


@contextmanager
def get_connection(db_path: str = DB_PATH):
    parent = Path(db_path).parent
    if str(parent) not in ("", "."):
        parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # CREATE TABLE IF NOT EXISTS라 멱등이지만, 매 연결마다 스크립트를 다시
    # 돌리진 않는다 — 이 프로세스에서 이 db_path를 처음 여는 순간에만
    # 실행해서 init_db()를 따로 부르지 않아도 자동으로 스키마가 갖춰지게
    # 한다(첫 실행 시 automation.db가 아예 없는 상태에서 CLI를 바로 돌려도
    # "no such table" 오류가 나지 않도록).
    if db_path not in _initialized_paths:
        conn.executescript(SCHEMA)
        _initialized_paths.add(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)


def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    return dict(row) if row is not None else None


# ---------------------------------------------------------------- accounts

def upsert_account(account_id: str, blog_id: str = "", category: str = "",
                    config_path: str = "", db_path: str = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO accounts (account_id, blog_id, category, config_path, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(account_id) DO UPDATE SET
                 blog_id=excluded.blog_id, category=excluded.category,
                 config_path=excluded.config_path""",
            (account_id, blog_id, category, config_path, _now()),
        )


# ------------------------------------------------------------------- posts

def next_post_id(account_id: str, report_date: Optional[str] = None, db_path: str = DB_PATH) -> str:
    """post_id를 YYYYMMDD_계정_NNN 형식으로 발급한다(예: 20260915_carblog_001)."""
    day = (report_date or datetime.now().strftime("%Y%m%d")).replace("-", "")
    prefix = f"{day}_{account_id}_"
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT post_id FROM posts WHERE post_id LIKE ? ORDER BY post_id DESC LIMIT 1",
            (prefix + "%",),
        ).fetchall()
    if not rows:
        seq = 1
    else:
        last = rows[0]["post_id"]
        seq = int(last[len(prefix):]) + 1
    return f"{prefix}{seq:03d}"


def create_post(post_id: str, account_id: str, topic: str = "", title: str = "",
                 db_path: str = DB_PATH) -> None:
    now = _now()
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT OR IGNORE INTO posts
               (post_id, account_id, topic, title, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'PENDING', ?, ?)""",
            (post_id, account_id, topic, title, now, now),
        )


def get_post(post_id: str, db_path: str = DB_PATH) -> Optional[dict]:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM posts WHERE post_id = ?", (post_id,)).fetchone()
    return _row_to_dict(row)


def update_post(post_id: str, db_path: str = DB_PATH, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = _now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    with get_connection(db_path) as conn:
        conn.execute(f"UPDATE posts SET {cols} WHERE post_id = ?", (*fields.values(), post_id))


def mark_naver_draft_completed(post_id: str, db_path: str = DB_PATH) -> None:
    """네이버 임시저장이 실제로 끝난 직후 바로 호출한다 — Playwright 응답을
    놓쳐도(예: save 클릭 후 confirm 대기 중 죽음) 이 플래그가 True가 되기
    전까지는 재개 시 NAVER_DRAFT를 다시 시도하게 되므로, 저장 직후 가능한
    한 빨리 이 함수를 불러 idempotency를 보장한다."""
    update_post(post_id, db_path=db_path, naver_draft_completed=1,
                status="COMPLETED", completed_at=_now())


def is_naver_draft_completed(post_id: str, db_path: str = DB_PATH) -> bool:
    post = get_post(post_id, db_path=db_path)
    return bool(post and post.get("naver_draft_completed"))


def list_posts(account_id: Optional[str] = None, report_date: Optional[str] = None,
                db_path: str = DB_PATH) -> list:
    query = "SELECT * FROM posts WHERE 1=1"
    params: list = []
    if account_id:
        query += " AND account_id = ?"
        params.append(account_id)
    if report_date:
        query += " AND post_id LIKE ?"
        params.append(report_date.replace("-", "") + "_%")
    query += " ORDER BY post_id"
    with get_connection(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


# -------------------------------------------------------------------- jobs

def create_job(post_id: str, db_path: str = DB_PATH) -> str:
    job_id = f"job_{post_id}"
    now = _now()
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT OR IGNORE INTO jobs (job_id, post_id, status, created_at, updated_at)
               VALUES (?, ?, 'PENDING', ?, ?)""",
            (job_id, post_id, now, now),
        )
    return job_id


def update_job_status(job_id: str, status: str, db_path: str = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, updated_at = ? WHERE job_id = ?",
            (status, _now(), job_id),
        )


def get_job_for_post(post_id: str, db_path: str = DB_PATH) -> Optional[dict]:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE post_id = ?", (post_id,)).fetchone()
    return _row_to_dict(row)


# --------------------------------------------------------------- job_steps

def init_steps_for_post(job_id: str, post_id: str, db_path: str = DB_PATH) -> None:
    """9단계를 전부 PENDING으로 미리 만들어 둔다(없는 것만)."""
    now = _now()
    with get_connection(db_path) as conn:
        for step in STEP_NAMES:
            conn.execute(
                """INSERT OR IGNORE INTO job_steps
                   (job_id, post_id, step_name, status, attempt)
                   VALUES (?, ?, ?, 'PENDING', 0)""",
                (job_id, post_id, step),
            )


def get_steps(post_id: str, db_path: str = DB_PATH) -> dict:
    """{step_name: row_dict} 형태로 돌려준다."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM job_steps WHERE post_id = ? ORDER BY id", (post_id,)
        ).fetchall()
    return {r["step_name"]: dict(r) for r in rows}


def get_step_status(post_id: str, step_name: str, db_path: str = DB_PATH) -> Optional[str]:
    steps = get_steps(post_id, db_path=db_path)
    row = steps.get(step_name)
    return row["status"] if row else None


def start_step(post_id: str, job_id: str, step_name: str, db_path: str = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """UPDATE job_steps
               SET status='RUNNING', started_at=?, attempt = attempt + 1
               WHERE post_id = ? AND step_name = ?""",
            (_now(), post_id, step_name),
        )


def complete_step(post_id: str, step_name: str, result_ref: str = "",
                   db_path: str = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """UPDATE job_steps
               SET status='SUCCESS', completed_at=?, result_ref=?, last_error=NULL
               WHERE post_id = ? AND step_name = ?""",
            (_now(), result_ref, post_id, step_name),
        )


def fail_step(post_id: str, step_name: str, error_message: str,
              retry: bool = False, db_path: str = DB_PATH) -> None:
    status = "RETRY" if retry else "FAILED"
    with get_connection(db_path) as conn:
        conn.execute(
            """UPDATE job_steps
               SET status=?, completed_at=?, last_error=?
               WHERE post_id = ? AND step_name = ?""",
            (status, _now(), error_message, post_id, step_name),
        )


def skip_step(post_id: str, step_name: str, reason: str = "", db_path: str = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """UPDATE job_steps
               SET status='SKIPPED', completed_at=?, result_ref=?
               WHERE post_id = ? AND step_name = ?""",
            (_now(), reason, post_id, step_name),
        )


def reset_step(post_id: str, step_name: str, db_path: str = DB_PATH) -> None:
    """--force-step으로 특정 단계를 강제로 다시 돌릴 때, 그 단계와 그
    뒤따르는 모든 단계를 PENDING으로 되돌린다."""
    if step_name not in STEP_NAMES:
        raise ValueError(f"알 수 없는 단계: {step_name}")
    idx = STEP_NAMES.index(step_name)
    to_reset = STEP_NAMES[idx:]
    with get_connection(db_path) as conn:
        for s in to_reset:
            conn.execute(
                """UPDATE job_steps
                   SET status='PENDING', started_at=NULL, completed_at=NULL, last_error=NULL
                   WHERE post_id = ? AND step_name = ?""",
                (post_id, s),
            )
    # NAVER_DRAFT가 리셋 범위(자기 자신이거나, 그보다 앞 단계를 강제 재실행해서
    # 뒤따라 딸려온 경우 모두)에 들어가면 idempotency 플래그도 같이 내려야
    # 재개 시 다시 임시저장을 시도할 수 있다.
    if "NAVER_DRAFT" in to_reset:
        update_post(post_id, db_path=db_path, naver_draft_completed=0)


def first_pending_step(post_id: str, db_path: str = DB_PATH) -> Optional[str]:
    """이 게시물에서 아직 SUCCESS나 SKIPPED가 아닌 첫 단계를 돌려준다.
    전부 끝났으면 None."""
    steps = get_steps(post_id, db_path=db_path)
    for step in STEP_NAMES:
        row = steps.get(step)
        if not row or row["status"] not in ("SUCCESS", "SKIPPED"):
            return step
    return None


# ------------------------------------------------------------------ images

def add_image(post_id: str, subheading: str, prompt: str, file_path: str,
              provider: str, db_path: str = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO images (post_id, subheading, prompt, file_path, provider, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (post_id, subheading, prompt, file_path, provider, _now()),
        )


# ------------------------------------------------------------------ errors

def log_error(post_id: Optional[str], account_id: Optional[str], step: str,
              error_type: str, error_message: str, traceback_text: str = "",
              db_path: str = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO errors
               (post_id, account_id, step, error_type, error_message, traceback, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (post_id, account_id, step, error_type, error_message, traceback_text, _now()),
        )


# ------------------------------------------------------------- daily_topics

def add_daily_topic(account_id: str, report_date: str, keyword: str,
                     reference: str, selected: bool, post_id: Optional[str] = None,
                     db_path: str = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO daily_topics
               (account_id, report_date, post_id, keyword, reference, selected, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (account_id, report_date, post_id, keyword, reference, int(selected), _now()),
        )


def get_daily_topic_by_post(post_id: str, db_path: str = DB_PATH) -> Optional[dict]:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM daily_topics WHERE post_id = ?", (post_id,)
        ).fetchone()
    return _row_to_dict(row)


def list_daily_topics(account_id: str, report_date: str, db_path: str = DB_PATH) -> list:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM daily_topics WHERE account_id = ? AND report_date = ? ORDER BY id",
            (account_id, report_date),
        ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------- published_topics

def add_published_topic(account_id: str, post_id: str, topic: str, title: str,
                         keywords: list, embedding: Optional[list], source_urls: list,
                         db_path: str = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO published_topics
               (account_id, post_id, topic, title, keywords, embedding, published_at, source_urls)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (account_id, post_id, topic, title, json.dumps(keywords, ensure_ascii=False),
             json.dumps(embedding) if embedding is not None else None,
             _now(), json.dumps(source_urls, ensure_ascii=False)),
        )


def list_recent_published_topics(account_id: str, since_days: int = 30,
                                  db_path: str = DB_PATH) -> list:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """SELECT * FROM published_topics
               WHERE account_id = ? AND published_at >= datetime('now', ?)
               ORDER BY published_at DESC""",
            (account_id, f"-{since_days} days"),
        ).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["keywords"] = json.loads(d["keywords"]) if d.get("keywords") else []
        d["embedding"] = json.loads(d["embedding"]) if d.get("embedding") else None
        d["source_urls"] = json.loads(d["source_urls"]) if d.get("source_urls") else []
        results.append(d)
    return results


# ----------------------------------------------------------- system_status

def set_system_status(key: str, value: Any, db_path: str = DB_PATH) -> None:
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO system_status (key, value, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
            (key, value, _now()),
        )


def get_system_status(key: str, db_path: str = DB_PATH) -> Optional[str]:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT value FROM system_status WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None
