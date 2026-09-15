"""
CASE 4: 이미 작성한 주제와 매우 유사한 뉴스가 들어오면 DUPLICATE_WARNING에
해당하는 판정(is_duplicate=True)이 나는지 확인한다. 실제 OpenAI 임베딩
호출은 모킹하고, 코사인 유사도·임계값 판정 로직만 검증한다.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("OPENAI_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import database as db
from core import duplicate_check


class DuplicateCheckTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db.init_db(self.db_path)

    def tearDown(self):
        os.remove(self.db_path)

    def test_similar_topic_flagged_as_duplicate(self):
        # "아이오닉 신차 공개"에 대한 임베딩을 미리 저장해둔다.
        db.add_published_topic(
            "carblog", "20260901_carblog_001", topic="아이오닉 신차 공개",
            title="아이오닉 신차, 드디어 공개", keywords=["아이오닉"],
            embedding=[1.0, 0.0, 0.0], source_urls=[], db_path=self.db_path,
        )
        # "아이오닉 가격 공개"는 표현만 다를 뿐 거의 같은 벡터 방향이라고 가정.
        with mock.patch.object(duplicate_check, "get_embedding", return_value=[0.99, 0.14, 0.0]):
            result = duplicate_check.check_duplicate(
                "carblog", "아이오닉 가격 공개", db_path=self.db_path
            )
        self.assertTrue(result["is_duplicate"])
        self.assertGreaterEqual(result["score"], 0.85)
        self.assertEqual(result["best_match"]["post_id"], "20260901_carblog_001")

    def test_unrelated_topic_not_flagged(self):
        db.add_published_topic(
            "carblog", "20260901_carblog_001", topic="아이오닉 신차 공개",
            title="아이오닉 신차, 드디어 공개", keywords=["아이오닉"],
            embedding=[1.0, 0.0, 0.0], source_urls=[], db_path=self.db_path,
        )
        with mock.patch.object(duplicate_check, "get_embedding", return_value=[0.0, 1.0, 0.0]):
            result = duplicate_check.check_duplicate(
                "carblog", "완전히 다른 브랜드의 전혀 다른 소식", db_path=self.db_path
            )
        self.assertFalse(result["is_duplicate"])

    def test_no_published_topics_yet(self):
        with mock.patch.object(duplicate_check, "get_embedding", return_value=[1.0, 0.0, 0.0]):
            result = duplicate_check.check_duplicate("newblog", "첫 게시물", db_path=self.db_path)
        self.assertFalse(result["is_duplicate"])
        self.assertIsNone(result["best_match"])

    def test_embedding_failure_is_non_fatal(self):
        with mock.patch.object(duplicate_check, "get_embedding", side_effect=RuntimeError("네트워크 오류")):
            result = duplicate_check.check_duplicate("carblog", "아무 주제", db_path=self.db_path)
        self.assertFalse(result["is_duplicate"])
        self.assertEqual(result["score"], 0.0)

    def test_cosine_similarity_basic(self):
        self.assertAlmostEqual(duplicate_check._cosine_similarity([1, 0], [1, 0]), 1.0)
        self.assertAlmostEqual(duplicate_check._cosine_similarity([1, 0], [0, 1]), 0.0)
        self.assertEqual(duplicate_check._cosine_similarity([], [1, 0]), 0.0)


if __name__ == "__main__":
    unittest.main()
