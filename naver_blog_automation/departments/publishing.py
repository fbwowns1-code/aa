"""
발행팀 — 작성팀의 최종본과 디자인팀의 이미지를 받아 네이버 블로그 글쓰기
에디터에 채워 넣고 임시저장까지 마무리한다. 회사의 마지막 창구다.

발행팀은 실제로 발행(공개)까지는 하지 않는다 — 항상 임시저장에서 멈추고,
최종 검토·발행은 대표(사용자)가 직접 한다.
"""

from typing import Dict, List, Optional

from core.naver_poster import post_draft


def publish_draft(
    blog_id: str,
    title: str,
    sections: List[Dict],
    tags: List[str],
    images: Optional[List[Dict]] = None,
    headless: bool = False,
    pause_before_save: bool = True,
    session_file: Optional[str] = None,
) -> None:
    """디자인팀이 만든 이미지를 소제목별로 배치해 네이버 블로그에 임시저장한다.

    session_file: 여러 계정을 운영할 때 그 계정의 로그인 세션 파일 경로.
    생략하면 .env의 기본 NAVER_SESSION_FILE(단일 계정)을 쓴다.
    """
    images = images or []
    section_images = {}
    for img in images:
        section_images.setdefault(img["subheading"], img["file_path"])

    print("[발행팀] 네이버 블로그 에디터에 제목·본문·이미지를 채워 넣습니다...")
    post_draft(
        blog_id=blog_id,
        title=title,
        sections=sections,
        tags=tags,
        section_images=section_images,
        headless=headless,
        pause_before_save=pause_before_save,
        session_file=session_file,
    )
    print("[발행팀] 임시저장을 완료했습니다. 최종 검토·발행은 직접 해주세요.")
