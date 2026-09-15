"""
네이버 블로그 포스팅 자동화 파이프라인.

키워드 하나를 입력하면:
  1) OpenAI(GPT + 웹 검색)로 F목록·제목 45/50개 생성 (턴1)
  2) 제목 선택 → 본문 작성 → 팩트체크 → 최종본 (턴2)
  3) 이미지 프롬프트 생성 (턴3) → OpenAI 이미지 생성 API로 실제 이미지 파일 제작
  4) Playwright로 네이버 블로그 글쓰기 에디터에 제목/본문/이미지를 채우고 임시저장

사용 전 준비:
  1) pip install -r requirements.txt && playwright install chromium
  2) .env.example을 .env로 복사하고 OPENAI_API_KEY 입력
  3) python -m src.naver_login  (최초 1회, 네이버 로그인 세션 저장)

예시:
  python main.py --keyword "쏘렌토 풀체인지 MQ5" --blog-id myblogid
"""

import argparse
from pathlib import Path

from config import PROMPT_PATH
from src.pipeline import BlogPipeline
from src.image_gen import generate_images
from src.naver_poster import post_draft


def load_system_prompt() -> str:
    return Path(PROMPT_PATH).read_text(encoding="utf-8")


def build_image_prompts(turn3: dict, image_mode: str) -> list:
    prompts = []

    if image_mode in ("실사", "둘다"):
        common = turn3.get("common_style_realistic", "")
        for item in turn3.get("realistic_prompts", []):
            prompts.append({
                "subheading": item.get("subheading", ""),
                "prompt": f"{common}\n{item.get('prompt', '')}".strip(),
                "size": "1536x1024",
            })

    if image_mode in ("인포", "둘다"):
        common = turn3.get("common_style_infographic", "")
        for item in turn3.get("infographic_prompts", []):
            subheading = "메인" if item.get("role") == "main" else item.get("subheading", "")
            prompts.append({
                "subheading": subheading,
                "prompt": f"{common}\n{item.get('prompt', '')}".strip(),
                "size": item.get("size", "1024x1024"),
            })

    return prompts


def main():
    parser = argparse.ArgumentParser(description="네이버 블로그 포스팅 자동화")
    parser.add_argument("--keyword", required=True, help="키워드 또는 제목")
    parser.add_argument("--reference", default="", help="참고 본문(선택)")
    parser.add_argument("--image-mode", default="둘다", choices=["실사", "인포", "둘다"])
    parser.add_argument("--title-index", type=int, default=None,
                         help="선택할 제목 번호(미지정 시 SEO 최적화형 1번을 자동 선택)")
    parser.add_argument("--blog-id", required=True, help="네이버 블로그 ID (blog.naver.com/아이디)")
    parser.add_argument("--out-dir", default="output", help="생성된 이미지 저장 폴더")
    parser.add_argument("--headless", action="store_true", help="브라우저 창을 띄우지 않고 실행")
    parser.add_argument("--no-pause", action="store_true",
                         help="임시저장 전 확인 절차를 건너뛴다 (처음 실행할 때는 권장하지 않음)")
    args = parser.parse_args()

    system_prompt = load_system_prompt()
    pipeline = BlogPipeline(system_prompt)

    print("[1/4] 정보 수집 및 제목 생성 중...")
    turn1 = pipeline.run_turn1(args.keyword, args.reference, args.image_mode)
    titles = turn1["titles"]
    if not titles:
        raise RuntimeError("제목이 하나도 생성되지 않았습니다. 턴1 원본 응답을 확인하세요:\n" + pipeline.turn1_raw)

    title_no = args.title_index or titles[0]["no"]
    chosen = next((t for t in titles if t["no"] == title_no), None)
    if chosen is None:
        raise RuntimeError(f"제목 번호 {title_no}를 목록에서 찾지 못했습니다.")
    print(f"  선택된 제목({title_no}번): {chosen['text']}")

    print("[2/4] 본문 작성 및 팩트체크 중...")
    turn2 = pipeline.run_turn2(title_no)
    print(f"  {turn2.get('factcheck_summary', '')}")
    print(f"  글자수(공백 제외): {turn2.get('char_count', '?')}")

    print("[3/4] 이미지 프롬프트 생성 및 이미지 제작 중...")
    turn3 = pipeline.run_turn3()
    image_prompts = build_image_prompts(turn3, args.image_mode)
    generated = generate_images(image_prompts, args.out_dir)

    section_images = {}
    for img in generated:
        section_images.setdefault(img["subheading"], img["file_path"])

    print("[4/4] 네이버 블로그에 임시저장 중...")
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
