# GenAI Emitters Refactoring Plan

This document is a living plan for refactoring the current PoC emitters (in `util/opentelemetry-util-genai-dev`) to the target reference architecture defined in `README.architecture.md` (reference architecture file colocated in this directory). It includes:
- Gap analysis (Current vs Target)
- Refactoring phases & tasks
- Changelog / Worklog section for an AI Coder Agent
- Engineering directives / execution prompt for the agent
- Acceptance criteria per phase
- Risk & mitigation notes

Keep this document updated as changes land. The AI Coder Agent must append updates under the CHANGELOG and not rewrite existing history.

---
## 1. Reference Documents
- Architecture: `util/opentelemetry-util-genai-dev/README.architecture.md`
- This plan: `util/opentelemetry-util-genai-dev/README.refactoring.emitters.md`

---
## 2. Current State (Summary)
Location: `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/`
Key components:
- `handler.py` (`TelemetryHandler`) owns environment parsing, emitter composition, evaluation emitter composition.
- Emitters implemented as "generators" via `GeneratorProtocol` (in `interfaces.py`).
- `CompositeGenerator` handles ordering with role heuristics (span vs others) and start/finish ordering.
- Environment variables (prefix `OTEL_INSTRUMENTATION_GENAI_*`) drive:
  - which emitters/generators set (span, span_metric, span_metric_event, traceloop_compat)
  - capture of message content (mode & boolean variants)
- Traceloop compatibility span is provided by the `opentelemetry-util-genai-emitters-traceloop` package (core no longer ships the compat emitter).
- No explicit third-party entry point discovery for emitters yet (there is a plugin loader concept via `load_emitter_plugin` but it differs from reference spec: uses `plugins.py` with `PluginEmitterBundle`).
- Splunk-specific emitter logic not present (exists only in separate Splunk dev package `opentelemetry-util-genai-emitters-splunk` but not yet aligned with target CompositeEmitter & EmitterSpec pattern).
- Naming still references "generator" in multiple places.

---
## 3. Target State (Abbreviated)
Per architecture spec:
- `EmitterProtocol` (rename of `GeneratorProtocol`) with `on_start/on_end/on_evaluation_results` (evaluation results optional).
- `CompositeEmitter` orchestrating category-specific chains: span, metrics, content_events, evaluation.
- Env variable prefix remains `OTEL_INSTRUMENTATION_GENAI_*` for emitter and evaluator configuration.
- Emitter registration via entry point group `opentelemetry_util_genai_emitters` returning list of `EmitterSpec` dicts (mirrors evaluator registration style).
- Traceloop-specific emitters extracted to separate package `opentelemetry-util-genai-emitters-traceloop` (no compat placeholder inside core).
- Splunk emitters as a separate package demonstrating replace-category for evaluation and append for metrics.
- Handler slimmed: delegates emitter chain construction and env parsing for emitters to `CompositeEmitter` builder.
- Invocation type filtering (optional field in spec) before dispatch.
- Error isolation per-emitter.

