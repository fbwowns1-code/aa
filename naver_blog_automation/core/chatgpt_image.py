"""
챗지피티 웹채팅(chatgpt.com)에 "한글 인포그래픽 썸네일 프롬프트"를 붙여넣어
이미지를 생성시키고, 생성된 이미지를 다운로드해서 파일로 저장한다.

주의:
- 이것은 OpenAI 이미지 생성 API가 아니라 챗지피티의 사람용 웹 채팅 화면을
  브라우저로 흉내 내서 쓰는 것이다. OpenAI 이용약관은 챗지피티 웹 제품에
  대한 프로그램적/자동화 접근을 금지하고 있으므로, 계정이 제재될 위험을
  감안하고 쓰는 기능이다 — 실사 이미지는 이 모듈을 쓰지 않고 계속
  src/image_gen.py(공식 이미지 생성 API)로 만든다.
- chatgpt.com은 UI를 예고 없이 바꾼다. 아래 SELECTORS가 안 맞으면
  headless=False로 두고 직접 화면을 보면서 최신 선택자로 갱신해야 한다.
"""

from pathlib import Path
from typing import Dict, List

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

CHATGPT_URL = "https://chatgpt.com/"

PROMPT_INPUT_SELECTORS = [
    "#prompt-textarea",
    "div[contenteditable='true']#prompt-textarea",
    "textarea[data-testid='prompt-textarea']",
]
SEND_BUTTON_SELECTORS = [
    "button[data-testid='send-button']",
    "button[aria-label='Send prompt']",
]
NEW_CHAT_SELECTORS = [
    "a[data-testid='create-new-chat-button']",
    "button[aria-label='New chat']",
]
GENERATED_IMAGE_SELECTORS = [
    "img[alt='Generated image']",
    "div[data-message-author-role='assistant'] img",
]

IMAGE_WAIT_TIMEOUT_MS = 180_000  # 인포그래픽 생성은 수십 초~수 분 걸릴 수 있다


def _click_first(page, selectors: List[str], timeout: int = 5000):
    last_err = None
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout)
            loc.click()
            return loc
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(
        f"선택자를 찾지 못했습니다(챗지피티 UI가 바뀌었을 수 있습니다): {selectors}"
    ) from last_err


def _start_new_chat(page):
    try:
        _click_first(page, NEW_CHAT_SELECTORS, timeout=3000)
    except RuntimeError:
        page.goto(CHATGPT_URL)
    page.wait_for_timeout(1500)


def _submit_prompt(page, prompt_text: str):
    box = _click_first(page, PROMPT_INPUT_SELECTORS)
    box.click()
    page.keyboard.insert_text(prompt_text)
    _click_first(page, SEND_BUTTON_SELECTORS)


def _wait_for_generated_image(page, timeout_ms: int = IMAGE_WAIT_TIMEOUT_MS):
    for sel in GENERATED_IMAGE_SELECTORS:
        try:
            page.wait_for_selector(sel, timeout=timeout_ms)
            return page.locator(sel).last
        except PWTimeout:
            continue
    raise RuntimeError("이미지 생성 결과를 찾지 못했습니다 (시간 초과 또는 선택자 불일치).")


def _download_image(page, img_locator, out_path: str):
    src = img_locator.get_attribute("src")
    if not src:
        raise RuntimeError("이미지 URL(src)을 가져오지 못했습니다.")
    # 같은 브라우저 컨텍스트(로그인 쿠키 포함)로 직접 요청해서 저장한다.
    response = page.context.request.get(src)
    if response.status != 200:
        raise RuntimeError(f"이미지 다운로드 실패: HTTP {response.status}")
    Path(out_path).write_bytes(response.body())


def generate_infographic_images_via_chatgpt(
    prompts: List[Dict],
    out_dir: str,
    session_file: str,
    headless: bool = False,
) -> List[Dict]:
    """prompts: [{"subheading": str, "prompt": str}, ...]
    각 prompt를 새 챗지피티 채팅에 붙여넣어 이미지를 생성시키고 저장한다.

    반환: 성공한 항목만 {"subheading", "prompt", "file_path"} 형태로 담는다.
    실패한 항목(선택자 불일치, 시간 초과, 정책 거부 등)은 건너뛰고 콘솔에
    이유를 출력한다 — 한 장이 실패해도 나머지는 계속 진행되게 하기 위함이다.
    """
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=session_file)
        page = context.new_page()
        page.goto(CHATGPT_URL)
        page.wait_for_timeout(2000)

        for i, item in enumerate(prompts):
            subheading = item.get("subheading", "")
            print(f"  [챗지피티] '{subheading}' 이미지 생성 요청 중...")
            try:
                _start_new_chat(page)
                _submit_prompt(page, item["prompt"])
                img_locator = _wait_for_generated_image(page)
                file_path = str(Path(out_dir) / f"infographic_{i + 1:02d}.png")
                _download_image(page, img_locator, file_path)
                results.append({**item, "file_path": file_path})
                print(f"    저장 완료: {file_path}")
            except Exception as e:
                print(f"    [경고] 실패해서 건너뜁니다 - {subheading}: {e}")
                continue

        browser.close()

    return results
