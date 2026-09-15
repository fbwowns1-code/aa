# 네이버 블로그 포스팅 자동화 (1인 회사 구조)

키워드 하나, 또는 하루치 뉴스 조사만 지시하면 나머지는 "회사"가 부서별로 나눠서 처리한다. 대표(사용자)는 `main.py`/`daily_batch.py`(터미널) 또는 `webapp/app.py`(브라우저 대시보드, 아래 "웹 대시보드로 실행하기" 참고)로 업무만 지시하면 된다.

## 조직도

```
대표(사용자)
  │  main.py(단발 지시) / daily_batch.py(하루 배치 지시)
  ▼
총괄 매니저 — manager.py
  │  부서에 순서대로 업무를 배정하고 보고를 취합한다
  ▼
┌────────────┬────────────┬────────────┬────────────┬────────────┐
│  리서치팀   │   기획팀    │   작성팀    │  디자인팀   │   발행팀    │
│ research.py│ planning.py│ writing.py │  design.py │publishing.py│
├────────────┼────────────┼────────────┼────────────┼────────────┤
│오늘의 자동차│제목 후보    │본문 작성 +  │인포그래픽   │네이버 블로그│
│업계 뉴스 조사│45/50개 생성,│팩트체크,    │썸네일 프롬  │에 채워 넣고 │
│→ 글감 8개  │번호 확정    │최종본 확정  │프트→실제   │임시저장     │
│선정        │            │            │이미지 제작  │            │
└────────────┴────────────┴────────────┴────────────┴────────────┘
     (departments/ 폴더)
```

- **리서치팀·기획팀·작성팀·디자인팀**은 `core/pipeline.py`(하나의 OpenAI 대화 맥락)를 순서대로 이어받아 일한다 — 매니저가 부서마다 새 대화를 여는 게 아니라, 같은 스레드를 넘겨가며 F목록·본문·이미지 시안을 공유한다.
- **디자인팀·발행팀**은 브라우저로 로그인이 필요한 부서라서, 각자 "출근 등록(온보딩)" 스크립트가 있다(`departments/onboarding_design.py`, `departments/onboarding_publishing.py`).
- `prompts/system_prompt.txt`는 사용자가 Claude 프로젝트에 저장해둔 "IT/자동차 네이버 블로그 홈판 프롬프트 v7.0" 지침 원문 그대로이며, 맨 아래에 자동화 파싱용 JSON을 추가로 뽑아내는 "자동화 어댑터" 섹션만 덧붙였다. 지침 자체(턴 구성·제목 규칙·본문 규칙·팩트체크·이미지 규칙)는 전혀 바꾸지 않았다. 기획팀·작성팀·디자인팀이 이 지침 하나를 나눠서 담당한다(턴1/턴2/턴3).

## 이미지에 대한 중요한 결정

본문에 넣을 이미지는 **웹에서 이미지를 가져와 가공("이미지 세탁")하는 방식은 구현하지 않았다.** 타인의 저작물을 역검색·저작권 탐지를 피해 재사용하는 것은 저작권 침해 회피 수단이기 때문이다.

디자인팀은 실사 이미지는 다루지 않고 **한글 인포그래픽 썸네일만** 만든다. 기본값은 **OpenAI 이미지 생성 API(`gpt-image-1`)**다(`core/image_gen.py`). `--infographic-via-chatgpt`를 주거나 계정 설정(`configs/accounts/<계정>.yaml`의 `images.provider: chatgpt_web`)으로 명시하면 대신 **챗지피티 웹채팅(chatgpt.com) 자동화**(레거시, `core/legacy/chatgpt_image.py`)로 만든다 — 인포그래픽 프롬프트를 실제로 챗지피티 채팅창에 붙여넣고, 생성된 이미지를 다운로드해서 저장하는 방식이다.

**챗지피티 웹채팅 자동화에 대한 주의**: OpenAI 이용약관은 챗지피티의 사람용 웹 제품에 대한 프로그램적/자동화 접근을 금지하고 있다. 이 방식은 API가 아니라 브라우저로 채팅 화면을 흉내 내는 것이므로, 계정이 제재될 수 있는 위험을 감안하고 쓰는 기능이다. 기본값(OpenAI 이미지 생성 API)을 쓰면 이 위험이 아예 없다 — `--infographic-via-chatgpt`를 명시적으로 켰을 때만 해당하는 주의사항이다.

유명인의 실제 얼굴을 그대로 그리는 프롬프트는 (API든 챗지피티든) 정책상 거부될 수 있다. 실패한 이미지는 건너뛰고 나머지는 계속 진행하도록 되어 있으니, 필요하면 지침의 유명인 관련 장치(1·20번) 사용을 줄이는 것을 권장한다.

## 설치

