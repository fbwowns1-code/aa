"""
네이버 블로그 포스팅 자동화 — 단발 실행용 CLI.

글 한 편을 처음부터 끝까지(제목→본문→인포그래픽 이미지→네이버 임시저장)
만든다. 여러 편을 매일 자동으로 돌리고 싶으면 daily_batch.py를 쓴다.

기본 모드는 대화형이다 — 지침 원문에 있는 "제목 번호를 골라달라"와
"수정할 곳이 있으면 말해달라" 지점에서 실제로 멈춰서 입력을 기다리고,
번호/Enter 대신 자유 텍스트를 입력하면 그걸 수정 요청으로 모델에 보낸다.
--auto를 주면 각 단계에서 묻지 않고 기본값(1번 제목, 수정 없음)으로
끝까지 자동 진행한다.

사용 전 준비:
  1) pip install -r requirements.txt && playwright install chromium
  2) .env.example을 .env로 복사하고 OPENAI_API_KEY 입력
  3) python -m src.naver_login  (최초 1회, 네이버 로그인 세션 저장)
  4) python -m src.chatgpt_login  (최초 1회, 인포그래픽을 챗지피티 웹채팅으로 만들 경우)

예시:
  python main.py --keyword "쏘렌토 풀체인지 MQ5" --blog-id myblogid
"""

import argparse

from src.post_runner import run_single_post


def main():
    parser = argparse.ArgumentParser(description="네이버 블로그 포스팅 자동화 (단발 실행)")
    parser.add_argument("--keyword", required=True, help="키워드 또는 제목")
    parser.add_argument("--reference", default="", help="참고 본문(선택)")
    parser.add_argument("--extra", default="", help="처음부터 반영하고 싶은 추가 요청사항(선택)")
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

    result = run_single_post(
        keyword=args.keyword,
        blog_id=args.blog_id,
        reference=args.reference,
        extra=args.extra,
        title_index=args.title_index,
        out_dir=args.out_dir,
        headless=args.headless,
        pause_before_save=not args.no_pause,
        auto=args.auto,
        infographic_via_chatgpt=args.infographic_via_chatgpt,
    )

    print(f"\n완료: {result['title']} (이미지 {result['image_count']}장, 글자수 {result['char_count']})")


if __name__ == "__main__":
    main()
