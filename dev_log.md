# Dev Log

## 목적

이 파일은 `MyMcpServer`를 처음부터 다시 만들거나 다른 PC로 옮겨 작업할 때, 구현 흐름과 판단 근거를 빠르게 복원하기 위한 개발 이력 요약이다.  
상세 설계는 `docs/`를 보고, 이 파일은 "무엇을 왜 이렇게 만들었는지"를 짧게 따라가는 용도로 사용한다.

## 현재 프로젝트 상태 요약

- 목표: 국가법령정보센터(NLIC) 기반의 한국 법률 질의용 MCP 서버 구축
- 핵심 인터페이스:
  - HTTP: `/ask`, `/tools/search_law`, `/tools/get_article`, `/tools/get_version`, `/tools/validate_article`, `/tools/search_precedent`, `/tools/get_precedent`
  - MCP stdio: `ask`, `answer_with_citations`, `search_law`, `get_article`, `get_version`, `validate_article`, `search_precedent`, `get_precedent`
- 현재 강점:
  - MCP 연결 정상화 완료
  - 법령 조회 안정화 완료
  - `/ask` 답변 품질 상당 부분 고도화 완료
  - 판례 검색과 고위험 질문 보강 시작
- 현재 미완/다음 과제:
  - 판례 활용을 더 정교하게 최종 답변에 반영
  - 프롬프트를 최종 답변 규칙에 더 깊게 반영
  - 멀티에이전트 결과를 최종 응답에 더 직접 연결
  - cost logger는 존재하지만 아직 우선순위는 낮음

## 처음부터 현재까지 구현 연표

### 1. NLIC 래퍼 기본 뼈대 구성

- `search_law`, `get_article`, `get_version`, `validate_article` 기본 경로를 구현했다.
- 요청 캐시와 기본 검색/상세 조회 구조를 `src/nlic_api_wrapper.py`에 모았다.
- 이 단계에서는 "법령 검색/조문 조회/버전 조회가 되는 최소 서버"를 만드는 것이 목표였다.

### 2. `get_article` 안정화와 fallback 강화

- 조문 조회가 실API에서 흔들리는 문제가 있어 `JO` 후보 확장과 fallback을 보강했다.
- 주요 개선:
  - `제1조` 같은 입력을 `000100` 형태 후보까지 확장
  - `service:law`, `service:lawjosub`, 필요 시 `MST + JO` fallback 추가
  - `matched_via`, `attempted_queries`, `article_candidates` 디버그 정보 추가
- 의도:
  - "왜 찾았는지 / 왜 못 찾았는지"를 바로 볼 수 있게 하고, 실API 변동에 더 강하게 만들기

### 3. `get_version` fallback 보강

- `history` 응답이 비거나 구조적으로 비정상일 때도 버전 정보를 최대한 복원하도록 했다.
- `law` 응답에서 `시행일자`, `공포일자`, `제개정구분명` 등을 nested 탐색으로 보강했다.

### 4. 실응답 fixture 기반 회귀 테스트 도입

- 실제 NLIC 응답 JSON을 `tests/fixtures/nlic/` 아래에 저장하고, fixture 기반 회귀 테스트를 추가했다.
- 목표:
  - 외부 API 상태와 무관하게 재현 가능한 테스트 확보
  - 실제 응답 구조가 바뀌면 즉시 감지
  - 장애 샘플을 테스트로 고정

### 5. `/ask` 파이프라인 enrichment 도입

- `src/request_pipeline.py`에서 질문을 바로 답하지 않고:
  - 법령 검색
  - 대표 법령 선택
  - 버전 조회
  - 조문 조회
  - 필요한 경우 추가 조문 조회
  과정을 거치게 만들었다.
- 이 단계에서 `/ask`는 단순 문자열 응답기가 아니라 "법령 근거 수집 + 답변 생성" 파이프라인이 됐다.

### 6. `/ask` 응답 슬림화

- 초기에는 원본 API payload가 너무 많이 응답에 실렸다.
- MCP 소비자 입장에서 너무 무거워서, `citations`는 요약형 구조로 줄이고 원본은 각 tool에서 직접 확인하도록 방향을 잡았다.

### 7. MCP stdio 서버 구현

- `src/mcp_stdio_server.py`를 추가해 `initialize`, `tools/list`, `tools/call`을 구현했다.
- 초기 노출 tool:
  - `ask`
  - `search_law`
  - `get_article`
  - `get_version`
  - `validate_article`
- 이후 `answer_with_citations` alias와 precedent tools도 추가했다.

### 8. MCP handshake 장애 해결

