Using dispatching-parallel-agents: one read-only subagent per script, plus a local pass over schemas and clock docs.Dispatching one read-only inventory agent per named script, and reading schemas plus clock/warn strings in parallel.Verifying merge/review/render/clock/warn paths and filling consumer gaps the agents may have missed.Need exact review/render/clock strings and every consumer field. Reading those slices next.Using dispatching-parallel-agents: one read-only inventory per named script. Tables only.

## A. LEDGER MERGE / schema

| step | file:line | what |
|---|---|---|
| merge keys only | `scripts/alx.py:2403-2445` | patch merged into ledger; `sources`/`claims` blocked |
| validate **merged ledger**, not patch | `scripts/alx.py:2447-2449` → `2629-2636` | `_ledger_findings` → `validate_ledger.collect_findings(ledger, schema_path=DEFAULT_SCHEMA, cache_dir=ws.sources)` |
| schema path | `scripts/validate_ledger.py:27` | `references/evidence-ledger.schema.json` |
| load + wrap | `scripts/validate_ledger.py:3082-3088` | `validate_schema` then `_f("ledger/schema", "{location}: {error.message}")` |
| Draft 2020-12 + **all** `iter_errors` | `scripts/validate_ledger.py:3459-3474` | `Draft202012Validator(..., FormatChecker()).iter_errors`; string `{path}: {msg}` |
| print | `scripts/alx.py:2451` → `391-395` → `scripts/gate_severity.py:84-139` | `render_grouped` default `verbose=False` |
| exit | `scripts/alx.py:2427` / `2485` | bad JSON → **1**; else **0** (findings do not fail merge) |

| `[ledger/schema] N — <path>: <msg>` | file:line | one vs all |
|---|---|---|
| compact WARN (merge / `validate_ledger` CLI) | `scripts/gate_severity.py:71-72,95-109` | **ONE line per family**: `[{family}] {len(members)} — {first.message[:160]}` + optional ` — Fix: …`. **N = count, body = first violation only** |
| `ledger/schema` is WARN | `scripts/validate_ledger.py:60-61` | so merge uses compact path, not HARD emit |
| HARD / `--verbose` | `scripts/gate_severity.py:111-132` | ALL items; `ledger/schema` **uncapped** (`cap = len(members)` at `116-119`) |
| merge never passes `verbose=True` | `scripts/alx.py:2451` | **one + count**, not all |

### `required` / `enum` / `minLength` / `minItems` (brief, people, coverage, synthesis)

