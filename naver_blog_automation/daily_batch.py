"""
매일 저녁 지정 시각(예: 21:30)에 실행하도록 스케줄링해서 쓰는 배치 스크립트.

1) 국내 자동차 업계 화제 뉴스를 조사해 리포트(reports/YYYY-MM-DD.md·json)를 만들고
2) 그중 선정된 글감(기본 8개)마다 제목→본문→인포그래픽 이미지→네이버 임시저장까지
   순서대로 실행한다.

스케줄링 방법은 README의 "매일 자동 실행 설정"을 참고한다(crontab / Windows
작업 스케줄러). 이 스크립트 자체는 한 번 실행하면 그날의 배치를 끝내고 종료하는
구조다 — 계속 켜놓는 상주 프로세스가 아니라, OS 스케줄러가 매일 21:30에 이
스크립트를 한 번씩 실행해주는 방식을 전제로 한다.

무인 실행이 기본이다 — 각 포스트마다 자동으로 제목 1번을 고르고 수정 없이
그대로 진행한다(밤 9시반에 사람이 붙어서 번호를 골라줄 수 없기 때문이다).
결과는 전부 '임시저장'일 뿐 실제 발행은 아니므로, 다음날 직접 검토 후 발행하는
것을 전제로 만들었다. 포스트 하나가 실패해도(선택자 불일치, 이미지 생성 실패
등) 나머지는 계속 진행하고, 마지막에 성공/실패 요약을 남긴다.

사전 준비 (README 참고):
  - python -m src.naver_login
  - python -m src.chatgpt_login  (--no-infographic-via-chatgpt를 안 쓸 경우 필수)
  이 두 세션은 야간 무인 실행 중에는 다시 로그인할 수 없으므로, 배치 실행 전에
  미리 로그인해서 세션 파일을 최신으로 유지해야 한다.

예시:
  python daily_batch.py --blog-id myblogid
  python daily_batch.py --blog-id myblogid --count 8 --headless
"""

import argparse
import json
import traceback
from datetime import date
from pathlib import Path

from src.news_research import research_daily_news
from src.post_runner import run_single_post


def main():
    parser = argparse.ArgumentParser(description="국내 자동차 뉴스 조사 + 하루 N개 포스트 배치")
    parser.add_argument("--blog-id", required=True, help="네이버 블로그 ID (blog.naver.com/아이디)")
    parser.add_argument("--count", type=int, default=8, help="오늘 만들 포스트 개수 (기본 8개)")
    parser.add_argument("--out-dir", default="output", help="포스트별 이미지 저장 폴더의 상위 경로")
    parser.add_argument("--reports-dir", default="reports", help="뉴스 리포트 저장 폴더")
    parser.add_argument("--headless", action="store_true", default=True,
                         help="브라우저 창 없이 실행 (배치는 기본값 사용을 권장 — 야간 무인 실행이므로)")
    parser.add_argument("--show-browser", dest="headless", action="store_false",
                         help="브라우저 창을 띄워서 확인하고 싶을 때(테스트용)")
    parser.add_argument("--no-infographic-via-chatgpt", dest="infographic_via_chatgpt",
                         action="store_false", default=True,
                         help="인포그래픽도 챗지피티 웹채팅 대신 이미지 생성 API로 만든다")
    args = parser.parse_args()

    print(f"[뉴스 조사] {date.today().isoformat()} 국내 자동차 업계 뉴스 조사 중...")
    report = research_daily_news(save_dir=args.reports_dir)
    report_date = report.get("report_date", date.today().isoformat())
    topics = report.get("selected_topics", [])[: args.count]
    print(f"  선정된 글감 {len(topics)}개 (리포트: {args.reports_dir}/{report_date}.md)")

    if not topics:
        print("선정된 글감이 없어서 배치를 종료합니다. 리포트 파일을 확인하세요.")
        return

    today_out_dir = Path(args.out_dir) / report_date
    results = []

    for i, topic in enumerate(topics, 1):
        keyword = topic.get("keyword", "")
        reference = topic.get("reference", "")
        print(f"\n===== [{i}/{len(topics)}] {keyword} =====")
        try:
            result = run_single_post(
                keyword=keyword,
                blog_id=args.blog_id,
                reference=reference,
                out_dir=str(today_out_dir / f"post_{i:02d}"),
                headless=args.headless,
                pause_before_save=False,  # 야간 무인 실행이므로 확인 대기 없음
                auto=True,  # 제목 1번 자동 선택, 수정 요청 없음
                infographic_via_chatgpt=args.infographic_via_chatgpt,
            )
            result["status"] = "ok"
            results.append(result)
            print(f"  완료: {result['title']}")
        except Exception as e:
            print(f"  [실패] {keyword}: {e}")
            traceback.print_exc()
            results.append({"keyword": keyword, "status": "failed", "error": str(e)})
            continue

    today_out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = today_out_dir / "batch_summary.json"
    summary_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = sum(1 for r in results if r.get("status") == "ok")
    print(f"\n배치 완료: {ok}/{len(results)}개 성공. 요약: {summary_path}")


if __name__ == "__main__":
    main()
