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

한 건이 실패하면 잠시 기다렸다가 재시도하고, 그래도 안 되거나(로그인 세션
만료 등 재시도해도 똑같이 막힐 문제) 연속으로 여러 건이 실패하면 남은
글감은 억지로 진행시키지 않고 배치를 멈추고 대기한다(output/<날짜>/
batch_state.json에 "paused": true로 기록). 문제를 해결한 뒤(보통
onboarding_* 재로그인) 같은 명령을 다시 실행하면 멈췄던 글감부터 이어서
진행된다 — 처음부터 다시 조사하지 않는다.

사전 준비 (README 참고):
  - python -m departments.onboarding_publishing
  - python -m departments.onboarding_design  (--no-infographic-via-chatgpt를 안 쓸 경우 필수)
  이 두 세션은 야간 무인 실행 중에는 다시 로그인할 수 없으므로, 배치 실행 전에
  미리 로그인해서 세션 파일을 최신으로 유지해야 한다.

여러 네이버 계정(여러 블로그)을 운영한다면 --blog-id 대신 --account로
accounts.json에 등록된 계정 이름을 준다. 계정별로 리포트·진행 상태가
output/<날짜>/<account>/, reports/<account>/ 아래에 따로 쌓이므로, 같은
날 계정마다 이 스크립트를 한 번씩 실행해도 서로 덮어쓰지 않는다.

예시:
  python daily_batch.py --blog-id myblogid
  python daily_batch.py --account car_blog --count 8 --show-browser
"""

import argparse

from manager import assign_daily_batch


def main():
    parser = argparse.ArgumentParser(description="국내 자동차 뉴스 조사 + 하루 N개 포스트 배치")
    parser.add_argument("--blog-id", default=None, help="네이버 블로그 ID (blog.naver.com/아이디). --account를 쓰면 생략 가능")
    parser.add_argument("--account", default=None, help="accounts.json에 등록된 계정 이름 (여러 계정을 운영할 때)")
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
    parser.add_argument("--max-retries", type=int, default=1,
                         help="한 건이 실패했을 때 재시도할 횟수 (기본 1회)")
    parser.add_argument("--retry-wait-seconds", type=int, default=60,
                         help="재시도 전 대기 시간(초) (기본 60초)")
    parser.add_argument("--consecutive-failure-limit", type=int, default=2,
                         help="이 횟수만큼 연속 실패하면 배치를 멈추고 대기한다 (기본 2)")
    parser.add_argument("--force-rerun", action="store_true",
                         help="중단된 배치가 있어도 무시하고 오늘 분량을 처음부터(새 리서치부터) 다시 돈다")
    args = parser.parse_args()

    if not args.blog_id and not args.account:
        parser.error("--blog-id 또는 --account 중 하나는 있어야 합니다.")

    assign_daily_batch(
        blog_id=args.blog_id,
        account=args.account,
        count=args.count,
        out_dir=args.out_dir,
        reports_dir=args.reports_dir,
        headless=args.headless,
        infographic_via_chatgpt=args.infographic_via_chatgpt,
        max_retries=args.max_retries,
        retry_wait_seconds=args.retry_wait_seconds,
        consecutive_failure_limit=args.consecutive_failure_limit,
        force_rerun=args.force_rerun,
    )


if __name__ == "__main__":
    main()
