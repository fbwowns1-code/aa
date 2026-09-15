"""
디자인팀 출근 등록(온보딩) — 챗지피티 웹채팅 로그인 세션을 저장한다.

인포그래픽 썸네일을 OpenAI 이미지 생성 API가 아니라 챗지피티의 사람용 웹
채팅 화면에 프롬프트를 직접 붙여넣어 만들 때만 필요하다(디자인팀이
via_chatgpt=False로 일할 경우에는 필요 없다).

주의: OpenAI 이용약관은 챗지피티 웹 제품에 대한 프로그램적/자동화 접근을
금지하고 있다. 이 스크립트와 departments/design.py의 챗지피티 경로는 그
약관을 우회하는 것이므로, 계정이 제재될 수 있는 위험을 감안하고 쓰는
기능이다.

계정 비밀번호는 이 코드 어디에도 저장하지 않는다 — 로그인은 항상 사용자가
브라우저 창에서 직접 입력한다.

사용법:
    python -m departments.onboarding_design
브라우저에서 로그인을 마친 뒤, 이 터미널로 돌아와 Enter를 누르면 세션이
저장된다.
"""

from playwright.sync_api import sync_playwright

from config import CHATGPT_SESSION_FILE


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://chatgpt.com/")

        print("[디자인팀 출근 등록] 브라우저 창에서 챗지피티에 직접 로그인해주세요.")
        print("로그인이 완료되어 채팅 화면이 보이면 이 터미널로 돌아와 Enter를 눌러주세요.")
        input()

        context.storage_state(path=CHATGPT_SESSION_FILE)
        print(f"[디자인팀 출근 등록] 완료. 세션을 저장했습니다: {CHATGPT_SESSION_FILE}")
        print("이 파일은 로그인 쿠키를 담고 있으므로 외부에 유출되지 않게 주의하세요.")

        browser.close()


if __name__ == "__main__":
    main()
