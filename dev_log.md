# 개발 로그

## 프로젝트 목표
- 국가법령정보센터 기반의 한국어 법률 질의응답용 MCP 서버를 구축한다.
- 광범위한 추측형 답변보다 아래 항목을 우선한다.
  - 법령 검색
  - 조문 조회
  - 시행일/연혁 조회
  - 판례 조회
  - 근거가 있는 답변
  - 관측 가능한 로그

## 현재 안정 범위
- HTTP 서버 제공 기능
  - `/ask`
  - 법령 도구
  - 판례 도구
  - 로그 대시보드
  - suggestion 대시보드
- MCP 서버 제공 도구
  - `ask`
  - `answer_with_citations`
  - `search_law`
  - `get_article`
  - `get_version`
  - `validate_article`
  - `search_precedent`
  - `get_precedent`
- 요청 파이프라인 주요 기능
  - 법령 검색 및 검색어 정규화
  - 관련 법령 힌트 확장
  - 조문/연혁 enrichment
  - 판례 enrichment
  - 질문 의도 분류
  - 고위험/적용여부/위법성 질문에 맞춘 답변 구성

## 주요 설계 결정
- 현재 retrieval 구조를 안정 버전 `v1`로 유지한다.
- 런타임 비용 때문에 LLM 기반 retrieval 추론은 기본 활성화하지 않는다.
- suggestion 기능은 원칙적으로 법령 grounding 실패나 흔들림에 대한 기록/진단용으로 쓴다.
- 로그는 아래를 구분해서 남긴다.
  - request 단위 처리 로그
  - raw MCP tool 호출 로그

## 최근 정리 작업
- `src/request_pipeline.py`에 남아 있던 폐기된 `v2` retrieval 흔적을 제거했다.
- 사용하지 않는 예전 판례 쿼리 빌더를 제거하고, anchor 기반 판례 검색 흐름만 유지했다.
- 현재 안정적인 판례 검색 전략은 다음과 같다.
  - 핵심 주제 anchor를 잡는다.
  - 더 좁은 쟁점 용어로 확장한다.
  - 너무 넓은 단독 판례 쿼리는 피한다.

## 현재 안정적으로 확인된 동작
- `LOW` 위험도 질문이라도 의도가 `applicability` 또는 `illegality`로 분류되면 multi-agent 경로를 탈 수 있다.
- 판례 검색 횟수와 최종 판례 채택은 다르다.
  - 검색 횟수 > 0 이라고 해서 반드시 판례가 답변에 채택되는 것은 아니다.
- MCP 클라이언트가 `ask` 호출 전에 질문을 다시 다듬을 수 있으므로, 로그의 question preview가 원문보다 더 자세할 수 있다.

## 로깅
- 비용/로그 대시보드는 아래 형식을 지원한다.
  - raw JSON
  - readable JSON
  - table view
  - HTML dashboard
- HTML 대시보드 현재 기능
  - request/tool 필터
  - 새로고침
  - 페이지 이동
  - 오류 강조 표시

## Suggestion 흐름
- suggestion 생성은 의도적으로 좁게 유지한다.
- 현재 기본 트리거는 다음과 같다.
  - request가 `/ask` 경로를 탔다.
  - 법령 grounding이 흔들리거나 실패했다.
- suggestion은 기본적으로 운영자 검토용 진단 기록이며, 승인된 규칙만 이후 검색 힌트나 우선순위 보강에 반영한다.

## 재시작 / 복구 메모
- `NLIC_OC`는 이제 코드 기본값이 아니라 런타임 환경변수로 받는다.
- HTTP 서버 재시작
  - `python -m src.http_server`
- MCP HTTP 서버 재시작
  - `python -m src.mcp_http_server`
  - `run_mcp_http_server.cmd`
- MCP stdio 서버 재시작
  - `python -m src.mcp_stdio_server`
  - `run_mcp_stdio_server.cmd`
- 런타임 역할 분리
  - `stdio`: 로컬 MCP 클라이언트 연동
  - `8000`: REST/로그 확인용 로컬 서버
  - `8001`: MCP HTTP transport
- `stdio`와 HTTP transport는 같은 코어를 공유한다.
  - `src/mcp_core.py`
  - `RequestPipeline`
- 코드 수정 후 동작이 예전처럼 보이면, 실행 중인 서버 프로세스를 먼저 재시작한다.

