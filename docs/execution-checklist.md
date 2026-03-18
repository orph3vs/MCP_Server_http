# 실행 체크리스트 (비개발자용)

아래 순서대로 실행하면 "정상 동작" 여부를 빠르게 확인할 수 있습니다.

## 1) 테스트 통과 확인
```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

정상 기준:
- 마지막에 `OK`
- `Ran ... tests` 출력

실행 전 준비:
```bash
export NLIC_OC="your-oc-value"
```

## 2) 로컬 단건 실행
```bash
python run_local.py "개인정보 제3자 제공 기준" --context "기준시점: 2025-01-01"
```

정상 기준:
- JSON 출력
- `request_id`, `mode`, `score` 필드 존재

## 3) HTTP 서버 헬스체크
터미널 A:
```bash
python -m src.http_server
```

터미널 B:
```bash
curl http://localhost:8000/health
```

정상 기준:
- `{"status": "ok"}` 응답
- `src.http_server`는 기본적으로 `127.0.0.1:8000`에만 바인딩됩니다.

## 4) HTTP 질의 요청
(선택) metadata/history를 함께 보내면 서버가 context를 자동 조립합니다.
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"user_query":"개인정보 위탁과 제3자 제공 차이","context":"기준시점: 2025-01-01","metadata":{"tenant":"acme","locale":"ko-KR"},"history":["이전 질문 1","이전 질문 2"]}'
```

정상 기준:
- JSON 응답
- `request_id`, `risk_level`, `mode`, `score` 필드 존재

## 참고
- 네트워크 환경 제약이 있으면 외부 NLIC 호출 단계에서 `error`가 나올 수 있습니다.
- 이 경우에도 파이프라인/에러 처리/로그 저장 동작 자체는 정상일 수 있습니다.


## Windows 인코딩 참고
- Git Bash/명령프롬프트에서 한글 JSON 전송 시 인코딩 충돌이 날 수 있습니다.
- 이 서버는 `utf-8`, `utf-8-sig`, `cp949`, `euc-kr` 요청 바디를 자동 처리합니다.
- 그래도 문제가 있으면 PowerShell의 `Invoke-RestMethod` 사용을 권장합니다.


## 5) Tool 엔드포인트 확인(선택)
Git Bash에서는 줄바꿈에 `` ` `` 대신 `\`를 사용합니다.

```bash
curl -X POST http://localhost:8000/tools/search_law \
  -H "Content-Type: application/json" \
  -d '{"query":"개인정보보호법"}'

```

```bash
curl "http://localhost:8000/logs/recent?limit=5"
```

정상 기준:
- `tools/*`는 `{"data": ...}` 형태
- `/logs/recent`는 `{"count": n, "items": [...]}` 형태

PowerShell 예시:
```powershell
curl -X POST http://localhost:8000/tools/get_article `
  -H "Content-Type: application/json" `
  -d '{"law_id":"011357","article_no":"제1조"}'
```

## 6) MCP HTTP 서버 확인
터미널 A:
```bash
python -m src.mcp_http_server
```

터미널 B:
```bash
curl http://localhost:8001/health
```

정상 기준:
- `{"status": "ok", "transport": "http", "protocol": "json-rpc-2.0"}` 응답

MCP initialize 요청:
```bash
curl -X POST http://localhost:8001/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}'
```

정상 기준:
- JSON-RPC `result.protocolVersion` 필드 존재

MCP tools/list 요청:
```bash
curl -X POST http://localhost:8001/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

## 7) 역할 구분 메모
- `8000`: `src.http_server`용. `/ask`, `/tools/*`, `/logs/recent` 확인용
- `8001`: `src.mcp_http_server`용. MCP 클라이언트/`ngrok` 연결용
- `ngrok`를 쓸 때는 `ngrok http 8001`만 실행하면 됩니다.
- `8000`을 끄고 질문을 보내도 로그는 `data/cost_logs.db`에 쌓여야 하며, 나중에 `8000`을 다시 켜서 `/logs/recent`로 조회할 수 있습니다.
- `ask` 호출 후에는 request 로그를, `search_law`/`validate_article` 호출 후에는 tool 로그를 확인하면 됩니다.
## 8) Recent Runtime Notes
- Some NLIC article routes may return `HTTP 404` while probing candidate article numbers.
- Current behavior is to keep trying the next article candidate instead of failing the whole `get_article` call immediately.
- Because of this, recent legal questions may complete with fewer follow-up raw tool calls and more `ask`-only completions.
- If a just-fixed behavior still looks old, restart the running server before debugging further.

## 9) stdio MCP Execution
- Local MCP clients can connect over stdio using the same core server logic.
- Launch with:

```bash
python -m src.mcp_stdio_server
```

- Windows helper script:

```bat
C:\MCP_Server\MyMcpServer-http\run_mcp_stdio_server.cmd
```

- `stdio` and HTTP share the same retrieval/answer core. Use `stdio` for local integration and HTTP for remote access.
