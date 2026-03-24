# 개발 로그

## 개요
이 문서는 `MyMcpServer-http`의 최근 구조 변경과 운영 기준을 정리한 로그다.  
초기 목표는 국가법령정보센터 기반 MCP 법률 Q&A 서버를 만들고, `stdio`/`HTTP` transport 모두에서 같은 코어를 재사용하는 것이었다. 최근 작업의 중심은 다음 세 가지였다.

- 질문 기준 법령과 보완 법령을 분리해서 설명하는 답변 정책 정리
- 개인정보 질문과 넓은 법체계 질문의 분류 안정화
- 골든 질문 세트 도입으로 회귀 방지 기준 수립

---

## 1. 공통 MCP 코어 정리
- 공통 MCP 코어를 `src/mcp_core.py`로 분리했다.
- `src/mcp_stdio_server.py`와 `src/mcp_http_server.py`는 transport wrapper 역할만 하도록 정리했다.
- `ask`와 `answer_with_citations`는 같은 `RequestPipeline`을 호출한다.
- 로그는 request 로그와 tool 로그를 구분해 남기도록 유지했다.

의미:
- stdio / HTTP가 서로 다른 구현처럼 보이던 혼선을 줄였다.
- 답변 정책과 retrieval 변경이 transport별로 따로 갈라지지 않게 했다.

---

## 2. 질문 기준 법령 우선 정책
- 질문에 특정 법령이 명시되면 `본법 + 시행령 + 시행규칙`을 우선 검토하는 정책을 넣었다.
- `question_law_scope`를 도입해 아래를 구조적으로 기록한다.
  - 질문 기준 법령군
  - 질문 기준 법령군에서 직접 근거를 찾았는지 여부
  - 현재 primary law / article
- 질문 기준 법령군에서 직접 근거가 없고 관련 법에서만 근거가 나온 경우, 답변에서 그 차이를 드러내도록 정리했다.

의미:
- 사용자가 특정 법을 물었는데 관련 법을 메인 답처럼 섞어 말하는 문제를 줄였다.
- “질문한 법에서 직접 찾은 답”과 “보완 근거”를 구분하는 기반을 만들었다.

---

## 3. AnswerPlan 도입
- 기존에는 retrieval 결과를 바로 텍스트 답변으로 렌더링했다.
- 이를 `AnswerPlan -> render` 구조로 바꿨다.
- 현재 `answer_plan`에는 다음이 포함된다.
  - intent
  - risk level
  - direct basis
  - question_law_scope
  - supplementary_basis
  - privacy_processing_question
  - processing_actions
  - privacy_analysis
  - clarification

의미:
- 텍스트 답변과 structured output을 분리했다.
- 클라이언트가 텍스트를 다시 요약하더라도 핵심 구조는 `answer_plan`으로 유지할 수 있게 했다.

---

## 4. Clarification 도입
- 모호한 질문에 대해 `clarification` 구조를 추가했다.
- 현재 반환 필드:
  - `clarification_needed`
  - `clarification_reason`
  - `missing_facts`
  - `clarification_questions`
  - `decision_sensitivity`
- 텍스트 답변에도 `[추가 확인 필요]` 블록으로 노출되도록 했다.

운영 원칙:
- 강제형 follow-up은 아니다.
- “이 질문은 이런 사실을 더 확인하면 정확도가 올라간다”는 신호를 주는 용도다.

---

## 5. 개인정보 질문 보강
### 5-1. 주민등록번호 / 고유식별정보 / 민감정보 fallback 정리
- generic 개인정보 질문에서 개보법 시행령의 운영 조문이 대표 근거로 잘못 뜨는 문제를 여러 차례 수정했다.
- 현재 일반 fallback 원칙은 다음과 같다.
  - 주민등록번호: `개인정보 보호법 제24조의2`
  - 민감정보: `개인정보 보호법 제23조`
  - 기타 고유식별정보: `개인정보 보호법 제24조`
  - 일반 수집/이용: 필요 시 `개인정보 보호법 제15조`
- 사용자가 특정 시행령/시행규칙/조문 번호를 직접 말한 경우에는 과교정이 일어나지 않도록 승격을 막는다.

### 5-2. privacy_analysis 강화
- `privacy_analysis`에 아래 정보를 구조적으로 담도록 했다.
  - actor_status_explicit
  - processing_actions
  - data_scope
  - identifier_subtype
  - legal_basis_checkpoints
  - special_rules
  - clarification_needed
- 특히 주민등록번호에 대해서는:
  - `동의만으로 처리할 수 없다`
  - `제24조의2가 핵심`
  를 더 강하게 구조화했다.
- 민감정보에 대해서는:
  - `제23조 민감정보 처리 제한`
  을 checkpoints와 special rules에 포함했다.

의미:
- 주민등록번호와 일반 고유식별정보를 같은 층위로 말하는 오류를 줄였다.
- 클라이언트가 재서술하더라도 특례 차이가 structured output에 남도록 했다.

---

## 6. 개인정보 질문 상위 분류 도입
- 개인정보 질문을 다음 보조 카테고리로 멀티태깅하도록 했다.
  - 처리 근거
  - 정보주체 권리
  - 절차/방법
  - 제재/책임
  - 적용 범위/주체