## 최근 Retrieval 튜닝
- 민감정보/고유식별정보 질문은 첫 번째 매치 법령에서 멈추지 않도록 보강했다.
  - `lsRlt` 기반 관련 법령 확장
  - 연결 법령 후속 검색
  - 직접 허용 조항이 중요할 때 시행령/시행규칙 우선 탐색
- 키워드 기반 조문 스캔이 explicit article number 없이도 전체 법령 payload에서 직접 조문을 집어올 수 있게 했다.
- 학교밖청소년 + 주민등록번호 질문군에서 현재 안정 동작은 다음과 같다.
  - primary grounding이 `청소년복지 지원법 시행령`으로 이동할 수 있다.
  - 직접 관련 항목이 여러 개면 함께 노출할 수 있다.
  - 답변 본문에 `[직접 관련 항목]` 블록이 포함될 수 있다.

## 직접 관련 항목 처리
- retrieval은 더 이상 `조` 단위에서만 멈추지 않는다.
- 매칭된 조문에 관련 `항/호`가 있으면 여러 직접 관련 항목을 함께 보존할 수 있다.
- 현재 의도는 질문이 여러 법정 사무를 걸칠 때, 하나만 억지로 좁히기보다 2~3개의 높은 관련 항목을 같이 보여주는 것이다.

## 오류 처리 메모
- 예전에는 `get_article`이 NLIC 조문 후보 탐색 중 `HTTP 404` 하나만 나와도 전체 실패로 끝났다.
- 현재 동작은 다음과 같다.
  - 개별 404는 recoverable miss로 취급
  - 다음 `JO` 후보 / target 조합을 계속 시도
  - 후보를 모두 소진한 뒤에만 실패 처리
- 이 변경으로 raw tool 연속 호출이 줄었고, `ask`가 한 번에 끝날 가능성이 높아졌다.

## 링크 정책 업데이트
- 사용자에게 노출되는 링크에는 NLIC `OC` 값이 들어가면 안 된다.
- 사용자용 근거 링크는 DRF query URL보다 공개 브라우저 경로를 우선한다.
  - `https://www.law.go.kr/법령/...`
- 링크 형태도 단순화했다.
  - 법 전체: `/법령/<법령명>`
  - 조문: `/법령/<법령명>/<조문>`
- 날짜/공포번호 tuple 세그먼트는 실제로 링크 파손 가능성을 높여서 제거했다.
- 근거 출력은 아래를 분리한다.
  - 조문/항목 수준 링크
  - 법 전체 링크

## 코드 리뷰 후속 작업 (2026-03-19)
- `code_review.md` 우선순위를 기준으로 retrieval 후속 보강을 적용했다.
- 파이프라인이 더 이상 첫 `search_law` 성공 결과에 고정되지 않는다.
  - 초기 hit를 누적
  - 후보를 전역 재정렬
  - 관련 법령 확장과 시행령/시행규칙 후속 검색 결과까지 다시 반영
- 조문 스캔은 특정 질문군에 묶이지 않도록 일반화했다.
  - 허용 / 예외 / 제한 / 처리 가능 조문을 공통 title/trigger keyword로 탐색
  - 민감정보 질문은 여전히 시행령/시행규칙 가중치가 있지만, 코어 로직 자체는 특정 도메인 하드코딩에서 벗어났다.
- 예전 학교밖청소년 전용 랭킹 보정은 core scoring에서 제거했다.
- MCP 공용 코어를 `src/mcp_stdio_server.py`에서 분리해 `src/mcp_core.py`로 옮겼다.
  - `src/mcp_stdio_server.py`: stdio transport 전용
  - `src/mcp_http_server.py`: 공용 코어 import
- 이 단계 이후 전체 테스트 결과:
  - `Ran 105 tests / OK`

## Retrieval 후속 작업: alias + 시행령 제목 (2026-03-19)
- 민감정보/고유식별정보 질문에서 구어체 약칭 법명이 들어와도, alias 해석을 먼저 시도한 뒤 공식 법령군을 우선 보게 했다.
- 초기 검색어 생성 단계에서 시행령 direct-title query를 더 앞에 배치했다.
  - 예: `<법령명> 시행령 고유식별정보의 처리`
  - 예: `<법령명> 시행령 민감정보 및 고유식별정보의 처리`