| JSON path | constraint |
|---|---|
| `$` | **required**: `schema_version,subject,research_question,brief,people,report_date,coverage,sources,claims,synthesis,unresolved_questions` (`references/evidence-ledger.schema.json:6-19`) |
| `$.coverage` | **minItems** `1` (`:47`) |
| `$.brief` | **required**: `intended_reader,decision_or_use,archetype,report_language,editorial_mode,scope` (`:115-122`) |
| `$.brief.intended_reader` | **minLength** `1` (`:126`) |
| `$.brief.decision_or_use` | **minLength** `1` (`:130`) |
| `$.brief.archetype` | **enum** `artifact,concept,event,organization,person,system,hybrid` (`:133-141`) |
| `$.brief.report_language` | **enum** `en,zh-CN,zh-HK` (`:144`) |
| `$.brief.editorial_mode` | **enum** `analytical,narrative,explanatory,investigative,historical,critical` (`:147-154`) |
| `$.brief.scope` | no required/enum/minLength (`:156-159`) |
| `$.people` | array, **no minItems** (`:35-39`) |
| `$.people[]` | **required**: `name` only (`:381`) |
| `$.people[].name` | **minLength** `1` (`:389`) |
| `$.people[].aliases[]` | **minLength** `1` (`:395`) |
| `$.people[]` | no **enum**; `public_role`/`relationship` **not in schema** (`additionalProperties: true` `:380`) |
| `$.coverage[]` | **required**: `area,question,priority,decision_relevance,completion_criteria,status,claim_ids,gap_impact` (`:165-174`) |
| `$.coverage[].area` | **minLength** `1` (`:218`) |
| `$.coverage[].question` | **minLength** `1` (`:221`) |
| `$.coverage[].priority` | **enum** `high,medium,low` (`:225`) |
| `$.coverage[].decision_relevance` | **minLength** `1` (`:229`) |
| `$.coverage[].completion_criteria` | **minLength** `1` (`:233`) |
| `$.coverage[].status` | **enum** `unstarted,in_progress,supported,disputed,gap` (`:239`) |
| `$.coverage[].claim_ids` | **minItems** `1` **if** `status` ∈ `supported,disputed` (`:175-191`) |
| `$.coverage[].gap_impact` | **minLength** `1` **if** `status==gap` (`:207-210`) |
| `$.synthesis` | **required**: `central_judgment_claim_ids,counterevidence_claim_ids,adversarial_tests,implications,decisions_or_takeaways,scenarios,limitations,research_stop_reason` (`:751-760`) |
| `$.synthesis.central_judgment_claim_ids` | **minItems** `1` (`:764`) |
| `$.synthesis.adversarial_tests` | **minItems** `1` (`:781`) |
| `$.synthesis.implications` | **minItems** `1` (`:788`) |
| `$.synthesis.decisions_or_takeaways` | **minItems** `1` (`:795`) |
| `$.synthesis.scenarios` | array, **no minItems** (`:800`) |
| `$.synthesis.limitations[]` | **minLength** `1` (`:810`) |
| `$.synthesis.research_stop_reason` | **minLength** `1` (`:816`) |
| `$.synthesis.implications[]` | **required**: `statement,claim_ids` (`:632`) |
| `$.synthesis.implications[].statement` | **minLength** `1` (`:636`) |
| `$.synthesis.implications[].claim_ids` | **minItems** `1` (`:640`) |
| `$.synthesis.decisions_or_takeaways[]` | **required**: `statement,rationale_claim_ids,tradeoff,success_signal,failure_signal` (`:658-664`) |
| `$.synthesis.decisions_or_takeaways[].statement` | **minLength** `1` (`:668`) |
| `$.synthesis.decisions_or_takeaways[].rationale_claim_ids` | **minItems** `1` (`:672`) |
| `$.synthesis.decisions_or_takeaways[].tradeoff` | **minLength** `1` (`:681`) |
| `$.synthesis.decisions_or_takeaways[].success_signal` | **minLength** `1` (`:685`) |
| `$.synthesis.decisions_or_takeaways[].failure_signal` | **minLength** `1` (`:689`) |
| `$.synthesis.scenarios[]` | **required**: `name,conditions,leading_indicators,disconfirming_indicators,implication,claim_ids` (`:696-703`) |
| `$.synthesis.scenarios[].name` | **minLength** `1` (`:707`) |
| `$.synthesis.scenarios[].conditions` | **minItems** `1`; items **minLength** `1` (`:710-715`) |
| `$.synthesis.scenarios[].leading_indicators` | **minItems** `1`; items **minLength** `1` (`:718-723`) |
| `$.synthesis.scenarios[].disconfirming_indicators` | **minItems** `1`; items **minLength** `1` (`:726-731`) |
| `$.synthesis.scenarios[].implication` | **minLength** `1` (`:735`) |
| `$.synthesis.scenarios[].claim_ids` | **minItems** `1` (`:739`) |
| `$.synthesis.adversarial_tests[]` | **required**: `hypothesis,test,claim_ids,outcome,result,effect_on_conclusion` (`:823-830`) |
| `$.synthesis.adversarial_tests[].hypothesis` | **minLength** `1` (`:834`) |
| `$.synthesis.adversarial_tests[].test` | **minLength** `1` (`:838`) |
| `$.synthesis.adversarial_tests[].claim_ids` | **minItems** `1` (`:842`) |
| `$.synthesis.adversarial_tests[].outcome` | **enum** `supported,rejected,unresolved` (`:850`) |
| `$.synthesis.adversarial_tests[].result` | **minLength** `1` (`:854`) |
| `$.synthesis.adversarial_tests[].effect_on_conclusion` | **minLength** `1` (`:858`) |

## B. CONSUMERS (reads outside jsonschema)

Scope: listed scripts + `validate_ledger.py` semantic (not `iter_errors`). Writes/merge-only omitted.

