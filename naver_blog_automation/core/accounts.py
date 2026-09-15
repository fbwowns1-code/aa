"""
여러 네이버 블로그 계정을 운영할 때 쓰는 계정 정보 로더.

프로젝트 루트의 accounts.json(git에 커밋되지 않음 — .gitignore 처리됨)에
계정 이름별로 blog_id·naver_id·naver_pw를 저장해두면, --account 이름만으로
로그인 자동 입력·계정별 세션 파일 선택·blog_id 지정을 한 번에 처리할 수
있다. accounts.example.json을 복사해서 만든다.

accounts.json이 없거나 --account를 안 주면 기존처럼 --blog-id를 직접 주고
단일 기본 세션 파일(.env의 NAVER_SESSION_FILE)을 쓰는 방식이 그대로
동작한다 — 계정이 하나뿐이면 accounts.json을 만들 필요가 없다.

accounts.json 예시:
{
  "car_blog": {
    "blog_id": "myblogid1",
    "naver_id": "naver_login_id_1",
    "naver_pw": "naver_login_password_1"
  },
  "it_blog": {
    "blog_id": "myblogid2",
    "naver_id": "naver_login_id_2",
    "naver_pw": "naver_login_password_2"
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
    """계정 이름에 맞는 네이버 세션 파일 경로를 돌려준다.
    account에 naver_session_file이 명시돼 있으면 그걸 쓰고, 없으면
    naver_session_<계정이름>.json을 쓴다. 계정 이름 자체가 없으면(단일 계정
    운영) .env의 기본 NAVER_SESSION_FILE을 쓴다."""
    if account and account.get("naver_session_file"):
        return account["naver_session_file"]
    if name:
        return f"naver_session_{name}.json"
    from config import NAVER_SESSION_FILE
    return NAVER_SESSION_FILE


def chatgpt_session_file_for(name: Optional[str], account: Optional[dict] = None) -> str:
    """디자인팀(챗지피티) 세션은 기본적으로 계정과 무관하게 공용
    CHATGPT_SESSION_FILE 하나를 쓴다 — 보통 네이버 블로그는 여러 개지만
    챗지피티 계정은 하나만 써도 되기 때문이다. account에
    chatgpt_session_file이 따로 지정돼 있으면 그것을 우선한다."""
    if account and account.get("chatgpt_session_file"):
        return account["chatgpt_session_file"]
    from config import CHATGPT_SESSION_FILE
    return CHATGPT_SESSION_FILE
