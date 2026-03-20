# Law Hint Suggestion Redesign

## Why this redesign exists

The current suggestion flow mixes two different concerns:

1. diagnostic capture
2. runtime search override

This makes the dashboard hard to understand and makes approved suggestions feel unsafe.

The intended operator workflow is different:

1. a request fails to ground well, or grounds only through fallback laws
2. the server records what happened and why
3. the system proposes what kind of fix may help
4. the operator reviews the proposal
5. the operator either:
   - applies a safe runtime override
   - or requests a code change

In other words:

- suggestion = diagnosis and recommendation
- override = explicit execution rule

They should not be treated as the same thing.

## Current behavior

### Suggestion generation

Suggestions are created when:

- `LawAPI / empty_law_data` occurs
- or the request finds a supplementary basis outside the question law scope

Stored fields already include:

- question summary
- question intent
- related law queries
- search queries
- proposed keywords
- question law family
- question scope direct-basis flag
- supplementary law/article
- matched clause labels

### Approval behavior

Approved suggestions currently become:

- `law_name -> keyword list`

At runtime this means:

- if any approved keyword is found as a substring in the user query
- the approved law name is injected into search normalization and related-law expansion

## Why the current behavior is confusing

### Problem 1: the dashboard does not explain the recommendation

The operator can see:

- what query failed
- what laws were involved
- what keywords were proposed

But cannot clearly answer:

- what exactly went wrong
- why this suggestion was created
- what approving it will change

### Problem 2: `proposed_keywords` look like live search triggers

This is the main trust issue.

`proposed_keywords` are currently shown in a way that suggests:

- "approve these keywords and the system will improve"

But a keyword list is not a precise legal-search rule. If reused directly, it can create false positives.

### Problem 3: diagnosis and action are not separated

The current system jumps too quickly from:

- "this request grounded badly"

to:

- "inject this law for future requests"

That skips the operator judgment layer.

## Design principles

1. Suggestions must describe failures, not act as runtime overrides by themselves.
2. Runtime overrides must be typed and explicit.
3. Free-form keywords should not be used as primary live triggers.
4. The dashboard should explain:
   - why the suggestion exists
   - what kind of change is being recommended
   - whether the recommendation is safe for runtime use
5. Unsafe or broad recommendations should result in a code-change task, not a runtime override.

## New mental model

### A. Suggestion record

Suggestion records are diagnostic artifacts.

They answer:

- what happened
- where grounding failed
- what fallback path succeeded
- what kind of remediation may help

They should not directly decide runtime behavior.

### B. Override rule

Override rules are explicit runtime controls.

They answer:

- under what conditions should search behavior change
- what exact change should happen

Only a subset of recommendation types should be eligible for runtime override.

## Suggested data split

### Suggestion fields

Suggestions should keep or evolve toward these fields:

- `suggestion_type`
- `reason_code`
- `question_summary`
- `user_query`
- `question_intent`
- `question_law_family`
- `question_scope_direct_basis_found`
- `question_scope_article_no`
- `supplementary_law_name`
- `supplementary_article_no`
- `matched_clause_labels`
- `search_queries`
- `related_law_queries`
- `issue_terms`
- `proposed_keywords`
- `recommended_change_type`
- `recommended_change_payload`
- `runtime_safe`
- `operator_note`

### Recommended change types

These are recommendations, not automatic runtime rules:

- `alias_normalization_review`
- `law_family_priority_review`
- `decree_title_priority_review`
- `question_scope_policy_review`
- `no_runtime_action`

Examples:

- If the request used `개보법` and the system only succeeded after broad search:
  - `recommended_change_type = alias_normalization_review`

- If the request asked for a specific law but only found direct basis in supplementary law:
  - `recommended_change_type = question_scope_policy_review`

- If the request succeeded only after deep decree/article fallback:
  - `recommended_change_type = decree_title_priority_review`

## Runtime override types

Runtime overrides should be narrower than suggestions.

Recommended rule types:

### 1. `alias_normalization`

Safe for runtime.

Use when:

- the alias is stable
- the target official law family is clear

Example:

- `개보법 -> 개인정보 보호법`

### 2. `law_family_priority`

Moderately safe for runtime if conditions are narrow.

Use when:

- a question consistently targets one law family
- the query wording is stable enough

Action:

- prioritize that law family in normalization and search ordering

### 3. `decree_title_priority`

Safe only with narrow conditions.

Use when:

- a law family is already identified
- issue type is clear
- a decree/article title pattern repeatedly matters

Action:

- prioritize title patterns such as:
  - `고유식별정보의 처리`
  - `민감정보 및 고유식별정보의 처리`

### 4. `question_scope_policy`

Do not treat as a normal runtime search hint.

This affects answer policy, not just retrieval.

Use when:

- the question names one law
- direct basis is missing there
- supplementary basis is found elsewhere

Action:

- answer should say:
  - direct basis not found in the asked law family
  - supplementary basis found in a related law

This should usually require code or policy review, not a blind runtime override.

## What should happen to `proposed_keywords`

`proposed_keywords` should remain diagnostic only.

They can help the operator understand:

- what issue terms appeared in the request
- what clause labels were matched
- what language seemed to help retrieval

But they should not be approved as direct runtime substring triggers by default.

If kept in the UI, they should be labeled more carefully:

- `diagnostic keywords`
- not `approved keywords`

## Dashboard changes

The dashboard should show three distinct sections for each suggestion:

### 1. What happened

- suggestion type
- reason code
- question law family
- direct basis found in question scope
- supplementary law/article

### 2. Why this matters

- short explanation of the grounding gap
- matched clause labels if any

### 3. Recommended action

- change type
- whether runtime-safe
- if runtime-safe, what override could be created
- if not runtime-safe, whether code or answer-policy review is needed

The key UI question should be:

- "What will approval actually do?"

That answer should be explicit.

## Approval flow after redesign

### Case A: runtime-safe recommendation

Example:

- alias normalization

Flow:

1. operator reviews suggestion
2. operator approves
3. system creates a typed override rule
4. runtime uses that rule

### Case B: not runtime-safe

Example:

- question-scope policy gap
- decree-title priority review that is too broad

Flow:

1. operator reviews suggestion
2. operator marks it for code review or policy review
3. no runtime override is created automatically

## Migration strategy

Recommended migration in stages:

### Stage 1

Keep current suggestion capture, but stop treating approved keywords as the primary runtime mechanism.

### Stage 2

Add:

- `recommended_change_type`
- `recommended_change_payload`
- `runtime_safe`

to suggestion records.

### Stage 3

Introduce a new override storage file for typed runtime rules.

Example:

- `data/law_hint_override_rules.json`

### Stage 4

Deprecate or shrink the old:

- `law_name -> keyword list`

override format.

## Recommended next implementation order

1. Change suggestion schema to include:
   - `recommended_change_type`
   - `recommended_change_payload`
   - `runtime_safe`
2. Update dashboard text to show:
   - what happened
   - why suggestion exists
   - what approval will do
3. Stop presenting `proposed_keywords` as if they are the main approved action
4. Add typed override rule storage
5. Migrate only truly safe approvals to runtime rules
6. Leave broader recommendations as operator review items

## Expected result

After this redesign:

- the dashboard becomes understandable
- suggestions become trustworthy as diagnostics
- runtime overrides become safer
- operators can distinguish:
  - "approve this runtime rule"
  - from
  - "this needs a code/policy change"