```bash
cd naver_blog_automation
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
# .env를 열어 OPENAI_API_KEY를 채운다
```

## 최초 1회: 부서별 출근 등록(온보딩)

**발행팀** — 네이버 블로그 로그인 세션 저장. 계정 비밀번호는 코드에 저장하지 않는다.

```bash
python -m departments.onboarding_publishing
```

브라우저가 뜨면 직접 로그인 → 터미널로 돌아와 Enter → `secrets/naver_session.json`(계정별로는 `secrets/naver_session_<계정이름>.json`) 저장 완료. 네이버 세션은 일정 기간 후 만료되므로, 자동화가 로그인 페이지에서 멈추면 이 스크립트를 다시 실행한다.

**디자인팀** — 인포그래픽을 챗지피티 웹채팅(레거시)으로 만들 경우에만 필요. 기본값(OpenAI 이미지 생성 API)을 쓴다면 생략 가능.

```bash
python -m departments.onboarding_design
```

브라우저가 뜨면 챗지피티에 직접 로그인 → 터미널로 돌아와 Enter → `chatgpt_session.json` 저장 완료. 이 계정은 GPT API 키와는 별개로, 실제 챗지피티 로그인 계정(무료든 Plus든)이어야 한다.

## 여러 네이버 계정(블로그) 운영하기

블로그를 하나만 운영한다면 이 섹션은 건너뛰어도 된다(`--blog-id` + 기본 세션 파일로 그대로 동작).

여러 계정을 운영한다면 `accounts.example.json`을 복사해서 `accounts.json`을 만든다(이 파일은 `.gitignore`에 들어 있어 커밋되지 않는다).

```bash
cp accounts.example.json accounts.json
```

```json
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
```

그리고 계정별로 출근 등록을 한다 — `naver_id`/`naver_pw`를 적어두면 로그인 페이지에 아이디·비밀번호를 자동으로 입력해준다(보안문자·2단계 인증은 직접 처리하고 로그인 버튼도 직접 눌러야 한다. 자동 제출은 하지 않는다):

```bash
python -m departments.onboarding_publishing --account car_it_blog
python -m departments.onboarding_publishing --account cooking_blog
```

각 계정의 세션은 `naver_session_<계정이름>.json`으로 따로 저장된다. 이후 모든 명령에서 `--blog-id` 대신 `--account`를 쓰면 된다:

```bash
python main.py --keyword "..." --account car_it_blog
python daily_batch.py --account cooking_blog
```

`daily_batch.py`를 계정별로 따로 실행해도 서로 덮어쓰지 않는다 — 리포트는 `reports/<계정이름>/`, 진행 상태·이미지는 `output/<날짜>/<계정이름>/`에 나뉘어 저장된다. 챗지피티(디자인팀) 로그인은 보통 계정과 무관하게 공용 세션 하나(`chatgpt_session.json`)를 여러 네이버 계정이 같이 써도 되며, 꼭 따로 쓰고 싶다면 `accounts.json`의 해당 계정에 `"chatgpt_session_file": "chatgpt_session_car_it_blog.json"`처럼 직접 지정하면 된다.

### 계정마다 다른 글쓰기 지침 쓰기

위 예시처럼 `accounts.json`의 계정에 `prompt_path`를 지정하면, 그 계정으로 글을 쓸 때 기획팀·작성팀·디자인팀이 `prompts/system_prompt.txt`(기본 IT/자동차 지침) 대신 그 파일을 쓴다. `prompt_path`를 안 주면 기본 지침을 그대로 쓴다.

다른 주제의 블로그(요리, 여행, 재테크 등)를 새 계정으로 추가하려면:

1. `prompts/system_prompt.txt`를 복사해서 새 파일(예: `prompts/cooking_blog.txt`)을 만든다.
2. 턴1/턴2/턴3 구조, 맨 아래 "자동화 어댑터" 섹션(`---AUTOMATION-JSON---` 블록)은 그대로 두고, 그 위의 내용(말투·카테고리·금지어·제목 규칙 등)만 해당 주제에 맞게 다시 쓴다 — 자동화 어댑터 섹션을 지우거나 JSON 형식을 바꾸면 매니저가 결과를 파싱하지 못한다.
3. `accounts.json`의 해당 계정에 `"prompt_path": "prompts/cooking_blog.txt"`를 적어준다.

`--prompt-path`를 명령줄에서 직접 주면(`main.py`/`daily_batch.py`) 계정에 등록된 지침보다 그게 우선한다 — 테스트용으로 임시 지침을 써볼 때 유용하다.

**보안 참고**: `naver_id`/`naver_pw`는 로그인 페이지에 자동으로 타이핑해주는 용도로만 쓰이고 이 코드가 다른 곳으로 전송하지 않는다. 그래도 평문으로 저장되는 파일이니 `accounts.json`을 외부에 공유하거나 git에 올리지 않도록 주의한다.

