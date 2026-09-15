"""
발행팀 출근 등록(온보딩) — 네이버 블로그 로그인 세션을 저장한다.

브라우저를 띄운 뒤 사용자가 직접 네이버에 로그인하도록 기다리고, 로그인된
세션(쿠키)을 파일로 저장한다. 이후 발행팀(departments.publishing)이 이
파일을 재사용해서 매번 로그인하지 않고 자동으로 임시저장까지 처리한다.

네이버 계정 비밀번호는 이 코드 어디에도 저장하지 않는다 — 로그인은 항상
사용자가 브라우저 창에서 직접 입력한다.

사용법:
    python -m departments.onboarding_publishing
브라우저에서 로그인을 마친 뒤, 이 터미널로 돌아와 Enter를 누르면 세션이
저장된다.
"""

from playwright.sync_api import sync_playwright

from config import NAVER_SESSION_FILE


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://nid.naver.com/nidlogin.login")

        print("[발행팀 출근 등록] 브라우저 창에서 네이버에 직접 로그인해주세요.")
        print("(2단계 인증이 있다면 그것까지 마쳐주세요.)")
        print("로그인이 완료되면 이 터미널로 돌아와 Enter를 눌러주세요.")
        input()

        context.storage_state(path=NAVER_SESSION_FILE)
        print(f"[발행팀 출근 등록] 완료. 세션을 저장했습니다: {NAVER_SESSION_FILE}")
        print("이 파일은 로그인 쿠키를 담고 있으므로 외부에 유출되지 않게 주의하세요.")

        browser.close()


if __name__ == "__main__":
    main()
