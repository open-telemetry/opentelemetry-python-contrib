from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol, Sequence

from opentelemetry.context import Context
from opentelemetry.trace import Link, SpanKind, TraceState
from opentelemetry.util.types import Attributes


@dataclass(frozen=True)
class SamplingIntent:
    threshold: int
    adjusted_count_reliable: bool = field(default=True)
    attributes: Attributes = field(default=None)
    update_trace_state: Callable[[TraceState], TraceState] = field(
        default=lambda ts: ts
    )


class ComposableSampler(Protocol):
    def sampling_intent(
        self,
        parent_ctx: Optional[Context],
        name: str,
        span_kind: Optional[SpanKind],
        attributes: Attributes,
        links: Optional[Sequence[Link]],
        trace_state: Optional[TraceState],
    ) -> SamplingIntent:
        """Returns information to make a consistent sampling decision."""
        ...

    def get_description(self) -> str:
        """Returns a description of the sampler."""
        ...
