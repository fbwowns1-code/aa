"""
디자인팀 출근 등록(온보딩) — 챗지피티 웹채팅 로그인 세션을 저장한다.

인포그래픽 썸네일을 OpenAI 이미지 생성 API가 아니라 챗지피티의 사람용 웹
채팅 화면에 프롬프트를 직접 붙여넣어 만들 때만 필요하다(디자인팀이
via_chatgpt=False로 일할 경우에는 필요 없다).

보통 네이버 블로그는 여러 개 운영해도 챗지피티 계정은 하나만 공용으로 써도
되므로 기본값은 계정 구분 없이 단일 세션이다. 그래도 계정별로 다른
챗지피티 로그인을 쓰고 싶다면 --account로 세션 파일을 따로 만들 수 있다.
(아이디·비밀번호 자동 입력은 지원하지 않는다 — 챗지피티 로그인은 이메일·
비밀번호 입력이 단계별로 나뉘고 보안문자 검증이 흔해서, 자동 입력을 붙여도
실제로는 매번 사람이 개입해야 하는 경우가 많기 때문이다.)

주의: OpenAI 이용약관은 챗지피티 웹 제품에 대한 프로그램적/자동화 접근을
금지하고 있다. 이 스크립트와 departments/design.py의 챗지피티 경로는 그
약관을 우회하는 것이므로, 계정이 제재될 수 있는 위험을 감안하고 쓰는
기능이다.

계정 비밀번호는 이 코드 어디에도 저장하지 않는다 — 로그인은 항상 사용자가
브라우저 창에서 직접 입력한다.

사용법:
    python -m departments.onboarding_design                  # 공용 세션 하나
    python -m departments.onboarding_design --account car_blog  # 계정별 세션
브라우저에서 로그인을 마친 뒤, 이 터미널로 돌아와 Enter를 누르면 세션이
저장된다.
"""

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

from core.accounts import chatgpt_session_file_for


def main():
    parser = argparse.ArgumentParser(description="디자인팀 출근 등록 (챗지피티 로그인 세션 저장)")
    parser.add_argument("--account", default=None,
                         help="계정별로 다른 챗지피티 세션을 쓸 경우 구분용 이름")
    args = parser.parse_args()

    # 세션 파일은 항상 secrets/ 아래에서만 관리한다(민감 정보).
    session_file = (
        str(Path("secrets") / f"chatgpt_session_{args.account}.json")
        if args.account else chatgpt_session_file_for(None)
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://chatgpt.com/")

        print("[디자인팀 출근 등록] 브라우저 창에서 챗지피티에 직접 로그인해주세요.")
        print("로그인이 완료되어 채팅 화면이 보이면 이 터미널로 돌아와 Enter를 눌러주세요.")
        input()

        Path(session_file).parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=session_file)
        print(f"[디자인팀 출근 등록] 완료. 세션을 저장했습니다: {session_file}")
        print("이 파일은 로그인 쿠키를 담고 있으므로 외부에 유출되지 않게 주의하세요.")

        browser.close()


if __name__ == "__main__":
    main()
