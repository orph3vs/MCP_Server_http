# Dev Log

## Project Goal
- Build an MCP server for Korean legal Q&A grounded on 국가법령정보센터 data.
- Prioritize law/article/version lookup, precedent lookup, grounded answers, and observable logs over broad speculative reasoning.

## Current Stable Scope
- HTTP server for `/ask`, law tools, precedent tools, logs, and hint suggestions.
- MCP server over stdio/HTTP transports exposing:
  - `ask`
  - `answer_with_citations`
  - `search_law`
  - `get_article`
  - `get_version`
  - `validate_article`
  - `search_precedent`
  - `get_precedent`
- Request pipeline with:
  - law search/query normalization
  - related law hint expansion
  - article/version enrichment
  - precedent enrichment
  - question intent classification
  - high-risk / applicability / illegality-aware answer composition

## Important Design Decisions
- Keep the current retrieval model as the stable `v1` approach.
- Do not enable LLM-based retrieval inference by default because of added runtime cost.
- Suggestions are only for law grounding failures, not for citation-format or answer-composition failures.
- Logs should distinguish between:
  - request-level processing
  - raw MCP tool calls

## Recent Cleanup
- Removed abandoned `v2` retrieval residue from `src/request_pipeline.py`.
- Removed the old unused precedent query builder and kept the refined anchor-based precedent query flow.
- Preserved the current stable precedent search strategy:
  - use a core topic anchor
  - expand with narrower issue terms
  - avoid overly broad standalone precedent queries

## Known Stable Behaviors
- Multi-agent mode may run for `LOW` risk questions when intent is classified as applicability/illegality oriented.
- Precedent search count and final precedent adoption are different:
  - search count > 0 does not guarantee a selected precedent
- MCP clients may rewrite the user question before calling `ask`, so logs can show a more detailed preview than the original user message.

## Logging
- Cost/log dashboard supports:
  - raw JSON
  - readable JSON
  - table view
  - HTML dashboard
- HTML dashboard currently supports:
  - request/tool filter
  - refresh button
  - paging
  - error highlighting

## Suggestion Flow
- Suggestion generation is intentionally narrow.
- Current trigger:
  - request goes through `/ask`
  - law grounding fails at `LawAPI`
- Approved suggestions are intended to strengthen related-law hints later.

## Recovery / Restart Notes
- `NLIC_OC` is now expected from the runtime environment rather than a code default.
- HTTP server restart:
  - `python -m src.http_server`
- MCP HTTP server restart:
  - `python -m src.mcp_http_server`
  - `run_mcp_http_server.cmd`
- MCP stdio server restart:
  - `python -m src.mcp_stdio_server`
  - `run_mcp_stdio_server.cmd`
- Runtime split:
  - `stdio`: local MCP client integration
  - `8000`: REST/log inspection (localhost only)
  - `8001`: MCP transport
- `stdio` and HTTP transports share the same retrieval/answer core (`src/mcp_core.py`, `RequestPipeline`).
- If behavior seems old after code edits, restart the running server process before debugging further.

## Recent Retrieval Tuning
- Sensitive-identifier questions now expand beyond the first matched law:
  - related-law expansion via `lsRlt`
  - follow-up search over connected laws
  - decree-level lookup prioritized when direct permission grounds are likely to matter
- Keyword-guided article scanning now supports direct article pickup from full law payloads, rather than waiting for explicit article numbers in the user query.
- For school-out-youth / resident-number questions, the current stable behavior is:
  - primary grounding can move to `청소년복지 지원법 시행령`
  - direct subclauses can be surfaced together when more than one is materially relevant
  - answer text can include a `[직접 관련 항목]` block

## Direct Clause Handling
- The retrieval layer no longer stops at `조` level only.
- When a matched article contains relevant `항/호/목`, the pipeline can preserve multiple matched clauses.
- Current intended behavior is to show 2-3 highly relevant clause-level items rather than a single narrowed clause when the question reasonably spans multiple statutory tasks.

## Error Handling Notes
- `get_article` previously failed hard when one attempted NLIC article route returned `HTTP 404`.
- Current behavior:
  - treat per-attempt 404 as a recoverable miss
  - continue trying the next `JO` candidate / target combination
  - only surface failure after candidate exhaustion
