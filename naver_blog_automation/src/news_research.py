"""
국내 자동차 업계(현대차·기아·제네시스·KG모빌리티·르노코리아·수입차 브랜드 등)의
화제 소식·이슈를 웹에서 조사해 리포트로 만들고, 그중 오늘 블로그 글감으로 쓸
항목을 선정하는 모듈.

daily_batch.py가 매일 이 모듈을 먼저 돌려서 나온 selected_topics를
src/post_runner.py의 run_single_post(keyword=..., reference=...)에 그대로
넣는다 — keyword/reference 조합은 원래 지침(prompts/system_prompt.txt)의
"제목+본문 참고형" 입력 방식과 같다(참고 본문은 팩트 소스로만 쓰이고,
본문 자체는 다시 F목록 검증을 거친다).
"""

import json
import os
import re
from datetime import date
from pathlib import Path

from openai import OpenAI

from config import OPENAI_MODEL, OPENAI_WEB_SEARCH_TOOL

RESEARCH_INSTRUCTIONS = """당신은 국내 자동차 업계 뉴스 리서치 에이전트다.

웹 검색으로 오늘(또는 최근 24~48시간 이내)의 현대차·기아·제네시스·
KG모빌리티·르노코리아·수입차 브랜드(BMW, 벤츠, 테슬라, 아우디, 폭스바겐,
볼보, 토요타 등) 관련 화제 소식과 이슈를 조사한다.

조사 범위: 신차 출시·페이스리프트·풀체인지 소식, 가격·스펙 발표, 판매량·
순위, 리콜·결함·논란, 프로모션·할인, 업계 이슈(전기차 보조금, 파업, 수출
등), 화제가 된 커뮤니티·SNS 반응까지 포함한다.

신뢰도 우선순위: 공식 사이트·제조사 보도자료 > 메이저 뉴스 > 자동차 전문
매체 > 커뮤니티. 각 항목마다 출처 URL을 반드시 단다(메인 페이지가 아니라
그 소식이 실제로 담긴 상세 페이지). 최소 12개 이상의 항목을 찾는다.

찾은 항목 중에서 네이버 블로그 글감으로 쓰기 좋은 것을 정확히 8개
selected_topics에 고른다. 기준: 화제성·검색 수요가 있을 것, 브랜드가
가능한 겹치지 않게 다양할 것(같은 브랜드를 연속으로 고르지 않는다), 같은
이슈를 중복으로 고르지 않을 것. 각 선정 항목에는 이후 블로그 작성
파이프라인에 바로 넣을 keyword(짧은 키워드나 제목 후보)와 reference
(발행일·핵심 내용·출처를 담은 3~5문장 요약, 마지막에 출처 URL 포함)를
만든다.

다음 JSON 형식으로만 답하라. 다른 텍스트나 코드블록 표시 없이 JSON 객체
하나만 출력한다.

{
  "report_date": "YYYY-MM-DD",
  "items": [
    {
      "published_at": "YYYY-MM-DD",
      "company": "현대차 | 기아 | 제네시스 | KG모빌리티 | 르노코리아 | 수입차 브랜드명 등",
      "headline": "소식 한 줄 제목",
      "summary": "핵심 내용 2~3문장",
      "source_name": "출처명",
      "source_url": "상세 페이지 URL"
    }
  ],
  "selected_topics": [
    {
      "company": "...",
      "keyword": "블로그 파이프라인에 넣을 키워드 또는 제목",
      "reference": "발행일 · 핵심 내용 · 출처 URL을 포함한 3~5문장 요약"
    }
  ]
}
"""


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("리서치 응답에서 JSON을 찾지 못했습니다:\n" + text[:2000])
    return json.loads(match.group(0))


def _to_markdown(report: dict) -> str:
    lines = [f"# 국내 자동차 업계 뉴스 리포트 ({report.get('report_date', '')})", ""]
    lines.append("## 전체 조사 항목")
    for item in report.get("items", []):
        lines.append(
            f"- **[{item.get('published_at', '')}] {item.get('company', '')}** "
            f"{item.get('headline', '')} — {item.get('summary', '')} "
            f"([{item.get('source_name', '출처')}]({item.get('source_url', '')}))"
        )
    lines.append("")
    lines.append("## 오늘의 블로그 글감 (선정)")
    for i, topic in enumerate(report.get("selected_topics", []), 1):
        lines.append(f"{i}. **[{topic.get('company', '')}] {topic.get('keyword', '')}**")
        lines.append(f"   - {topic.get('reference', '')}")
    return "\n".join(lines)


def research_daily_news(save_dir: str = "reports", api_key: str = None) -> dict:
    """오늘의 국내 자동차 업계 뉴스를 조사해서 report(dict)로 돌려주고,
    JSON·Markdown 파일로도 save_dir에 저장한다."""
    client = OpenAI(api_key=api_key or os.environ["OPENAI_API_KEY"])
    response = client.responses.create(
        model=OPENAI_MODEL,
        instructions=RESEARCH_INSTRUCTIONS,
        input="오늘 기준으로 국내 자동차 업계 화제 뉴스를 조사해줘.",
        tools=[{"type": OPENAI_WEB_SEARCH_TOOL}],
    )
    report = _extract_json(response.output_text)
    report_date = report.get("report_date") or date.today().isoformat()

    Path(save_dir).mkdir(parents=True, exist_ok=True)
    (Path(save_dir) / f"{report_date}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (Path(save_dir) / f"{report_date}.md").write_text(_to_markdown(report), encoding="utf-8")

    return report


if __name__ == "__main__":
    # 단독 실행하면 리포트만 만들고 파이프라인은 돌리지 않는다.
    r = research_daily_news()
    print(f"리포트 생성 완료: report_date={r.get('report_date')}, "
          f"항목 {len(r.get('items', []))}개, 선정 {len(r.get('selected_topics', []))}개")
