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

import asyncio

from graphql import (
    GraphQLField,
    GraphQLObjectType,
    GraphQLSchema,
    GraphQLString,
    graphql,
    graphql_sync,
)

from opentelemetry.instrumentation.graphql_core import GraphQLCoreInstrumentor
from opentelemetry.test.test_base import TestBase


def async_call(coro):
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


class TestGraphQLCoreInstrumentor(TestBase):
    def setUp(self):
        super().setUp()
        GraphQLCoreInstrumentor().instrument()

    def tearDown(self):
        super().tearDown()
        GraphQLCoreInstrumentor().uninstrument()

    def test_graphql(self):
        async def resolve_hello(parent, info):
            await asyncio.sleep(0)
            return "Hello world!"

        schema = GraphQLSchema(
            query=GraphQLObjectType(
                name="RootQueryType",
                fields={
                    "hello": GraphQLField(GraphQLString, resolve=resolve_hello)
                },
            )
        )

        result = async_call(graphql(schema, "query Test { hello }"))
        self.assertEqual(result.errors, None)
        self.assertEqual(result.data["hello"], "Hello world!")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 6)

        parse_span = spans[0]
        self.assertEqual("graphql.parse", parse_span.name)
        self.assertEqual(
            "query Test { hello }", parse_span.attributes["graphql.document"]
        )

        validate_span = spans[1]
        self.assertEqual("graphql.validate", validate_span.name)
        self.assertEqual(
            "query Test { hello }",
            validate_span.attributes["graphql.document"],
        )

        resolve_span = spans[2]
        self.assertEqual("graphql.resolve", resolve_span.name)
        self.assertEqual(
            "hello", resolve_span.attributes["graphql.field.name"]
        )

        execute_span = spans[3]
        self.assertEqual("graphql.execute", execute_span.name)
        self.assertEqual(
            "query Test { hello }", execute_span.attributes["graphql.document"]
        )
        self.assertEqual(
            "query", execute_span.attributes["graphql.operation.type"]
        )
        self.assertEqual(
            "Test", execute_span.attributes["graphql.operation.name"]
        )

        resolve_await_span = spans[4]
        self.assertEqual("graphql.resolve.await", resolve_await_span.name)
        self.assertEqual(
            "hello", resolve_await_span.attributes["graphql.field.name"]
        )

        execute_await_span = spans[5]
        self.assertEqual("graphql.execute.await", execute_await_span.name)
        self.assertEqual(
            "query Test { hello }",
            execute_await_span.attributes["graphql.document"],
        )
        self.assertEqual(
            "query", execute_await_span.attributes["graphql.operation.type"]
        )
        self.assertEqual(
            "Test", execute_await_span.attributes["graphql.operation.name"]
        )

    def test_graphql_sync(self):
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

        result = graphql_sync(schema, "query Test { hello }")
        self.assertEqual(result.errors, None)
        self.assertEqual(result.data["hello"], "Hello world!")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 4)

        parse_span = spans[0]
        self.assertEqual("graphql.parse", parse_span.name)
        self.assertEqual(
            "query Test { hello }", parse_span.attributes["graphql.document"]
        )

        validate_span = spans[1]
        self.assertEqual("graphql.validate", validate_span.name)
        self.assertEqual(
            "query Test { hello }",
            validate_span.attributes["graphql.document"],
        )

        resolve_span = spans[2]
        self.assertEqual("graphql.resolve", resolve_span.name)
        self.assertEqual(
            "hello", resolve_span.attributes["graphql.field.name"]
        )

        execute_span = spans[3]
        self.assertEqual("graphql.execute", execute_span.name)
        self.assertEqual(
            "query Test { hello }", execute_span.attributes["graphql.document"]
        )
        self.assertEqual(
            "query", execute_span.attributes["graphql.operation.type"]
        )
        self.assertEqual(
            "Test", execute_span.attributes["graphql.operation.name"]
        )
