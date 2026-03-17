# Dev Log

## 목적

이 문서는 `MyMcpServer`를 다른 PC에서 다시 복구하거나, 현재 구조를 빠르게 이해하기 위한 개발 요약 문서다.
세부 사용법은 `docs/`를 참고하고, 이 파일은 "무엇을 어떤 순서로 만들었는지"와 "현재 어디까지 안정화됐는지"를 정리한다.

## 현재 기준선

- 현재 기준 버전: `v1 안정판`
- v2 실험 분기:
  - 한때 관련 법령 탐지 v2를 분리했지만, 비용/복잡도 대비 이점이 아직 부족하다고 판단해 롤백
  - 현재는 다시 `v1` 기준으로 운영

## 주요 구현 내역

### 1. NLIC wrapper 구축

- 파일: [src/nlic_api_wrapper.py](C:\MCP_Server\MyMcpServer\src\nlic_api_wrapper.py)
- 주요 기능:
  - `search_law`
  - `get_article`
  - `get_version`
  - `validate_article`
  - `search_precedent`
  - `get_precedent`

### 2. 조문 조회 fallback 강화

- `get_article`에서 `JO` 후보를 확장
- 실패 시 다른 조회 경로로 재시도
- 디버그 필드 추가:
  - `matched_via`
  - `attempted_queries`
  - `article_candidates`

### 3. 버전 조회 fallback 강화

- `history` 응답이 비거나 약할 때 `law` 응답에서 시행일/공포일/개정구분을 복원

### 4. fixture 기반 회귀 테스트 도입

- 실제 API 응답 샘플을 `tests/fixtures/nlic/`에 저장
- 실응답 기반 회귀 테스트로 파서 안정성 보강

### 5. `/ask` 파이프라인 고도화

- 파일: [src/request_pipeline.py](C:\MCP_Server\MyMcpServer\src\request_pipeline.py)
- 포함 내용:
  - 질문 의도 분류
  - 관련 법령 힌트 기반 검색
  - 대표 법령 선택
  - 버전/조문/판례 enrichment
  - suggestion 저장

### 6. 답변 조립기 도입

- 파일: [src/answer_composer.py](C:\MCP_Server\MyMcpServer\src\answer_composer.py)
- 역할:
  - 조문 유형별 설명 방식 분기
  - 질문 의도별 답변 구조 분기
  - 근거 블록, 판례 블록, 고위험 안내 정리

### 7. 멀티에이전트 검토 파이프라인 도입

- 파일: [src/multi_agent_review.py](C:\MCP_Server\MyMcpServer\src\multi_agent_review.py)
- 주요 에이전트:
  - `StatuteReviewAgent`
  - `ComplianceAgent`
  - `PrecedentReviewAgent`
  - `RiskReviewerAgent`

현재 구조는 "에이전트별 판단 신호를 만들고 최종 답변에 반영하는 내부 검토형"에 가깝다.

### 8. MCP stdio 서버 구현

- 파일: [src/mcp_stdio_server.py](C:\MCP_Server\MyMcpServer\src\mcp_stdio_server.py)
- 지원 기능:
  - `initialize`
  - `tools/list`
  - `tools/call`
  - `resources/list`
  - `resources/templates/list`

### 9. MCP handshake 안정화

- newline-delimited JSON 기준으로 stdio 처리
- lazy pipeline init 적용
- `run_mcp_stdio_server.cmd` 추가

### 10. cost logger 및 로그 뷰 확장

- 파일:
  - [src/cost_logger.py](C:\MCP_Server\MyMcpServer\src\cost_logger.py)
  - [src/http_server.py](C:\MCP_Server\MyMcpServer\src\http_server.py)
- 현재 가능:
  - request 로그
  - tool 로그
  - JSON / readable / table / HTML 뷰

### 11. law hint suggestion 흐름 도입

- 파일: [src/law_hint_suggestions.py](C:\MCP_Server\MyMcpServer\src\law_hint_suggestions.py)
- 흐름:
  - `LawAPI` grounding 실패 시 suggestion 저장
  - 승인/거절 가능
  - 승인된 힌트는 이후 관련 법령 탐지에 반영

## 현재 남은 과제

- 실사용 질문 기반 튜닝
  - 관련 법령 힌트 보강
  - grounding 약한 케이스 식별
  - answer_with_citations 실패 케이스 추적
- suggestion 기준 보강 여부 검토
  - 현재는 `LawAPI 완전 실패` 위주로만 저장

## 복구 우선순위

다른 PC에서 다시 세팅할 때는 아래 순서를 추천한다.

1. NLIC wrapper + 테스트 복구
2. request pipeline + answer composer 복구
3. MCP stdio 서버 복구
4. HTTP 서버 및 로그 뷰 복구
5. suggestion / 승인 흐름 복구

## 최근 메모

- 2026-03-17:
  - retrieval v2 분기 실험 후 롤백
  - 현재는 다시 `v1 안정판` 기준으로 운영
  - 로그 뷰/도구 로그/HTML 대시보드는 유지