- 가장 큰 장애 중 하나였다.
- 초기에 stdio 프로토콜을 LSP 스타일 `Content-Length` 기반처럼 처리하고 있었는데, MCP stdio는 newline-delimited JSON이 핵심이었다.
- 수정 후:
  - newline-delimited JSON 처리
  - `Content-Length`는 호환 fallback 정도로만 유지
  - lazy pipeline init
  - `resources/list`, `resources/templates/list` 빈 응답 추가
- 결과:
  - 실제 ChatGPT/Codex에서 handshake 성공
  - `tools/list`, `tools/call` 로그 확인

### 9. MCP 실행 안정화

- `run_mcp_stdio_server.cmd`를 추가해서 Python 경로, `-u`, 작업 디렉터리, unbuffered 실행을 고정했다.
- 이 래퍼를 통해 설정 UI에서 Python 직접 인자 입력 시 생기던 문제를 줄였다.

### 10. `AnswerComposer` 도입

- `/ask` 최종 응답이 `[통합검토]` 스타일의 검토문처럼 보이는 문제가 있어, 최종 사용자용 답변 조립 계층을 분리했다.
- `src/answer_composer.py`를 도입해:
  - 법령명
  - 조문번호
  - 조문 본문
  - 쉬운 설명
  - 시행일자
  - 근거 블록
  을 구조적으로 조립하게 했다.

### 11. 조문 유형 세분화

- 제목 패턴으로 조문 성격을 나누도록 고도화했다.
- 현재 반영된 유형:
  - 목적
  - 정의
  - 적용범위
  - 책무/의무
  - 권리
  - 신고/통지/보고
  - 허가/등록
  - 위임/위탁
  - 예외/특례/적용배제
  - 금지행위/제한
  - 벌칙/과태료/과징금

### 12. 질문 의도 분류 추가

- 질문 문장 패턴을 읽어서 답변 톤을 다르게 만들었다.
- 현재 반영된 의도:
  - 설명
  - 위법 여부
  - 차이/비교
  - 요건/기준
  - 절차
  - 적용 가능성

### 13. 비교/절차/적용 질문 고도화

- 질문에 여러 조문이 들어 있으면 추가 조문도 자동 조회하게 했다.
- 답변 블록도 상황에 따라 다르게 생성:
  - `[비교 요약]`
  - `[비교 참고 조문]`
  - `[판단 순서]`
  - `[추가 확인 포인트]`
  - `[적용 판단 포인트]`
  - `[함께 볼 조문]`
  - `[절차 정리]`
  - `[연관 조문]`

### 14. 답변 하단 근거 블록 추가

- 최종 답변에 `[근거]` 블록을 붙여 사용자가 기준 법령/조문/시행일자를 바로 확인할 수 있게 했다.

### 15. 멀티에이전트 역할 분리

- `src/multi_agent_review.py`를 정리해서 역할을 나눴다.
- 현재 agent:
  - `StatuteReviewAgent`
  - `ComplianceAgent`
  - `PrecedentReviewAgent`
  - `RiskReviewerAgent`
- low risk:
  - statute + compliance
- high risk:
  - precedent + risk까지 추가

### 16. 판례 검색 계층 추가

- `src/nlic_api_wrapper.py`에:
  - `search_precedent(query, reference_law=None)`
  - `get_precedent(precedent_id)`
  를 추가했다.
- `src/request_pipeline.py`에서 다음 조건이면 precedent enrichment를 수행한다:
  - `risk_level == HIGH`
  - 질문 의도가 `위법 여부`
  - 질문 의도가 `적용 가능성`
  - 사용자가 판례를 직접 요청

### 17. 판례 요청 트리거 확장

- 다음 표현이 있으면 risk와 무관하게 판례 검색을 켠다:
  - `판례`
  - `대법원`
  - `법원은`
  - `유사 사례`
  - `관련 사례`
  - `사례도`
  - `판결`

### 18. 판례를 답변에 반영

- `[참고 판례]` 블록을 붙였다.
- 현재 포함 내용:
  - 사건명
  - 사건번호
  - 법원명
  - 선고일자
  - 판례 검색 기준
  - 가능하면 판례 요지

### 19. 프롬프트 로더 도입 및 프롬프트 기반 방향성 반영

- `config/prompts/manifest.json`
- `config/prompts/v1/system_prompt.md`
- `config/prompts/v1/orchestration_prompt.md`
- `src/prompt_loader.py`
  를 통해 버전형 프롬프트 로딩 구조를 만들었다.