---
## 4. Gap Analysis (Detailed)
| Aspect | Current | Target | Gap / Action |
|--------|---------|--------|--------------|
| Protocol name | `GeneratorProtocol.start/finish/error` | `EmitterProtocol.on_start/on_end/on_evaluation_results` | Rename + adapt method names + add evaluation handler layering |
| Composite orchestrator | `CompositeGenerator` ad-hoc role ordering | `CompositeEmitter` category-based lists (span, metrics, content_events, evaluation) | Implement new class; deprecate old; map existing emitters into categories |
| Env var namespace | `OTEL_INSTRUMENTATION_GENAI_*` | Same | No change needed (retain existing prefix) |
| Configuration parsing location | Inside `TelemetryHandler` | Inside `CompositeEmitter` (handler only calls builder) | Move logic; keep handler minimal |
| Registration/discovery | Custom plugin loader + `extra_emitters` in settings | Entry points returning `EmitterSpec` list | Replace plugin loader path with unified loader; migrate traceloop & splunk packages |
| Traceloop emitter placement | In core dev package | External package | **Completed:** emitted by `opentelemetry-util-genai-emitters-traceloop` |
| Splunk emission pattern | Basic example emitter (not full spec) | Replace evaluation category + append metrics | Expand Splunk package to implement evaluation aggregator + metrics extender |
| Evaluation emission | Separate `CompositeEvaluationEmitter` internal | Part of unified evaluation emitters chain | Fold evaluation emitters into CompositeEmitter evaluation category |
| Message content capture control | Mixed span/events logic in handler refresh | Config-driven category toggles & per-emitter flags | Abstract message capture decisions into emitter initialization & runtime settings |
| Invocation type filtering | `handles()` method per emitter | `invocation_types` list in spec | Provide adapter: wrap old `handles` or generate spec with invocation_types |
| Error isolation | Partial try/except (only error stage) | Wrap each call per emitter & emit counter | Add uniform wrapper & metric/log hook |
| Naming (`generator_kind`) | Terms: generator, generator_kind | Terms: emitter, categories | Rename config keys & adapt tests |
| Tests | Extensive tests referencing generators & traceloop_compat | New tests for registration, ordering, replacement, invocation filtering | Rewrite / remove obsolete tests |

---
## 5. Phased Refactoring Plan
Phases designed to keep repository in a buildable state while minimizing churn. Backward compatibility is not required (dev branch) so we can cut over aggressively after internal consistency is ensured.

### Phase 0: Preparation (Optional Fast Cut)
- Freeze current dev emitters behavior snapshot (tag or doc note) if needed.

### Phase 1: Core Type & Protocol Renaming
Tasks:
1. Introduce `EmitterProtocol` (new file or modify `interfaces.py`).
2. Copy / adapt existing emitters: rename `start`->`on_start`, `finish`->`on_end`, `error` -> remain separate or optional mapping (decide: we keep `error` or merge into `on_end` with error state attribute). For simplicity retain `error` hook temporarily and have CompositeEmitter call it; architecture doc only mandated on_start/on_end but we can extend.
3. Provide a shim class mapping `GeneratorProtocol` to new interface for incremental migration (optional – since no backward compat needed, can just rename).
4. Update imports across code & tests.

Exit Criteria:
- Tests compile after rename (even if many tests marked xfail or pending updates).

### Phase 2: Introduce `CompositeEmitter`
Tasks:
1. Implement new structure with category arrays.
2. Provide adapter function to take legacy emitters and bucket them (SpanEmitter -> span, MetricsEmitter -> metrics, ContentEventsEmitter -> content_events, Evaluation* -> evaluation).
3. Replace `CompositeGenerator` usage in handler with `CompositeEmitter` construction.
4. Remove `CompositeEvaluationEmitter` by merging evaluation emitters into evaluation category.

Exit Criteria:
- Handler uses new composite; old composite removed or deprecated comment.

### Phase 3: Configuration & Env Variable Migration
Tasks:
1. Extend parser to support category-specific env vars (optional granular control) under `OTEL_INSTRUMENTATION_GENAI_EMITTERS_*` (SPAN, METRICS, CONTENT_EVENTS, EVALUATION) while still honoring legacy aggregate `OTEL_INSTRUMENTATION_GENAI_EMITTERS`.
2. Move parsing logic from `handler.py` into a `emitter_config.py` or inside CompositeEmitter builder.
3. Keep existing prefix only (no rename); deprecate `generator_kind` semantics.
4. Update tests to cover category-specific overrides + aggregate fallback.
5. Remove now-obsolete `generator_kind` branching.

Exit Criteria:
- Emission choices driven solely by new env variables.

### Phase 4: Registration Infrastructure
Tasks:
1. Add entry point group to project `pyproject.toml`: `opentelemetry_util_genai_emitters`.
2. Define `load_emitters_entrypoints()` that collects each entry point's list of `EmitterSpec`.
3. Implement ordering, mode application, and invocation type filtering.
4. Add tests for: append, replace-category, replace-same-name ordering collisions.

Exit Criteria:
- External example package (temporary stub) can register an extra metrics emitter via entry point and appears in chain.

