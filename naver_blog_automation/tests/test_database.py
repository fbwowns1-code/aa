"""core/database.py의 기본 CRUD와 재개/idempotency에 필요한 조회 동작을 검증한다."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("OPENAI_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import database as db


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db.init_db(self.db_path)

    def tearDown(self):
        os.remove(self.db_path)

    def test_post_id_format_and_sequence(self):
        pid1 = db.next_post_id("carblog", report_date="20260915", db_path=self.db_path)
        self.assertEqual(pid1, "20260915_carblog_001")
        db.create_post(pid1, "carblog", db_path=self.db_path)
        pid2 = db.next_post_id("carblog", report_date="20260915", db_path=self.db_path)
        self.assertEqual(pid2, "20260915_carblog_002")

    def test_step_lifecycle_and_first_pending(self):
        post_id = "20260915_carblog_001"
        db.create_post(post_id, "carblog", db_path=self.db_path)
        job_id = db.create_job(post_id, db_path=self.db_path)
        db.init_steps_for_post(job_id, post_id, db_path=self.db_path)

        self.assertEqual(db.first_pending_step(post_id, db_path=self.db_path), "RESEARCH")

        db.start_step(post_id, job_id, "RESEARCH", db_path=self.db_path)
        db.complete_step(post_id, "RESEARCH", db_path=self.db_path)
        self.assertEqual(db.first_pending_step(post_id, db_path=self.db_path), "DUPLICATE_CHECK")

        db.start_step(post_id, job_id, "DUPLICATE_CHECK", db_path=self.db_path)
        db.fail_step(post_id, "DUPLICATE_CHECK", "네트워크 오류", db_path=self.db_path)
        self.assertEqual(db.first_pending_step(post_id, db_path=self.db_path), "DUPLICATE_CHECK")

        steps = db.get_steps(post_id, db_path=self.db_path)
        self.assertEqual(steps["DUPLICATE_CHECK"]["status"], "FAILED")
        self.assertEqual(steps["DUPLICATE_CHECK"]["last_error"], "네트워크 오류")
        self.assertEqual(steps["DUPLICATE_CHECK"]["attempt"], 1)

    def test_reset_step_cascades_and_clears_naver_flag(self):
        post_id = "20260915_carblog_001"
        db.create_post(post_id, "carblog", db_path=self.db_path)
        job_id = db.create_job(post_id, db_path=self.db_path)
        db.init_steps_for_post(job_id, post_id, db_path=self.db_path)

        for step in db.STEP_NAMES:
            db.start_step(post_id, job_id, step, db_path=self.db_path)
            db.complete_step(post_id, step, db_path=self.db_path)
        db.mark_naver_draft_completed(post_id, db_path=self.db_path)

        self.assertIsNone(db.first_pending_step(post_id, db_path=self.db_path))
        self.assertTrue(db.is_naver_draft_completed(post_id, db_path=self.db_path))

        # IMAGE부터 강제 재실행하면 IMAGE와 그 뒤(NAVER_DRAFT)가 PENDING으로
        # 돌아가고, naver_draft_completed도 같이 내려가야 한다(아니면
        # NAVER_DRAFT를 다시 돌 때 idempotency 가드에 막혀버린다).
        db.reset_step(post_id, "IMAGE", db_path=self.db_path)
        steps = db.get_steps(post_id, db_path=self.db_path)
        self.assertEqual(steps["IMAGE"]["status"], "PENDING")
        self.assertEqual(steps["NAVER_DRAFT"]["status"], "PENDING")
        self.assertEqual(steps["WRITING"]["status"], "SUCCESS")  # 앞 단계는 안 건드림
        self.assertFalse(db.is_naver_draft_completed(post_id, db_path=self.db_path))

    def test_published_topics_round_trip(self):
        db.add_published_topic(
            "carblog", "20260915_carblog_001", topic="아이오닉 신차 공개",
            title="아이오닉 신차, 드디어 공개", keywords=["아이오닉"],
            embedding=[0.1, 0.2, 0.3], source_urls=["https://example.com/a"],
            db_path=self.db_path,
        )
        recent = db.list_recent_published_topics("carblog", since_days=30, db_path=self.db_path)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["embedding"], [0.1, 0.2, 0.3])
        self.assertEqual(recent[0]["keywords"], ["아이오닉"])

    def test_daily_topic_lookup_by_post(self):
        db.add_daily_topic("carblog", "20260915", "아이오닉 가격 발표", "참고 본문",
                           selected=True, post_id="20260915_carblog_001", db_path=self.db_path)
        topic = db.get_daily_topic_by_post("20260915_carblog_001", db_path=self.db_path)
        self.assertEqual(topic["keyword"], "아이오닉 가격 발표")


if __name__ == "__main__":
    unittest.main()
