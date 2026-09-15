"""
CASE 1: WRITING까지 성공한 뒤 이후 단계에서 실패(=프로세스가 죽은 상황을
흉내)했을 때, 다음 실행이 처음부터가 아니라 실패했던 단계부터 이어지는지
확인한다. 실제 OpenAI/Playwright 호출은 전부 모킹한다.
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
from core.pipeline import BlogPipeline
from departments import planning, writing, design, publishing

FAKE_TURN1 = {
    "titles": [
        {"no": 1, "category": "SEO 최적화형", "text": "테스트 제목 1"},
        {"no": 6, "category": "후킹/클릭 유도형", "text": "테스트 후킹 제목"},
    ]
}
FAKE_TURN2 = {
    "title": "테스트 제목 1",
    "sections": [{"subheading": "소제목1", "paragraphs": ["본문 문단입니다." * 20]}],
    "tags": ["태그1", "태그2"],
    "char_count": 1300,
    "factcheck_summary": "검증 5건 · 통과 5 · 수정 0 · 삭제 0",
}
FAKE_TURN3 = {
    "common_style_infographic": "공통 스타일",
    "infographic_prompts": [{"role": "main", "subheading": "메인", "prompt": "메인 프롬프트"}],
}


class JobResumeTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.out_dir = os.path.join(self.tmpdir, "output")
        db.init_db(self.db_path)

        self.call_counts = {"propose_titles": 0, "select_title": 0, "draft_body": 0}

        self.patchers = [
            mock.patch.object(planning, "propose_titles", side_effect=self._propose_titles),
            mock.patch.object(planning, "select_title", side_effect=self._select_title),
            mock.patch.object(writing, "draft_body", side_effect=self._draft_body),
            mock.patch.object(writing, "finalize", side_effect=lambda p, t2, auto: t2),
            mock.patch.object(design, "propose_visuals", return_value=FAKE_TURN3),
            mock.patch.object(design, "finalize", side_effect=lambda p, t3, auto: t3),
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
        self.publish_calls = []

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _propose_titles(self, pipeline, keyword, reference, extra):
        self.call_counts["propose_titles"] += 1
        return FAKE_TURN1

    def _select_title(self, pipeline, turn1, auto, title_index, title_strategy, keyword):
        self.call_counts["select_title"] += 1
        return 1

    def _draft_body(self, pipeline, title_no):
        self.call_counts["draft_body"] += 1
        return FAKE_TURN2

    def _publish_draft(self, **kwargs):
        self.publish_calls.append(kwargs)
        on_saved = kwargs.get("on_save_clicked")
        if on_saved:
            on_saved()

    def test_case1_resume_from_last_success(self):
        """1회차: IMAGE 단계에서 영구 실패(재시도 소진) → WRITING/FACT_CHECK/
        QUALITY_GATE는 SUCCESS로 남아야 한다.
        2회차(별도 호출 = 프로세스 재시작을 흉내): IMAGE부터 이어져야 하고,
        PLANNING/WRITING은 다시 호출되면 안 된다."""
        post_id = "20260915_testacc_001"

        with mock.patch.object(design, "produce_images", side_effect=RuntimeError("이미지 API 영구 실패")):
            result1 = job_manager.run_post_job(
                post_id=post_id, account_id="testacc", blog_id="myblog",
                keyword="테스트 키워드", out_dir=self.out_dir, headless=True,
                pause_before_save=False, auto=True, db_path=self.db_path,
            )

        self.assertEqual(result1["status"], "FAILED")
        self.assertEqual(self.call_counts["propose_titles"], 1)
        self.assertEqual(self.call_counts["draft_body"], 1)

        steps = db.get_steps(post_id, db_path=self.db_path)
        self.assertEqual(steps["RESEARCH"]["status"], "SKIPPED")
        self.assertEqual(steps["PLANNING"]["status"], "SUCCESS")
        self.assertEqual(steps["TITLE"]["status"], "SUCCESS")
        self.assertEqual(steps["WRITING"]["status"], "SUCCESS")
        self.assertEqual(steps["FACT_CHECK"]["status"], "SUCCESS")
        self.assertEqual(steps["QUALITY_GATE"]["status"], "SUCCESS")
        self.assertEqual(steps["IMAGE"]["status"], "FAILED")
        self.assertEqual(steps["NAVER_DRAFT"]["status"], "PENDING")

        # ---- 2회차: 같은 post_id로 다시 실행 (이번엔 IMAGE가 성공한다) ----
        with mock.patch.object(design, "produce_images", return_value=[
            {"subheading": "메인", "prompt": "p", "file_path": "img.png"}
        ]):
            result2 = job_manager.run_post_job(
                post_id=post_id, account_id="testacc", blog_id="myblog",
                keyword="테스트 키워드", out_dir=self.out_dir, headless=True,
                pause_before_save=False, auto=True, db_path=self.db_path,
            )

        self.assertEqual(result2["status"], "COMPLETED")
        self.assertEqual(self.call_counts["propose_titles"], 1, "PLANNING이 재개 시 다시 불렸다")
        self.assertEqual(self.call_counts["draft_body"], 1, "WRITING이 재개 시 다시 불렸다")
        self.assertEqual(len(self.publish_calls), 1)

        steps = db.get_steps(post_id, db_path=self.db_path)
        for name in ("PLANNING", "TITLE", "WRITING", "FACT_CHECK", "QUALITY_GATE", "IMAGE", "NAVER_DRAFT"):
            self.assertEqual(steps[name]["status"], "SUCCESS", f"{name} 단계가 SUCCESS가 아님")

    def test_blog_pipeline_resume_restores_conversation_id(self):
        """BlogPipeline.resume()이 저장해둔 previous_response_id를 그대로
        이어받는지 확인한다(실제 네트워크 호출 없이 속성만 검증)."""
        pipeline = BlogPipeline.resume("시스템 프롬프트", "resp_abc123", current_raw="이전 응답 텍스트")
        self.assertEqual(pipeline.client.previous_response_id, "resp_abc123")
        self.assertEqual(pipeline.current_raw, "이전 응답 텍스트")


if __name__ == "__main__":
    unittest.main()