### Phase 5: Traceloop Extraction *(completed)*
Delivered:
1. Created `opentelemetry-util-genai-emitters-traceloop` exposing the compat span emitter via entry points.
2. Migrated the legacy emitter out of core and removed handler/config special-casing.
3. Added focused tests ensuring the plug-in captures content and propagates errors correctly.
4. Documentation now instructs installing the plug-in for Traceloop scenarios.

### Phase 6: Splunk Package Alignment
Tasks:
1. Ensure Splunk package implements two emitters: `SplunkEvaluationAggregator` (evaluation kind, mode replace-category) and `SplunkExtraMetricsEmitter` (metrics kind append).
2. Add entry point registration returning both specs.
3. Implement evaluation aggregation logic (batch -> single event with message preview) per architecture.
4. Write tests verifying replacement of evaluation emitter chain & coexistence of metrics emitters.

Exit Criteria:
- Splunk tests pass; evaluation events shape validated.

### Phase 7: Cleanup & Test Rewrite
Tasks:
1. Remove obsolete tests referencing generator kinds & compat paths.
2. Add fresh tests: ordering, env var parsing, invocation type filtering, error isolation, evaluation emission integration.
3. Add minimal performance smoke (ensuring constant-time emitter dispatch overhead measured within threshold; optional).

Exit Criteria:
- Test suite green.

### Phase 8: Documentation & Finalization
Tasks:
1. Update README.rst (dev packages) with new env vars & registration model.
2. Ensure `READEM.architecture.md` still matches implementation; adjust if deviations required.
3. Expand this document CHANGELOG with final milestone summary.

Exit Criteria:
- Docs updated & consistent.

---
## 6. Detailed Task List (Backlog Items)
Numbered for incremental execution (referenced in CHANGELOG):
1. Introduce `EmitterProtocol` replacing `GeneratorProtocol` (interfaces rename).
2. Rename emitter classes method names (start->on_start, finish->on_end) & update references.
3. Implement `CompositeEmitter` with categories; port emitters.
4. Merge evaluation emitters into composite evaluation category.
5. Remove `CompositeEvaluationEmitter` and legacy `CompositeGenerator`.
6. Implement new env var parser (`emitter_config.py`).
7. Add support for `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGES` (span|events|both|none) controlling initialization flags.
8. Remove old `generator_kind` branching in handler.
9. Move emitter configuration building from handler to composite builder.
10. Add entry point group & loader function for emitter specs.
11. Implement ordering + mode resolution logic.
12. Create error wrapping & metrics/logging for per-emitter exceptions.
13. Extract traceloop compat emitter to new package & implement entry point.
14. Remove traceloop special-casing logic from core config.
15. Update tests removing generator/traceloop assumptions.
16. Implement Splunk evaluation aggregator emitter (replace-category behavior).
17. Implement Splunk extra metrics emitter (append behavior).
18. Add tests for Splunk replacement + coexistence scenarios.
19. Implement invocation type filtering using `invocation_types` in spec.
20. Add tests for invocation-type specific emitter (AgentInvocation only metrics example).
21. Documentation: update env var references across repo.
22. Update architecture doc if any pragmatic deviations occurred.
23. Final cleanup: remove deprecated code blocks & transitional shims.

---
## 7. Risks & Mitigations
| Risk | Impact | Mitigation |
|------|--------|-----------|
| Large rename causing transient breakage | Test failures during multi-step PR | Perform rename + adapter in single commit; run tests iteratively |
| Entry point ordering cycles | Undefined final ordering | Detect cycle; log warning; fall back to declared order |
| Performance regression in hot path | Increased latency for each invocation | Pre-resolve emitter lists to plain arrays; avoid dynamic attr lookups |
| Missing evaluation results interface parity | Lost evaluator output | Provide temporary compatibility adapter calling new `on_evaluation_results` |
| Splunk aggregator semantics mismatched | Vendor integration confusion | Write contract test with expected event schema shape |