## 웹 대시보드로 실행하기 (터미널 대신 브라우저로)

계정 등록 → 지침 작성/선택 → 실행을, 매번 명령줄 옵션을 치는 대신 브라우저 화면 하나에서 누르고 싶다면 이 방법을 쓴다.

```bash
python webapp/app.py
```

`naver_blog_automation` 폴더 **안에서** 실행해야 한다(`webapp` 폴더로 들어가서 실행하면 `prompts/`, `accounts.json`, `output/` 등 상대 경로가 어긋난다). 실행 후 브라우저에서 `http://localhost:5000` 을 연다.

화면은 위에서부터 이렇게 구성된다:

- **오늘 진행 현황 패널** (맨 위, 항상 보임): 오늘 전체/완료/진행중/실패/검토 필요 건수, 스케줄러 정상/OFFLINE 배지, 계정별로 묶인 게시물 목록과 게시물마다 9단계(리서치~네이버저장) 상태가 표로 보인다. `automation.db`를 2초마다 다시 읽어서 자동 갱신되고, 실패/검토 필요 단계에는 "이 단계부터 재시도" 버튼이 있다(터미널을 쓰지 않고도 그 자리에서 재시도할 수 있다 — `NAVER_DRAFT` 재시도는 중복 저장 확인 팝업이 뜬다).
- **1. 계정** 섹션: 등록된 계정을 고르는 드롭다운. "계정 추가/수정"을 펼치면 계정 이름·블로그 ID·네이버 로그인 아이디·비밀번호를 입력해 저장할 수 있다(`accounts.json`에 반영됨). 비밀번호는 화면에 다시 보여주지 않는다. **저장만으로 로그인이 되는 건 아니다** — 저장 후 터미널에서 `python -m departments.onboarding_publishing --account 계정이름`을 한 번 실행해서 실제 로그인 세션을 만들어야 한다(보안문자·2단계 인증은 그때 직접 처리).
- **2. 지침** 섹션: 저장된 지침 파일을 드롭다운에서 골라 현재 선택된 계정에 연결하는 버튼이 있고, "지침 새로 쓰기/수정하기"를 펼치면 파일 이름과 내용을 직접 입력해서 새 지침 파일을 만들거나 기존 파일을 고쳐 저장할 수 있다. 드롭다운에서 파일을 고르면 내용이 자동으로 불러와진다.
- **3. 실행** 섹션: 키워드(+참고 본문)를 입력해 **단발 실행**하거나, 개수를 정해 **하루 배치 실행**(뉴스 조사부터)을 누른다. 둘 다 현재 선택된 계정으로 실행된다.

**중요한 제약**: 이 화면에서 누른 실행은 항상 **완전 자동 모드**로 돈다 — 기획팀이 "3. 실행" 섹션에서 고른 제목 채택 방식대로 자동으로 제목을 채택하고, 중간에 "이 부분 고쳐줘" 같은 대화형 수정은 할 수 없다(웹 버튼은 터미널 입력을 받을 방법이 없기 때문이다). 턴마다 결과를 보면서 대화로 고치고 싶으면 터미널에서 `python main.py`를 직접 실행한다(위 "지시 방법 1" 참고) — 그 경우에도 진행 현황 패널은 같은 `automation.db`를 보므로, 터미널로 돌리는 동안 웹 화면을 열어서 진행 상황만 구경할 수도 있다. `scheduler.py`로 야간 배치를 돌리는 동안에도 마찬가지다(스케줄러 하트비트도 같이 보인다).

**보안 참고**: 이 대시보드는 로그인 화면이 따로 없고(`127.0.0.1`에서만 접속 가능하도록 기본 설정돼 있다), 네이버 비밀번호를 실제로 로그인 폼에 입력하는 기능이 있다. 같은 네트워크의 다른 사람이 접근하지 못하게 `host`를 바꾸거나 포트를 외부에 노출하지 말 것 — `webapp/app.py` 맨 아래 `app.run(host="127.0.0.1", ...)`을 그대로 두는 것을 권장한다.

## 지시 방법 1: 단발 지시 (main.py)

```bash
python main.py --keyword "쏘렌토 풀체인지 MQ5" --blog-id 내블로그아이디
```

기본 모드는 **대화형**이다. 기획팀이 "제목 번호를 골라달라"고 묻고, 작성팀·디자인팀도 결과물을 보여주며 "수정할 곳이 있으면 말해달라"고 묻는다. 이때:

