"""
발행팀 출근 등록(온보딩) — 네이버 블로그 로그인 세션을 저장한다.

여러 네이버 계정(여러 블로그)을 운영한다면 --account 이름으로 계정별
세션 파일을 따로 관리한다. accounts.json(accounts.example.json 참고)에
해당 계정의 naver_id/naver_pw를 저장해두면 로그인 페이지의 아이디·비밀번호
칸에 자동으로 입력해준다 — 실제 키 입력처럼 한 글자씩 타이핑해서 넣으므로
네이버의 자동입력 방지 로직과도 보통 호환된다. 보안문자(캡차)나 2단계
인증이 뜨면 그건 직접 처리해야 하고, 로그인 버튼도 직접 눌러야 한다 —
이 스크립트가 자동으로 제출하지는 않는다.

accounts.json이 없거나 --account를 안 주면 기존처럼 완전히 수동으로
로그인하면 된다(아이디·비밀번호 자동 입력 없이).

네이버 계정 비밀번호는 화면에 입력하는 용도로만 쓰이고, 이 코드가 저장하거나
어디로 전송하지 않는다(저장되는 것은 accounts.json에 사용자가 직접 적어둔
값과, 로그인 후의 쿠키 세션뿐이다).

사용법:
    python -m departments.onboarding_publishing                  # 계정 구분 없이 기본 세션 하나
    python -m departments.onboarding_publishing --account car_blog  # 계정별 세션
브라우저에서 로그인을 마친 뒤, 이 터미널로 돌아와 Enter를 누르면 세션이
저장된다.
"""

import argparse

from playwright.sync_api import sync_playwright

from config import NAVER_SESSION_FILE
from core.accounts import get_account, naver_session_file_for


def main():
    parser = argparse.ArgumentParser(description="발행팀 출근 등록 (네이버 로그인 세션 저장)")
    parser.add_argument("--account", default=None,
                         help="accounts.json에 등록된 계정 이름 (여러 계정을 운영할 때)")
    args = parser.parse_args()

    account = None
    if args.account:
        try:
            account = get_account(args.account)
        except KeyError as e:
            print(f"[발행팀 출근 등록] {e}")
            return

    session_file = naver_session_file_for(args.account, account) if args.account else NAVER_SESSION_FILE

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://nid.naver.com/nidlogin.login")

        if account and account.get("naver_id") and account.get("naver_pw"):
            print(f"[발행팀 출근 등록] '{args.account}' 계정의 아이디·비밀번호를 입력합니다...")
            page.click("#id")
            page.keyboard.type(account["naver_id"], delay=50)
            page.click("#pw")
            page.keyboard.type(account["naver_pw"], delay=50)
            print("[발행팀 출근 등록] 입력 완료. 보안문자(캡차)나 2단계 인증이 뜨면 직접 처리하고, "
                  "로그인 버튼을 눌러주세요.")
        else:
            print("[발행팀 출근 등록] 브라우저 창에서 네이버에 직접 로그인해주세요.")
            print("(2단계 인증이 있다면 그것까지 마쳐주세요.)")

        print("로그인이 완료되면 이 터미널로 돌아와 Enter를 눌러주세요.")
        input()

        context.storage_state(path=session_file)
        print(f"[발행팀 출근 등록] 완료. 세션을 저장했습니다: {session_file}")
        print("이 파일은 로그인 쿠키를 담고 있으므로 외부에 유출되지 않게 주의하세요.")

        browser.close()


if __name__ == "__main__":
    main()