- 이 분류는 기존 `question_intent`를 대체하지 않고, 개인정보 질문에만 보조 해석층으로 붙는다.

활용:
- retrieval relevance 보정
- 조문 스캔 키워드 조정
- 답변 템플릿 선택 보조

의미:
- `동의 철회`, `회원탈퇴`, `과태료`, `제재` 질문이 단순 `처리 일반` 질문으로 흘러가는 문제를 줄였다.

---

## 7. framework_overview 모드 도입
- “관련 법적 근거를 정리해 달라” 같은 넓은 질문은 더 이상 `대표 조문 1개` 방식으로 처리하지 않도록 했다.
- 새 `query_mode`:
  - `single_basis`
  - `framework_overview`
- `framework_overview`에서는 `framework_axes`를 만든다.

예:
- 광고성 정보 전송 규제
- 광고 목적 개인정보 활용
- 광고 내용/표시 규제
- 통신판매/소비자 유인 규제

의미:
- `문자 광고나 온라인 광고의 법적 근거` 같은 질문에 개보법 시행령 일반 조문 하나가 대표로 뜨는 문제를 줄였다.

---

## 8. framework 프로필 외부화
- framework용 법령 축 프로필을 코드에서 분리했다.
- 현재 파일:
  - `config/framework_law_profiles.json`
- `RequestPipeline`은 이 외부 파일을 우선 읽고, 없거나 깨졌을 때만 내부 fallback을 사용한다.

이점:
- 도메인 프로필 수정과 파이프라인 로직 수정을 분리할 수 있다.
- 새 넓은 질문 유형 추가 시 코드 변경 범위를 줄일 수 있다.

현재 운영 원칙:
- 넓은 법체계 질문 실패는 우선 `framework_law_profiles.json` 확장으로 대응
- 단일 근거형 질문에서 엉뚱한 조문을 잡는 문제는 `request_pipeline` 분류/점수/승격 로직 문제로 본다

---

## 9. suggestion 기능 정리
- suggestion은 현재 “자동 수정 엔진”이 아니라 진단/기록에 더 가깝다.
- runtime override 구조는 남아 있지만, 현재 운영 우선순위는 높지 않다.
- 최근에는 suggestion보다:
  - 질문 분류 안정화
  - 골든 질문 회귀 고정
  쪽이 더 중요하다고 판단했다.

운영 판단:
- suggestion은 당장 핵심 기능이 아니다.
- 자동 보정 기능을 키우기보다, 실패 케이스를 분류해서 코드/프로필/골든 질문으로 반영하는 편이 효율적이다.

---

## 10. request_pipeline 정리
- 죽은 1세대 framework 경로를 제거했다.
- 실제 사용 중인 `framework` 경로를 정식 이름으로 정리했다.
- generic 조문 오탐을 줄이기 위해 relevance 조정을 여러 차례 손봤다.
- 최근에는 `위반`, `과태료`, `처벌`, `벌칙`, `제재` 표현을:
  - illegality intent
  - clause scan trigger
  양쪽에 포함시켰다.

의미:
- `문자 광고 수신거부를 했는데 계속 오면 위반이야?` 같은 질문에서 조문 스캔 자체가 꺼지는 문제를 막았다.

---

## 11. 골든 질문 세트
- 문서:
  - `docs/golden-question-set.md`
- 자동 회귀 테스트:
  - `tests/test_golden_question_set.py`

현재 대표 질문군:
- 주민등록번호 동의 처리 질문
- 민감정보 동의 처리 질문
- 고유식별정보 처리 질문
- 학교밖청소년지원센터 주민등록번호 질문
- 노인일자리법 고유식별정보 질문
- 아파트 관리업체 주민정보 질문
- 동의 철회/제재 질문의 privacy category 분류
- 문자/온라인 광고 법적 근거 정리 질문
- 특정 조문 해석 질문
- 문자 광고 수신거부 후 재전송 질문

운영 원칙:
- 새 버그를 고칠 때는 가능하면 해당 질문을 골든 세트 또는 인접 회귀 테스트에 추가한다.
- 골든 세트는 문서가 아니라 실제 회귀 기준으로 사용한다.

---

## 12. 현재 상태 평가
현재 구현 상태는 다음과 같이 정리한다.

완료된 것:
- 공통 MCP 코어
- grounded retrieval 파이프라인
- question_law_scope / clarification / answer_plan / privacy_analysis
- 개인정보 질문 보강
- framework_overview 모드
- framework 프로필 외부화
- 골든 질문 세트 및 자동 회귀 테스트

진행 중인 것:
- 넓은 법체계 질문에 대한 프로필 확장
- 골든 질문 세트 확대
- 운영 중 새 실패 케이스를 상위 분류로 흡수하는 작업

보류 또는 우선순위 낮음:
- suggestion 기능 고도화
- 추가적인 자동 보정 시스템

---

## 최신 검증 결과
- 골든 질문 세트: `Ran 10 tests / OK`
- 전체 테스트: `Ran 155 tests / OK`