- **숫자**를 입력하면 그 번호로 확정하고 다음 부서로 넘어간다.
- **문장**을 입력하면 해당 부서에 대한 재작업 지시로 그대로 전달되고, 같은 턴을 다시 받아서 또 보여준다 — 예를 들어 기획팀에게 `"오너 감정형 위주로 5개만 다시"`, 작성팀에게 `"3번째 소제목에 연비 얘기 추가해줘"`, 디자인팀에게 `"메인 이미지 배경을 도심으로"` 같은 식으로 몇 번이든 반복해서 지시할 수 있다.
- 아무것도 입력하지 않고 그냥 Enter를 누르면 작성팀/디자인팀 단계는 "수정 없음"으로 다음 부서로 넘어간다(기획팀 단계는 번호를 입력해야 넘어간다).

주요 옵션:

| 옵션 | 설명 |
|---|---|
| `--keyword` | 키워드 또는 완성된 제목, 참고 본문이 있으면 `--reference`와 함께 |
| `--reference` | 참고 본문(기사·타 블로그 등, 팩트 소스로만 사용됨) |
| `--extra` | 시작할 때부터 반영하고 싶은 요청사항(예: `"경쟁사 A 모델은 언급하지 말아줘"`) |
| `--title-index` | 제목 번호를 미리 고정해서 대화형 프롬프트 자체를 생략한다 |
| `--blog-id` | `blog.naver.com/이 부분`. 여러 계정을 운영한다면 이 대신 `--account` |
| `--account` | `accounts.json`에 등록된 계정 이름 (여러 계정 운영 시) |
| `--prompt-path` | 글쓰기 지침 파일을 직접 지정(생략 시 계정의 지침 또는 기본 지침) |
| `--headless` | 브라우저 창 없이 실행 (처음에는 끄고 눈으로 확인하는 것을 권장) |
| `--no-pause` | 임시저장 직전 확인 절차 생략 (처음 실행할 때는 권장하지 않음) |
| `--auto` | 부서마다 묻지 않고 기본값(제목은 `--title-strategy`대로 자동 채택, 수정 없음)으로 끝까지 자동 진행 |
| `--title-strategy` | `--auto`일 때 제목 채택 방식. `ai_click_appeal`(기본값): 후킹/클릭 유도형(6~10번)+궁금증 폭발형(21~25번) 후보를 놓고 웹에서 반응 좋은 실제 제목 사례를 찾아본 뒤 AI가 직접 판단 / `hook_curiosity_mix`: 같은 후보 중 가장 짧은 제목 / `first`: SEO 최적화형 1번 |
| `--no-infographic-via-chatgpt` | 디자인팀이 인포그래픽을 챗지피티 대신 이미지 생성 API로 만든다 |

기본값(`--no-pause` 미지정)은 발행팀이 에디터에 내용을 다 채운 뒤, **임시저장을 누르기 전에 터미널에서 Enter 입력을 기다린다.** 브라우저 창에서 실제로 제목·본문·이미지가 잘 들어갔는지 눈으로 확인한 뒤 Enter를 눌러야 저장된다. 몇 번 돌려서 안정적으로 동작하는 걸 확인한 뒤에 `--auto --headless --no-pause`로 완전 무인 자동화하는 걸 권장한다.

`main.py`는 창구일 뿐이고, 실제 부서 배정은 `manager.py`의 `assign_single_post()`가 한다. 아래 하루 배치도 이 함수를 그대로 재사용한다.

## 지시 방법 2: 하루 배치 지시 (daily_batch.py)

매일 저녁 국내 자동차 업계(현대차·기아·제네시스·KG모빌리티·르노코리아·수입차 브랜드 등)의 화제 소식을 리서치팀이 조사하고, 그중 8개를 골라 각 부서가 순서대로 처리해서 임시저장까지 하는 배치다.

```bash
python daily_batch.py --blog-id 내블로그아이디
```

동작 순서 (`manager.assign_daily_batch()`):

1. **리서치팀**(`departments/research.py`)이 GPT + 웹 검색으로 오늘/최근 뉴스를 조사해 `reports/YYYY-MM-DD.json`(구조화 데이터)과 `reports/YYYY-MM-DD.md`(발행일·핵심 내용·출처 링크가 정리된 리포트)를 만든다. 브랜드가 겹치지 않도록 8개를 골라 각 항목에 `keyword`(제목 후보)와 `reference`(요약+출처)를 붙인다.
2. 그 8개를 하나씩 매니저가 `assign_single_post(keyword=..., reference=...)`로 나머지 부서(기획→작성→디자인→발행)에 넘긴다. `keyword`+`reference` 조합은 지침 원문의 "제목+본문 참고형" 입력과 같은 방식이다 — reference는 팩트 소스로만 쓰이고, 본문 자체는 작성팀이 F목록·팩트체크를 그대로 다시 거친다.
3. 배치는 **완전 무인**으로 돈다(기획팀 1번 제목 자동 채택, 재작업 지시 없음, 저장 전 확인 대기 없음) — 밤에 사람이 붙어있지 않기 때문이다. 결과는 전부 **임시저장**이며 실제 발행은 하지 않으니, 다음날 아침에 직접 검토 후 발행한다.
4. 진행 상황은 게시물 1건마다 9단계(리서치~네이버저장) 단위로 `automation.db`(SQLite)에 즉시 기록된다. 자세한 실패 처리·재개 동작은 아래 "실패하면 멈추고 대기하기" 참고, 실시간으로 보려면 웹 대시보드(`python webapp/app.py`)를 연다.

