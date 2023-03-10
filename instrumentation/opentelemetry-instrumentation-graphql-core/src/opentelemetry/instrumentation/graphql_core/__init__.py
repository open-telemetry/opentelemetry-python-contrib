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
Instrument `GraphQL-core`_ to trace the parsing, validation and execution of queries.

There are two options for instrumenting code. The first option is to use the
``opentelemetry-instrument`` executable which will automatically
instrument your GraphQL-core client. The second is to programmatically enable
instrumentation via the following code:

.. _GraphQL-core: https://pypi.org/project/graphql-core/

Usage
-----

.. code:: python

    # Instrument GraphQL-core
    from opentelemetry.instrumentation.graphql_core import GraphQLCoreInstrumentor

    GraphQLCoreInstrumentor().instrument()

    # This will create a span with GraphQL-specific attributes
    from graphql import (
        GraphQLField,
        GraphQLObjectType,
        GraphQLSchema,
        GraphQLString,
        graphql,
    )

    def resolve_hello(parent, info):
        return "Hello world!"

    schema = GraphQLSchema(
        query=GraphQLObjectType(
            name="RootQueryType",
            fields={
                "hello": GraphQLField(GraphQLString, resolve=resolve_hello)
            },
        )
    )

    await graphql(schema, "{ hello }")

API
---
The `instrument` method accepts the following keyword args:

tracer_provider (TracerProvider) - an optional tracer provider
skip_default_resolvers (Boolean) - whether to skip spans for default resolvers. True by default.

for example:

.. code: python

    # Instrument GraphQL-core
    from opentelemetry.instrumentation.graphql_core import GraphQLCoreInstrumentor

    GraphQLCoreInstrumentor().instrument(skip_default_resolvers=False)
