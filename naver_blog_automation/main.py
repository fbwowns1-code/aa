"""
네이버 블로그 포스팅 자동화 파이프라인.

키워드 하나를 입력하면:
  1) OpenAI(GPT + 웹 검색)로 F목록·제목 45/50개 생성 (턴1)
  2) 제목 선택 → 본문 작성 → 팩트체크 → 최종본 (턴2)
  3) 이미지 프롬프트 생성 (턴3) → OpenAI 이미지 생성 API로 실제 이미지 파일 제작
  4) Playwright로 네이버 블로그 글쓰기 에디터에 제목/본문/이미지를 채우고 임시저장

기본 모드는 대화형이다 — 지침 원문에 있는 "제목 번호를 골라달라"와
"수정할 곳이 있으면 말해달라" 지점에서 실제로 멈춰서 입력을 기다리고,
번호/Enter 대신 자유 텍스트를 입력하면 그걸 수정 요청으로 모델에 보낸다.
--auto를 주면 각 단계에서 묻지 않고 기본값(1번 제목, 수정 없음)으로
끝까지 자동 진행한다.

사용 전 준비:
  1) pip install -r requirements.txt && playwright install chromium
  2) .env.example을 .env로 복사하고 OPENAI_API_KEY 입력
  3) python -m src.naver_login  (최초 1회, 네이버 로그인 세션 저장)

예시:
  python main.py --keyword "쏘렌토 풀체인지 MQ5" --blog-id myblogid
"""

import argparse
from pathlib import Path

from config import PROMPT_PATH, CHATGPT_SESSION_FILE
from src.pipeline import BlogPipeline
from src.image_gen import generate_images
from src.chatgpt_image import generate_infographic_images_via_chatgpt
from src.naver_poster import post_draft


def load_system_prompt() -> str:
    return Path(PROMPT_PATH).read_text(encoding="utf-8")


def build_realistic_prompts(turn3: dict, image_mode: str) -> list:
    if image_mode not in ("실사", "둘다"):
        return []
    common = turn3.get("common_style_realistic", "")
    return [
        {
            "subheading": item.get("subheading", ""),
            "prompt": f"{common}\n{item.get('prompt', '')}".strip(),
            "size": "1536x1024",
        }
        for item in turn3.get("realistic_prompts", [])
    ]


def build_infographic_prompts(turn3: dict, image_mode: str) -> list:
    if image_mode not in ("인포", "둘다"):
        return []
    common = turn3.get("common_style_infographic", "")
    prompts = []
    for item in turn3.get("infographic_prompts", []):
        subheading = "메인" if item.get("role") == "main" else item.get("subheading", "")
        prompts.append({
            "subheading": subheading,
            "prompt": f"{common}\n{item.get('prompt', '')}".strip(),
        })
    return prompts


def choose_title(pipeline: BlogPipeline, turn1: dict, auto: bool) -> int:
    titles = turn1["titles"]
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