| field | file:line | does |
|---|---|---|
| `brief` container | `scripts/content_gate.py:531-532,687-688` | dict guard |
| `brief.report_language` | `scripts/content_gate.py:531,687` | compare vs `review.report_lang` → `content/language` |
| `brief.intended_reader` | — | no consumer |
| `brief.decision_or_use` | — | no consumer |
| `brief.archetype` | — | no consumer |
| `brief.editorial_mode` | — | no consumer |
| `brief.scope` (+ `time_horizon,geography,inclusions,exclusions`) | — | no consumer |
| `people` list | `scripts/alx.py:3426-3427` | `derive_person_ids(claim, ledger.get("people"))` on `check --fix` |
| `people` list | `scripts/validate_ledger.py:2244-2255,2568-2585` | dup `person_id`; `person_ids` must exist |
| `people[].person_id` | `scripts/validate_ledger.py:2246-2255,2574-2585` | index + unknown-id WARN |
| `people[].name` | `scripts/validate_ledger.py:232-245,2568-2572` | alias match for auto-link |
| `people[].aliases` | `scripts/validate_ledger.py:235,2568-2572` | same |
| `people[].public_role` | — | no consumer |
| `people[].relationship` | — | no consumer |
| `coverage` list | `scripts/alx.py:2347-2349,2470-2472,3248-3250` | drop filter; missing-claim print; freshness JSON |
| `coverage[]` | `scripts/validate_ledger.py:2219,2312-2358,2459-2481,3062-3072` | ref/status/gap/interested/high-priority vs central |
| `coverage[].area` | `scripts/validate_ledger.py:2315,2322-2354,2475` | error text |
| `coverage[].question` | — | no consumer |
| `coverage[].priority` | `scripts/validate_ledger.py:2325-2328,3064-3072` | high unresolved; central ∈ high |
| `coverage[].decision_relevance` | — | no consumer |
| `coverage[].completion_criteria` | — | no consumer |
| `coverage[].owner` | — | no consumer |
| `coverage[].status` | `scripts/validate_ledger.py:2325-2357,2459-2481` | gap/disputed/supported + interested-only |
| `coverage[].claim_ids` | `scripts/alx.py:2347-2349,2470-2472,3248-3250`; `scripts/validate_ledger.py:2316-2357,2462-2466,3066` | drop/cross-check/freshness/refs |
| `coverage[].gap_impact` | `scripts/validate_ledger.py:2329-2332` | gap must have impact |
| `coverage[].notes` | — | no consumer |
| `synthesis` container | `scripts/alx.py:2351,2473,2639,3201-3220,3252`; `scripts/source_fidelity.py:1262,1594`; `scripts/validate_ledger.py:2940` | strip/freshness/provenance/sample |
| `synthesis.central_judgment_claim_ids` | `scripts/alx.py:2473,2639,3204-3205`; `scripts/source_fidelity.py:1265,1596`; `scripts/validate_ledger.py:2942-3072` | missing-id print; key-source set; sample weight; `disclosure_required`; unknown/key/coverage |
| `synthesis.counterevidence_claim_ids` | `scripts/alx.py:3204-3205`; `scripts/validate_ledger.py:2944-3019` | strip; unknown; must appear in a test |
| `synthesis.adversarial_tests` | `scripts/alx.py:3206-3219`; `scripts/validate_ledger.py:2993-3019` | strip if `claim_ids` emptied; unknown ids |
| `synthesis.adversarial_tests[].claim_ids` | same | only nested field read |
| `synthesis.adversarial_tests[].hypothesis` | — | no consumer |
| `synthesis.adversarial_tests[].test` | — | no consumer |
| `synthesis.adversarial_tests[].outcome` | — | no consumer |
| `synthesis.adversarial_tests[].result` | — | no consumer |
| `synthesis.adversarial_tests[].effect_on_conclusion` | — | no consumer |
| `synthesis.implications` | `scripts/alx.py:3206-3219`; `scripts/validate_ledger.py:3022-3034` | strip; unknown/`claim_ids` ∩ central |
| `synthesis.implications[].claim_ids` | same | only nested field read |
| `synthesis.implications[].statement` | — | no consumer |
| `synthesis.implications[].for_whom` | — | no consumer |
| `synthesis.implications[].timing` | — | no consumer |
| `synthesis.decisions_or_takeaways` | `scripts/alx.py:3206-3219`; `scripts/validate_ledger.py:3035-3047` | strip `rationale_claim_ids`; unknown ∩ central |
| `synthesis.decisions_or_takeaways[].rationale_claim_ids` | same | only nested field read |
| `synthesis.decisions_or_takeaways[].statement` | — | no consumer |
| `synthesis.decisions_or_takeaways[].tradeoff` | — | no consumer |
| `synthesis.decisions_or_takeaways[].success_signal` | — | no consumer |
| `synthesis.decisions_or_takeaways[].failure_signal` | — | no consumer |
| `synthesis.scenarios` | `scripts/validate_ledger.py:3048-3060` | unknown `claim_ids` ∩ central; **not** in `strip_synthesis` buckets |
| `synthesis.scenarios[].claim_ids` | same | only nested field read |
| `synthesis.scenarios[].name` | — | no consumer |
| `synthesis.scenarios[].conditions` | — | no consumer |
| `synthesis.scenarios[].leading_indicators` | — | no consumer |
| `synthesis.scenarios[].disconfirming_indicators` | — | no consumer |
| `synthesis.scenarios[].implication` | — | no consumer |
| `synthesis.limitations` | — | no consumer |
| `synthesis.research_stop_reason` | — | no consumer |
| `validate_report.py` / `md_to_pdf.py` / `pdf_templates.py` / `report_contract.py` / `rewild_gate.py` | — | **no** `brief`/`people`/`coverage`/`synthesis` reads |

## C. REVIEWS

### start skeleton (verbatim keys; values computed)

| kind | file:line | JSON written |
|---|---|---|
| rewild | `scripts/alx.py:3660-3673,3730` | `{"schema_version":1,"status":"draft","report_sha256":<sha>,"source_sha256":<snapshot sha or "">,"report_lang":<lang>,"profile":<PROFILES[lang][0]>,"fidelity_checks":{facts_and_figures,attribution_and_uncertainty,causality,direction_and_negation:false},"findings":[]}` |
| content | `scripts/alx.py:3674-3698,3730` | `{"schema_version":2,"status":"draft","report_path":<ws.report>,"report_sha256":<sha>,"ledger_path":<ledger>,"ledger_sha256":<sha>,"report_lang":<lang>,"reviewed_at":<date.today ISO date>,"reviewer_mode":"fresh_eyes","scores":{8 keys:{score:null,rationale:""}},"checks":{10 keys:false},"section_reviews":[],"visual_assets":[],"findings":[],"evidence_limitations":[],"completion_note":"","claim_support":[]}` |
| keys | `scripts/alx.py:158-179` | score keys / check keys match schema |

