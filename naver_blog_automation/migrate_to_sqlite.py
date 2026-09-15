"""
예전 방식(output/status.json, output/<날짜>/<계정>/batch_state.json)으로
남아 있던 진행 상태를 automation.db(SQLite)로 옮기는 1회성 마이그레이션
스크립트.

원본 파일은 지우지 않는다 — 전부 backup/ 아래로 같은 상대 경로 구조로
복사해 둔다(원본은 그 자리에 그대로 남긴다. 정말로 지우고 싶으면 이
스크립트를 실행해 정상적으로 옮겨졌는지 확인한 뒤 직접 지운다).

사용:
    python migrate_to_sqlite.py                 # output/ 아래를 훑어서 이관
    python migrate_to_sqlite.py --out-dir output --dry-run   # 미리보기만(DB에 쓰지 않음)

한계(중요): batch_state.json에는 core/database.py의 job_steps처럼 9단계
세부 기록이 없다 — 옛 시스템은 "부서" 단위로만 진행을 표시했지, 리서치/
중복확인/기획/제목/작성/팩트체크/품질검사/이미지/네이버저장으로 나눠
기록하지 않았다. 그래서 이관 규칙은 다음과 같다.

  - results[i]["status"] == "ok"  → 그 글은 실제로 네이버에 임시저장까지
    끝난 글이므로 posts.status=COMPLETED, 9단계 전부 SUCCESS, 무엇보다
    naver_draft_completed=1로 남긴다 — 이관 후 실수로 이 글을 다시
    저장(중복 저장)하지 않게 하기 위한 필수 조치다.
  - results[i]["status"] == "failed" → posts.status=FAILED로만 남긴다.
    어느 단계에서 실패했는지는 옛 기록에 없으므로 9단계는 전부 PENDING으로
    둔다 — 이 글을 이어서 하려면 사실상 RESEARCH부터 다시 도는 것과 같다.
  - topics 개수가 results 개수보다 많으면(아직 시도 안 한 글감) PENDING으로만
    등록해둔다.
"""

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

from core import database as db

BACKUP_DIR = Path("backup")


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [경고] {path} 읽기 실패, 건너뜁니다: {e}")
        return None


def _backup(path: Path) -> Path:
    """원본과 같은 상대 경로 구조로 backup/ 아래에 복사한다(원본은 안 지움)."""
    try:
        rel = path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        rel = Path(path.name)
    dest = BACKUP_DIR / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
    return dest


def migrate_batch_state(path: Path, db_path: str, dry_run: bool = False) -> int:
    state = _read_json(path)
    if not state:
        return 0

    report_date = (state.get("report_date") or "").replace("-", "")
    if not report_date:
        print(f"  [경고] {path}: report_date가 없어 건너뜁니다.")
        return 0

    blog_id = state.get("blog_id") or ""
    account_id = state.get("account") or blog_id
    if not account_id:
        print(f"  [경고] {path}: account/blog_id가 모두 없어 건너뜁니다.")
        return 0

    topics = state.get("topics", [])
    results = state.get("results", [])
    migrated = 0

    print(f"  {path} → 계정 '{account_id}', 글감 {len(topics)}건, 결과 {len(results)}건")

    if not dry_run:
        db.upsert_account(account_id, blog_id=blog_id, db_path=db_path)

    for i, topic in enumerate(topics):
        post_id = f"{report_date}_{account_id}_{i + 1:03d}"
        keyword = topic.get("keyword", "")
        result = results[i] if i < len(results) else None
        result_status = (result or {}).get("status")

        if result_status == "ok":
            new_status = "COMPLETED"
        elif result_status == "failed":
            new_status = "FAILED"
        else:
            new_status = "PENDING"

        if dry_run:
            print(f"    [dry-run] {post_id} ← {keyword!r} ({new_status})")
            migrated += 1
            continue

        if db.get_post(post_id, db_path=db_path):
            print(f"    {post_id}는 이미 automation.db에 있어 건너뜁니다(중복 이관 방지).")
            continue

        db.create_post(post_id, account_id, topic=keyword,
                        title=(result or {}).get("title", ""), db_path=db_path)
        job_id = db.create_job(post_id, db_path=db_path)
        db.init_steps_for_post(job_id, post_id, db_path=db_path)

        if new_status == "COMPLETED":
            for step in db.STEP_NAMES:
                db.start_step(post_id, job_id, step, db_path=db_path)
                db.complete_step(post_id, step,
                                  result_ref="migrate_to_sqlite.py로 이관(옛 batch_state.json)",
                                  db_path=db_path)
            db.mark_naver_draft_completed(post_id, db_path=db_path)
            db.update_post(post_id, db_path=db_path, status="COMPLETED",
                            completed_at=datetime.now().isoformat(timespec="seconds"))
            db.update_job_status(job_id, "SUCCESS", db_path=db_path)
        elif new_status == "FAILED":
            db.update_post(post_id, db_path=db_path, status="FAILED")
            db.update_job_status(job_id, "FAILED", db_path=db_path)
            db.log_error(post_id, account_id, "UNKNOWN", "MIGRATED_FAILURE",
                         (result or {}).get("error", ""), "", db_path=db_path)
        # PENDING은 init_steps_for_post가 만든 기본값 그대로 둔다.

        migrated += 1

    return migrated


