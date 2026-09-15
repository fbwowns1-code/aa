"""
CASE 2: NAVER_DRAFT가 완료된 게시물을 재실행해도 같은 글을 다시
임시저장하지 않는지 확인한다. force_step="NAVER_DRAFT"로 명시했을 때만
다시 저장되는 것도 함께 확인한다.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("OPENAI_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import database as db
from core import job_manager
from departments import planning, writing, design, publishing

FAKE_TURN1 = {"titles": [{"no": 1, "category": "SEO 최적화형", "text": "테스트 제목"}]}
FAKE_TURN2 = {
    "title": "테스트 제목",
    "sections": [{"subheading": "소제목1", "paragraphs": ["본문 문단입니다." * 20]}],
    "tags": ["태그1"],
    "char_count": 1300,
    "factcheck_summary": "검증 3건 · 통과 3 · 수정 0 · 삭제 0",
}
FAKE_TURN3 = {
    "common_style_infographic": "공통 스타일",
    "infographic_prompts": [{"role": "main", "subheading": "메인", "prompt": "메인 프롬프트"}],
}


class IdempotencyTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.out_dir = os.path.join(self.tmpdir, "output")
        db.init_db(self.db_path)
        self.publish_calls = []

        self.patchers = [
            mock.patch.object(planning, "propose_titles", return_value=FAKE_TURN1),
            mock.patch.object(planning, "select_title", return_value=1),
            mock.patch.object(writing, "draft_body", return_value=FAKE_TURN2),
            mock.patch.object(writing, "finalize", side_effect=lambda p, t2, auto: t2),
            mock.patch.object(design, "propose_visuals", return_value=FAKE_TURN3),
            mock.patch.object(design, "finalize", side_effect=lambda p, t3, auto: t3),
            mock.patch.object(design, "produce_images", return_value=[
                {"subheading": "메인", "prompt": "p", "file_path": "img.png"}
            ]),
            mock.patch.object(publishing, "publish_draft", side_effect=self._publish_draft),
            mock.patch("core.job_manager.check_duplicate", return_value={
                "is_duplicate": False, "best_match": None, "score": 0.0, "embedding": None,
            }),
            mock.patch("core.job_manager.quality_evaluate", return_value={
                "score": 90, "verdict": "PASS", "findings": [],
            }),
            mock.patch("core.job_manager.backoff_seconds", return_value=0),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _publish_draft(self, **kwargs):
        self.publish_calls.append(kwargs)
        on_saved = kwargs.get("on_save_clicked")
        if on_saved:
            on_saved()

    def _run(self, post_id, **extra):
        return job_manager.run_post_job(
            post_id=post_id, account_id="testacc", blog_id="myblog",
            keyword="테스트", out_dir=self.out_dir, headless=True,
            pause_before_save=False, auto=True, db_path=self.db_path, **extra,
        )

    def test_case2_naver_draft_not_repeated_on_rerun(self):
        post_id = "20260915_testacc_010"

        result1 = self._run(post_id)
        self.assertEqual(result1["status"], "COMPLETED")
        self.assertEqual(len(self.publish_calls), 1)
        self.assertTrue(db.is_naver_draft_completed(post_id, db_path=self.db_path))

        # 완전히 끝난 게시물을 그냥 다시 실행 — 아무 것도 다시 하면 안 된다.
        result2 = self._run(post_id)
        self.assertEqual(len(self.publish_calls), 1, "NAVER_DRAFT가 중복 실행됐다")
        self.assertEqual(result2["status"], "COMPLETED")

        steps = db.get_steps(post_id, db_path=self.db_path)
        self.assertEqual(steps["NAVER_DRAFT"]["status"], "SUCCESS")

    def test_case2b_force_step_allows_explicit_resave(self):
        post_id = "20260915_testacc_011"
        self._run(post_id)
        self.assertEqual(len(self.publish_calls), 1)

        # 관리자가 명시적으로 NAVER_DRAFT만 강제 재실행 — 이번엔 다시 저장돼야 한다.
        result = self._run(post_id, force_step="NAVER_DRAFT")
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(len(self.publish_calls), 2, "force-step으로도 재저장이 안 됐다")
        self.assertTrue(db.is_naver_draft_completed(post_id, db_path=self.db_path))

    def test_crash_right_after_save_click_does_not_duplicate_within_retries(self):
        """save 버튼 클릭 직후 응답을 놓치는 상황(예: 확인 대기 중 예외)을
        흉내낸다 — on_save_clicked는 정상 호출된 뒤 예외가 난다. _run_step이
        자동으로 재시도하더라도, 두 번째 시도는 이미 저장된 걸 알아채고
        publish_draft를 다시 부르면 안 된다(그래서 재시도만으로 같은 실행
        안에서 자연 복구된다 — 별도 재실행이 없어도 결과는 COMPLETED)."""
        post_id = "20260915_testacc_012"
        call_state = {"n": 0}

        def _publish_then_crash_once(**kwargs):
            call_state["n"] += 1
            self.publish_calls.append(kwargs)
            on_saved = kwargs.get("on_save_clicked")
            if on_saved:
                on_saved()  # 저장 버튼 클릭 직후 콜백은 정상 호출됐다고 가정
            if call_state["n"] == 1:
                raise RuntimeError("확인 대기 중 브라우저 연결 끊김")

        with mock.patch.object(publishing, "publish_draft", side_effect=_publish_then_crash_once):
            result1 = self._run(post_id)

        # 재시도 1회차에서 이미 naver_draft_completed가 세워졌으므로, 재시도
        # 2회차는 publish_draft를 다시 부르지 않고 바로 성공 처리돼야 한다.
        self.assertEqual(result1["status"], "COMPLETED")
        self.assertEqual(len(self.publish_calls), 1, "재시도 중에 같은 글이 다시 저장됐다")
        self.assertTrue(db.is_naver_draft_completed(post_id, db_path=self.db_path))
        steps = db.get_steps(post_id, db_path=self.db_path)
        self.assertEqual(steps["NAVER_DRAFT"]["status"], "SUCCESS")

        # 완전히 끝난 뒤 또 실행해도 publish_draft는 다시 불리면 안 된다.
        result2 = self._run(post_id)
        self.assertEqual(len(self.publish_calls), 1, "이미 저장된 글인데 다시 저장을 시도했다")
        self.assertEqual(result2["status"], "COMPLETED")


if __name__ == "__main__":
    unittest.main()