### finish: pre-fill vs demand

| field | pre-fill | demand | file:line |
|---|---|---|---|
| `status` | **PRE-FILL** `"completed"` | — | `3756` |
| `section_reviews[].disposition` | **PRE-FILL** `"keep"` if empty | schema `const: keep` via content schema | `3757-3759` |
| rewild `fidelity_checks.*` | start `false` | **DEMAND** `true` | `3103-3107` |
| rewild `findings[].disposition` | — | **DEMAND** `resolved\|rejected`; region/fidelity → `resolved` | `3109-3119` |
| rewild prose `minLength` | — | **DEMAND** `prose_floor_errors` on `rewild-review.schema.json` | `3080-3086,3121` |
| rewild full schema (`status` const, sha pattern, `additionalProperties`) | — | **not run** | — |
| content `scores.*.score` | `null` | **DEMAND** int ≥ 4 | `3124-3129` |
| content `scores.*.rationale` | `""` | **DEMAND** non-empty (+ schema minLength 20 / CJK floor) | `3130-3131,3176` |
| content `checks.*` | `false` | **DEMAND** `true` | `3132-3136` |
| `section_reviews` | `[]` | **DEMAND** ≥1 | `3138-3139` |
| `completion_note` | `""` | **DEMAND** truthy | `3140-3141` |
| content `findings[]` | `[]` | critical → `fixed`; excerpt ∈ report | `3142-3153` |
| `claim_support[].note` | — | **DEMAND** if disposition qualified/removed | `3157-3165` |
| content full schema | — | **DEMAND** `validate_schema(note, content-review.schema.json)` | `3170-3174` |
| `schema_version` | start 1/2 | content: schema `const` 2; rewild: not rechecked | `3663,3675` |
| `report_sha256` / `ledger_sha256` / `source_sha256` | start hash | content: schema hex pattern only; **no current-file compare** | `3665-3680` |
| `reviewed_at` | start **date** (`3682`) | schema **date-time** (`content-review.schema.json:51-53`) → finish WARNs format | `3172` |
| `reviewer_mode` | start `"fresh_eyes"` | schema enum via `validate_schema` | `3683,3172` |

| finish print / exit | file:line |
|---|---|
| **ALL** missing paths | `3763-3768` `WARN review/{kind}: {field}` or `… {field} missing` |
| still marks finished | `3769` |
| success line | `3776` `{kind} review {iteration} finished.` |
| exit | no start → **1** (`3750`); else **0** (`3778`) even with WARNs |

### downstream readers of `reviews/content.json` / `reviews/rewild.json`

| reader | file:line | does |
|---|---|---|
| finish / completeness | `scripts/alx.py:3096-3099,3753-3762` | read/write |
| `check` | `scripts/alx.py:3371-3397` | `content_gate.run_check(..., reviews/content.json)`; completeness + freshness |
| `issue` stamp | `scripts/alx.py:4068-4081` | re-hash if freshness clean |
| `issue` gates | `scripts/alx.py:4086-4110` | `rewild_gate.run_gate(..., reviews/rewild.json)`; `content_gate.run_content_gate(..., reviews/content.json)` |
| `content_gate.run_check` | `scripts/content_gate.py:506-594` | scores/checks/findings/lang; **no sha compare** |
| `content_gate.run_content_gate` | `scripts/content_gate.py:665-784` | same + **HARD** path/sha bind (`748-755`) + visuals |
| `rewild_gate._load_review_note` | `scripts/rewild_gate.py:265-328` | status/schema_version/hashes/lang/profile/fidelity/findings; **sha must match files** |
| `validate_report.py` | — | no review JSON (receipts only) |
| `md_to_pdf.py` `alx render` | `scripts/alx.py:4312-4314` | **receipts**, not `reviews/*.json` |

### `references/rewild-gate.md` vs `rewild-review.schema.json`

| in doc, not schema | in schema, not doc |
|---|---|
| snapshot / `--restore` (`:8-22`) | `additionalProperties: false` (`:5`) |
| non-rewrite zones (`:24-32`) | `schema_version` const `1` (`:18-19`) |
| blind isolation: no ledger/draft (`:36-40`) | `status` const `completed` (start writes `draft`) (`:21-22`) |
| `REWILD_REVIEW_NOTE` path (`:45`) | sha `^[0-9a-f]{64}$` (`:24-30`) |
| “record what you changed” — no field (`:47`) | `report_lang` / `profile` enums (`:32-36`) |
| stale invalid (`:46`) — no rule object | 4 named `fidelity_checks` keys (`:41-46`) |
| semantic reminders (`:49`) | `findings[].category` `style\|region\|fidelity` (`:61-62`) |
| fabricated-figure restore (`:50`) | `disposition` `resolved\|rejected` (`:68-70`) |
| split-remnant cap 8 (`:52-54`) | `finding` minLength 1; `reason` minLength **5** (`:64-73`) |
| `--iter` / mechanical deltas (`:58-61`) | allOf region/fidelity → `resolved` (`:76-92`) |
| | no `reviewed_at` / `reviewer_mode` / `ledger_sha256` / changelog |
| | code `rewild_gate.py:325-327` reason **≥10** > schema 5; finish does not run this schema |

