# MyMCPServer

국가법령정보센터 API 기반 MCP 서버 프로젝트입니다.

## 문서 안내
- 전체 구조 설계: `docs/nlic-mcp-architecture.md`
- Multi-Agent Review: `docs/multi-agent-review.md`
- NLIC API Wrapper: `docs/nlic-api-wrapper.md`
- Confidence Scoring: `docs/confidence-scoring.md`
- Cost Logging: `docs/cost-logging.md`
- Request Pipeline: `docs/request-pipeline.md`
- MCP Tool Contract: `docs/mcp-tool-contract.md`
- 실행 체크리스트: `docs/execution-checklist.md`

## Prompt 구성
- `config/prompts/manifest.json`: 프롬프트 버전 매니페스트
- `config/prompts/<version>/system_prompt.md`
- `config/prompts/<version>/orchestration_prompt.md`
- `src/prompt_loader.py`: 요청마다 자동 결합하는 로더 모듈
- `src/risk_classifier.py`: 질문 위험도(HIGH/LOW) 점수 기반 분기 모듈
- `src/multi_agent_review.py`: 요약→병렬분석→통합 Multi-Agent Review 파이프라인
- `src/nlic_api_wrapper.py`: 국가법령정보센터 API wrapper(search_law/get_article/get_version/validate_article + cache)
- `src/confidence_scoring.py`: 답변 신뢰도 점수(100점 만점) 자동 계산 엔진
- `src/cost_logger.py`: 요청 비용 로그(SQLite) 저장 모듈
- `src/request_pipeline.py`: 전체 요청 흐름(User→...→Response) 오케스트레이션 파이프라인
- `src/http_server.py`: RequestPipeline HTTP 엔드포인트(`/health`, `/ask`)
- `src/mcp_stdio_server.py`: MCP JSON-RPC core (`initialize`, `tools/list`, `tools/call`)
- `src/mcp_http_server.py`: HTTP transport MCP 서버(`POST /mcp`, `GET /health`)
- `run_local.py`: 로컬 단건 실행 스크립트

## Runtime Notes
- `src.http_server`는 `8000` 포트에서 REST/로그 확인용으로 사용합니다.
- `src.mcp_http_server`는 `8001` 포트에서 MCP 연결용으로 사용합니다.
- 외부 공개가 필요할 때는 `ngrok`를 `8001`에만 연결하면 됩니다.
- 질문 처리 로그는 SQLite `data/cost_logs.db`에 저장되고, `8000`의 `/logs/recent`는 그 DB를 조회하는 화면입니다.

- 보안 주의: NLIC OC 값은 공개 문서에 기재하지 마세요.

## 진행 방식
- 본 저장소의 상세 설계/정책/플로우는 README가 아닌 `docs/` 하위 문서에서 관리합니다.
- 다음 작업은 사용자께서 전달하는 **단계별 프롬프트**를 기준으로 순차 반영합니다.
