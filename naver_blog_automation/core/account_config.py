"""
계정별 동작 설정(configs/accounts/<계정>.yaml) 로더.

accounts.json에는 로그인 정보(아이디·비밀번호·blog_id) 같은 비밀만 두고,
글자수 범위·소제목 개수·제목 후보 구성·이미지 개수/제공자·발행 모드·
재시도 횟수 같은 "동작 설정"은 여기(커밋해도 되는 YAML)로 분리했다.
prompts/*.txt에는 순수한 AI 역할·작성 지침만 남기고, 이런 숫자 설정은
account_config를 통해 파이프라인이 프롬프트에 주입하거나 QUALITY_GATE
검증 기준으로 사용한다.

YAML이 없거나 일부 키가 비어 있어도 DEFAULTS로 채워지므로, 계정 하나만
쓰고 설정 파일을 안 만들어도 기존처럼 동작한다(하위 호환).
"""

import copy
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:  # pyyaml이 아직 설치 안 된 환경에서도 기본값으로 동작
    yaml = None

CONFIGS_DIR = Path("configs/accounts")

DEFAULTS = {
    "blog": {"id": "", "category": ""},
    "writing": {
        "min_chars": 1200,
        "max_chars": 1500,
        "headings": 5,
        "tone": "professional_editorial",
    },
    "title": {
        # candidate_count: 45(지침 원문 그대로) 또는 15(신규 숏리스트 모드).
        # 15로 설정하면 departments/planning.py가 5개 카테고리×3개 숏리스트
        # 생성 후 3라운드 AI 평가(15→3→1)를 탄다.
        "candidate_count": 45,
        "categories": ["curiosity", "comparison", "number", "information", "reversal"],
    },
    "images": {
        "count": 6,
        "ratio": "1:1",
        "provider": "openai_api",   # "openai_api" 또는 "chatgpt_web"(레거시)
    },
    "publishing": {"mode": "draft"},  # "draft"만 지원(실제 발행은 하지 않는다)
    "retry": {"max_attempts": 3},
    "quality_gate": {"pass_score": 85, "review_score": 70},
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_account_config(account_name: Optional[str]) -> dict:
    """DEFAULTS 위에 configs/accounts/<계정>.yaml을 덮어씌운 dict를 돌려준다.
    파일이 없거나 PyYAML이 설치 안 됐으면 DEFAULTS 그대로 돌려준다."""
    config = copy.deepcopy(DEFAULTS)
    if not account_name or yaml is None:
        return config
    path = CONFIGS_DIR / f"{account_name}.yaml"
    if not path.exists():
        return config
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[account_config] {path} 읽기 실패({e}) — 기본값을 씁니다.")
        return config
    return _deep_merge(config, data)
