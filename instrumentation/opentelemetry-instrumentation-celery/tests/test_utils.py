# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import unittest
from unittest import mock

from celery import Celery
from celery.app.task import Context
from kombu import Exchange, Queue

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.celery import utils
from opentelemetry.sdk import trace
from opentelemetry.semconv._incubating.attributes.messaging_attributes import (
    MESSAGING_MESSAGE_ID,
)
from opentelemetry.semconv.trace import MessagingDestinationKindValues, SpanAttributes


class TestUtils(unittest.TestCase):
    def setUp(self):
        self.app = Celery("celery.test_app")

    def test_get_request_attributes(self) -> None:
        request = Context(
            compression="gzip",
            correlation_id="44b7f305",
            countdown=5,
            delivery_info={"routing_key": "celery", "priority": 4},
            eta="soon",
            exchange=Exchange("tasks"),
            expires="later",
            hostname="localhost",
            id="44b7f305",
            origin="gen8@localhost",
            priority=4,
            queue=Queue("celery"),
            reply_to="44b7f305",
            retries=4,
            routing_key="celery",
            serializer="json",
            timelimit=(10, 20),
            args=["secret"],
            kwargs={"secret": "value"},
        )

        attributes = utils.get_request_attributes(request)

        expected = {
            "celery.compression": "gzip",
            "celery.countdown": 5,
            "celery.exchange": "tasks",
            "celery.priority": 4,
            "celery.queue": "celery",
            "celery.serializer": "json",
            MESSAGING_MESSAGE_ID: "44b7f305",
            SpanAttributes.MESSAGING_CONVERSATION_ID: "44b7f305",
            SpanAttributes.MESSAGING_DESTINATION: "celery",
            "celery.delivery_info": str({"routing_key": "celery", "priority": 4}),
            "celery.eta": "soon",
            "celery.expires": "later",
            "celery.hostname": "localhost",
            "celery.origin": "gen8@localhost",
            "celery.reply_to": "44b7f305",
            "celery.retries": 4,
            "celery.timelimit": (10, 20),
        }
        self.assertEqual(attributes, expected)
        for key, value in expected.items():
            self.assertIs(type(attributes[key]), type(value))

    def test_get_request_attributes_routing_key_overrides_delivery_info(self) -> None:
        request = Context(delivery_info={"routing_key": "delivery"}, routing_key="explicit")

        attributes = utils.get_request_attributes(request)

        self.assertEqual(attributes[SpanAttributes.MESSAGING_DESTINATION], "explicit")
        self.assertIs(type(attributes[SpanAttributes.MESSAGING_DESTINATION]), str)

    def test_get_request_attributes_empty_routing_objects(self) -> None:
        self.assertEqual(utils.get_request_attributes(Context(exchange=Exchange(""), queue=Queue(""))), {})

    def test_get_request_attributes_zero_publish_options(self) -> None:
        attributes = utils.get_request_attributes(Context(countdown=0, priority=0))

        self.assertEqual(attributes, {"celery.countdown": 0, "celery.priority": 0})
        for value in attributes.values():
            self.assertIs(type(value), int)

    def test_get_request_attributes_origin_not_aliased_to_hostname(self) -> None:
        attributes = utils.get_request_attributes(Context(origin="gen8@localhost"))

        self.assertEqual(attributes, {"celery.origin": "gen8@localhost"})

    def test_get_request_attributes_partial_timelimit(self) -> None:
        for timelimit, expected in (((10, None), ["10", ""]), ((None, 20), ["", "20"])):
            with self.subTest(timelimit=timelimit):
                attributes = utils.get_request_attributes(Context(timelimit=timelimit))

                self.assertEqual(attributes, {"celery.timelimit": expected})
                self.assertIs(type(attributes["celery.timelimit"]), list)

    def test_get_request_attributes_empty_values(self) -> None:
        for timelimit in ((None, None), [None, None]):
            with self.subTest(timelimit=timelimit):
                request = Context(correlation_id=None, origin="", retries=0, timelimit=timelimit)
                self.assertEqual(utils.get_request_attributes(request), {})

    def test_get_publish_attributes(self) -> None:
        for exchange, kind in (
            (Exchange("direct", type="direct"), MessagingDestinationKindValues.QUEUE.value),
            (Exchange("topic", type="topic"), MessagingDestinationKindValues.TOPIC.value),
        ):
            with self.subTest(exchange=exchange):
                signal_kwargs = {
                    "exchange": exchange,
                    "routing_key": "celery",
                    "declare": [Queue("celery", exchange=exchange)],
                    "headers": {"origin": "publisher", "retries": 2},
                    "properties": {"priority": 4, "correlation_id": "id"},
                    "body": (["secret"], {"secret": "value"}, {}),
                }
                attributes = utils.get_publish_attributes(signal_kwargs)

                expected = {
                    "celery.exchange": exchange.name,
                    SpanAttributes.MESSAGING_DESTINATION: "celery",
                    SpanAttributes.MESSAGING_DESTINATION_KIND: kind,
                }
                self.assertEqual(attributes, expected)
                for key, value in expected.items():
                    self.assertIs(type(attributes[key]), type(value))

    def test_get_publish_attributes_string_exchange(self) -> None:
        self.assertEqual(utils.get_publish_attributes({"exchange": "celery"}), {"celery.exchange": "celery"})

    def test_get_publish_attributes_empty_values(self) -> None:
        for signal_kwargs in ({}, {"exchange": "", "routing_key": "", "declare": None}, {"exchange": Exchange("")}):
            with self.subTest(signal_kwargs=signal_kwargs):
                self.assertEqual(utils.get_publish_attributes(signal_kwargs), {})

    def test_span_propagation(self):
        # ensure spans getter and setter works properly
        @self.app.task
        def fn_task():
            return 42

        # propagate and retrieve a Span
        task_id = "7c6731af-9533-40c3-83a9-25b58f0d837f"
        span = trace._Span("name", mock.Mock(spec=trace_api.SpanContext))
        utils.attach_context(fn_task, task_id, span, mock.Mock(), "")
        ctx = utils.retrieve_context(fn_task, task_id)
        self.assertIsNotNone(ctx)
        span_after, _, _ = ctx
        self.assertIs(span, span_after)

    def test_span_delete(self):
        # ensure the helper removes properly a propagated Span
        @self.app.task
        def fn_task():
            return 42

        # propagate a Span
        task_id = "7c6731af-9533-40c3-83a9-25b58f0d837f"
        span = trace._Span("name", mock.Mock(spec=trace_api.SpanContext))
        utils.attach_context(fn_task, task_id, span, mock.Mock(), "")
        # delete the Span
        utils.detach_context(fn_task, task_id)
        self.assertEqual(utils.retrieve_context(fn_task, task_id), None)

    def test_optional_task_span_attach(self):
        task_id = "7c6731af-9533-40c3-83a9-25b58f0d837f"
        span = trace._Span("name", mock.Mock(spec=trace_api.SpanContext))

        # assert this is is a no-aop
        self.assertIsNone(utils.attach_context(None, task_id, span, mock.Mock(), ""))

    def test_span_delete_empty(self):
        # ensure detach_span doesn't raise an exception if span is not present
        @self.app.task
        def fn_task():
            return 42

        # delete the Span
        task_id = "7c6731af-9533-40c3-83a9-25b58f0d837f"
        try:
            utils.detach_context(fn_task, task_id)
            self.assertEqual(utils.retrieve_context(fn_task, task_id), None)
        except Exception as ex:  # pylint: disable=broad-except
            self.fail(f"Exception was raised: {ex}")

    def test_task_id_from_protocol_v1(self):
        # ensures a `task_id` is properly returned when Protocol v1 is used.
        # `context` is an example of an emitted Signal with Protocol v1
        context = {
            "body": {
                "expires": None,
                "utc": True,
                "args": ["user"],
                "chord": None,
                "callbacks": None,
                "errbacks": None,
                "taskset": None,
                "id": "dffcaec1-dd92-4a1a-b3ab-d6512f4beeb7",
                "retries": 0,
                "task": "tests.contrib.celery.test_integration.fn_task_parameters",
                "timelimit": (None, None),
                "eta": None,
                "kwargs": {"force_logout": True},
            },
            "sender": "tests.contrib.celery.test_integration.fn_task_parameters",
            "exchange": "celery",
            "routing_key": "celery",
            "retry_policy": None,
            "headers": {},
            "properties": {},
        }

        task_id = utils.retrieve_task_id_from_message(context)
        self.assertEqual(task_id, "dffcaec1-dd92-4a1a-b3ab-d6512f4beeb7")

    def test_task_id_from_protocol_v2(self):
        # ensures a `task_id` is properly returned when Protocol v2 is used.
        # `context` is an example of an emitted Signal with Protocol v2
        context = {
            "body": (
                ["user"],
                {"force_logout": True},
                {
                    "chord": None,
                    "callbacks": None,
                    "errbacks": None,
                    "chain": None,
                },
            ),
            "sender": "tests.contrib.celery.test_integration.fn_task_parameters",
            "exchange": "",
            "routing_key": "celery",
            "retry_policy": None,
            "headers": {
                "origin": "gen83744@hostname",
                "root_id": "7e917b83-4018-431d-9832-73a28e1fb6c0",
                "expires": None,
                "shadow": None,
                "id": "7e917b83-4018-431d-9832-73a28e1fb6c0",
                "kwargsrepr": "{'force_logout': True}",
                "lang": "py",
                "retries": 0,
                "task": "tests.contrib.celery.test_integration.fn_task_parameters",
                "group": None,
                "timelimit": [None, None],
                "parent_id": None,
                "argsrepr": "['user']",
                "eta": None,
            },
            "properties": {
                "reply_to": "c3054a07-5b28-3855-b18c-1623a24aaeca",
                "correlation_id": "7e917b83-4018-431d-9832-73a28e1fb6c0",
            },
        }

        task_id = utils.retrieve_task_id_from_message(context)
        self.assertEqual(task_id, "7e917b83-4018-431d-9832-73a28e1fb6c0")