def migrate_status_json(path: Path, db_path: str, dry_run: bool = False) -> bool:
    """output/status.json은 게시물 단위 기록이 없는 "마지막 실행 상태" 스냅샷이라
    posts/job_steps로 옮길 방법이 없다. 참고용으로 system_status에 원문을
    그대로 보관만 해둔다(대시보드는 이제 이 값을 쓰지 않는다 — automation.db의
    posts/job_steps를 직접 읽는다)."""
    state = _read_json(path)
    if not state:
        return False
    if dry_run:
        print(f"  [dry-run] {path} → system_status['legacy_status_snapshot']로 보관 예정")
        return True
    db.set_system_status("legacy_status_snapshot", state, db_path=db_path)
    print(f"  {path} → system_status['legacy_status_snapshot']에 참고용으로 보관했습니다.")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="output/status.json, output/**/batch_state.json을 automation.db로 이관"
    )
    parser.add_argument("--out-dir", default="output",
                         help="batch_state.json을 찾을 최상위 폴더 (기본 output)")
    parser.add_argument("--status-json", default="output/status.json",
                         help="옛 status.json 경로 (기본 output/status.json)")
    parser.add_argument("--db-path", default=db.DB_PATH, help="automation.db 경로")
    parser.add_argument("--dry-run", action="store_true",
                         help="실제로 DB에 쓰지 않고 무엇을 이관할지만 보여준다")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    status_path = Path(args.status_json)

    if not args.dry_run:
        db.init_db(args.db_path)

    total = 0
    batch_state_files = sorted(out_dir.rglob("batch_state.json")) if out_dir.exists() else []
    if not batch_state_files:
        print(f"{out_dir} 아래에서 batch_state.json을 찾지 못했습니다.")
    else:
        print(f"batch_state.json {len(batch_state_files)}개를 찾았습니다.")
        for path in batch_state_files:
            total += migrate_batch_state(path, args.db_path, dry_run=args.dry_run)
            if not args.dry_run:
                dest = _backup(path)
                print(f"    백업: {dest}")

    if status_path.exists():
        migrated = migrate_status_json(status_path, args.db_path, dry_run=args.dry_run)
        if migrated and not args.dry_run:
            dest = _backup(status_path)
            print(f"    백업: {dest}")
    else:
        print(f"{status_path}가 없어 건너뜁니다.")

    if args.dry_run:
        print(f"\n[dry-run] 총 {total}건의 게시물을 이관할 예정입니다. 실제로 실행하려면 "
              "--dry-run 없이 다시 실행하세요.")
    else:
        print(f"\n총 {total}건의 게시물을 automation.db({args.db_path})로 이관했습니다. "
              f"원본 파일은 지우지 않았고 backup/ 아래에 복사본을 남겼습니다.")


if __name__ == "__main__":
    main()
