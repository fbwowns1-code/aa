"""core/quality_gate.py의 점수 산출·PASS/REVIEW/FAILED 경계를 검증한다.
AI 판정 호출은 실패하게 두고(네트워크 없음) 휴리스틱 경로만 검증한다."""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("OPENAI_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import quality_gate


def _sections(paragraphs_per_section=1, chars_each=400, n_sections=5):
    return [
        {"subheading": f"소제목{i}", "paragraphs": ["가" * chars_each] * paragraphs_per_section}
        for i in range(n_sections)
    ]


class QualityGateTestCase(unittest.TestCase):
    def setUp(self):
        # AI 판정은 항상 실패하게 만들어서(네트워크 없음) 휴리스틱만으로 평가되게 한다.
        self.patcher = mock.patch.object(quality_gate, "_ai_judge", return_value=None)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_good_post_passes(self):
        sections = _sections(chars_each=300, n_sections=5)
        char_count = sum(len(p) for s in sections for p in s["paragraphs"])
        result = quality_gate.evaluate(
            title="정상적인 제목입니다", sections=sections, char_count=char_count,
            factcheck_summary="검증 10건 통과 10", min_chars=1000, max_chars=3000,
            headings_target=5, has_image_prompts=True, duplicate_result=None,
        )
        self.assertEqual(result["verdict"], "PASS")
        self.assertGreaterEqual(result["score"], 85)

    def test_too_short_gets_penalized(self):
        sections = [{"subheading": "s1", "paragraphs": ["짧은 본문"]}]
        result = quality_gate.evaluate(
            title="제목", sections=sections, char_count=50,
            min_chars=1200, max_chars=1500, headings_target=5,
            has_image_prompts=True, duplicate_result=None,
        )
        self.assertLess(result["score"], 100)
        self.assertIn("글자수 부족", " ".join(result["findings"]))

    def test_missing_image_prompts_penalized(self):
        sections = _sections(chars_each=300, n_sections=5)
        char_count = sum(len(p) for s in sections for p in s["paragraphs"])
        result = quality_gate.evaluate(
            title="제목", sections=sections, char_count=char_count,
            min_chars=1000, max_chars=3000, headings_target=5,
            has_image_prompts=False, duplicate_result=None,
        )
        self.assertIn("이미지 생성 프롬프트가 없음", result["findings"])

    def test_duplicate_result_pushes_toward_review_or_lower(self):
        sections = _sections(chars_each=300, n_sections=5)
        char_count = sum(len(p) for s in sections for p in s["paragraphs"])
        dup = {"is_duplicate": True, "score": 0.9, "best_match": {"post_id": "20260901_carblog_001"}}
        result = quality_gate.evaluate(
            title="제목", sections=sections, char_count=char_count,
            min_chars=1000, max_chars=3000, headings_target=5,
            has_image_prompts=True, duplicate_result=dup,
        )
        self.assertLess(result["score"], 100)
        self.assertTrue(any("유사도 높음" in f for f in result["findings"]))

    def test_very_bad_post_fails(self):
        sections = [{"subheading": "s1", "paragraphs": ["대박 레전드 미쳤다"]}]
        result = quality_gate.evaluate(
            title="대박 제목", sections=sections, char_count=10,
            min_chars=1200, max_chars=1500, headings_target=5,
            has_image_prompts=False,
            duplicate_result={"is_duplicate": True, "score": 0.95, "best_match": {"post_id": "x"}},
        )
        self.assertEqual(result["verdict"], "FAILED")
        self.assertLess(result["score"], 70)


if __name__ == "__main__":
    unittest.main()
