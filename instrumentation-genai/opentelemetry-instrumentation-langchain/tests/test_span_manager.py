import unittest.mock
import uuid

import pytest

from opentelemetry.instrumentation.langchain.span_manager import (
    SpanManager,
    _SpanState,
)
from opentelemetry.trace import SpanKind, get_tracer
from opentelemetry.trace.span import Span


class TestSpanManager:
    @pytest.fixture
    def tracer(self):
        return get_tracer("test_tracer")

    @pytest.fixture
    def handler(self, tracer):
        return SpanManager(tracer=tracer)

    @pytest.mark.parametrize(
        "parent_run_id,parent_in_spans",
        [
            (None, False),  # No parent
            (uuid.uuid4(), False),  # Parent not in spans
            (uuid.uuid4(), True),  # Parent in spans
        ],
    )
    def test_create_span(
        self, handler, tracer, parent_run_id, parent_in_spans
    ):
        # Arrange
        run_id = uuid.uuid4()
        span_name = "test_span"
        kind = SpanKind.INTERNAL

        mock_span = unittest.mock.Mock(spec=Span)

        # Setup parent if needed
        if parent_run_id is not None and parent_in_spans:
            parent_mock_span = unittest.mock.Mock(spec=Span)
            handler.spans[parent_run_id] = _SpanState(
                span=parent_mock_span, context=None
            )

        with (
            unittest.mock.patch.object(
                tracer, "start_span", return_value=mock_span
            ) as mock_start_span,
            unittest.mock.patch(
                "opentelemetry.instrumentation.langchain.span_manager.set_span_in_context"
            ) as mock_set_span_in_context,
            unittest.mock.patch(
                "opentelemetry.instrumentation.langchain.span_manager.get_current"
            ),
        ):
            # Act
            result = handler.create_span(
                run_id, parent_run_id, span_name, kind
            )

            # Assert
            assert result == mock_span
            assert run_id in handler.spans
            assert handler.spans[run_id].span == mock_span

            # Verify parent-child relationship
            if parent_run_id is not None and parent_in_spans:
                mock_set_span_in_context.assert_called_once_with(
                    handler.spans[parent_run_id].span
                )
                mock_start_span.assert_called_once_with(
                    name=span_name,
                    kind=kind,
                    context=mock_set_span_in_context.return_value,
                )
                assert run_id in handler.spans[parent_run_id].children
            else:
                mock_start_span.assert_called_once_with(
                    name=span_name, kind=kind
                )
                mock_set_span_in_context.assert_not_called()
