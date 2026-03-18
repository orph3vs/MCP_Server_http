# Dev Log

## Project Goal
- Build an MCP server for Korean legal Q&A grounded on 국가법령정보센터 data.
- Prioritize law/article/version lookup, precedent lookup, grounded answers, and observable logs over broad speculative reasoning.

## Current Stable Scope
- HTTP server for `/ask`, law tools, precedent tools, logs, and hint suggestions.
- MCP server over HTTP transport exposing:
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
- HTTP server restart:
  - `python -m src.http_server`
- MCP HTTP server restart:
  - `python -m src.mcp_http_server`
  - `run_mcp_http_server.cmd`
- Runtime split:
  - `8000`: REST/log inspection (localhost only)
  - `8001`: MCP transport
- If behavior seems old after code edits, restart the running server process before debugging further.

## Recommended Next Work
- Tune based on real user questions.
- Expand related-law hints only when repeated misses appear.
- Improve weak-grounding detection later if needed.
- Keep the retrieval path cost-controlled unless real usage proves the need for LLM fallback.