## D. STALENESS

| compare | file:line | print / effect |
|---|---|---|
| review **copy** paragraphs vs current report | `scripts/alx.py:3273-3291` | `review/content-stale` or `review/rewild`: `re-review required: {n} paragraph(s) added or changed and {m} removed since the {kind} review.` |
| content **mechanical ledger** JSON | `scripts/alx.py:3293-3303,3223-3253` | `re-review required: the ledger changed beyond accessed/verified_at/report_excerpts since the content review.` |
| finished + incomplete note | `scripts/alx.py:3389-3394` | `reviews/{kind}.json is incomplete; run \`alx review finish {kind}\`.` |
| review JSON `report_sha256`/`ledger_sha256` vs files in `freshness_findings` | — | **never compared** |
| skip re-stamp if freshness dirty | `scripts/alx.py:4071-4074` | no print; gate sees old hashes |
| `run_content_gate` note vs files | `scripts/content_gate.py:748-755` | HARD `Content review does not match the final report/ledger.` / `belongs to a different …` |
| content receipt vs files | `scripts/content_gate.py:461-469,896-906` | stale skip / HARD mismatch (no word “stale”) |
| rewild note vs report/source sha | `scripts/rewild_gate.py:274-285` | `Blind-review note does not match the reviewed report, source, language, or profile: {names}` |
| rewild receipt sha | `scripts/rewild_gate.py:1377-1379` | overwrite if stale; no “stale” print |
| `issue.json` vs files at render | `scripts/alx.py:4280-4290` | **silent** re-`cmd_issue` |
| `issue.json` vs files in `_next_command` | `scripts/alx.py:4452-4463` | no print; next hint |
| fidelity receipt `ledger_sha256` | `scripts/source_fidelity.py:2166,1884` | `"Source-fidelity receipt does not match the ledger."` |
| md_to_pdf issue/content/rewild receipts | `scripts/md_to_pdf.py:2193-2194,2272-2273,2776-2786` | hash mismatch errors (CLI render) |

## E. CLOCK

| code literal | file:line | role |
|---|---|---|
| `--budget-minutes` default **60** | `scripts/alx.py:4493` | init |
| `timedelta(minutes=args.budget_minutes)` | `scripts/alx.py:1448` | `state.deadline` |
| `// 60` elapsed | `scripts/alx.py:1059` | minutes from `total_seconds` |
| `// 60` remaining | `scripts/alx.py:1060` | same |
| `elapsed {n} min, remaining {n} min` | `scripts/alx.py:1073` | every `_emit` |
| **3600** | — | **absent** |
| **15-min polish** | — | **absent in code** (docs only) |
| `ONLINE_CAP_MINUTES = 4` | `scripts/alx.py:363` | live fetch cap, not 60-min clock |

| doc | line | text |
|---|---|---|
| `SKILL.md` | 8 | `within about 60 min` |
| `SKILL.md` | 252 | `60 min wall-clock from init; every command prints elapsed/remaining… At remaining ≤ 15 min stop polishing: alx issue, alx render…` |
| `README.md` | 13 | `预算 60 分钟。剩余时间不足 15 分钟时执行 alx issue，再执行 alx render` |
| `README.zh-CN.md` | 13 | same |
| `README.zh-HK.md` | 13 | `預算 60 分鐘。剩餘時間不足 15 分鐘時…` |
| `README.en.md` | 13 | `60-minute budget. When remaining time is 15 minutes or less, run alx issue then alx render` |
| `INSTALL.md` | — | **no mention** |
| `references/*.md` | — | **no 60/15 clock** (`content-quality.md:150` is “remaining uncertainty”, not clock) |

## F. `alx render` print templates