- This materially reduced unnecessary follow-up raw tool calls from the client and improved the chance that `ask` can finish in one pass.

## Recommended Next Work
- Tune based on real user questions.
- Expand related-law hints only when repeated misses appear.
- Improve weak-grounding detection later if needed.
- Keep the retrieval path cost-controlled unless real usage proves the need for LLM fallback.

## Link Policy Update
- User-facing evidence links should no longer expose NLIC `OC` values.
- Public answer links now prefer open browser routes under `https://www.law.go.kr/법령/...` instead of DRF query URLs.
- Link shape was simplified again:
  - whole law: `/법령/<법령명>`
  - article: `/법령/<법령명>/<조문>`
- The date/promulgation tuple segment was removed from generated public links because it increased the chance of broken pages in practice.
- Evidence output now separates:
  - clause/article-level links
  - whole-law link

## Review Follow-up (2026-03-19)
- Retrieval follow-up work was applied against `code_review.md` priorities rather than another single-case tuning pass.
- The pipeline no longer hard-anchors on the first successful `search_law` hit:
  - initial hits are accumulated
  - merged candidates are re-prioritized globally
  - related-law expansion and follow-up decree/regulation searches are re-ranked again before final grounding
- Clause scanning was generalized beyond one question family:
  - direct permission / exception / prohibition style clauses are now searched through generic title and trigger keywords
  - sensitive-identifier questions still get extra decree/regulation emphasis, but the core scan is no longer tied to one named domain
- The old school-youth-specific ranking boosts were removed from core scoring logic.
- MCP shared core was split out of `src/mcp_stdio_server.py` into `src/mcp_core.py`.
  - `src/mcp_stdio_server.py` now contains stdio transport only
  - `src/mcp_http_server.py` now imports the shared core directly
- Full test suite was green after this refactor pass.

## Retrieval Follow-up (2026-03-19 / alias + decree titles)
- Sensitive-identifier questions that mention a colloquial law alias should now prefer alias-matched official law families before treating the alias text itself as the primary search anchor.
- Initial search query generation now includes decree-level direct-title queries earlier in the flow:
  - e.g. `<법령명> 시행령 고유식별정보의 처리`
  - e.g. `<법령명> 시행령 민감정보 및 고유식별정보의 처리`
- Added regression coverage for:
  - `노인일자리법` alias queries
  - preference for the official decree path
  - grounding to `제14조` style direct permission clauses
## Retrieval Follow-up (2026-03-19 / generic alias normalization)
- Alias handling was pushed one level broader so descriptive shorthand law names do not require one-off code edits whenever possible.
- The pipeline now:
  - extracts likely law-reference candidates from the user question
  - resolves them through `search_law`
  - feeds successful alias-resolution queries back into the main retrieval flow
- Explicit law-reference detection was tightened so generic words like `위법`, `불법`, `적법` are not treated as law names.
- Ranking was adjusted so when a question already points to a domain law family, that family is less likely to be displaced by a general framework law such as `개인정보 보호법`.
- Added regression coverage for:
  - descriptive alias canonicalization (`전자상거래법` -> official law)
  - preserving `공동주택관리법` as primary law for apartment-management questions
- Full suite was green after this alias-normalization pass.

## Answer Policy Follow-up (2026-03-20)
- Retrieval keeps the ability to expand into related laws when needed, but answer composition now separates:
  - the result within the law family explicitly named in the question
  - supplementary grounds found in related laws
- A new `question_law_scope` summary is built inside `law_enrichment` so the answer layer can distinguish:
  - "질문 기준 법령에서 직접 근거를 찾은 경우"
  - "질문 기준 법령에서는 직접 근거를 못 찾았고, 관련 법령을 보완 근거로 쓴 경우"
- This policy is intended to preserve the current system's strength (still finding the answer when the user names a law loosely or partially) without making related-law grounds look like they came from the exact law the user asked about.
- Answer composition now prefers:
  - question-law-family result first
  - supplementary related-law basis second
- Full test suite is green in the current state:
  - `python -m unittest discover -s tests -p 'test_*.py' -q`
  - `Ran 114 tests / OK`

## Answer Planning Follow-up (2026-03-20)
- The answer layer now has an explicit planning step instead of composing directly from `law_enrichment`.
- `src/answer_composer.py` now builds an `AnswerPlan` first and only then renders the final answer.
  - derived fields such as:
    - question-scope block
    - related-article block
    - matched-clause summary
    - privacy-processing practical frame
    - evidence block
    - clarification block
    are prepared in the plan before rendering
