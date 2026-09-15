"""
매일 지정된 시각(기본 21:30)에 하루 배치를 자동으로 실행해주는 상주
스케줄러 — 회사의 "경비/비서" 역할이다. 대표가 매번 명령어를 치지 않아도,
정해진 시각이 되면 이 스케줄러가 대신 총괄 매니저(manager.assign_daily_batch)
에게 업무를 지시한다.

OS 수준 crontab/작업 스케줄러를 따로 설정하고 싶지 않을 때 쓰는 대안이다
(README의 "매일 21:30에 자동 실행되게 예약하기" 참고 — crontab 방식은
스케줄러를 계속 켜둘 필요가 없는 대신 OS 설정이 필요하고, 이 스크립트는
설정이 필요 없는 대신 컴퓨터에서 계속 실행되고 있어야 한다. 둘 중 편한
쪽을 쓰면 된다).

실행 중인 동안 컴퓨터를 꺼두면 그날 배치는 건너뛰게 된다. 실행은 보통
`nohup python scheduler.py --blog-id ... &` (Linux/Mac)이나 Windows에서는
시작프로그램에 등록하는 방식으로 계속 켜둔다.

배치가 "중단(paused)" 상태로 끝나면(로그인 세션 만료, 연속 실패 등) 콘솔에
사유를 남기고 다음날 예정된 시각에 다시 시도한다 — 원인이 해결되지 않으면
또 같은 이유로 멈출 수 있으니, 로그에 찍힌 paused_reason을 보고 직접
조치(재로그인 등)가 필요하다.
"""

import argparse
import time
from datetime import datetime, timedelta

from manager import assign_daily_batch


def _seconds_until(hour: int, minute: int) -> float:
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _run_one_batch(label: str, **kwargs):
    print(f"[스케줄러] {label} 배치를 시작합니다.")
    try:
        state = assign_daily_batch(**kwargs)
        if state.get("paused"):
            print(f"[스케줄러] {label} 배치가 중단된 채로 끝났습니다 — {state.get('paused_reason')}")
            print(f"[스케줄러] 원인을 해결하면 다음 예정 시각에 이어서 진행됩니다"
                  f"(또는 지금 바로 `python daily_batch.py ...`로 수동 재시도 가능).")
    except Exception as e:
        # 매니저 안에서 못 잡은 예상 밖 오류 — 스케줄러 자체는 죽지 않고 내일 다시 시도한다.
        print(f"[스케줄러] {label} 배치 실행 중 예상치 못한 오류가 발생했습니다: {e}")
        print(f"[스케줄러] {label}은 내일 같은 시각에 다시 시도합니다.")


def run_forever(
    blog_id: str = None,
    accounts: list = None,
    hour: int = 21,
    minute: int = 30,
    count: int = 8,
    out_dir: str = "output",
    reports_dir: str = "reports",
    headless: bool = True,
    infographic_via_chatgpt: bool = True,
    title_strategy: str = "hook_curiosity_mix",
    max_retries: int = 1,
    retry_wait_seconds: int = 60,
    consecutive_failure_limit: int = 2,
):
    """accounts가 주어지면(여러 계정 운영) 매일 같은 시각에 계정마다 순서대로
    하루 배치를 한 번씩 돌린다. accounts가 없으면 blog_id 하나로 기존처럼
    동작한다."""
    who = f"{len(accounts)}개 계정({', '.join(accounts)})" if accounts else "단일 블로그"
    print(f"[스케줄러] 매일 {hour:02d}:{minute:02d}에 {who} 배치를 실행하도록 대기합니다. "
          "(Ctrl+C로 종료)")
    while True:
        wait_seconds = _seconds_until(hour, minute)
        next_run = datetime.now() + timedelta(seconds=wait_seconds)
        print(f"[스케줄러] 다음 실행: {next_run.strftime('%Y-%m-%d %H:%M:%S')} "
              f"(약 {wait_seconds / 3600:.1f}시간 후)")
        time.sleep(wait_seconds)

        print(f"[스케줄러] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} — 오늘 배치를 시작합니다.")
        common_kwargs = dict(
            count=count, out_dir=out_dir, reports_dir=reports_dir, headless=headless,
            infographic_via_chatgpt=infographic_via_chatgpt, title_strategy=title_strategy,
            max_retries=max_retries, retry_wait_seconds=retry_wait_seconds,
            consecutive_failure_limit=consecutive_failure_limit,
        )
        if accounts:
            for account in accounts:
                _run_one_batch(f"'{account}' 계정", account=account, **common_kwargs)
        else:
            _run_one_batch("블로그", blog_id=blog_id, **common_kwargs)

        # 같은 분에 _seconds_until()을 또 부르면 0초가 나와 그날을 또 실행할 수 있으므로
        # 다음 날짜로 넘어가도록 충분히 대기한다.
        time.sleep(120)


def main():
    parser = argparse.ArgumentParser(description="daily_batch를 매일 지정 시각에 자동 실행하는 상주 스케줄러")
    parser.add_argument("--blog-id", default=None,
                         help="네이버 블로그 ID (blog.naver.com/아이디). 계정을 하나만 운영할 때")
    parser.add_argument("--account", dest="accounts", action="append", default=None,
                         help="accounts.json에 등록된 계정 이름. 여러 번 줄 수 있고(--account a --account b), "
                              "그러면 매일 같은 시각에 계정마다 순서대로 배치를 돌린다")
    parser.add_argument("--hour", type=int, default=21, help="실행 시(0-23), 기본 21")
    parser.add_argument("--minute", type=int, default=30, help="실행 분(0-59), 기본 30")
    parser.add_argument("--count", type=int, default=8, help="하루에 만들 포스트 개수 (기본 8개)")
    parser.add_argument("--out-dir", default="output")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--show-browser", dest="headless", action="store_false",
                         help="브라우저 창을 띄워서 확인하고 싶을 때(테스트용)")
    parser.add_argument("--no-infographic-via-chatgpt", dest="infographic_via_chatgpt",
                         action="store_false", default=True)
    parser.add_argument("--title-strategy", default="hook_curiosity_mix",
                         choices=["hook_curiosity_mix", "first"])
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--retry-wait-seconds", type=int, default=60)
    parser.add_argument("--consecutive-failure-limit", type=int, default=2)
    args = parser.parse_args()

    if not args.blog_id and not args.accounts:
        parser.error("--blog-id 또는 --account 중 하나는 있어야 합니다.")

    run_forever(
        blog_id=args.blog_id,
        accounts=args.accounts,
        hour=args.hour,
        minute=args.minute,
        count=args.count,
        out_dir=args.out_dir,
        reports_dir=args.reports_dir,
        headless=args.headless,
        infographic_via_chatgpt=args.infographic_via_chatgpt,
        title_strategy=args.title_strategy,
        max_retries=args.max_retries,
        retry_wait_seconds=args.retry_wait_seconds,
        consecutive_failure_limit=args.consecutive_failure_limit,
    )


if __name__ == "__main__":
    main()