def main():
    parser = argparse.ArgumentParser(description="네이버 블로그 포스팅 자동화")
    parser.add_argument("--keyword", required=True, help="키워드 또는 제목")
    parser.add_argument("--reference", default="", help="참고 본문(선택)")
    parser.add_argument("--extra", default="", help="처음부터 반영하고 싶은 추가 요청사항(선택)")
    parser.add_argument("--image-mode", default="둘다", choices=["실사", "인포", "둘다"])
    parser.add_argument("--title-index", type=int, default=None,
                         help="선택할 제목 번호를 미리 고정한다(대화형 프롬프트 생략, --auto와 함께 쓸 때 유용)")
    parser.add_argument("--blog-id", required=True, help="네이버 블로그 ID (blog.naver.com/아이디)")
    parser.add_argument("--out-dir", default="output", help="생성된 이미지 저장 폴더")
    parser.add_argument("--headless", action="store_true", help="브라우저 창을 띄우지 않고 실행")
    parser.add_argument("--no-pause", action="store_true",
                         help="임시저장 전 확인 절차를 건너뛴다 (처음 실행할 때는 권장하지 않음)")
    parser.add_argument("--auto", action="store_true",
                         help="턴마다 멈추지 않고 기본값으로 끝까지 자동 진행 (제목 1번 자동 선택, 수정 없음)")
    parser.add_argument("--infographic-via-chatgpt", action="store_true", default=True,
                         help="한글 인포그래픽 썸네일을 챗지피티 웹채팅으로 생성한다(기본값: 사용). "
                              "끄려면 --no-infographic-via-chatgpt")
    parser.add_argument("--no-infographic-via-chatgpt", dest="infographic_via_chatgpt",
                         action="store_false",
                         help="인포그래픽도 이미지 생성 API로 만든다(챗지피티 웹채팅 자동화 안 씀)")
    args = parser.parse_args()

    system_prompt = load_system_prompt()
    pipeline = BlogPipeline(system_prompt)

    print("[1/4] 정보 수집 및 제목 생성 중...")
    turn1 = pipeline.run_turn1(args.keyword, args.reference, args.image_mode, args.extra)
    if not turn1.get("titles"):
        raise RuntimeError("제목이 하나도 생성되지 않았습니다. 원본 응답을 확인하세요:\n" + pipeline.current_raw)

    if args.title_index:
        title_no = args.title_index
    else:
        title_no = choose_title(pipeline, turn1, args.auto)
    chosen = next(t for t in turn1["titles"] if t["no"] == title_no)
    print(f"  선택된 제목({title_no}번): {chosen['text']}")

    print("[2/4] 본문 작성 및 팩트체크 중...")
    turn2 = pipeline.run_turn2(title_no)
    turn2 = finalize_body(pipeline, turn2, args.auto)
    print(f"\n  {turn2.get('factcheck_summary', '')}")
    print(f"  글자수(공백 제외): {turn2.get('char_count', '?')}")

    print("\n[3/4] 이미지 프롬프트 생성 및 이미지 제작 중...")
    turn3 = pipeline.run_turn3()
    turn3 = finalize_images(pipeline, turn3, args.auto)

    realistic_prompts = build_realistic_prompts(turn3, args.image_mode)
    infographic_prompts = build_infographic_prompts(turn3, args.image_mode)

    generated = []
    if realistic_prompts:
        print(f"  실사 이미지 {len(realistic_prompts)}개는 이미지 생성 API로 제작합니다.")
        generated += generate_images(realistic_prompts, args.out_dir)

    if infographic_prompts:
        if args.infographic_via_chatgpt:
            if not Path(CHATGPT_SESSION_FILE).exists():
                raise RuntimeError(
                    f"챗지피티 세션 파일({CHATGPT_SESSION_FILE})이 없습니다. "
                    "먼저 `python -m src.chatgpt_login`을 실행해서 로그인 세션을 저장하세요. "
                    "또는 --no-infographic-via-chatgpt로 이미지 생성 API를 쓰세요."
                )
            print(f"  인포그래픽 썸네일 {len(infographic_prompts)}개는 챗지피티 웹채팅으로 제작합니다.")
            generated += generate_infographic_images_via_chatgpt(
                infographic_prompts, args.out_dir, CHATGPT_SESSION_FILE, headless=args.headless,
            )
        else:
            print(f"  인포그래픽 썸네일 {len(infographic_prompts)}개는 이미지 생성 API로 제작합니다.")
            generated += generate_images(infographic_prompts, args.out_dir, default_size="1024x1024")

    section_images = {}
    for img in generated:
        section_images.setdefault(img["subheading"], img["file_path"])

    print("\n[4/4] 네이버 블로그에 임시저장 중...")
    post_draft(
        blog_id=args.blog_id,
        title=turn2["title"],
        sections=turn2["sections"],
        tags=turn2["tags"],
        section_images=section_images,
        headless=args.headless,
        pause_before_save=not args.no_pause,
    )

    print("\n완료되었습니다.")


if __name__ == "__main__":
    main()