---
## 8. Acceptance Criteria Summary
- All old generator naming eliminated from core after Phase 7 (except migration notes).
- New env vars fully control emission; old ones optional or removed by design (PoC freedom).
- Installing traceloop or splunk packages modifies emitter chains without code changes.
- Tests exist for: env var parsing, chain replace/append, invocation filtering, evaluation aggregation, error isolation.
- Architecture document remains accurate.

---
## 9. AI Coder Agent Execution Prompt
The following directives guide an automated agent implementing this plan. The agent MUST update the CHANGELOG section below after each logical task group.

### Directives
You are a senior software engineer refactoring the GenAI emitters subsystem to match the reference architecture. Follow SOLID design, keep diffs focused, and maintain incremental buildability.

### Constraints & Requirements
- Do NOT modify non-related subsystems (exporters, unrelated instrumentation) unless required by compilation.
- Prefer creation of new modules over editing large legacy modules until stable.
- Each commit (or logical unit) should keep tests passing or provide temporary skipped tests with TODO markers referencing the task number.
- All new environment variables must continue using the `OTEL_INSTRUMENTATION_GENAI_` prefix.
- The handler must not parse emitter chain env vars after Phase 3.
- Emitters must not raise exceptions out of CompositeEmitter (wrap and log).
- Keep documentation changes synchronized (README, architecture).

### Implementation Notes
- Introduce `emitter_spec.py` for EmitterSpec typing.
- `CompositeEmitter.build_from_environment()` constructs chains: (a) builtin specs (semantic convention), (b) entry point specs, (c) env var overrides.
- Provide a temporary adapter calling old `start/finish` from new `on_start/on_end` if some emitters lag behind during refactor (delete by Task 23).

### Output Expectations
After each task: append to CHANGELOG under appropriate heading with:
```
### Task <n>: <short title>
- Summary of changes
- Files touched
- Follow-ups
```

If blocked, append a BLOCKED section with reason and proposed resolution.

### Prohibited
- Adding new third-party dependencies without explicit necessity
- Introducing global mutable singletons beyond existing handler pattern

---
## 10. CHANGELOG (Agent Maintains Below)
(Agent: append incremental updates here; do not rewrite previous content.)

### Task 0: Document Initialized
- Created initial refactoring plan & gap analysis.
- No code changes yet.

### Task 1: Introduce EmitterProtocol
- Replaced GeneratorProtocol with EmitterProtocol and added evaluation hook scaffold.
- Files touched: `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/interfaces.py`.
- Follow-ups: ensure downstream modules adopt new protocol naming and imports.

### Task 2: Rename emitter lifecycle methods
- Renamed start/finish/error lifecycle hooks to on_start/on_end/on_error across emitters and handler wiring.
- Files touched: `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/emitters/{span.py,metrics.py,content_events.py,traceloop_compat.py,composite.py}`, `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/handler.py`, `util/opentelemetry-util-genai-dev/tests/test_span_metric_event_generator.py`, `util/opentelemetry-util-genai-emitters-splunk/src/opentelemetry/util/genai/emitters/splunk.py`, `util/opentelemetry-util-genai-emitters-splunk/tests/test_splunk_emitters.py`.
- Follow-ups: Future CompositeEmitter implementation should enforce category-aware fanout and remove legacy CompositeGenerator naming.

### Task 3: Implement CompositeEmitter categories
- Replaced CompositeGenerator with CompositeEmitter that orchestrates span, metrics, content, and evaluation emitters with ordered dispatch and defensive error handling.
- Files touched: `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/emitters/composite.py`, `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/emitters/__init__.py`, `util/opentelemetry-util-genai-dev/tests/test_span_metric_event_generator.py`.
- Follow-ups: Extend dispatcher to honour invocation-type filters once emitter specs support them.

### Task 4: Fold evaluation emitters into composite
- Adapted evaluation emitters to implement on_evaluation_results and removed CompositeEvaluationEmitter in favour of CompositeEmitter's evaluation category.
- Files touched: `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/emitters/evaluation.py`, `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/handler.py`.
- Follow-ups: Add metrics/log assertions ensuring evaluation emitters fire when manager reports results.

