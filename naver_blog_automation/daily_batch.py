"""
매일 저녁 지정 시각(예: 21:30)에 실행하도록 스케줄링해서 쓰는 배치 CLI.

대표(사용자)가 매니저에게 "오늘 자동차 뉴스 조사해서 8개 만들어서 임시저장까지
해줘"라고 하루 업무를 통째로 지시하는 창구다. 실제 배정·진행은
manager.assign_daily_batch()가 리서치팀부터 발행팀까지 순서대로 맡긴다.

스케줄링 방법은 README의 "매일 자동 실행 설정"을 참고한다(crontab / Windows
작업 스케줄러). 이 스크립트 자체는 한 번 실행하면 그날 배치를 끝내고 종료하는
구조다 — 상주 프로세스가 아니라, OS 스케줄러가 매일 21:30에 이 스크립트를
한 번씩 실행해주는 방식을 전제로 한다.

무인 실행이 기본이다 — 밤 9시반에 사람이 붙어서 부서마다 확인해줄 수 없기
때문에, 매니저가 각 부서에 자동 모드로 지시한다(제목 1번 자동 채택, 재작업
지시 없음, 저장 전 확인 대기 없음). 결과는 전부 '임시저장'일 뿐 실제 발행은
아니므로, 다음날 직접 검토 후 발행하는 것을 전제로 만들었다.

사전 준비 (README 참고):
  - python -m departments.onboarding_publishing
  - python -m departments.onboarding_design  (--no-infographic-via-chatgpt를 안 쓸 경우 필수)
  이 두 세션은 야간 무인 실행 중에는 다시 로그인할 수 없으므로, 배치 실행 전에
  미리 로그인해서 세션 파일을 최신으로 유지해야 한다.

예시:
  python daily_batch.py --blog-id myblogid
  python daily_batch.py --blog-id myblogid --count 8 --show-browser
"""

import argparse

from manager import assign_daily_batch


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
                         help="디자인팀이 인포그래픽을 이미지 생성 API로 만든다(챗지피티 자동화 안 씀)")
    args = parser.parse_args()

    assign_daily_batch(
        blog_id=args.blog_id,
        count=args.count,
        out_dir=args.out_dir,
        reports_dir=args.reports_dir,
        headless=args.headless,
        infographic_via_chatgpt=args.infographic_via_chatgpt,
    )


if __name__ == "__main__":
    main()
