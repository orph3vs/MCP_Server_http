# Dev Log

## 목적

이 문서는 `MyMcpServer`를 처음부터 다시 복원하거나 다른 PC에서 재구축할 때 참고하는 개발 기록이다.
세부 설계는 `docs/`를 보고, 이 파일은 "무엇을 어떤 순서로 만들었는지"를 빠르게 따라가기 위한 요약본으로 쓴다.

## 현재 상태 요약

- 목표: 국가법령정보센터(NLIC) 기반 한국 법률 질의용 MCP 서버
- 주요 인터페이스
  - HTTP: `/ask`, `/tools/search_law`, `/tools/get_article`, `/tools/get_version`, `/tools/validate_article`, `/tools/search_precedent`, `/tools/get_precedent`, `/logs/recent`
  - MCP stdio: `ask`, `answer_with_citations`, `search_law`, `get_article`, `get_version`, `validate_article`, `search_precedent`, `get_precedent`
- 현재 강점
  - MCP 연결 안정화 완료
  - 법령/조문/버전/판례 조회 가능
  - `/ask`에 관련 법령, 판례, 멀티에이전트 검토, 답변 조립 규칙 반영
  - cost logger와 로그 조회 뷰 제공
- 현재 단계
  - 큰 기능 구현보다는 실사용 질문 기반 튜닝 단계

## 구현 연표

### 1. NLIC wrapper 기본 구현

- `src/nlic_api_wrapper.py`
- 구현한 기본 기능
  - `search_law`
  - `get_article`
  - `get_version`
  - `validate_article`

### 2. `get_article` fallback 강화

- 조문 조회 실패에 대비해 `JO` 후보 확장 및 fallback 추가
- 디버그용 필드 추가
  - `matched_via`
  - `attempted_queries`
  - `article_candidates`

### 3. `get_version` fallback 강화

- `history` 응답이 비거나 불완전할 때 `law` 응답에서 시행일자, 공포일자, 제개정구분을 복원

### 4. fixture 기반 회귀 테스트 도입

- `tests/fixtures/nlic/`
- 실제 API 응답 샘플을 고정해서 회귀 방지

### 5. `/ask` pipeline enrichment 도입

- `src/request_pipeline.py`
- 질문 처리 흐름에 아래를 추가
  - 법령 검색
  - 대표 법령 선택
  - 버전 조회
  - 조문 조회
  - 필요 시 관련 조문 조회

### 6. `/ask` 응답 슬림화

- MCP 소비자 입장에서 너무 무거운 원본 payload를 줄이고 요약형 citations 구조로 정리

### 7. MCP stdio 서버 구현

- `src/mcp_stdio_server.py`
- 구현 메서드
  - `initialize`
  - `tools/list`
  - `tools/call`

### 8. MCP handshake 문제 해결

- stdio transport를 newline-delimited JSON 기준으로 수정
- lazy pipeline init 적용
- `resources/list`, `resources/templates/list` 호환 응답 추가

### 9. MCP 실행 래퍼 추가

- `run_mcp_stdio_server.cmd`
- Python 경로, `-u`, 작업 디렉터리, unbuffered 실행을 고정

### 10. `AnswerComposer` 도입

- `src/answer_composer.py`
- 최종 사용자용 답변을 조립하는 계층 분리
- 답변에 아래를 구조화
  - 법령명
  - 조문번호
  - 조문 요약
  - 쉬운 설명
  - 근거 블록

### 11. 조문 유형 분류 추가

- 현재 반영된 분류
  - 목적
  - 정의
  - 적용범위
  - 책무/의무
  - 권리
  - 신고/통지/보고
  - 허가/등록
  - 위임
  - 예외/특례/적용배제
  - 금지/제한
  - 벌칙/과태료/과징금

### 12. 질문 의도 분류 추가

- 현재 반영된 의도
  - 설명
  - 위법 여부
  - 비교
  - 요건
  - 절차
  - 적용 가능성

### 13. 비교/절차/적용 질문 강화

- 질문에 여러 조문이 있으면 관련 조문을 함께 조회
- 답변 블록 추가
  - `[비교 요약]`
  - `[비교 참고 조문]`
  - `[판단 순서]`
  - `[적용 판단 포인트]`
  - `[절차 정리]`
  - `[연관 조문]`

### 14. 근거 블록 추가

- 답변 하단에 `[근거]` 블록 자동 추가