### Task 5: Update handler and plugins for new emitter architecture
- Reworked handler configuration to build category lists, updated plugin tests, and ensured Splunk emitter implements new protocol.
- Files touched: `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/handler.py`, `util/opentelemetry-util-genai-dev/tests/test_plugins.py`, `util/opentelemetry-util-genai-emitters-splunk/src/opentelemetry/util/genai/emitters/splunk.py`, `util/opentelemetry-util-genai-emitters-splunk/tests/test_splunk_emitters.py`.
- Follow-ups: Future work will introduce emitter spec parsing and environment-driven category overrides.

### Task 6: Implement emitter settings parser
- Replaced legacy generator-centric env parsing with structured Settings including category overrides and capture semantics.
- Files touched: `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/config.py`, `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/environment_variables.py`.
- Follow-ups: Add targeted tests covering category override directives and legacy compatibility.

### Task 7: Add OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGES support
- Introduced the new capture-messages env var and updated helpers to prioritise it over legacy capture flags.
- Files touched: `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/environment_variables.py`, `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/utils.py`, `util/opentelemetry-util-genai-emitters-splunk/src/opentelemetry/util/genai/emitters/splunk.py`.
- Follow-ups: Extend test matrix to assert both legacy and new env vars produce expected capture modes.

### Task 8: Remove generator_kind branching in handler
- Streamlined TelemetryHandler by eliminating generator_kind checks and deferring capture toggles to new capture control metadata.
- Files touched: `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/handler.py`.
- Follow-ups: Ensure future handler logic reads capture allowances from CaptureControl only.

### Task 9: Move emitter composition to builder
- Added emitter spec/build pipeline with category-aware composition and per-category overrides, returning CompositeEmitter plus capture control.
- Files touched: `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/emitters/configuration.py`, `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/emitters/spec.py`, `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/emitters/__init__.py`, `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/handler.py`, `util/opentelemetry-util-genai-dev/tests/test_plugins.py`.
- Follow-ups: Layer entry-point sourced specs and ordering semantics atop the builder.

### Task 10: Introduce emitter spec entry-point loading
- Replaced legacy plugin bundles with spec-based entry point discovery and conversion helpers.
- Files touched: `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/plugins.py`, `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/emitters/configuration.py`, `util/opentelemetry-util-genai-dev/tests/test_plugins.py`.
- Follow-ups: Document the new entry-point contract and add coverage for duplicate spec resolution.

### Task 11: Apply spec mode ordering semantics
- Honoured spec-level modes (append/prepend/replace) and wired the Splunk entry point to replace content events via an emitter spec.
- Files touched: `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/emitters/configuration.py`, `util/opentelemetry-util-genai-emitters-splunk/src/opentelemetry/util/genai/emitters/splunk.py`, `util/opentelemetry-util-genai-emitters-splunk/tests/test_splunk_emitters.py`.
- Follow-ups: Add tests covering prepend and replace-same-name combinations with builtin specs.

### Task 12: Enhance emitter instantiation robustness
- Centralised spec instantiation with defensive logging to isolate emitter factory failures.
- Files touched: `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/emitters/configuration.py`, `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/plugins.py`.
- Follow-ups: Emit telemetry counters for instantiation failures once metrics plumbing is available.

### Task 13: Externalise NLTK sentiment evaluator
- Removed the NLTK sentiment implementation from core builtins and updated demo docs to point to an optional evaluator package.
- Files touched: `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/evaluators/builtins.py`, `util/opentelemetry-util-genai-dev/README.refactoring.emitters.demo-scenarios.md`.
- Follow-ups: Publish package metadata once the refactor branch is merged.

### Task 14: Introduce util/opentelemetry-util-genai-evals-nltk package
- Added standalone NLTK sentiment evaluator plug-in with entry-point registration and tests.
- Files touched: `util/opentelemetry-util-genai-evals-nltk/**`, `util/opentelemetry-util-genai-dev/tests/test_evaluators.py`.
- Follow-ups: Consider bundling VADER lexicon download guidance or automation post-install.