"""

import importlib
import re
from typing import (
    Any,
    Callable,
    Collection,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
    cast,
)

import graphql
from graphql import (
    DocumentNode,
    ExecutionContext,
    FieldNode,
    GraphQLError,
    GraphQLField,
    GraphQLFieldResolver,
    GraphQLObjectType,
    OperationDefinitionNode,
    Source,
    default_field_resolver,
    get_operation_ast,
)
from graphql.execution.execute import get_field_def
from graphql.language.parser import SourceType

try:
    # Faster, but only available from 3.1.0 onwards
    from graphql.pyutils import is_awaitable
except ImportError:
    from inspect import isawaitable as is_awaitable

from wrapt import wrap_function_wrapper

from opentelemetry import context
from opentelemetry.instrumentation.graphql_core.package import _instruments
from opentelemetry.instrumentation.graphql_core.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import (
    _SUPPRESS_INSTRUMENTATION_KEY,
    unwrap,
)
from opentelemetry.trace import Span, get_tracer

graphql_module = importlib.import_module("graphql.graphql")
graphql_execute_module = importlib.import_module("graphql.execution.execute")


class GraphQLCoreInstrumentor(BaseInstrumentor):
    """An instrumentor for GraphQL-core.

    See `BaseInstrumentor`
    """

    def __init__(self) -> None:
        super().__init__()
        self._tracer = None
        self.skip_default_resolvers = False

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        self._tracer = get_tracer(
            __name__, __version__, kwargs.get("tracer_provider")
        )
        self.skip_default_resolvers = kwargs.get(
            "skip_default_resolvers", True
        )

        wrap_function_wrapper(
            graphql,
            "parse",
            self._patched_parse,
        )
        wrap_function_wrapper(
            graphql_module,
            "parse",
            self._patched_parse,
        )
        wrap_function_wrapper(
            graphql.validation,
            "validate",
            self._patched_validate,
        )
        wrap_function_wrapper(
            graphql,
            "execute",
            self._patched_execute,
        )
        wrap_function_wrapper(
            graphql_module,
            "execute",
            self._patched_execute,
        )
        wrap_function_wrapper(
            graphql,
            "ExecutionContext.execute_field",
            self._patched_execute_field,
        )

    def _uninstrument(self, **kwargs: Any) -> None:
        unwrap(graphql, "parse")
        unwrap(graphql_module, "parse")
        unwrap(graphql.validation, "validate")
        unwrap(graphql, "execute")
        unwrap(graphql_module, "execute")
        unwrap(ExecutionContext, "execute_field")

    def _patched_parse(
        self,
        original_func: Callable[..., Any],
        _instance: Any,
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
    ) -> Any:
        if context.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return original_func(*args, **kwargs)

        with self._tracer.start_as_current_span("graphql.parse") as span:
            source_arg: SourceType = args[0]
            _set_document_attr(span, source_arg)

            return original_func(*args, **kwargs)

    def _patched_validate(
        self,
        original_func: Callable[..., Any],
        _instance: Any,
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
    ) -> Any:
        if context.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return original_func(*args, **kwargs)

        with self._tracer.start_as_current_span("graphql.validate") as span:
            document_arg: DocumentNode = args[1]
            _set_document_attr(span, document_arg)

            errors = original_func(*args, **kwargs)
            _set_errors(span, errors)
            return errors

    def _patched_execute(
        self,
        original_func: Callable[..., Any],
        _instance: Any,
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
    ) -> Any:
        if context.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return original_func(*args, **kwargs)

        with self._tracer.start_as_current_span("graphql.execute") as span:
            document_arg: DocumentNode = args[1]
            _set_operation_attrs(span, document_arg)
            result = original_func(*args, **kwargs)

            if is_awaitable(result):

                async def await_result() -> Any:
                    with self._tracer.start_as_current_span(
                        "graphql.execute.await"
                    ) as span:
                        _set_operation_attrs(span, document_arg)
                        async_result = await result
                        _set_errors(span, async_result.errors)
                        return async_result

                return await_result()
            _set_errors(span, result.errors)
            return result

    def _patched_execute_field(
        self,
        original_func: Callable[..., Any],
        instance: ExecutionContext,
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
    ) -> Any:
        if context.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return original_func(*args, **kwargs)

        parent_type_arg: GraphQLObjectType = args[0]
        field_nodes_arg: List[FieldNode] = args[2]
        field_node = field_nodes_arg[0]
        field = get_field_def(instance.schema, parent_type_arg, field_node)

        if _should_skip_field(
            field, instance.operation, self.skip_default_resolvers
        ):
            return original_func(*args, **kwargs)

        with self._tracer.start_as_current_span("graphql.resolve") as span:
            _set_field_attrs(span, field_node)
            result = original_func(*args, **kwargs)

            if is_awaitable(result):

                async def await_result() -> Any:
                    with self._tracer.start_as_current_span(
                        "graphql.resolve.await"
                    ) as span:
                        _set_field_attrs(span, field_node)
                        return await result

                return await_result()
            return result


def _format_source(obj: Union[DocumentNode, Source, str]) -> str:
    if isinstance(obj, str):
        value = obj
    elif isinstance(obj, Source):
        value = obj.body
    elif isinstance(obj, DocumentNode) and obj.loc:
        value = obj.loc.source.body
    else:
        value = ""

    return re.sub(r"\s+", " ", value).strip()


def _set_document_attr(
    span: Span, obj: Union[DocumentNode, Source, str]
) -> None:
    source = _format_source(obj)
    span.set_attribute("graphql.document", source)


def _set_operation_attrs(span: Span, document: DocumentNode) -> None:
    _set_document_attr(span, document)

    operation_definition = get_operation_ast(document)

    if operation_definition:
        span.set_attribute(
            "graphql.operation.type",
            operation_definition.operation.value,
        )

        if operation_definition.name:
            span.set_attribute(
                "graphql.operation.name",
                operation_definition.name.value,
            )


def _set_errors(span: Span, errors: Optional[List[GraphQLError]]) -> None:
    if errors:
        for error in errors:
            span.record_exception(error)


def _set_field_attrs(span: Span, field_node: FieldNode) -> None:
    span.set_attribute("graphql.field.name", field_node.name.value)


def _is_default_resolver(resolver: Optional[GraphQLFieldResolver]) -> bool:
    # pylint: disable=comparison-with-callable
    return (
        # graphql-core
        resolver is None
        or resolver == default_field_resolver
        # ariadne
        or getattr(resolver, "_ariadne_alias_resolver", False)
        # strawberry
        or getattr(resolver, "_is_default", False)
    )


def _is_introspection_query(operation: OperationDefinitionNode) -> bool:
    selections = operation.selection_set.selections

    if selections:
        root_field = cast(FieldNode, selections[0])
        return root_field.name.value == "__schema"
    return False


def _should_skip_field(
    field: GraphQLField,
    operation: OperationDefinitionNode,
    skip_default_resolvers: bool,
) -> bool:
    if _is_default_resolver(field.resolve):
        return skip_default_resolvers

    return _is_introspection_query(operation)
