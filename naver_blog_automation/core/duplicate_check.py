"""
같은 소재(예: "아이오닉 신차 공개" → "아이오닉 가격 공개" → "아이오닉
사전계약")가 표현만 바뀌어 반복 작성되는 것을 막기 위한 중복/유사 주제
탐지.

단순 문자열 일치가 아니라 OpenAI 임베딩으로 의미적 유사도를 잰다.
최근 N일(published_topics 테이블) 게시물과 비교해서 유사도가 임계값을
넘으면 "중복 경고"를 매기지만, 그 자체로 글 작성을 막지는 않는다 —
실제로 새로운 정보(가격 발표, 사전계약 등)가 있으면 "업데이트 글"로
쓸 수 있어야 하므로, DUPLICATE_CHECK 단계는 경고만 기록하고 기획팀에게
"기존 글과 뭐가 달라졌는지 명시하라"는 지시를 얹어 넘긴다.
"""

import os
from typing import Optional

from openai import OpenAI

from config import (
    OPENAI_EMBEDDING_MODEL,
    DUPLICATE_CHECK_WINDOW_DAYS,
    DUPLICATE_SIMILARITY_THRESHOLD,
)
from core import database


def get_embedding(text: str, api_key: Optional[str] = None) -> list:
    client = OpenAI(api_key=api_key or os.environ["OPENAI_API_KEY"])
    response = client.embeddings.create(model=OPENAI_EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


def _cosine_similarity(a: list, b: list) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def check_duplicate(account_id: str, topic_text: str, db_path: str = database.DB_PATH) -> dict:
    """topic_text(키워드+참고자료 요약 정도)를 최근
    DUPLICATE_CHECK_WINDOW_DAYS일 내 이 계정의 발행글과 비교한다.

    반환값: {
      "is_duplicate": bool,           # 임계값 이상으로 유사한 글이 있었는지
      "best_match": dict | None,      # 가장 유사했던 published_topics 행
      "score": float,                 # 그 유사도(0~1)
      "embedding": list,              # 이번 topic_text의 임베딩(호출자가 재사용 가능)
    }

    임베딩 API 호출이 실패하면(네트워크 등) 중복 아님으로 보수적으로
    처리하고 조용히 넘어간다 — 이 단계 때문에 전체 파이프라인이 멈추면
    안 되기 때문이다.
    """
    try:
        embedding = get_embedding(topic_text)
    except Exception as e:
        print(f"[중복검사] 임베딩 생성 실패({e}) — 중복 검사를 건너뜁니다.")
        return {"is_duplicate": False, "best_match": None, "score": 0.0, "embedding": None}

    recent = database.list_recent_published_topics(
        account_id, since_days=DUPLICATE_CHECK_WINDOW_DAYS, db_path=db_path
    )

    best_score = 0.0
    best_match = None
    for row in recent:
        if not row.get("embedding"):
            continue
        score = _cosine_similarity(embedding, row["embedding"])
        if score > best_score:
            best_score = score
            best_match = row

    is_duplicate = best_score >= DUPLICATE_SIMILARITY_THRESHOLD
    return {
        "is_duplicate": is_duplicate,
        "best_match": best_match,
        "score": best_score,
        "embedding": embedding,
    }