| file:line | exact string |
|---|---|
| `scripts/alx.py:4324` | `{template} not rendered: {exc}` (inside `tooling/render`) |
| `scripts/alx.py:4334` | `{template}: {output}` |
| `scripts/alx.py:4349` | `{template} PDF check: {error}` |
| `scripts/alx.py:4351` | `{template} PDF check: passed (text, links, fonts, pages, overflow)` |
| `scripts/alx.py:4355-4356` | `{template} PDF: extractable text {chars} characters (blocked below 500).` |
| `scripts/alx.py:4265-4266` | `{template} contact sheet: PDFKit failed ({reason}); rendered with {selected}` |
| `scripts/alx.py:4376` | `{template} contact sheet not rendered: {exc}` |
| `scripts/alx.py:4387` | `{template} contact sheet: {pages}` |
| `scripts/alx.py:432` | `=== BLOCKED (fix, then alx issue again) ===` |
| `scripts/alx.py:4391` | `no PDF file produced by any template.` |
| `scripts/alx.py:4394` | `produced PDF extractable text is under 500 characters.` |
| `scripts/alx.py:4398` | emit summary `{len(templates)} PDFs` |
| `scripts/validate_report.py:1008` | `PDF has {page_count} pages; minimum is {min_pages}.` (`min_pages=10` at `alx.py:4341`) |
| `scripts/validate_report.py:1011-1012` | `PDF has {n} extracted text characters; minimum is {min_text_chars}.` (`5000`) |
| `scripts/validate_report.py:1016` | `PDF has {n} external clickable links; minimum is {min_links}.` |
| `scripts/validate_report.py:1019` | `PDF is missing title metadata.` |
| `scripts/validate_report.py:1021` | `PDF is missing author metadata.` |
| `scripts/validate_report.py:1026` | `PDF is not tagged for assistive technology.` |
| `scripts/validate_report.py:1029` | `PDF is missing its document language.` |
| `scripts/validate_report.py:1032` | `PDF language is {pdf_lang}; expected {expected_lang}.` |
| `scripts/validate_report.py:1038` | `PDF page {index} is not A4: {width:.2f}x{height:.2f} pt.` |
| `scripts/validate_report.py:1045` | `PDF page sizes are inconsistent.` |
| `scripts/validate_report.py:1047` | `PDF is missing navigation bookmarks.` |
| `scripts/validate_report.py:1071-1072` | `PDF page-quality checks skipped, render backend missing: {exc}` |
| `scripts/validate_report.py:1076` | `PDF page-quality checks could not run: {exc}` |
| `scripts/pdf_quality.py:151-153` (errors) | `ERROR {check} [{where}]: {message}` |
| `scripts/pdf_quality.py:855-860` | `blank_page`: `page carries {pct}% ink inside the content box, needs {min}%` |
| `scripts/pdf_quality.py:875-877` | `blank_page`: `page carries only {n} characters ({mm}mm blank below), needs {min}` |
| `scripts/pdf_quality.py:887-892` | `sparse_page` WARN: `content stops after {pct}% of the text block ({mm}mm blank below), needs {min}%` |
| `scripts/pdf_quality.py:774-780` | `overflow`: `text box escapes the page: (…) outside 0..W x 0..H` |
| `scripts/pdf_quality.py:828-831` | `header_gap`: `running header sits {mm}mm above the first body line, needs {min}mm` |
| `scripts/validate_report.py:1078-1083` | WARN wrap: `WARNING: {check} [{where}]: {message}` |
| executive vs atlas/terrain **page parity** | **no string / no compare** |
| PDF **file byte size** | **not printed** (`md_to_pdf.py:2938,2961` `[OK] HTML/PDF generated:` unused by `alx render`) |

## G. Other message families (not fabrication HARD, not 4 BLOCKED)

Excluded: `fidelity/mismatch`; `fidelity/quotation-lost`; `integrity/quotation-lost`; `binding/link-not-in-ledger`; BLOCKED `issue/snapshot`; `integrity/length` 2/3 floor (`alx.py:518-525`); `integrity/encoding`; render no-PDF / `<500` chars.

