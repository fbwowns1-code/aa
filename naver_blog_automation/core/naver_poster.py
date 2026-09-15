"""
네이버 블로그 글쓰기 에디터(스마트에디터 ONE)에 제목·본문·이미지를 채워 넣고
'임시저장'까지 수행하는 Playwright 자동화 모듈.

중요: 네이버는 에디터 DOM 구조를 예고 없이 바꾼다. 이 모듈은 여러 후보
선택자를 순서대로 시도하도록 짜여 있지만, 그래도 실패하면 브라우저 개발자도구
(F12)로 최신 선택자를 확인해 아래 SELECTORS 상수들을 갱신해야 한다.
기본값은 headless=False, pause_before_save=True 로 두어 최소 처음 한두 번은
직접 화면을 보면서 확인하도록 되어 있다.
"""

from typing import Dict, List, Optional

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from config import NAVER_SESSION_FILE

WRITE_URL_TMPL = "https://blog.naver.com/PostWriteForm.naver?blogId={blog_id}"

TITLE_SELECTORS = [
    ".se-documentTitle .se-placeholder",
    ".se-documentTitle .se-text-paragraph",
    ".se-title-text",
]
IMAGE_BUTTON_SELECTORS = [
    "button.se-image-toolbar-button",
    "button[data-name='image']",
    ".se-toolbar-item-image button",
]
SAVE_BUTTON_SELECTORS = [
    "button:has-text('임시저장')",
    ".save_btn:has-text('임시저장')",
]
CONTINUE_DIALOG_DISMISS_TEXTS = ["취소", "새로 작성"]


def _click_first(locatable, selectors: List[str], timeout: int = 5000):
    last_err = None
    for sel in selectors:
        try:
            loc = locatable.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout)
            loc.click()
            return loc
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"선택자를 찾지 못했습니다(네이버 에디터 구조가 바뀌었을 수 있습니다): {selectors}") from last_err


def _dismiss_continue_dialog(frame):
    """이전에 쓰다 만 글이 있으면 뜨는 '이어서 작성하시겠습니까' 팝업을 닫는다."""
    for text in CONTINUE_DIALOG_DISMISS_TEXTS:
        try:
            btn = frame.get_by_text(text, exact=True)
            if btn.count() > 0:
                btn.first.click(timeout=2000)
                return
        except PWTimeout:
            continue
        except Exception:
            continue


def _insert_image(page, frame, img_path: str):
    with page.expect_file_chooser(timeout=10000) as fc_info:
        _click_first(frame, IMAGE_BUTTON_SELECTORS)
    file_chooser = fc_info.value
    file_chooser.set_files(img_path)
    page.wait_for_timeout(3000)  # 업로드 처리 대기
    page.keyboard.press("End")
    page.keyboard.press("Enter")


def _save_draft(page, frame):
    try:
        _click_first(page, SAVE_BUTTON_SELECTORS, timeout=8000)
    except RuntimeError:
        _click_first(frame, SAVE_BUTTON_SELECTORS, timeout=8000)
    page.wait_for_timeout(2000)


def post_draft(
    blog_id: str,
    title: str,
    sections: List[Dict],
    tags: List[str],
    section_images: Optional[Dict[str, str]] = None,
    headless: bool = False,
    pause_before_save: bool = True,
):
    """제목·본문·이미지를 채워 넣고 네이버 블로그에 임시저장한다.

    section_images: {소제목 텍스트: 이미지 파일 경로} — 있는 소제목 다음에
    바로 이미지를 삽입한다.
    pause_before_save: True면 마지막 저장 전에 터미널에서 Enter를 기다린다.
    첫 실행 시에는 반드시 True로 두고 화면을 눈으로 확인하는 것을 권장한다.
    """
    section_images = section_images or {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=NAVER_SESSION_FILE)
        page = context.new_page()
        page.goto(WRITE_URL_TMPL.format(blog_id=blog_id))
        page.wait_for_selector("iframe#mainFrame", timeout=30000)
        frame = page.frame_locator("iframe#mainFrame")
        page.wait_for_timeout(2000)

        _dismiss_continue_dialog(frame)

        # 제목 입력
        _click_first(frame, TITLE_SELECTORS)
        page.keyboard.type(title, delay=20)
        page.keyboard.press("Enter")

        # 본문 입력 (소제목 → 이미지 → 문단들)
        for section in sections:
            subheading = section.get("subheading", "")
            paragraphs = section.get("paragraphs", [])

            if subheading:
                page.keyboard.press("Control+B")
                page.keyboard.type(subheading, delay=15)
                page.keyboard.press("Control+B")
                page.keyboard.press("Enter")

            img_path = section_images.get(subheading)
            if img_path:
                _insert_image(page, frame, img_path)

            for para in paragraphs:
                page.keyboard.type(para, delay=10)
                page.keyboard.press("Enter")
            page.keyboard.press("Enter")

        if tags:
            tag_line = " ".join(f"#{t.lstrip('#')}" for t in tags)
            page.keyboard.type(tag_line, delay=10)

        if pause_before_save:
            print("\n에디터 내용을 브라우저 창에서 직접 확인해주세요.")
            print("이상 없으면 이 터미널에서 Enter를 눌러 임시저장을 진행합니다.")
            input()

        _save_draft(page, frame)
        print("임시저장을 완료했습니다.")

        browser.close()
