# Commands

현재 `MyMcpServer`에서 바로 사용할 수 있는 실행 명령과 API 호출 예시를 정리한 문서입니다.

## 1. 서버 실행

### HTTP 서버 실행

```powershell
C:\Users\orph3\AppData\Local\Programs\Python\Python314\python.exe -m src.http_server
```

### MCP stdio 서버 실행

```powershell
.\run_mcp_stdio_server.cmd
```

## 2. 기본 상태 확인

```bash
curl http://localhost:8000/health
```

## 3. 질문 처리

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"user_query":"개인정보 보호법 제15조 설명해줘"}'
```

## 4. 법령 도구

### 법령 검색

```bash
curl -X POST http://localhost:8000/tools/search_law \
  -H "Content-Type: application/json" \
  -d '{"query":"개인정보보호법"}'
```

### 조문 조회

```bash
curl -X POST http://localhost:8000/tools/get_article \
  -H "Content-Type: application/json" \
  -d '{"law_id":"011357","article_no":"제1조"}'
```

### 버전 조회

```bash
curl -X POST http://localhost:8000/tools/get_version \
  -H "Content-Type: application/json" \
  -d '{"law_id":"011357"}'
```

### 조문 유효성 확인

```bash
curl -X POST http://localhost:8000/tools/validate_article \
  -H "Content-Type: application/json" \
  -d '{"law_id":"011357","article_no":"제1조"}'
```

## 5. 판례 도구

### 판례 검색

```bash
curl -X POST http://localhost:8000/tools/search_precedent \
  -H "Content-Type: application/json" \
  -d '{"query":"개인정보 보호법 위반"}'
```

### 판례 상세 조회

```bash
curl -X POST http://localhost:8000/tools/get_precedent \
  -H "Content-Type: application/json" \
  -d '{"precedent_id":"판례일련번호"}'
```

## 6. 로그 보기

### 원본 JSON

```bash
curl "http://localhost:8000/logs/recent"
```

### 읽기 쉬운 JSON

```bash
curl "http://localhost:8000/logs/recent?view=readable"
```

### 터미널 표 형태

```bash
curl "http://localhost:8000/logs/recent?view=table"
```

### HTML 대시보드

브라우저에서 아래 주소를 엽니다.

```text
http://localhost:8000/logs/recent?view=html
```

### 개수 제한

```bash
curl "http://localhost:8000/logs/recent?limit=30&view=table"
```

## 7. suggestion 관리

### pending suggestion 보기

```bash
curl "http://localhost:8000/suggestions/law-hints?status=pending"
```

### suggestion 승인

```bash
curl -X POST http://localhost:8000/suggestions/law-hints/approve \
  -H "Content-Type: application/json" \
  -d '{"suggestion_id":"아이디","law_name":"도서관법","keywords":["도서관","출석부"]}'
```

### suggestion 거절

```bash
curl -X POST http://localhost:8000/suggestions/law-hints/reject \
  -H "Content-Type: application/json" \
  -d '{"suggestion_id":"아이디"}'
```

## 8. MCP에서 노출되는 도구

- `ask`
- `answer_with_citations`
- `search_law`
- `get_article`
- `get_version`
- `validate_article`
- `search_precedent`
- `get_precedent`

## 9. 테스트 실행

```powershell
C:\Users\orph3\AppData\Local\Programs\Python\Python314\python.exe -m unittest discover -s tests -p "test_*.py" -q
```
