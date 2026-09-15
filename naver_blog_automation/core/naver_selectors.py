"""
네이버 블로그 글쓰기 에디터(스마트에디터 ONE) selector 후보 목록.

네이버는 에디터 DOM 구조(클래스명 등)를 예고 없이 바꾼다. 여러 후보를
순서대로 시도하도록 리스트로 관리하고, 전부 실패하면 core/naver_poster.py가
RuntimeError를 낸다 — 그러면 브라우저 개발자도구(F12)로 최신 선택자를
확인해서 이 파일의 해당 리스트 맨 앞에 새 선택자를 추가하면 된다(다른
코드는 건드릴 필요 없다).
"""

TITLE_SELECTORS = [
    ".se-documentTitle .se-placeholder",
    ".se-documentTitle .se-text-paragraph",
    ".se-title-text",
]

BODY_SELECTORS = [
    ".se-main-container",
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

WRITE_URL_TMPL = "https://blog.naver.com/PostWriteForm.naver?blogId={blog_id}"