- 회귀 테스트 추가
  - `노인일자리법` 같은 alias 질의
  - 공식 시행령 경로 우선
  - `제14조` 같은 직접 허용 조문 grounding

## Retrieval 후속 작업: 범용 alias 정규화 (2026-03-19)
- 서술형 약칭 법명을 매번 하드코딩하지 않도록 alias 정규화를 한 단계 일반화했다.
- 현재 파이프라인은 다음 흐름을 따른다.
  - 질문에서 법령명 후보를 추출
  - `search_law`로 공식 법령명 해석
  - 성공한 alias 정규화 결과를 main retrieval에 다시 투입
- `위법`, `불법`, `적법` 같은 일반 단어가 법령명처럼 오인되지 않도록 explicit law-reference detection을 강화했다.
- 질문이 이미 특정 도메인 법령군을 가리키면, 해당 법령군이 `개인정보 보호법` 같은 일반법에 덜 밀리도록 랭킹을 조정했다.
- 회귀 테스트 추가
  - 서술형 alias canonicalization
  - 아파트 관리 질문에서 `공동주택관리법` 유지
- 이 단계 이후 전체 테스트 결과:
  - `Ran 110 tests / OK`

## 답변 정책 후속 작업 (2026-03-20)
- retrieval은 관련 법령 확장 능력을 유지하되, 답변에서는 아래를 분리하게 했다.
  - 질문에서 직접 언급한 법령군 안의 결과
  - 관련 법령에서 보완적으로 찾은 근거
- `law_enrichment` 안에 `question_law_scope` 요약을 추가해서 answer layer가 아래를 구분할 수 있게 했다.
  - 질문 기준 법령군에서 직접 근거를 찾은 경우
  - 질문 기준 법령군에서는 직접 근거가 없고 관련 법령에서 보완 근거를 찾은 경우
- 이 정책은 “사용자가 법명을 조금 느슨하게 말해도 답을 찾는 현재 시스템의 장점”은 유지하면서도, 관련 법령 근거가 마치 질문한 정확한 법에서 나온 것처럼 보이지 않게 하려는 목적이다.
- answer composition은 아래 순서를 선호한다.
  - 질문 기준 법령군 결과 먼저
  - 관련 법령의 보완 근거는 그다음
- 이 단계 이후 전체 테스트 결과:
  - `Ran 114 tests / OK`

## 답변 계획 도입 (2026-03-20)
- 답변 레이어가 `law_enrichment`에서 바로 문장을 만드는 구조에서, 먼저 `AnswerPlan`을 만든 뒤 렌더하는 구조로 바뀌었다.
- `src/answer_composer.py`는 이제 아래 파생 요소를 plan 단계에서 먼저 준비한다.
  - question-scope block
  - related-article block
  - matched-clause summary
  - 개인정보 처리 실무 프레임
  - evidence block
  - clarification block
- 렌더 경로도 분리했다.
  - grounded article answer
  - law-only answer
  - fallback answer
- clarification도 answer flow 안으로 옮겼다.
  - `RequestPipeline`이 answer composition 전에 `clarification`을 계산
  - `AnswerComposer`가 `[추가 확인 필요]` 블록으로 렌더
  - `src/mcp_core.py`도 같은 힌트를 MCP text output에 노출
- `_matched_clause_labels()`의 숨은 버그도 같이 수정했다.
- 이 단계 이후 전체 테스트 결과:
  - `Ran 124 tests / OK`

## 답변 계획 후속 작업 2 (2026-03-20)
- 초기 `AnswerPlan` 리팩터링을 확장해서, plan 자체를 structured MCP output에도 싣도록 했다.
- `PipelineResponse`는 이제 아래를 함께 가진다.
  - `clarification`
  - `answer_plan`
- 현재 `answer_plan`에 노출되는 주요 필드
  - intent / risk level
  - direct basis
  - question-law scope
  - supplementary basis
  - privacy-processing 여부 / processing actions
  - clarification
- `AnswerComposer`도 정리했다.
  - intent별 내용 선택을 helper로 분리
  - `render_plan()` 중심 렌더
- 이 단계 이후 전체 테스트 결과:
  - `Ran 124 tests / OK`