| family | subcommand | file:line | checks (≤12 words) | REPORT vs SHAPE |
|---|---|---|---|---|
| `ledger/schema` | merge,check,issue | `validate_ledger.py:3088` | JSON Schema on merged ledger | SHAPE |
| `ledger/status` | check,issue | `validate_ledger.py:32` | status words unevidenced | REPORT |
| `ledger/direction` | check,issue | `validate_ledger.py:33` | direction unevidenced | REPORT |
| `ledger/quantity` | check,issue | `validate_ledger.py:31` | figure not in extract (WARN) | REPORT |
| `ledger/source-ids` | check | `validate_ledger.py:35` | source_ids vs source_evidence | SHAPE |
| `ledger/https` | check,issue | `validate_ledger.py:36` | source URL not https | SHAPE |
| `ledger/provenance` | check,issue | `alx.py:2678`; `validate_ledger.py:37` | unverified/interested on key/coverage | REPORT |
| `ledger/key-claim` | check,issue | `validate_ledger.py:38` | key-claim source rules | REPORT |
| `ledger/portfolio` | check,issue | `validate_ledger.py:39` | no independent source | REPORT |
| `ledger/coverage` | check,issue | `validate_ledger.py:40` | coverage status vs claims | REPORT |
| `ledger/synthesis` | check,issue | `validate_ledger.py:41` | synthesis claim-id rules | REPORT |
| `ledger/source-family` | check | `validate_ledger.py:42` | domain/family split | SHAPE |
| `ledger/derived` | check,issue | `validate_ledger.py:43` | derived_assertions rules | REPORT |
| `ledger/person` | check | `validate_ledger.py:44` | person_ids vs people | SHAPE |
| `ledger/excluded-supports` | check,issue | `validate_ledger.py:45` | supports excluded claim | SHAPE |
| `ledger/undated-reason` | check,issue | `validate_ledger.py:46` | undated time-sensitive source | SHAPE |
| `ledger/host-conflict` | check,issue | `validate_ledger.py:47` | same-host provenance clash | SHAPE |
| `ledger/claim-input` | claim add,check | `validate_ledger.py:48` | claim-input schema | SHAPE |
| `ledger/extract-length` | check,issue | `validate_ledger.py:49` | extract too short | SHAPE |
| `ledger/triangulation` | check,issue | `validate_ledger.py:50` | triangulation vs families | REPORT |
| `ledger/freshness` | check | `validate_ledger.py:51` | dates vs report/cache | SHAPE |
| `ledger/reference` | check,issue | `validate_ledger.py:52` | unknown ids / synthesis links | SHAPE |
| `fidelity/cache-missing` | check,issue | `alx.py:2647` | missing `sources/*.txt` | SHAPE |
| `fidelity/cache-detached` | check,issue | `alx.py:2662` | cache URL/sha mismatch | SHAPE |
| `fidelity/context-changed` | check,issue | `source_fidelity.py:1110` | probe window drifted | REPORT |
| `fidelity/unreachable` | issue | `alx.py:346-349` | live fetch down | SHAPE |
| `fidelity/undecodable` | issue | `alx.py:346-349` | live fetch undecodable | SHAPE |
| `fidelity/semantic` | check,issue | `rewild_gate.py:1386` | direction/negation/causal drift | REPORT |
| `fidelity/rewild` | check,issue | `rewild_gate.py:1387` | hard checker Fidelity | REPORT |
| `integrity/structure` | check,issue | `validate_report.py:93` | H1 / standfirst | SHAPE |
| `integrity/date-line` | check,issue | `validate_report.py:95` | date line format | SHAPE |
| `integrity/length` | check | `validate_report.py:96` | band (not 2/3 BLOCKED) | REPORT |
| `integrity/control-chars` | check,issue | `validate_report.py:92` | C0 controls | SHAPE |
| `integrity/replacement-char` | check,issue | `validate_report.py:93` | U+FFFD | SHAPE |
| `binding/claim-paragraph` | check,issue | `validate_report.py:99` | `report_paragraph` bind | SHAPE |
| `binding/excerpt-missing` | check,issue | `alx.py:316` | missing excerpts | SHAPE |
| `binding/leftover-prose` | check,issue | `alx.py:317` | dropped-claim prose left | SHAPE |
| `binding/sources-section` | check | `validate_report.py:100` | Sources H2 list | SHAPE |
| `content/score` | check,issue | `content_gate.py:93` | score &lt; 4 | REPORT |
| `content/check` | check,issue | `content_gate.py:94` | review check false | REPORT |
| `content/critical-finding` | check,issue | `content_gate.py:95` | unfixed critical | REPORT |
| `content/disclosure` | check,issue | `content_gate.py:96` | excerpt not in report | REPORT |
| `content/language` | check,issue | `content_gate.py:97` | note lang vs brief | SHAPE |
| `rewild/region` | check,issue | `rewild_gate.py:1388` | locale/register | REPORT |
| `rewild/ai-vocabulary` | check,issue | `rewild_gate.py:1389` | AI diction | REPORT |
| `rewild/style` | check,issue | `rewild_gate.py:1390` | style warnings | REPORT |
| `rewild/length` | check,issue | `rewild_gate.py:1391` | rewild length band | REPORT |
| `rewild/checker` | check,issue | `rewild_gate.py:1392` | checker subprocess | SHAPE |
| `review/rewild` | check,issue | `alx.py:3267`; `rewild_gate.py:1393` | missing/stale/bad note | SHAPE |
| `review/content-missing` | check,issue | `alx.py:3267` | content review not finished | SHAPE |
| `review/content-stale` | check,issue | `alx.py:3288,3300,3392` | paragraphs/ledger/incomplete | SHAPE |
| `tooling/receipt` | issue | `alx.py:320` | receipt tooling (class A) | SHAPE |
| `tooling/render` | render,issue | `alx.py:4327,4379` | PDF/contact-sheet degrade | SHAPE |
| `review-finish` | review finish | `alx.py:3766-3768` | incomplete note fields | SHAPE |
| `ledger-merge-keys` | ledger merge | `alx.py:2462,2481` | ignored keys / missing claim ids | SHAPE |

## H. SCHEMA FILES

### `references/content-review.schema.json`

