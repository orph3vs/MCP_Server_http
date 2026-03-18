# MCP Tool Contract

`src/mcp_http_server.py`는 HTTP transport 기반 MCP 서버를 제공합니다.

실행:
```bash
python -m src.mcp_http_server
```

Windows MCP 클라이언트 연결 시 권장 실행 파일:
```bat
C:\MCP_Server\MyMcpServer-http\run_mcp_http_server.cmd
```

권장 이유:
- 작업 디렉터리를 고정합니다.
- `PYTHONUNBUFFERED=1`과 `-u`를 함께 적용합니다.
- UI 설정에서 Python 경로/인자 분리를 잘못 넣어 발생하는 handshake 실패를 줄입니다.

지원 메서드:
- `initialize`
- `tools/list`
- `tools/call`

노출되는 tool:
- `ask`
  - 입력: `user_query`, `context?`, `request_id?`
- `answer_with_citations`
  - 입력: `user_query`, `context?`, `request_id?`
- `search_law`
  - 입력: `query`
- `get_article`
  - 입력: `law_id`, `article_no`
- `get_version`
  - 입력: `law_id`
- `validate_article`
  - 입력: `law_id`, `article_no`

설계 원칙:
- `/tools/*` HTTP 엔드포인트와 동일한 기능을 MCP tool로 노출합니다.
- `ask`와 `answer_with_citations`는 같은 파이프라인을 호출합니다.
- `answer_with_citations`는 모델 자동선택을 돕기 위한 법률 Q&A용 대표 alias입니다.
- `/ask`는 요약된 citation 구조를 반환합니다.
- 원본 API payload가 필요하면 `search_law`, `get_article`, `get_version`, `validate_article`를 직접 호출합니다.

반환 형식:
- MCP `tools/call` 결과는 `content[0].text`에 JSON 문자열을 담아 반환합니다.
- tool 내부 오류는 JSON-RPC 오류가 아니라 `isError=true`인 tool result로 반환합니다.

HTTP transport 메모:
- MCP endpoint: `POST /mcp`
- health check: `GET /health`
- set `MCP_AUTH_TOKEN` in the local shell or deployment environment when bearer auth is needed
- notification처럼 응답 본문이 없는 메시지는 HTTP `204 No Content`를 반환합니다.
- `8001`은 MCP 전용 포트입니다.
- `8000`은 별도 `src.http_server`를 띄웠을 때 로그/REST 확인용 포트입니다.
- `ngrok`를 사용할 때는 `8001`만 터널링하면 됩니다.
- `ask`/`answer_with_citations`는 파이프라인 전체를 실행하므로 request 로그가 남습니다.
- `search_law`, `validate_article` 같은 개별 도구는 tool 로그로 남습니다.