주요 옵션:

| 옵션 | 설명 |
|---|---|
| `--blog-id` / `--account` | 단발 지시와 동일 — 여러 계정을 운영한다면 `--account` |
| `--count` | 오늘 만들 포스트 개수 (기본 8개) |
| `--reports-dir` | 뉴스 리포트 저장 폴더 (기본 `reports`) |
| `--show-browser` | 브라우저 창을 띄워서 확인 (테스트용, 기본은 headless) |
| `--infographic-via-chatgpt` | 디자인팀이 인포그래픽을 챗지피티 웹채팅(레거시)으로 만든다(기본은 이미지 생성 API) |
| `--force-rerun` | 중단된 배치를 무시하고 오늘 분량을 새 리서치부터 처음부터 다시 돈다 |
| `--force-step` | 이어서 진행되는 첫 건에 한해 이미 성공한 단계도 강제로 다시 실행(예: `IMAGE`, `NAVER_DRAFT`) |
| `--max-retries` / `--retry-wait-seconds` / `--consecutive-failure-limit` | **더 이상 쓰이지 않음** — 아래 "실패하면 멈추고 대기하기"의 오류 유형별 자동 재시도로 대체됐다. 옛 명령을 그대로 써도 오류는 안 나지만 값은 무시된다 |

**사전 준비**: 위의 "부서별 출근 등록"(발행팀, 그리고 챗지피티 레거시 이미지 경로를 쓴다면 디자인팀도)을 미리 마쳐둬야 한다. 야간 무인 실행 중에는 로그인 화면이 떠도 아무도 로그인해줄 수 없으므로, 세션이 만료되면 그날 배치가 멈춘다(아래 참고) — 정기적으로(예: 2주에 한 번) 온보딩 스크립트를 다시 돌려서 세션을 갱신하는 걸 권장한다.

### 실패하면 멈추고 대기하기

야간 무인 실행 중 예상치 못한 변수(네트워크 순단, API 일시 오류, 로그인 세션 만료, 네이버 UI 구조 변경 등)로 한 건이 실패할 수 있다. `core/job_manager.py`는 이렇게 처리한다.

1. **단계별 자동 재시도**: 오류를 유형별로 분류해서(`core/retry_policy.py`) 네트워크 오류·API 일시 장애처럼 재시도하면 회복될 오류는 그 단계(리서치/기획/작성/이미지/네이버저장 등)만 지수 백오프(1차 5초 → 2차 15초 → 3차 45초, 계정 설정의 `retry.max_attempts`로 조절 가능)로 자동 재시도한다. 로그인 세션 만료·API 키 오류처럼 "재시도해도 똑같이 막힐" 오류는 재시도하지 않고 바로 다음 단계로 넘어간다.
2. **한 건 실패는 배치를 막지 않는다**: 위 재시도까지 다 써도 특정 게시물 1건이 실패하면, 그 게시물만 `FAILED`로 남기고 **나머지 게시물은 계속 진행**한다(예: "전체 8건 / 완료 6건 / 실패 1건 / 검토 필요 1건").
3. **배치 전체를 멈추는 경우**: 로그인 세션 만료·네이버 UI 구조 변경처럼 "다음 게시물에서도 똑같이 막힐" 시스템적 오류는 바로 그 시점에 **배치 전체를 멈춘다** — 안 그러면 남은 게시물 전부가 똑같은 이유로 헛되이 실패하기 때문이다. 알림을 설정해뒀다면(위 "무인 운영을 위한 3가지 추가 설정" 참고) 이때 Slack/이메일로도 알려준다.
4. **이어서 진행(재개)**: 문제를 해결한 뒤(대개 온보딩 스크립트로 재로그인, 또는 `core/naver_selectors.py` 갱신) 같은 명령(`python daily_batch.py --blog-id ...`)을 다시 실행하면, 새로 리서치를 돌리지 않고 **멈췄던 시점부터**(게시물 단위가 아니라 그 게시물이 멈춘 단계부터) 이어서 진행한다. 오늘 배치가 이미 끝까지 완료돼 있으면 아무 일도 하지 않고 그대로 기존 결과를 보여준다. 처음부터 다시 돌리고 싶으면 `--force-rerun`을 준다.

