"""
네이버 블로그 포스팅 자동화 — 단발 지시용 CLI.

대표(사용자)가 매니저에게 "이 키워드로 글 한 편 만들어서 임시저장까지 해줘"
라고 지시하는 창구다. 실제 업무 배정은 manager.py가 부서별로 처리한다
(리서치팀·기획팀·작성팀·디자인팀·발행팀 — README의 조직도 참고).

여러 편을 매일 자동으로 돌리고 싶으면 daily_batch.py를 쓴다.

기본 모드는 대화형이다 — 기획팀이 제목을 고르라고 물어보고, 작성팀·
디자인팀도 결과물을 보여주며 수정할지 물어본다. 번호/Enter 대신 자유
텍스트를 입력하면 재작업 지시로 그대로 전달된다. --auto를 주면 각 단계에서
묻지 않고 기본값(1번 제목, 수정 없음)으로 끝까지 자동 진행한다.

여러 네이버 계정(여러 블로그)을 운영한다면 --blog-id 대신 --account로
accounts.json에 등록된 계정 이름을 주면 blog_id·로그인 세션·글쓰기 지침
(prompt_path)을 그 계정 것으로 자동으로 고른다 — 계정마다 전혀 다른
블로그 지침(자동차/요리/IT 등)을 쓸 수 있다는 뜻이다(README의 "여러 계정
운영하기" 참고). --prompt-path를 직접 주면 계정 설정보다 그게 우선한다.

사용 전 준비:
  1) pip install -r requirements.txt && playwright install chromium
  2) .env.example을 .env로 복사하고 OPENAI_API_KEY 입력
  3) python -m departments.onboarding_publishing [--account 이름]  (최초 1회, 네이버 로그인 세션 저장)
  4) python -m departments.onboarding_design       (최초 1회, 인포그래픽을 챗지피티로 만들 경우)

예시:
  python main.py --keyword "쏘렌토 풀체인지 MQ5" --blog-id myblogid
  python main.py --keyword "..." --account car_blog
"""

import argparse

from manager import assign_single_post


def main():
    parser = argparse.ArgumentParser(description="네이버 블로그 포스팅 자동화 (단발 실행)")
    parser.add_argument("--keyword", required=True, help="키워드 또는 제목")
    parser.add_argument("--reference", default="", help="참고 본문(선택)")
    parser.add_argument("--extra", default="", help="처음부터 반영하고 싶은 추가 요청사항(선택)")
    parser.add_argument("--title-index", type=int, default=None,
                         help="선택할 제목 번호를 미리 고정한다(대화형 프롬프트 생략, --auto와 함께 쓸 때 유용)")
    parser.add_argument("--blog-id", default=None, help="네이버 블로그 ID (blog.naver.com/아이디). --account를 쓰면 생략 가능")
    parser.add_argument("--account", default=None, help="accounts.json에 등록된 계정 이름 (여러 계정을 운영할 때)")
    parser.add_argument("--prompt-path", default=None,
                         help="글쓰기 지침 파일 경로를 직접 지정한다. 생략하면 계정에 등록된 "
                              "지침 또는 .env의 기본 지침을 쓴다")
    parser.add_argument("--out-dir", default="output", help="생성된 이미지 저장 폴더")
    parser.add_argument("--headless", action="store_true", help="브라우저 창을 띄우지 않고 실행")
    parser.add_argument("--no-pause", action="store_true",
                         help="임시저장 전 확인 절차를 건너뛴다 (처음 실행할 때는 권장하지 않음)")
    parser.add_argument("--auto", action="store_true",
                         help="부서마다 묻지 않고 기본값으로 끝까지 자동 진행 (제목 1번 자동 선택, 수정 없음)")
    parser.add_argument("--infographic-via-chatgpt", action="store_true", default=True,
                         help="디자인팀이 인포그래픽을 챗지피티 웹채팅으로 만든다(기본값). "
                              "끄려면 --no-infographic-via-chatgpt")
    parser.add_argument("--no-infographic-via-chatgpt", dest="infographic_via_chatgpt",
                         action="store_false",
                         help="디자인팀이 인포그래픽을 이미지 생성 API로 만든다(챗지피티 자동화 안 씀)")
    args = parser.parse_args()

    if not args.blog_id and not args.account:
        parser.error("--blog-id 또는 --account 중 하나는 있어야 합니다.")

    result = assign_single_post(
        keyword=args.keyword,
        blog_id=args.blog_id,
        account=args.account,
        reference=args.reference,
        extra=args.extra,
        title_index=args.title_index,
        out_dir=args.out_dir,
        headless=args.headless,
        pause_before_save=not args.no_pause,
        auto=args.auto,
        infographic_via_chatgpt=args.infographic_via_chatgpt,
        prompt_path=args.prompt_path,
    )

    print(f"\n[매니저] 대표님께 보고: '{result['title']}' 임시저장 완료 "
          f"(이미지 {result['image_count']}장, 글자수 {result['char_count']}).")


if __name__ == "__main__":
    main()