- 현재 프롬프트는 "실제 LLM 호출의 유일한 소스"라기보다, 파이프라인과 컴포저가 지켜야 할 원칙을 제공하는 역할이다.
- 최근 `AnswerComposer`에 직접 반영한 원칙:
  - 근거 중심 답변
  - 근거 없는 단정 회피
  - 불명확하면 보수 응답
  - evidence mapping이 있을 때 근거 블록 유지

### 20. 저장소 정리

- `.gitignore` 추가:
  - `__pycache__/`
  - `*.pyc`
  - `data/*.db`
  - `data/*.log`
- 실행/로그 산출물이 Git 상태를 더럽히지 않도록 정리했다.

## 재작업 시 먼저 보면 좋은 파일

- 아키텍처 개요: `docs/nlic-mcp-architecture.md`
- NLIC 래퍼: `src/nlic_api_wrapper.py`
- MCP 서버: `src/mcp_stdio_server.py`
- HTTP 서버: `src/http_server.py`
- 파이프라인: `src/request_pipeline.py`
- 답변 조립기: `src/answer_composer.py`
- 멀티에이전트: `src/multi_agent_review.py`
- 프롬프트 로더: `src/prompt_loader.py`
- 프롬프트 원문:
  - `config/prompts/v1/system_prompt.md`
  - `config/prompts/v1/orchestration_prompt.md`
- 회귀 테스트:
  - `tests/test_nlic_api_wrapper.py`
  - `tests/test_request_pipeline.py`
  - `tests/test_answer_composer.py`
  - `tests/test_mcp_stdio_server.py`
  - `tests/test_multi_agent_review.py`

## 재작업 우선순위 추천

다른 PC에서 처음부터 복원해야 한다면 아래 순서를 추천한다.

1. `nlic_api_wrapper.py`와 HTTP tools 복원
2. `request_pipeline.py`에서 law enrichment 복원
3. `mcp_stdio_server.py` 복원
4. MCP handshake가 되는지 먼저 확인
5. `answer_composer.py` 복원
6. precedent enrichment 복원
7. `multi_agent_review.py` 역할 분리 반영
8. 마지막으로 prompt rule 반영

## 주의했던 문제들

- MCP stdio는 newline-delimited JSON이어야 한다.
- handshake가 안 될 때는 `server_start`만 찍히고 `initialize`가 안 찍히는 증상이 있었다.
- `get_article`는 `JO` 포맷과 endpoint 조합이 흔들릴 수 있어 fallback이 중요하다.
- 법률 답변은 모델 자유 생성에 맡기기보다, 서버가 답변 구조와 보수 문구를 고정하는 편이 안정적이었다.
- 판례는 "찾는 것"보다 "왜 참고되는지 짧게 설명하는 것"이 실제 체감에 더 중요하다.

## 최근 작업 로그

- 2026-03-13: `AnswerComposer` rebuilt with prompt-aware grounding rules, stronger precedent gist output, and clearer fallback handling.
- 2026-03-13: `tests/test_answer_composer.py` refreshed to cover purpose/sanction/applicability/procedure/comparison and precedent-summary cases.
- 2026-03-13: Full test suite passed (`Ran 56 tests`, `OK`).
- 2026-03-13: Multi-agent review now emits structured caution/relevance signals and marks high-risk conflicts conservatively.
- 2026-03-13: Request pipeline now exposes `review_summary` in citations and passes review signals into final answer composition.
- 2026-03-13: Full test suite passed again after review/precedent upgrades (`Ran 58 tests`, `OK`).
- 2026-03-13: Prompt files were upgraded to reflect statute-first, precedent-as-support, conflict-aware, evidence-mapped answer rules.
- 2026-03-13: Prompt policy extraction is now applied in the request pipeline for mode selection, validation, and response citations.
- 2026-03-13: Full test suite passed after prompt integration (`Ran 59 tests`, `OK`).
- 2026-03-13: Final answer polish improved precedent block readability by adding a short interpretation meaning when relevance and precedent gist are both available.
- 2026-03-13: Full test suite passed after answer-polish updates (`Ran 59 tests`, `OK`).
- 2026-03-13: Request pipeline now searches related laws together for domain-heavy questions (e.g. 공동주택관리법, 위치정보법, 정보통신망법, 신용정보법) instead of relying on one primary law only.
- 2026-03-13: Full test suite passed after related-law expansion (`Ran 60 tests`, `OK`).
- 2026-03-16: Expanded related-law keyword hints across privacy/security, fintech, e-commerce, healthcare, labor, education, youth, senior welfare, housing, and public-record domains.
- 2026-03-16: Full test suite passed after keyword-hint expansion (`Ran 61 tests`, `OK`).