- Rendering paths were split into:
  - grounded article answer
  - law-only answer
  - fallback answer
- This reduced the amount of repeated conditional logic inside one long `compose()` path and makes later answer-policy changes easier to isolate from retrieval changes.
- Clarification handling was also moved into the planned answer flow:
  - `RequestPipeline` now computes `clarification` before answer composition
  - `AnswerComposer` renders `[추가 확인 필요]` from that structured data
  - `src/mcp_core.py` also exposes the same clarification hints in MCP text output so clients that only render text still see them
- Fixed a hidden bug in `_matched_clause_labels()` where deduped clause labels were not being collected due to an indentation mistake.
- Current full-suite status after the answer-plan/clarification refactor:
  - `python -m unittest discover -s tests -p 'test_*.py' -q`
  - `Ran 124 tests / OK`

## Answer Planning Follow-up 2 (2026-03-20)
- The initial `AnswerPlan` refactor was extended so the plan is now also exposed in structured MCP output.
- `PipelineResponse` now carries:
  - `clarification`
  - `answer_plan`
- `answer_plan` currently exposes the main elements that matter to the client layer:
  - intent / risk level
  - direct basis
  - question-law scope
  - supplementary basis
  - privacy-processing flag / processing actions
  - clarification
- `AnswerComposer` was further cleaned up:
  - intent-specific content selection now goes through a dedicated helper instead of a long inline chain
  - rendering is centralized through `render_plan()`
- This makes it easier to keep answer policy changes separate from retrieval changes and gives clients a more stable contract than free-form text alone.
- Full suite remains green after the structured-plan exposure:
  - `python -m unittest discover -s tests -p 'test_*.py' -q`
  - `Ran 124 tests / OK`

## Answer Planning Follow-up 3 (2026-03-20)
- The structured `answer_plan` contract now carries a dedicated `privacy_analysis` block for privacy-processing questions.
- `privacy_analysis` currently includes:
  - whether the actor status is explicit in the question
  - inferred processing actions (`수집`, `이용`, `제공`, `위탁`, `목적 외 이용·제공`)
  - inferred data-scope level (`general`, `identifier`, `mixed`, `unknown`)
  - legal-basis checkpoints the client can use for follow-up handling
  - whether clarification is still needed
- `question_law_scope` in the structured plan now also exposes a coarse status:
  - `direct_basis_found`
  - `supplementary_basis_used`
  - `direct_basis_not_found`
  - `not_applicable`
- This pushes one more layer of answer interpretation out of free-form text and into a stable structure that clients can reuse without re-parsing the rendered answer.
- Regression coverage was extended so:
  - ambiguous privacy-processing questions expose `privacy_analysis`
  - MCP structured output keeps carrying that block
  - question-scope status is visible in the serialized plan
- Full suite after this phase:
  - `python -m unittest discover -s tests -p 'test_*.py' -q`
  - `Ran 125 tests / OK`

## Answer Planning Stabilization (2026-03-20)
- The phase-1/2/3 answer-planning work was reviewed for follow-up regressions and three concrete issues were tightened.
- `privacy_analysis` no longer infers processing actions or data scope from loosely related articles by default.
  - The structured analysis now prefers the user question plus the directly grounded article text.
  - This reduces false positives such as turning a simple collection question into a mixed collection/provision/identifier analysis just because a related article mentioned `제공` or `주민등록번호`.
- Fallback `question_law_scope` now persists back into `law_enrichment` when an explicit law reference is present but scoped grounding fails.
  - This keeps clarification and `answer_plan.question_law_scope` aligned with the user's named law family.
- MCP text summaries now avoid re-appending structured sections when the answer text already contains planner-rendered blocks such as:
  - `[결론]`
  - `[근거]`
  - `[직접 관련 항목]`
  - `[추가 확인 필요]`
- Regression coverage was extended for:
  - privacy-analysis false-positive prevention
  - fallback question-scope persistence
  - duplicate clarification block prevention in MCP text summaries
- Full suite after the stabilization pass:
  - `python -m unittest discover -s tests -p 'test_*.py' -q`
  - `Ran 127 tests / OK`
