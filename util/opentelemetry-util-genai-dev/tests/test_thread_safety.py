import threading

from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import (
    EmbeddingInvocation,
    LLMInvocation,
    ToolCall,
)


def test_thread_safety_parallel_invocations():
    handler = get_telemetry_handler()
    lock = threading.Lock()
    tool_calls = []
    embeddings = []
    llms = []
    errors = []

    def run_tool(i):
        try:
            inv = ToolCall(name=f"tool{i}", id=str(i), arguments={"i": i})
            handler.start_tool_call(inv)
            handler.stop_tool_call(inv)
            with lock:
                tool_calls.append(inv)
        except Exception as e:  # pragma: no cover - debugging aid
            with lock:
                errors.append(e)

    def run_embedding(i):
        try:
            inv = EmbeddingInvocation(
                request_model="embed-model", input_texts=[f"t{i}"]
            )
            handler.start_embedding(inv)
            handler.stop_embedding(inv)
            with lock:
                embeddings.append(inv)
        except Exception as e:  # pragma: no cover
            with lock:
                errors.append(e)

    def run_llm(i):
        try:
            inv = LLMInvocation(request_model="model-x")
            handler.start_llm(inv)
            handler.stop_llm(inv)
            with lock:
                llms.append(inv)
        except Exception as e:  # pragma: no cover
            with lock:
                errors.append(e)

    threads = []
    for i in range(5):
        threads.append(threading.Thread(target=run_tool, args=(i,)))
        threads.append(threading.Thread(target=run_embedding, args=(i,)))
        threads.append(threading.Thread(target=run_llm, args=(i,)))

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert not errors, f"Errors occurred in threads: {errors}"
    # Basic assertions: all invocations have spans and end_time set (where applicable)
    assert len(tool_calls) == 5
    assert len(embeddings) == 5
    assert len(llms) == 5
    for inv in tool_calls + embeddings + llms:
        assert inv.span is not None
        assert inv.end_time is not None
