"""
여러 네이버 블로그 계정을 운영할 때 쓰는 계정 정보 로더.

프로젝트 루트의 accounts.json(git에 커밋되지 않음 — .gitignore 처리됨)에
계정 이름별로 blog_id·naver_id·naver_pw를 저장해두면, --account 이름만으로
로그인 자동 입력·계정별 세션 파일 선택·blog_id 지정을 한 번에 처리할 수
있다. accounts.example.json을 복사해서 만든다.

accounts.json이 없거나 --account를 안 주면 기존처럼 --blog-id를 직접 주고
단일 기본 세션 파일(.env의 NAVER_SESSION_FILE)을 쓰는 방식이 그대로
동작한다 — 계정이 하나뿐이면 accounts.json을 만들 필요가 없다.

계정마다 다른 글쓰기 지침(prompt_path)도 줄 수 있다 — prompt_path를 안
주면 .env의 기본 지침(PROMPT_PATH, 보통 prompts/system_prompt.txt, 지금은
IT/자동차 지침)을 쓰고, 다른 주제의 블로그 계정에는 그 계정만의 지침
파일을 따로 지정할 수 있다.

accounts.json 예시 (car_it_blog는 기본 지침을 그대로 쓰고, cooking_blog는
별도로 작성한 요리 블로그 지침을 쓰는 경우):
{
  "car_it_blog": {
    "blog_id": "myblogid1",
    "naver_id": "naver_login_id_1",
    "naver_pw": "naver_login_password_1"
  },
  "cooking_blog": {
    "blog_id": "myblogid2",
    "naver_id": "naver_login_id_2",
    "naver_pw": "naver_login_password_2",
    "prompt_path": "prompts/cooking_blog.txt"
  }
}

주의: naver_id/naver_pw는 로그인 자동 입력(온보딩 스크립트)에만 쓰이고
로컬 브라우저 안에서만 쓰인다 — 이 코드가 다른 곳으로 전송하지 않는다.
그래도 평문으로 저장되는 파일이므로 accounts.json을 git에 올리지 말고
파일 권한을 본인만 읽을 수 있게 관리하는 것을 권장한다.
"""

import json
from pathlib import Path
from typing import Optional

ACCOUNTS_FILE = "accounts.json"
SECRETS_DIR = Path("secrets")


def _migrate_legacy_session_file(path: str) -> str:
    """세션 파일을 secrets/ 밑에서만 관리하도록 강제한다. 예전 버전이
    프로젝트 루트에 바로 저장했던 파일이 남아 있으면 자동으로 옮긴다."""
    target = Path(path)
    if target.exists():
        return path
    legacy = Path(target.name)
    if legacy.exists() and legacy.resolve() != target.resolve():
        target.parent.mkdir(parents=True, exist_ok=True)
        legacy.rename(target)
        print(f"[core.accounts] 기존 세션 파일을 secrets/로 옮겼습니다: {legacy} → {target}")
    return path


def load_accounts(path: str = ACCOUNTS_FILE) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def get_account(name: str, path: str = ACCOUNTS_FILE) -> dict:
    accounts = load_accounts(path)
    if name not in accounts:
        raise KeyError(
            f"{path}에 '{name}' 계정이 없습니다. accounts.example.json을 참고해서 "
            f"{path}를 만들거나 계정 이름을 확인해주세요. 등록된 계정: {list(accounts.keys())}"
        )
    return accounts[name]


def naver_session_file_for(name: Optional[str], account: Optional[dict] = None) -> str:
    """계정 이름에 맞는 네이버 세션 파일 경로를 돌려준다. 세션 파일은
    민감 정보(로그인 쿠키)이므로 항상 secrets/ 아래에서만 관리한다.
    account에 naver_session_file이 명시돼 있으면 그걸 쓰고, 없으면
    secrets/naver_session_<계정이름>.json을 쓴다. 계정 이름 자체가
    없으면(단일 계정 운영) .env의 기본 NAVER_SESSION_FILE을 쓴다."""
    if account and account.get("naver_session_file"):
        path = account["naver_session_file"]
    elif name:
        path = str(SECRETS_DIR / f"naver_session_{name}.json")
    else:
        from config import NAVER_SESSION_FILE
        path = NAVER_SESSION_FILE
    return _migrate_legacy_session_file(path)


def chatgpt_session_file_for(name: Optional[str], account: Optional[dict] = None) -> str:
    """디자인팀(챗지피티) 세션은 기본적으로 계정과 무관하게 공용
    CHATGPT_SESSION_FILE 하나를 쓴다 — 보통 네이버 블로그는 여러 개지만
    챗지피티 계정은 하나만 써도 되기 때문이다. account에
    chatgpt_session_file이 따로 지정돼 있으면 그것을 우선한다. 세션 파일은
    항상 secrets/ 아래에서만 관리한다."""
    if account and account.get("chatgpt_session_file"):
        path = account["chatgpt_session_file"]
    else:
        from config import CHATGPT_SESSION_FILE
        path = CHATGPT_SESSION_FILE
    return _migrate_legacy_session_file(path)


def prompt_path_for(account: Optional[dict] = None) -> Optional[str]:
    """계정에 등록된 지침(프롬프트) 파일 경로를 돌려준다. 계정에
    prompt_path가 없거나 계정 자체가 없으면 None을 돌려주고, 호출 쪽에서
    기본 지침(.env의 PROMPT_PATH)으로 대체한다."""
    if account and account.get("prompt_path"):
        return account["prompt_path"]
    return None
