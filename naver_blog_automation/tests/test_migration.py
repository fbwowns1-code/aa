"""migrate_to_sqlite.py가 옛 batch_state.json/status.json을 automation.db로
올바르게 옮기는지, 원본을 지우지 않고 backup/에 남기는지, 다시 실행해도
중복 이관되지 않는지를 검증한다."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("OPENAI_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import migrate_to_sqlite as migrate  # noqa: E402
from core import database as db  # noqa: E402

BATCH_STATE = {
    "report_date": "2026-09-01",
    "account": "testmigacc",
    "blog_id": "testblogid",
    "topics": [
        {"keyword": "쏘렌토 풀체인지", "reference": ""},
        {"keyword": "아이오닉6 페이스리프트", "reference": ""},
        {"keyword": "미정 주제", "reference": ""},
    ],
    "topics_total": 3,
    "results": [
        {"keyword": "쏘렌토 풀체인지", "title": "쏘렌토 풀체인지 MQ5, 드디어 공개",
         "char_count": 2500, "image_count": 6, "status": "ok"},
        {"keyword": "아이오닉6 페이스리프트", "status": "failed",
         "error": "선택자를 찾지 못했습니다"},
    ],
    "paused": True,
    "paused_reason": "치명적인 오류로 판단해 배치를 멈춥니다",
}


class MigrationTestCase(unittest.TestCase):
    def setUp(self):
        self._orig_cwd = os.getcwd()
        self._tmpdir = tempfile.TemporaryDirectory()
        os.chdir(self._tmpdir.name)

        fd, self.db_path = tempfile.mkstemp(suffix=".db", dir=self._tmpdir.name)
        os.close(fd)
        db.init_db(self.db_path)

        self.out_dir = Path("output/20260901/testmigacc")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.batch_state_path = self.out_dir / "batch_state.json"
        self.batch_state_path.write_text(
            json.dumps(BATCH_STATE, ensure_ascii=False), encoding="utf-8"
        )

        self.status_path = Path("output/status.json")
        self.status_path.write_text(
            json.dumps({"label": "테스트 배치", "finished": True, "running": False,
                        "error": "선택자를 찾지 못했습니다"}, ensure_ascii=False),
            encoding="utf-8",
        )

    def tearDown(self):
        os.chdir(self._orig_cwd)
        self._tmpdir.cleanup()

    def test_completed_post_migrated_with_idempotency_flag(self):
        migrate.migrate_batch_state(self.batch_state_path, self.db_path, dry_run=False)

        post = db.get_post("20260901_testmigacc_001", db_path=self.db_path)
        self.assertEqual(post["status"], "COMPLETED")
        self.assertEqual(post["title"], "쏘렌토 풀체인지 MQ5, 드디어 공개")
        self.assertTrue(db.is_naver_draft_completed("20260901_testmigacc_001", db_path=self.db_path))

        steps = db.get_steps("20260901_testmigacc_001", db_path=self.db_path)
        for step_name in db.STEP_NAMES:
            self.assertEqual(steps[step_name]["status"], "SUCCESS")

    def test_failed_post_migrated_without_step_detail(self):
        migrate.migrate_batch_state(self.batch_state_path, self.db_path, dry_run=False)

        post = db.get_post("20260901_testmigacc_002", db_path=self.db_path)
        self.assertEqual(post["status"], "FAILED")
        self.assertFalse(db.is_naver_draft_completed("20260901_testmigacc_002", db_path=self.db_path))

        # 옛 기록에는 단계별 실패 지점이 없으므로 전부 PENDING으로 남아야
        # 재실행 시 RESEARCH부터(사실상 처음부터) 다시 돌게 된다.
        steps = db.get_steps("20260901_testmigacc_002", db_path=self.db_path)
        for step_name in db.STEP_NAMES:
            self.assertEqual(steps[step_name]["status"], "PENDING")

    def test_untried_topic_migrated_as_pending(self):
        migrate.migrate_batch_state(self.batch_state_path, self.db_path, dry_run=False)

        post = db.get_post("20260901_testmigacc_003", db_path=self.db_path)
        self.assertEqual(post["status"], "PENDING")

    def test_rerun_does_not_duplicate(self):
        first = migrate.migrate_batch_state(self.batch_state_path, self.db_path, dry_run=False)
        second = migrate.migrate_batch_state(self.batch_state_path, self.db_path, dry_run=False)

        self.assertEqual(first, 3)
        self.assertEqual(second, 0)
        posts = db.list_posts("testmigacc", db_path=self.db_path)
        self.assertEqual(len(posts), 3)

    def test_dry_run_writes_nothing_to_db(self):
        migrated = migrate.migrate_batch_state(self.batch_state_path, self.db_path, dry_run=True)
        self.assertEqual(migrated, 3)
        self.assertIsNone(db.get_post("20260901_testmigacc_001", db_path=self.db_path))

    def test_original_file_untouched_and_backup_created(self):
        migrate.migrate_batch_state(self.batch_state_path, self.db_path, dry_run=False)
        dest = migrate._backup(self.batch_state_path)

        self.assertTrue(self.batch_state_path.exists())
        self.assertEqual(
            json.loads(self.batch_state_path.read_text(encoding="utf-8")), BATCH_STATE
        )
        self.assertTrue(dest.exists())
        self.assertEqual(json.loads(dest.read_text(encoding="utf-8")), BATCH_STATE)

    def test_status_json_stored_as_legacy_snapshot(self):
        ok = migrate.migrate_status_json(self.status_path, self.db_path, dry_run=False)
        self.assertTrue(ok)
        snapshot = db.get_system_status("legacy_status_snapshot", db_path=self.db_path)
        self.assertIsNotNone(snapshot)
        self.assertIn("테스트 배치", snapshot)


if __name__ == "__main__":
    unittest.main()