| path | constraint |
|---|---|
| `$` | **required**: `schema_version,status,report_path,report_sha256,ledger_path,ledger_sha256,report_lang,reviewed_at,reviewer_mode,scores,checks,section_reviews,visual_assets,findings,evidence_limitations,completion_note` (`:6-24`) |
| `$.schema_version` | const `2` (`:27`) |
| `$.status` | const `completed` (`:30`) |
| `$.report_path` | minLength `1` (`:34`) |
| `$.ledger_path` | minLength `1` (`:42`) |
| `$.report_lang` | enum `en,zh-CN,zh-HK` (`:49`) |
| `$.reviewer_mode` | enum `independent,fresh_eyes` (`:56`) |
| `$.scores` | **required** 8 keys (`:61-70`) |
| `$.scores.*.score` | integer 1–5 (`:190-193`) |
| `$.scores.*.rationale` | minLength `20` (`:197`) |
| `$.scores[]` item | **required** `score,rationale` (`:188`) |
| `$.checks` | **required** 10 booleans (`:101-112`) |
| `$.section_reviews` | minItems `1` (`:154`) |
| `$.section_reviews[]` | **required**: `section_heading,purpose,new_value,evidence_or_reasoning,limitation_or_tradeoff,contribution_to_governing_question,disposition` (`:204-212`) |
| `$.section_reviews[].section_heading` | minLength `1` (`:216`) |
| `$.section_reviews[].purpose` | minLength `20` (`:220`) |
| `$.section_reviews[].new_value` | minLength `20` (`:224`) |
| `$.section_reviews[].evidence_or_reasoning` | minLength `20` (`:228`) |
| `$.section_reviews[].limitation_or_tradeoff` | minLength `20` (`:232`) |
| `$.section_reviews[].contribution_to_governing_question` | minLength `20` (`:236`) |
| `$.section_reviews[].disposition` | const `keep` (`:239`) |
| `$.visual_assets[]` | **required**: `path,sha256,usage,visible_text_and_claims_review,disposition` (`:246-252`) |
| `$.visual_assets[].path` | minLength `1` (`:256`) |
| `$.visual_assets[].usage` | enum `body,cover,body_and_cover` (`:263`) |
| `$.visual_assets[].visible_text_and_claims_review` | minLength `20` (`:267`) |
| `$.visual_assets[].disposition` | const `approved` (`:270`) |
| `$.evidence_limitations[]` | minLength `1` (`:169`) |
| `$.completion_note` | minLength `1` (`:175`) |
| `$.claim_support[]` | **required**: `claim_id,paragraph,disposition,note` (`:277`) |
| `$.claim_support[].claim_id` | minLength `1` (`:281`) |
| `$.claim_support[].disposition` | enum `supported,qualified,removed` (`:288`) |
| `$.claim_support[].note` | minLength `1` (`:292`) |
| `$.findings[]` | **required**: `finding_id,severity,category,location,finding,disposition,rationale,report_disclosure_excerpt` (`:299-308`) |
| `$.findings[].severity` | enum `critical,major,minor` (`:315`) |
| `$.findings[].category` | enum `scope,evidence,reasoning,counterevidence,depth,decision_value,forecast,structure,writing` (`:318-328`) |
| `$.findings[].location` | minLength `1` (`:332`) |
| `$.findings[].finding` | minLength `1` (`:336`) |
| `$.findings[].disposition` | enum `fixed,accepted_limitation,rejected` (`:339`) |
| `$.findings[].rationale` | minLength `1` (`:343`) |

### `references/rewild-review.schema.json`

| path | constraint |
|---|---|
| `$` | **required**: `schema_version,status,report_sha256,source_sha256,report_lang,profile,fidelity_checks,findings` (`:6-16`) |
| `$.schema_version` | const `1` (`:19`) |
| `$.status` | const `completed` (`:22`) |
| `$.report_lang` | enum `en,zh-CN,zh-HK` (`:33`) |
| `$.profile` | enum `rewild,rewild-zh,rewild-hk` (`:36`) |
| `$.fidelity_checks` | **required**: `facts_and_figures,attribution_and_uncertainty,direction_and_negation,causality` (`:41-46`) |
| `$.findings[]` | **required**: `category,finding,disposition,reason` (`:59`) |
| `$.findings[].category` | enum `style,region,fidelity` (`:62`) |
| `$.findings[].finding` | minLength `1` (`:66`) |
| `$.findings[].disposition` | enum `resolved,rejected`; region/fidelity → const `resolved` (`:69,88`) |
| `$.findings[].reason` | minLength `5` (`:73`) |

### `references/claim-input.schema.json`

| path | constraint |
|---|---|
| `$` | **required**: `claim_id,claim,source_evidence` (`:6-10`) |
| `$.claim` | minLength `1` (`:19`) |
| `$.kind` | enum `fact,reported_claim,estimate,analysis` (`:22`) |
| `$.importance` | enum `key,supporting,context` (`:25`) |
| `$.source_evidence` | minItems `1` (`:29`) |
| `$.source_evidence[]` | **required**: `source_id,extract_or_location` (`:33`) |
| `$.source_evidence[].extract_or_location` | minLength `1` (`:41`) |
