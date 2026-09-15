"""
디자인팀 — 작성팀이 확정한 본문을 받아 한글 인포그래픽 썸네일 프롬프트를
뽑고, 실제 이미지 파일까지 제작해서 발행팀에 넘긴다. 지침 원문(턴3)의
이미지 프롬프트 단계 + 실제 이미지 생성(챗지피티 웹채팅 또는 이미지 생성
API)을 담당한다.

실사 이미지는 다루지 않는다 — 이 회사는 인포그래픽 썸네일만 만든다.
"""

from pathlib import Path

from config import CHATGPT_SESSION_FILE
from core.pipeline import BlogPipeline
from core.image_gen import generate_images
from core.chatgpt_image import generate_infographic_images_via_chatgpt


def propose_visuals(pipeline: BlogPipeline) -> dict:
    """본문을 바탕으로 인포그래픽 썸네일 프롬프트를 뽑는다."""
    print("[디자인팀] 본문에 맞는 인포그래픽 썸네일 프롬프트를 구상합니다...")
    return pipeline.run_turn3()


def finalize(pipeline: BlogPipeline, turn3: dict, auto: bool) -> dict:
    """auto=True면 그대로 확정한다. 그렇지 않으면 자유 텍스트로 시안 수정을
    지시할 수 있고, Enter만 누르면 그대로 확정된다."""
    if auto:
        return turn3

    while True:
        print("\n" + pipeline.human_part())
        answer = input(
            "\n>> [디자인팀에게 지시] 이미지 시안에 수정할 내용이 있으면 문장으로 입력하세요 "
            "(예: '메인 이미지 배경을 도심으로'). 없으면 그냥 Enter: "
        ).strip()
        if not answer:
            return turn3
        turn3 = pipeline.revise(answer)


def _build_prompts(turn3: dict) -> list:
    common = turn3.get("common_style_infographic", "")
    prompts = []
    for item in turn3.get("infographic_prompts", []):
        subheading = "메인" if item.get("role") == "main" else item.get("subheading", "")
        prompts.append({
            "subheading": subheading,
            "prompt": f"{common}\n{item.get('prompt', '')}".strip(),
        })
    return prompts


def produce_images(turn3: dict, out_dir: str, via_chatgpt: bool = True, headless: bool = False,
                    chatgpt_session_file: str = None) -> list:
    """확정된 이미지 시안으로 실제 이미지 파일을 만든다.

    via_chatgpt=True(기본)면 챗지피티 웹채팅 자동화로, False면 OpenAI
    이미지 생성 API로 만든다. 반환값: [{"subheading", "prompt", "file_path"}]
    chatgpt_session_file: 계정별로 다른 챗지피티 세션을 쓸 경우 지정. 생략하면
    .env의 기본 CHATGPT_SESSION_FILE(공용 세션)을 쓴다.
    """
    prompts = _build_prompts(turn3)
    if not prompts:
        print("[디자인팀] 만들 이미지가 없어서 건너뜁니다.")
        return []

    session_file = chatgpt_session_file or CHATGPT_SESSION_FILE

    if via_chatgpt:
        if not Path(session_file).exists():
            raise RuntimeError(
                f"디자인팀이 챗지피티에 출근하지 않았습니다(세션 파일 {session_file} 없음). "
                "먼저 `python -m departments.onboarding_design`으로 출근 등록하세요."
            )
        print(f"[디자인팀] 인포그래픽 썸네일 {len(prompts)}개를 챗지피티 웹채팅으로 제작합니다.")
        return generate_infographic_images_via_chatgpt(
            prompts, out_dir, session_file, headless=headless,
        )

    print(f"[디자인팀] 인포그래픽 썸네일 {len(prompts)}개를 이미지 생성 API로 제작합니다.")
    return generate_images(prompts, out_dir, default_size="1024x1024")