웹 대시보드(`python webapp/app.py`)를 열면 오늘 진행 상황을 실시간으로 확인할 수 있다 — 전체/완료/진행중/실패/검토필요 건수, 계정별·게시물별 9단계 상태, 스케줄러 하트비트(정상/OFFLINE), 단계별 재시도 버튼까지 한 화면에서 본다.

### 매일 자동 실행되게 만들기

두 가지 방법이 있다. 컴퓨터를 24시간 켜두지 않고 가끔만 켠다면 OS 스케줄러가 편하고, 컴퓨터를 계속 켜둔다면 `scheduler.py`를 실행해두는 쪽이 설정이 더 간단하다.

**방법 A. 상주 스케줄러 (`scheduler.py`)** — OS 설정이 필요 없다. 이 스크립트를 한 번 실행해서 계속 켜두면, 매일 지정된 시각(기본 21:30)에 자동으로 `manager.assign_daily_batch()`를 호출한다.

```bash
# 터미널에 계속 띄워두거나, Linux/Mac이면 nohup으로 백그라운드 실행
nohup python scheduler.py --blog-id 내블로그아이디 > logs/scheduler.log 2>&1 &

# 여러 계정을 운영한다면 --account를 여러 번 줄 수 있다 — 매일 같은 시각에
# 계정마다 순서대로 한 번씩 배치를 돌린다
nohup python scheduler.py --account car_blog --account it_blog > logs/scheduler.log 2>&1 &
```

컴퓨터를 끄거나 이 프로세스가 죽으면 그날 배치는 건너뛰게 된다는 점을 기억해야 한다. 배치가 중단(`paused`)된 채로 끝나도 스케줄러 자체는 죽지 않고 다음날 같은 시각에 다시 시도한다 — 단, 원인(예: 로그인 세션 만료)이 해결되지 않으면 또 같은 이유로 멈출 수 있으니 로그를 가끔 확인한다.

**방법 B. OS 스케줄러 (crontab / 작업 스케줄러)** — `scheduler.py`를 계속 켜둘 필요 없이, OS가 매일 정해진 시각에 `daily_batch.py`를 한 번씩 실행해준다.

Linux/Mac (crontab):

```bash
crontab -e
```

다음 줄을 추가한다(경로는 실제 설치 위치와 python 실행 파일 경로로 바꾼다):

```
30 21 * * * cd /home/user/aa/naver_blog_automation && /usr/bin/python3 daily_batch.py --blog-id 내블로그아이디 >> logs/daily.log 2>&1
```

(로그를 남기려면 `mkdir -p logs`로 폴더를 미리 만들어둔다.)

Windows (작업 스케줄러):

1. "작업 스케줄러" 실행 → "기본 작업 만들기"
2. 트리거: 매일, 오후 9:30
3. 동작: 프로그램 시작 → 프로그램/스크립트에 `python.exe` 경로, 인수에 `daily_batch.py --blog-id 내블로그아이디`, 시작 위치에 `naver_blog_automation` 폴더 경로 입력

두 방법 모두 컴퓨터가 그 시각에 켜져 있어야 동작한다는 점, 그리고 로그인 세션이 만료되지 않아야 한다는 점을 기억해야 한다. 배치가 중단된 채 끝났다면 로그(`logs/daily.log`, `logs/scheduler.log`, `logs/automation_YYYYMMDD.log`)나 웹 대시보드(`python webapp/app.py`)의 게시물별 단계 상태로 원인을 확인하고, 해결한 뒤에는 아무것도 더 할 필요 없이 다음 예정 실행(또는 수동 재실행)에서 automation.db에 남은 마지막 성공 단계부터 자동으로 이어서 진행된다.

### 무인 운영을 위한 3가지 추가 설정

"컴퓨터 전원만 켜두면" 알아서 매일 돌아가게 하려면, 위의 스케줄 설정과 별개로 아래 세 가지가 더 필요하다. 하나라도 안 돼 있으면 재부팅 후 스케줄러가 안 켜지거나, 컴퓨터가 잠들어서 멈추거나, 배치가 중단된 걸 며칠씩 모르고 지나갈 수 있다.

**1) 재부팅해도 스케줄러가 자동으로 다시 켜지게 하기** (방법 A: 상주 스케줄러를 쓸 때만 해당 — 방법 B인 crontab/작업 스케줄러는 OS가 직접 관리하므로 이 항목이 필요 없다)

`deploy/` 폴더에 OS별 등록 템플릿을 준비해뒀다. 안의 `<여기를-바꾸세요>` 부분을 실제 경로로 바꿔서 등록한다.

