"""
네이버 블로그 글쓰기 에디터(스마트에디터 ONE)에 제목·본문·이미지를 채워 넣고
'임시저장'까지 수행하는 Playwright 자동화 모듈.

중요: 네이버는 에디터 DOM 구조를 예고 없이 바꾼다. 이 모듈은 여러 후보
선택자를 순서대로 시도하도록 짜여 있지만(core/naver_selectors.py), 그래도
실패하면 브라우저 개발자도구(F12)로 최신 선택자를 확인해 그 파일의 후보
목록 맨 앞에 새 선택자를 추가하면 된다 — 이 파일은 건드릴 필요 없다.
기본값은 headless=False, pause_before_save=True 로 두어 최소 처음 한두 번은
직접 화면을 보면서 확인하도록 되어 있다.

주요 동작 전후로 상태를 NAVER_OPEN_EDITOR / NAVER_TITLE_FILLED /
NAVER_BODY_FILLED / NAVER_IMAGE_UPLOADED / NAVER_DRAFT_SAVE_CLICKED /
NAVER_DRAFT_CONFIRMED 6단계로 기록하고(core/logger.py), 오류가 나면
가능한 경우 output/errors/<post_id>_naver_error.png로 스크린샷을 남긴다.
"""

from pathlib import Path
from typing import Callable, Dict, List, Optional

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from config import NAVER_SESSION_FILE
from core.logger import log_event
from core.naver_selectors import (
    BODY_SELECTORS,
    CONTINUE_DIALOG_DISMISS_TEXTS,
    IMAGE_BUTTON_SELECTORS,
    SAVE_BUTTON_SELECTORS,
    TITLE_SELECTORS,
    WRITE_URL_TMPL,
)

DEFAULT_ERRORS_DIR = "output/errors"


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


def _wait_visible(locatable, selectors: List[str], timeout: int = 5000):
    last_err = None
    for sel in selectors:
        try:
            loc = locatable.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout)
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


def _save_draft(page, frame, on_save_clicked=None):
    try:
        _click_first(page, SAVE_BUTTON_SELECTORS, timeout=8000)
    except RuntimeError:
        _click_first(frame, SAVE_BUTTON_SELECTORS, timeout=8000)
    # 클릭이 실제로 들어간 직후 바로 idempotency 플래그를 확정한다 — 그
    # 이후 확인 대기(wait_for_timeout)나 브라우저 종료 중에 죽더라도 다음
    # 실행이 같은 글을 또 저장하지 않게 하기 위해서다. 클릭 자체가 실패하면
    # 위에서 이미 예외가 나서 여기까지 오지 않는다.
    if on_save_clicked:
        on_save_clicked()
    page.wait_for_timeout(2000)


def _screenshot_on_error(page, post_id: Optional[str], errors_dir: str) -> Optional[str]:
    if page is None:
        return None
    try:
        Path(errors_dir).mkdir(parents=True, exist_ok=True)
        name = f"{post_id or 'unknown'}_naver_error.png"
        path = str(Path(errors_dir) / name)
        page.screenshot(path=path, full_page=True)
        return path
    except Exception:
        return None


def post_draft(
    blog_id: str,
    title: str,
    sections: List[Dict],
    tags: List[str],
    section_images: Optional[Dict[str, str]] = None,
    headless: bool = False,
    pause_before_save: bool = True,
    session_file: Optional[str] = None,
    on_save_clicked: Optional[Callable[[], None]] = None,
    post_id: Optional[str] = None,
    account_id: Optional[str] = None,
    errors_dir: str = DEFAULT_ERRORS_DIR,
):
    """제목·본문·이미지를 채워 넣고 네이버 블로그에 임시저장한다.

    section_images: {소제목 텍스트: 이미지 파일 경로} — 있는 소제목 다음에
    바로 이미지를 삽입한다.
    pause_before_save: True면 마지막 저장 전에 터미널에서 Enter를 기다린다.
    첫 실행 시에는 반드시 True로 두고 화면을 눈으로 확인하는 것을 권장한다.
    session_file: 여러 계정을 운영할 때 계정별 로그인 세션 파일 경로.
    생략하면 .env의 NAVER_SESSION_FILE(단일 계정용 기본 세션)을 쓴다.
    on_save_clicked: 임시저장 버튼 클릭이 실제로 들어간 직후 호출되는
    콜백(중복 저장 방지용 idempotency 플래그를 세우는 용도). 그 뒤 확인
    대기 중에 죽어도 이미 호출된 뒤이므로 다음 실행이 다시 저장하지 않는다.
    post_id/account_id: 로그·오류 스크린샷 파일명에 쓰인다(생략 가능).
    errors_dir: 오류 스크린샷을 저장할 디렉터리.
    """
    section_images = section_images or {}
    session_file = session_file or NAVER_SESSION_FILE

    def _state(step: str, message: str = ""):
        print(f"[네이버] {step}{(' - ' + message) if message else ''}")
        log_event(account_id, post_id, step, "INFO", message or step)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=session_file)
        page = context.new_page()

        try:
            page.goto(WRITE_URL_TMPL.format(blog_id=blog_id))
            page.wait_for_selector("iframe#mainFrame", timeout=30000)
            frame = page.frame_locator("iframe#mainFrame")
            page.wait_for_timeout(2000)
            _dismiss_continue_dialog(frame)
            _state("NAVER_OPEN_EDITOR", f"blog_id={blog_id}")

            # 제목 입력
            _click_first(frame, TITLE_SELECTORS)
            page.keyboard.type(title, delay=20)
            page.keyboard.press("Enter")
            _state("NAVER_TITLE_FILLED", title)

            # 본문 영역이 실제로 떠 있는지 확인만 한다(클릭하면 제목 입력
            # 직후의 커서 위치가 흐트러지므로 클릭하지 않는다). 후보 선택자가
            # 모두 없으면 네이버 에디터 구조가 바뀐 것이므로 바로 예외를 낸다.
            _wait_visible(frame, BODY_SELECTORS, timeout=8000)

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
                    _state("NAVER_IMAGE_UPLOADED", subheading)

                for para in paragraphs:
                    page.keyboard.type(para, delay=10)
                    page.keyboard.press("Enter")
                page.keyboard.press("Enter")

            if tags:
                tag_line = " ".join(f"#{t.lstrip('#')}" for t in tags)
                page.keyboard.type(tag_line, delay=10)
            _state("NAVER_BODY_FILLED", f"섹션 {len(sections)}개")

            if pause_before_save:
                print("\n에디터 내용을 브라우저 창에서 직접 확인해주세요.")
                print("이상 없으면 이 터미널에서 Enter를 눌러 임시저장을 진행합니다.")
                input()

            _save_draft(page, frame, on_save_clicked=on_save_clicked)
            _state("NAVER_DRAFT_SAVE_CLICKED")

            _state("NAVER_DRAFT_CONFIRMED")
            print("임시저장을 완료했습니다.")
        except Exception as e:
            shot = _screenshot_on_error(page, post_id, errors_dir)
            log_event(
                account_id, post_id, "NAVER_DRAFT",
                "ERROR",
                f"{e}" + (f" (스크린샷: {shot})" if shot else ""),
            )
            raise
        finally:
            browser.close()