### Task 15: Simplify emitter context & evaluation emission
- Removed Traceloop-specific and span-mode fields from `EmitterFactoryContext`, aligned capture logic, and switched builtin evaluation emission to per-result events.
- Files touched: `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/{config.py,emitters/spec.py,emitters/configuration.py,emitters/evaluation.py,emitters/__init__.py,handler.py,environment_variables.py}`, `util/opentelemetry-util-genai-emitters-splunk/tests/test_splunk_emitters.py`, `.vscode/launch.json`, `util/opentelemetry-util-genai-dev/README.refactoring.emitters.demo-scenarios.md`.
- Follow-ups: Add coverage ensuring Traceloop emitter respects combined capture flags and document per-result evaluation semantics in core README.

### Task 16: Default Deepeval telemetry opt-out & docs refresh
- Opted Deepeval out of its internal telemetry by default within the evaluator plug-in and refreshed demo scenarios / launch configs accordingly.
- Files touched: `util/opentelemetry-util-genai-evals-deepeval/src/opentelemetry/util/evaluator/deepeval.py`, `util/opentelemetry-util-genai-dev/README.refactoring.emitters.demo-scenarios.md`, `.vscode/launch.json`.
- Follow-ups: When publishing the Deepeval adapter, highlight the opt-out behavior in release notes.

### Task 17: Extract Traceloop compat emitter to plug-in
- Moved the Traceloop compatibility emitter into the new `opentelemetry-util-genai-emitters-traceloop` package and removed all core references.
- Files touched: `util/opentelemetry-util-genai-emitters-traceloop/**`, `util/opentelemetry-util-genai-dev/src/opentelemetry/util/genai/{emitters/configuration.py,emitters/__init__.py,config.py,handler.py,environment_variables.py}`, docs, and launch configs.
- Follow-ups: Monitor adoption of the plug-in and remove any lingering mentions of the legacy compat emitter.

### Validation Audit (Implementation Status up to Task 12)
Date: 2025-10-05 *(tasks 13–16 added afterwards; run a fresh audit once remaining milestones land)*

Audit Summary:
- Tasks 1–12 are PRESENT in the codebase and align with the target architecture draft.
- `EmitterProtocol` defined in `interfaces.py`; legacy generator naming removed from active code paths.
- `CompositeEmitter` with category ordering implemented in `emitters/composite.py`.
- Evaluation emitters (`EvaluationMetrics`, `EvaluationEvents`, optional `EvaluationSpans`) integrated as a category inside the composite.
- Env parsing & capture logic delegated to `build_emitter_pipeline` + `Settings`; handler no longer constructs emitters directly (it only invokes the builder).
- Spec-based registration (`EmitterSpec`, `load_emitter_specs`) and category override logic implemented; ordering / replace modes (`replace-category`, `prepend`, `replace-same-name`, `append`) supported.
- Traceloop compat emitter now lives in `opentelemetry-util-genai-emitters-traceloop` and is consumed via entry points.
- Invocation-type filtering NOT YET implemented (pending Task 19 – no `invocation_types` evaluation in dispatch path yet).
- Error isolation: dispatch wrapper catches and logs exceptions (metrics counters still TODO – Task 12 follow-up).

Outstanding (Not Started Unless Noted):
- Task 13–14: Completed (Traceloop extraction & removal of compat from core).
- Task 15: Test suite rewrite / pruning of legacy generator assumptions (partial – some tests still reference old names; needs cleanup pass).
- Task 16–18: Splunk evaluation aggregator & extra metrics emitter (not implemented here – separate package work pending; current Splunk package adaptation status unverified in this audit).
- Task 19–20: Invocation type filtering & tests (not implemented).
- Task 21–22: Documentation sync & architecture drift review (partially pending; README still legacy prior to this audit, will be rewritten).
- Task 23: Final cleanup / shim removal (future).

Next Immediate Actions:
1. Implement invocation-type filtering in composite dispatch or during spec instantiation (Task 19).
2. Add metrics counters for emitter failures (extend Task 12 follow-up).
3. Rewrite README (Task 21) – concise quick start + link to architecture.

Notes:
- Keep CHANGELOG append-only; do not retroactively edit earlier task sections.
- When Task 13 lands, add a new CHANGELOG entry rather than altering this audit.