- **Linux (systemd)**: `deploy/systemd/naver-blog-scheduler.service` — `sudo cp`로 `/etc/systemd/system/`에 넣고 `sudo systemctl enable --now naver-blog-scheduler`. `Restart=on-failure`가 걸려 있어 프로세스가 죽어도 30초 뒤 자동 재시작되고, `enable`로 재부팅 후에도 자동 시작된다.
- **macOS (launchd)**: `deploy/launchd/com.naverblog.scheduler.plist` — `~/Library/LaunchAgents/`에 복사하고 `launchctl load`. `KeepAlive`로 크래시 시 재시작, `RunAtLoad`로 로그인 시 자동 시작된다.
- **Windows (작업 스케줄러)**: `deploy/windows/register_scheduler_task.ps1`을 관리자 권한 PowerShell에서 실행하면 "재부팅 시 시작 + 실패 시 1분 뒤 재시작" 작업이 등록된다.

**2) 절전 모드(잠자기) 끄기** — 컴퓨터가 잠들면 스케줄러 프로세스도 같이 멈춘다.

- **Linux**: 위 systemd 서비스 파일에 `systemd-inhibit --what=sleep:idle:shutdown`이 이미 포함돼 있어 서비스가 실행되는 동안은 자동으로 절전이 안 걸린다.
- **macOS**: 위 launchd plist가 `caffeinate -dims`로 감싸서 실행하므로 별도 설정이 필요 없다.
- **Windows**: `register_scheduler_task.ps1`이 `powercfg /change standby-timeout-ac 0`도 같이 실행해 AC 전원 기준 절전을 꺼준다(노트북이라 배터리로도 켜둘 거라면 `powercfg /change standby-timeout-dc 0`도 직접 실행한다).

**3) 배치가 멈췄을 때 알림 받기** — 야간 무인 실행 중 로그인 세션 만료·네이버 UI 변경 같은 시스템적 오류로 배치가 멈추면, 지금까지는 콘솔/로그에만 남고 아무도 모르고 지나갈 수 있었다. `.env`에 아래 중 하나 이상을 채우면 Slack 또는 이메일로 알려준다(`core/notify.py`, 아무 것도 안 채우면 기존처럼 로그에만 남고 조용히 넘어간다 — 선택 기능이다).

```
# Slack로 받기 (Slack 워크스페이스에서 Incoming Webhook을 만들어 URL을 넣는다)
NOTIFY_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# 이메일로 받기 (Gmail이면 "앱 비밀번호"를 발급해서 써야 한다 — 일반 비밀번호는 막혀 있다)
NOTIFY_EMAIL_TO=me@example.com
NOTIFY_EMAIL_SMTP_HOST=smtp.gmail.com
NOTIFY_EMAIL_SMTP_PORT=587
NOTIFY_EMAIL_SMTP_USER=bot@example.com
NOTIFY_EMAIL_SMTP_PASSWORD=앱비밀번호
```

알림은 (a) 배치가 시스템적 오류로 중단된 채 끝났을 때, (b) 스케줄러가 예상치 못한 오류로 완전히 죽었을 때 두 경우에 온다. 알림 전송 자체가 실패해도(웹훅 URL 오타 등) 배치 실행에는 영향을 주지 않는다.

## 폴더 구조

