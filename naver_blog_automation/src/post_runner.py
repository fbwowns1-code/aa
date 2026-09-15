"""
네이버 블로그 글 한 편을 처음부터 끝까지 만들어내는 핵심 로직.

키워드(+선택적으로 참고 본문) 하나를 받아서:
  1) F목록·제목 45/50개 생성 (턴1)
  2) 제목 선택 → 본문 작성 → 팩트체크 → 최종본 (턴2)
  3) 한글 인포그래픽 썸네일 이미지 제작 (턴3 → 챗지피티 웹채팅 또는 이미지 생성 API)
  4) 네이버 블로그 글쓰기 에디터에 채워 넣고 임시저장

단발 실행(main.py)과 하루 여러 편을 도는 배치(daily_batch.py) 양쪽에서
이 모듈의 run_single_post()를 그대로 재사용한다.
"""

from pathlib import Path
from typing import Optional

from config import PROMPT_PATH, CHATGPT_SESSION_FILE
from src.pipeline import BlogPipeline
from src.image_gen import generate_images
from src.chatgpt_image import generate_infographic_images_via_chatgpt
from src.naver_poster import post_draft

IMAGE_MODE = "인포"  # 실사 이미지 프롬프트는 쓰지 않고, 한글 인포그래픽 썸네일만 생성한다


def load_system_prompt() -> str:
    return Path(PROMPT_PATH).read_text(encoding="utf-8")


def build_infographic_prompts(turn3: dict) -> list:
    common = turn3.get("common_style_infographic", "")
    prompts = []
    for item in turn3.get("infographic_prompts", []):
        subheading = "메인" if item.get("role") == "main" else item.get("subheading", "")
        prompts.append({
            "subheading": subheading,
            "prompt": f"{common}\n{item.get('prompt', '')}".strip(),
        })
    return prompts


def choose_title(pipeline: BlogPipeline, turn1: dict, auto: bool, title_index: Optional[int] = None) -> int:
    titles = turn1["titles"]
    if title_index:
        return title_index
    if auto:
        return titles[0]["no"]

    while True:
        print("\n" + pipeline.human_part())
        answer = input(
            "\n>> 마음에 드는 제목 번호를 입력하세요.\n"
            "   수정 요청이 있으면 문장으로 입력하세요 (예: '오너 감정형 위주로 5개만 다시', "
            "'가격 정보를 제목에 넣어줘'): "
        ).strip()
        if not answer:
            continue
        if answer.isdigit():
            title_no = int(answer)
            if any(t["no"] == title_no for t in titles):
                return title_no
            print(f"[안내] {title_no}번은 목록에 없습니다. 다시 입력해주세요.")
            continue
        # 숫자가 아니면 수정 요청으로 간주해서 그대로 모델에 전달한다.
        turn1 = pipeline.revise(answer)
        titles = turn1["titles"]


def finalize_body(pipeline: BlogPipeline, turn2: dict, auto: bool) -> dict:
    if auto:
        return turn2

    while True:
        print("\n" + pipeline.human_part())
        answer = input(
            "\n>> 본문에 수정할 내용이 있으면 문장으로 입력하세요 (예: '3번째 소제목에 연비 얘기 추가해줘', "
            "'말투를 좀 더 담백하게'). 없으면 그냥 Enter: "
        ).strip()
        if not answer:
            return turn2
        turn2 = pipeline.revise(answer)


def finalize_images(pipeline: BlogPipeline, turn3: dict, auto: bool) -> dict:
    if auto:
        return turn3

    while True:
        print("\n" + pipeline.human_part())
        answer = input(
            "\n>> 이미지 프롬프트에 수정할 내용이 있으면 문장으로 입력하세요 (예: '메인 이미지 배경을 도심으로'). "
            "없으면 그냥 Enter: "
        ).strip()
        if not answer:
            return turn3
        turn3 = pipeline.revise(answer)


def run_single_post(
    keyword: str,
    blog_id: str,
    reference: str = "",
    extra: str = "",
    title_index: Optional[int] = None,
    out_dir: str = "output",
    headless: bool = False,
    pause_before_save: bool = True,
    auto: bool = False,
    infographic_via_chatgpt: bool = True,
) -> dict:
    """글 한 편을 끝까지 만들어 네이버 블로그에 임시저장한다.

    반환값: {"keyword", "title", "char_count", "image_count"}
    """
    system_prompt = load_system_prompt()
    pipeline = BlogPipeline(system_prompt)

    print(f"[1/4] '{keyword}' 정보 수집 및 제목 생성 중...")
    turn1 = pipeline.run_turn1(keyword, reference, IMAGE_MODE, extra)
    if not turn1.get("titles"):
        raise RuntimeError("제목이 하나도 생성되지 않았습니다. 원본 응답:\n" + pipeline.current_raw)

    chosen_no = choose_title(pipeline, turn1, auto, title_index)
    chosen = next(t for t in turn1["titles"] if t["no"] == chosen_no)
    print(f"  선택된 제목({chosen_no}번): {chosen['text']}")

    print("[2/4] 본문 작성 및 팩트체크 중...")
    turn2 = pipeline.run_turn2(chosen_no)
    turn2 = finalize_body(pipeline, turn2, auto)
    print(f"  {turn2.get('factcheck_summary', '')} · 글자수: {turn2.get('char_count', '?')}")

    print("[3/4] 이미지 프롬프트 생성 및 이미지 제작 중...")
    turn3 = pipeline.run_turn3()
    turn3 = finalize_images(pipeline, turn3, auto)
    infographic_prompts = build_infographic_prompts(turn3)

    generated = []
    if infographic_prompts:
        if infographic_via_chatgpt:
            if not Path(CHATGPT_SESSION_FILE).exists():
                raise RuntimeError(
                    f"챗지피티 세션 파일({CHATGPT_SESSION_FILE})이 없습니다. "
                    "먼저 `python -m src.chatgpt_login`을 실행해서 로그인 세션을 저장하세요. "
                    "또는 infographic_via_chatgpt=False로 이미지 생성 API를 쓰세요."
                )
            print(f"  인포그래픽 썸네일 {len(infographic_prompts)}개는 챗지피티 웹채팅으로 제작합니다.")
            generated = generate_infographic_images_via_chatgpt(
                infographic_prompts, out_dir, CHATGPT_SESSION_FILE, headless=headless,
            )
        else:
            print(f"  인포그래픽 썸네일 {len(infographic_prompts)}개는 이미지 생성 API로 제작합니다.")
            generated = generate_images(infographic_prompts, out_dir, default_size="1024x1024")

    section_images = {}
    for img in generated:
        section_images.setdefault(img["subheading"], img["file_path"])

    print("[4/4] 네이버 블로그에 임시저장 중...")
    post_draft(
        blog_id=blog_id,
        title=turn2["title"],
        sections=turn2["sections"],
        tags=turn2["tags"],
        section_images=section_images,
        headless=headless,
        pause_before_save=pause_before_save,
    )

    return {
        "keyword": keyword,
        "title": turn2["title"],
        "char_count": turn2.get("char_count"),
        "image_count": len(generated),
    }