## 답변 계획 후속 작업 3 (2026-03-20)
- 구조화된 `answer_plan`에 개인정보 처리 질문 전용 `privacy_analysis` 블록을 추가했다.
- 현재 `privacy_analysis`에는 아래 정보가 포함된다.
  - 질문에 행위자 지위가 명시되어 있는지 여부
  - 추론된 처리 행위 (`수집`, `이용`, `제공`, `위탁`, `목적 외 이용·제공`)
  - 추론된 정보 범위 (`general`, `identifier`, `mixed`, `unknown`)
  - 후속 판단에 참고할 법적 체크포인트
  - 추가 확인 필요 여부
- `question_law_scope`도 구조화 plan 안에서 상태값을 같이 노출한다.
  - `direct_basis_found`
  - `supplementary_basis_used`
  - `direct_basis_not_found`
  - `not_applicable`
- 이 단계 이후 전체 테스트 결과:
  - `Ran 125 tests / OK`

## 답변 계획 안정화 (2026-03-20)
- 1/2/3차 answer planning 작업 후 follow-up regression을 점검하고 세 가지 문제를 정리했다.
- `privacy_analysis`가 느슨한 관련 조문만 보고 처리 행위나 정보 범위를 추론하지 않도록 조정했다.
  - 이제 질문 본문과 직접 grounding된 조문을 우선 본다.
  - 그 결과 단순 수집 질문이 관련 조문에 `제공`, `주민등록번호`가 나온다는 이유만으로 과하게 오염되는 false positive를 줄였다.
- explicit law reference가 있는데 scoped grounding이 실패한 경우, fallback `question_law_scope`를 다시 `law_enrichment`에 반영하도록 바꿨다.
- MCP text summary도 planner가 이미 만든 구조화 블록을 다시 덧붙이지 않도록 조정했다.
  - `[결론]`
  - `[근거]`
  - `[직접 관련 항목]`
  - `[추가 확인 필요]`
- 이 단계 이후 전체 테스트 결과:
  - `Ran 127 tests / OK`

## 개인정보 처리 근거 안정화 (2026-03-23)
- 다음과 같은 generic 개인정보 질문에서 대표 근거가 잘못 잡히는 크리티컬 버그를 수정했다.
  - `주민등록번호 수집할 때 정보주체한테 동의받아서 처리하면 되지?`
- 원인은 다음과 같았다.
  - keyword article scan이 민감정보/고유식별정보 관련 문구가 있다는 이유만으로 generic 시행령 조문을 대표 근거로 뽑을 수 있었음
  - 실제 처리 제한 조문이 아니라 개인정보 영향평가 같은 시행령 조문이 메인으로 잡힐 수 있었음
- 그래서 privacy-law fallback 정책을 다음처럼 정리했다.
  1. 먼저 개별 법령 체계(시행령/시행규칙 포함)에서 직접 처리 근거를 찾는다.
  2. 질문이 generic 개인정보법 질문이면, 관련 없는 generic 시행령 조문을 그대로 대표 근거로 두지 않고 개인정보 보호법 본문 조문으로 승격한다.
- 현재 general-law fallback은 아래 순서로 동작한다.
  - 주민등록번호 -> 개인정보 보호법 제24조의2 우선
  - 민감정보 -> 개인정보 보호법 제23조
  - 기타 고유식별정보 -> 개인정보 보호법 제24조
  - 수집/이용 맥락 -> 필요하면 개인정보 보호법 제15조
- 다만 사용자가 아래처럼 범위를 명확히 좁힌 경우엔 fallback 승격을 막는다.
  - 특정 시행령/시행규칙을 직접 말한 경우
  - 특정 조문 번호를 직접 말한 경우
- structured output 일관성도 같이 수정했다.
  - generic privacy-law promotion이 일어난 뒤에는 `question_law_scope`도 같은 law/article로 갱신
  - 그래서 본문 답변과 `answer_plan`, `clarification.current_answer_scope`가 서로 다른 조문을 가리키지 않도록 맞췄다.
- privacy structured analysis도 보강했다.
  - 주민등록번호:
    - 개인정보 보호법 제24조의2에 따라 동의만으로는 부족하다는 특례 문구를 명시
  - 주민등록번호 외 고유식별정보:
    - 개인정보 보호법 제24조에 따른 처리 요건을 별도로 확인하도록 명시
  - 민감정보:
    - 개인정보 보호법 제23조 제한을 checkpoints와 special rules에 포함
- 이 단계 이후 전체 테스트 결과:
  - `Ran 137 tests / OK`
