# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
The **OpenTelemetry Rich Console Exporter** provides a span exporter from a batch span processor
to print `OpenTelemetry`_ traces using `Rich`_.

Installation
------------

::

    pip install opentelemetry-exporter-richconsole


Usage
-----

The Rich Console Exporter is a console exporter that prints a tree view onto stdout of the traces
with the related spans and properties as children of that tree. The Rich Console Exporter must be
used with a BatchSpanProcessor.

.. code:: python

    from opentelemetry import trace
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.richconsole import RichConsoleExporter
    from opentelemetry.sdk.trace import TracerProvider

    trace.set_tracer_provider(TracerProvider())
    tracer = trace.get_tracer(__name__)

    tracer.add_span_processor(BatchSpanProcessor(RichConsoleExporter()))


API
---
.. _Rich: https://rich.readthedocs.io/
.. _OpenTelemetry: https://github.com/open-telemetry/opentelemetry-python/
"""
# pylint: disable=import-error

import datetime
import typing
from typing import Optional

from rich.console import Console
from rich.syntax import Syntax
from rich.text import Text
from rich.tree import Tree

import opentelemetry.trace
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.semconv.trace import SpanAttributes


def ns_to_time(nanoseconds):
    ts = datetime.datetime.utcfromtimestamp(nanoseconds / 1e9)
    return ts.strftime("%H:%M:%S.%f")


class RichConsoleSpanExporter(SpanExporter):
    """Implementation of :class:`SpanExporter` that prints spans to the
    console.

    Must be used within a BatchSpanProcessor
    """

    def __init__(
        self,
        service_name: Optional[str] = None,
    ):
        self.service_name = service_name
        self.console = Console()

    def _child_to_tree(self, child: Tree, span: ReadableSpan):
        child.add(
            Text.from_markup(f"[bold cyan]Kind :[/bold cyan] {span.kind.name}")
        )
        if not span.status.is_unset:
            if not span.status.is_ok:
                child.add(
                    Text.from_markup(
                        f"[bold cyan]Status :[/bold cyan] [red]{span.status.status_code}[/red]"
                    )
                )
            else:
                child.add(
                    Text.from_markup(
                        f"[bold cyan]Status :[/bold cyan] {span.status.status_code}"
                    )
                )
        if span.status.description:
            child.add(
                Text.from_markup(
                    f"[bold cyan]Description :[/bold cyan] {span.status.description}"
                )
            )

        if span.events:
            events = child.add(
                label=Text.from_markup(f"[bold cyan]Events :[/bold cyan] ")
            )
            for event in span.events:
                event_node = events.add(Text(event.name))
                for k, v in event.attributes.items():
                    event_node.add(
                        Text.from_markup(f"[bold cyan]{k} :[/bold cyan] {v}")
                    )
        if span.attributes:
            attributes = child.add(
                label=Text.from_markup(f"[bold cyan]Attributes :[/bold cyan] ")
            )
            for attribute in span.attributes:
                if attribute == SpanAttributes.DB_STATEMENT:
                    attributes.add(
                        Text.from_markup(
                            f"[bold cyan]{attribute} :[/bold cyan] "
                        )
                    )
                    attributes.add(Syntax(span.attributes[attribute], "sql"))
                else:
                    attributes.add(
                        Text.from_markup(
                            f"[bold cyan]{attribute} :[/bold cyan] {span.attributes[attribute]}"
                        )
                    )

    def export(self, spans: typing.Sequence[ReadableSpan]) -> SpanExportResult:
        if not spans:
            return SpanExportResult.SUCCESS
        tree = Tree(
            label=f"Trace {opentelemetry.trace.format_trace_id(spans[0].context.trace_id)}"
        )
        parents = {}
        for span in spans:
            if not span.parent:
                ...
            child = tree.add(
                label=Text.from_markup(
                    f"[blue][{ns_to_time(span.start_time)}][/blue] [bold]{span.name}[/bold], span {opentelemetry.trace.format_span_id(span.context.span_id)}"
                )
            )
            parents[span.context.span_id] = child
            self._child_to_tree(child, span)

        for span in spans:
            if span.parent and span.parent.span_id not in parents:
                child = tree.add(
                    label=Text.from_markup(
                        f"[blue][{ns_to_time(span.start_time)}][/blue] [bold]{span.name}[/bold], span {opentelemetry.trace.format_span_id(span.context.span_id)}"
                    )
                )
            else:
                child = parents[span.parent.span_id].add(
                    label=Text.from_markup(
                        f"[blue][{ns_to_time(span.start_time)}][/blue] [bold]{span.name}[/bold], span {opentelemetry.trace.format_span_id(span.context.span_id)}"
                    )
                )
            parents[span.context.span_id] = child
            self._child_to_tree(child, span)

        self.console.print(tree)
        return SpanExportResult.SUCCESS
