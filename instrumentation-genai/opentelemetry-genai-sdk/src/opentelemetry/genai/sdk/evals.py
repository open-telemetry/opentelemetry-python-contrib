from abc import ABC, abstractmethod
from opentelemetry._events import Event

from .types import LLMInvocation
from opentelemetry import trace
from opentelemetry.trace import (
    Tracer,
)
from opentelemetry import _events
from .deepeval import evaluate_answer_relevancy_metric
from opentelemetry.trace import SpanContext, Span
from opentelemetry.trace.span import NonRecordingSpan


class EvaluationResult:
    """
    Standardized result for any GenAI evaluation.
    """
    def __init__(self, score: float, details: dict = None):
        self.score = score
        self.details = details or {}


class Evaluator(ABC):
    """
    Abstract base: any evaluation backend must implement.
    """
    @abstractmethod
    def evaluate(self, invocation: LLMInvocation) -> EvaluationResult:
        """
        Evaluate a completed LLMInvocation and return a result.
        """
        pass

class DeepEvalEvaluator(Evaluator):
    """
    Uses DeepEvals library for LLM-as-judge evaluations.
    """
    def __init__(self, event_logger, tracer: Tracer = None, config: dict = None):
        # e.g. load models, setup API keys
        self.config = config or {}
        self._tracer = tracer or trace.get_tracer(__name__)
        self._event_logger = event_logger or _events.get_event_logger(__name__)

    def evaluate(self, invocation: LLMInvocation):
        # stub: integrate with deepevals SDK
        # result = deepevals.judge(invocation.prompt, invocation.response, **self.config)
        human_message = next((msg for msg in invocation.messages if msg.type == "human"), None)
        content = invocation.chat_generations[0].content
        if content is not None and content != "":
            eval_arm = evaluate_answer_relevancy_metric(human_message.content, invocation.chat_generations[0].content, [])
            self._do_telemetry(invocation.messages[1].content, invocation.chat_generations[0].content,
                               invocation.span_id, invocation.trace_id, eval_arm)

    def _do_telemetry(self, query, output, parent_span_id, parent_trace_id, eval_arm):

        # emit event
        body = {
            "content": f"query: {query} output: {output}",
        }
        attributes = {
            "gen_ai.evaluation.name": "relevance",
            "gen_ai.evaluation.score": eval_arm.score,
            "gen_ai.evaluation.reasoning": eval_arm.reason,
            "gen_ai.evaluation.cost": eval_arm.evaluation_cost,
        }

        event = Event(
            name="gen_ai.evaluation.message",
            attributes=attributes,
            body=body if body else None,
            span_id=parent_span_id,
            trace_id=parent_trace_id,
        )
        self._event_logger.emit(event)

        # create span
        span_context = SpanContext(
            trace_id=parent_trace_id,
            span_id=parent_span_id,
            is_remote=False,
        )

        span = NonRecordingSpan(
            context=span_context,
        )

        tracer = trace.get_tracer(__name__)

        with tracer.start_as_current_span("evaluation relevance") as span:
            # do evaluation

            span.add_link(span_context, attributes={
                "gen_ai.operation.name": "evaluation",
            })
            span.set_attribute("gen_ai.operation.name", "evaluation")
            span.set_attribute("gen_ai.evaluation.name", "relevance")
            span.set_attribute("gen_ai.evaluation.score", eval_arm.score)
            span.set_attribute("gen_ai.evaluation.label", "Pass")
            span.set_attribute("gen_ai.evaluation.reasoning", eval_arm.reason)
            span.set_attribute("gen_ai.evaluation.model", eval_arm.evaluation_model)
            span.set_attribute("gen_ai.evaluation.cost", eval_arm.evaluation_cost)
            #span.set_attribute("gen_ai.evaluation.verdict", eval_arm.verdicts)


class OpenLitEvaluator(Evaluator):
    """
    Uses OpenLit or similar OSS evaluation library.
    """
    def __init__(self, config: dict = None):
        self.config = config or {}

    def evaluate(self, invocation: LLMInvocation) -> EvaluationResult:
        # stub: integrate with openlit SDK
        score = 0.0  # placeholder
        details = {"method": "openlit"}
        return EvaluationResult(score=score, details=details)


# Registry for easy lookup
EVALUATORS = {
    "deepeval": DeepEvalEvaluator,
    "openlit": OpenLitEvaluator,
}


def get_evaluator(name: str, event_logger = None, tracer: Tracer = None, config: dict = None) -> Evaluator:
    """
    Factory: return an evaluator by name.
    """
    cls = EVALUATORS.get(name.lower())
    if not cls:
        raise ValueError(f"Unknown evaluator: {name}")
    return cls(event_logger, tracer, config)