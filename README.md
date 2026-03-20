# MyMCPServer

국가법령정보센터 API 기반 MCP 법률 판단 보조 서버입니다.

이 프로젝트는 법령을 단순 검색하는 수준이 아니라, 질문에 맞는 본법/시행령/시행규칙/관련 법령을 따라가며 근거 조문을 찾아 MCP 도구 형태로 반환합니다.

## 문서 안내
- 실행/운영 체크리스트: `docs/execution-checklist.md`
- MCP 도구 계약: `docs/mcp-tool-contract.md`
- Request pipeline: `docs/request-pipeline.md`
- NLIC API wrapper: `docs/nlic-api-wrapper.md`
- 비용/로그 구조: `docs/cost-logging.md`
- 아키텍처 개요: `docs/nlic-mcp-architecture.md`

## 실행 구조
- `src/mcp_core.py`: stdio/HTTP가 함께 쓰는 MCP JSON-RPC 코어
- `src/mcp_stdio_server.py`: 로컬 MCP 클라이언트용 stdio transport
- `src/mcp_http_server.py`: 원격 MCP 클라이언트용 HTTP transport (`POST /mcp`)
- `src/http_server.py`: 로컬 REST/로그 대시보드 (`127.0.0.1:8000`)
- `src/request_pipeline.py`: 법령 검색, 관련 법령 확장, 조문 grounding 파이프라인

## 빠른 시작
실행 전 `NLIC_OC` 환경변수를 설정해야 합니다.

### 1. stdio로 로컬 연결
```bash
export NLIC_OC="your-oc-value"
python -m src.mcp_stdio_server
```

### 2. HTTP로 원격 연결
```bash
export NLIC_OC="your-oc-value"
python -m src.mcp_http_server
```

- 기본 MCP HTTP 엔드포인트: `http://localhost:8001/mcp`
- 외부 공개가 필요하면 `ngrok`는 `8001`에만 연결하면 됩니다.

### 3. 로그 대시보드 보기
```bash
python -m src.http_server
```

- 로컬 로그 대시보드: `http://localhost:8000/logs/recent?view=html`
- 로그 DB: `data/cost_logs.db`

## Runtime Notes
- `stdio`와 `HTTP`는 같은 코어(`src/mcp_core.py`, `src/request_pipeline.py`)를 공유합니다.
- `src.http_server`는 `127.0.0.1:8000`에만 바인딩되며, 로그/REST 확인용입니다.
- 질문 처리 로그는 SQLite `data/cost_logs.db`에 저장되고, `8000` 대시보드는 그 DB를 조회해 보여줍니다.
- 사용자에게 노출되는 법령/조문 링크는 공개용 `https://www.law.go.kr/법령/...` 형식만 사용합니다.

## 보안 주의
- `NLIC_OC` 값은 코드나 공개 문서에 직접 적지 마세요.
- 외부 공개 시에는 `MCP_AUTH_TOKEN` 같은 인증과 HTTPS를 함께 사용하세요.