### 15. 멀티에이전트 역할 분리

- `src/multi_agent_review.py`
- 현재 agent
  - `StatuteReviewAgent`
  - `ComplianceAgent`
  - `PrecedentReviewAgent`
  - `RiskReviewerAgent`
- low risk: statute + compliance
- high risk: precedent + risk 추가

### 16. 판례 검색 계층 추가

- `src/nlic_api_wrapper.py`
  - `search_precedent`
  - `get_precedent`
- `src/request_pipeline.py`
  - high-risk, 위법 여부, 적용 가능성, 판례 요청 시 precedent enrichment 수행

### 17. 판례 relevance 반영

- 답변에 `[참고 판례]` 블록 추가
- review summary를 통해 판례가 왜 relevant한지 짧게 설명

### 18. prompt loader 및 정책 반영

- `config/prompts/manifest.json`
- `config/prompts/v1/system_prompt.md`
- `config/prompts/v1/orchestration_prompt.md`
- `src/prompt_loader.py`
- prompt policy를 request pipeline과 answer composer에 반영

### 19. 관련 법령 힌트 확장

- `src/request_pipeline.py`의 `_RELATED_LAW_HINTS` 확장
- 현재 강화된 분야
  - 개인정보/보안
  - 금융/신용/전자금융
  - 이커머스
  - 헬스케어/의료
  - 세금
  - 근로/채용
  - 교육
  - 청소년
  - 노인복지
  - 주택/아파트
  - 위치정보/공공기록물

### 20. cost logger 고도화

- `src/cost_logger.py`
- 저장 필드 확대
  - 질문 의도
  - error stage
  - NLIC 호출 수
  - 법령 검색 수
  - 조문 조회 수
  - 판례 검색/상세 조회 수
  - 관련 법령 수
- `/logs/recent` 확장
  - raw JSON
  - `view=readable`
  - `view=table`

### 21. 생성물 정리

- `.gitignore` 반영
  - `__pycache__/`
  - `*.pyc`
  - `data/*.db`
  - `data/*.log`
- Git에 잘못 추적되던 생성물 추적 해제

## 핵심 파일

- NLIC wrapper: `src/nlic_api_wrapper.py`
- request pipeline: `src/request_pipeline.py`
- answer composer: `src/answer_composer.py`
- multi-agent review: `src/multi_agent_review.py`
- prompt loader: `src/prompt_loader.py`
- MCP stdio server: `src/mcp_stdio_server.py`
- HTTP server: `src/http_server.py`
- cost logger: `src/cost_logger.py`
- 로컬 실행기: `run_local.py`
- MCP 실행 래퍼: `run_mcp_stdio_server.cmd`

## 복원 순서 추천

1. `src/nlic_api_wrapper.py`
2. `src/request_pipeline.py`
3. `src/http_server.py`
4. `src/mcp_stdio_server.py`
5. MCP handshake 확인
6. `src/answer_composer.py`
7. `src/multi_agent_review.py`
8. `src/prompt_loader.py` + `config/prompts/`
9. `src/cost_logger.py`
10. 테스트 복원

## 주의했던 문제

- MCP stdio는 newline-delimited JSON 기준으로 맞춰야 했다
- handshake 실패 시 `server_start`만 찍히고 `initialize`가 안 찍혔다
- `get_article`는 `JO` 형식과 fallback 순서가 중요했다
- 법률 답변은 자유 생성보다 서버가 답변 구조를 잡아주는 편이 안정적이었다
- 판례는 "찾는 것"보다 "왜 relevant한지 설명하는 것"이 체감상 더 중요했다
- cost logger는 단순 비용 기록보다 "왜 비쌌는지"가 보이게 만드는 것이 중요했다

## 최근 상태

- 2026-03-13: prompt-aware answer composition, review summary, precedent relevance 반영
- 2026-03-13: related law enrichment와 prompt policy pipeline 반영
- 2026-03-16: 관련 법령 키워드 힌트 대폭 확장
- 2026-03-16: cost logger 스키마 확장
- 2026-03-16: `/logs/recent?view=readable` 추가
- 2026-03-16: `/logs/recent?view=table` 추가
- 2026-03-16: 생성물(`pyc`, cache, db/log tracking`) 정리

## 최근 테스트 결과

- 전체 테스트 통과
- 최신 기준: `Ran 66 tests`, `OK`