```
naver_blog_automation/
  main.py                          단발 지시 CLI
  daily_batch.py                   하루 배치 지시 CLI (한 번 실행하고 종료)
  scheduler.py                     상주 스케줄러 (매일 지정 시각에 daily_batch 역할 자동 실행 + 하트비트 + 실패 알림)
  manager.py                       core/job_manager.py 위의 얇은 호환 계층 (main/daily_batch/scheduler가 부름)
  migrate_to_sqlite.py             옛 batch_state.json/status.json → automation.db 이관 스크립트
  config.py                        환경변수 로드
  automation.db                    (실행 시 자동 생성) 모든 실행 상태가 담기는 SQLite DB
  departments/                     다섯 부서
    research.py                     리서치팀 (뉴스 조사)
    planning.py                     기획팀 (제목 기획)
    writing.py                      작성팀 (본문·팩트체크)
    design.py                       디자인팀 (이미지 제작)
    publishing.py                   발행팀 (네이버 임시저장)
    onboarding_publishing.py        발행팀 출근 등록 (네이버 로그인)
    onboarding_design.py            디자인팀 출근 등록 (챗지피티 로그인, 레거시 이미지 경로 쓸 때만 필요)
  core/                            부서들이 공유하는 내부 엔진
    database.py                      automation.db 스키마·CRUD (모든 실행 상태의 단일 원천)
    job_manager.py                   게시물 1건을 9단계로 실행·재개·재시도하는 오케스트레이터
    retry_policy.py                  오류 유형 분류 + 지수 백오프 재시도 정책
    duplicate_check.py               임베딩 기반 유사 주제 감지
    quality_gate.py                  발행 전 품질 점수 산정(PASS/REVIEW/FAILED)
    account_config.py                configs/accounts/*.yaml 로더
    naver_selectors.py               네이버 에디터 selector 후보 목록(UI 바뀌면 여기만 고치면 됨)
    naver_poster.py                  네이버 에디터 Playwright 자동화
    accounts.py                      여러 계정 정보(accounts.json) 로더 + secrets/ 경로 관리
    logger.py                        logs/automation_YYYYMMDD.log 평문 로그
    notify.py                        배치 중단·스케줄러 크래시 시 Slack/이메일 알림
    openai_client.py                 OpenAI Responses API 래퍼
    pipeline.py                      3턴(제목→본문→이미지) 대화 진행 + 재개(resume)
    image_gen.py                     OpenAI 이미지 생성 API 호출(기본 이미지 경로)
    legacy/chatgpt_image.py          챗지피티 웹채팅 이미지 생성(레거시, image_provider="chatgpt_web"일 때만)
  configs/accounts/                계정별 동작 설정(YAML) — 글자수/제목 개수/이미지/재시도/품질기준 등
  webapp/                          로컬 웹 대시보드 (automation.db 기반)
    app.py                           Flask 서버 (계정/지침 관리, 실행, 오늘 진행 현황+재시도 API)
    templates/index.html             3단 제어판 + 계정별 게시물×9단계 진행 현황
    static/app.js, style.css         프론트엔드
  deploy/                          재부팅 자동시작 등록 템플릿 (systemd/launchd/Windows 작업 스케줄러)
  tests/                           유닛 테스트(DB, 재개, idempotency, 재시도, 중복감지, 품질검사, 이관, 알림)
  prompts/
    system_prompt.txt               지침 원문 + 자동화 어댑터
  accounts.example.json             여러 계정 운영 시 accounts.json 템플릿
  secrets/                         (실행 시 생성) 네이버/챗지피티 로그인 세션 — git에 안 올라감
  reports/                         (실행 시 생성) 일일 뉴스 리포트 (계정별 하위 폴더)
  output/                          (실행 시 생성) 생성된 이미지, 게시물별 OpenAI 대화 재개용 상태
  logs/                            (실행 시 생성) 평문 로그
  backup/                          (마이그레이션 시 생성) 옛 JSON 상태 파일 백업
```

## 선택자가 깨졌을 때

네이버와 챗지피티 둘 다 UI(DOM 구조·클래스명)를 예고 없이 바꾼다. `core/naver_selectors.py`(`TITLE_SELECTORS` / `BODY_SELECTORS` / `IMAGE_BUTTON_SELECTORS` / `SAVE_BUTTON_SELECTORS`)와 `core/legacy/chatgpt_image.py`(`PROMPT_INPUT_SELECTORS` / `SEND_BUTTON_SELECTORS` / `NEW_CHAT_SELECTORS` / `GENERATED_IMAGE_SELECTORS`) 안에 후보 선택자가 여러 개 들어 있지만, 전부 실패하면:

1. `--headless` 옵션을 빼고(또는 `--show-browser`로) 실행해서 브라우저 창을 직접 본다.
2. 막힌 지점에서 F12(개발자도구)로 해당 요소의 클래스명/속성을 확인한다.
3. 해당 리스트 맨 앞에 새 선택자를 추가한다.
4. 이런 오류는 재시도해도 똑같이 막히는 "시스템적 오류"로 분류돼 배치 전체가 멈추고 대기한다(알림을 설정해뒀다면 Slack/이메일로도 온다) — 고치고 나서 다음 예정 실행(또는 수동 재실행)에서 자동으로 이어서 진행된다. `output/errors/<post_id>_naver_error.png`에 오류 시점 스크린샷이 남으니 참고한다.

## 유의사항

- 네이버 블로그 이용약관상 자동화 도구 사용에 제약이 있을 수 있으니, 본인 계정에서 과도한 빈도로 돌리지 않는 것을 권장한다. 발행팀은 **임시저장까지만** 하고 실제 발행(공개)은 하지 않는다 — 최종 검토·발행은 대표(사용자)가 직접 하는 것을 전제로 만들었다.
- OpenAI 웹 검색 tool 이름(`OPENAI_WEB_SEARCH_TOOL`)은 계정/모델에 따라 `web_search_preview` 또는 `web_search`일 수 있다. 실행 중 tool 관련 에러가 나면 `.env`에서 값을 바꿔본다.
- 생성된 이미지·본문에 포함된 가격·스펙 등 사실 정보는 지침의 팩트체크 절차를 거치지만, AI가 만든 콘텐츠이므로 발행 전에 한 번은 직접 훑어보는 것을 권장한다.
