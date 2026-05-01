@AGENTS.md

For GenAI streaming wrappers, use `SyncStreamWrapper` and
`AsyncStreamWrapper` from `opentelemetry.util.genai._stream` instead of
reimplementing iteration, close/context-manager, and finalization behavior in
provider packages. Keep provider-specific chunk parsing and telemetry
finalization in private hooks or a narrow mixin, and do not make async stream
wrappers inherit from sync stream wrappers.
