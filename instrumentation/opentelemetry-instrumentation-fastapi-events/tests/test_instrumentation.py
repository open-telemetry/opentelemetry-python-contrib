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
from fastapi import FastAPI
from fastapi_events.dispatcher import dispatch
from fastapi_events.handlers.local import LocalHandler
from fastapi_events.middleware import EventHandlerASGIMiddleware
from opentelemetry.test.test_base import TestBase
from starlette.testclient import TestClient

from opentelemetry.instrumentation.fastapi_events import FastAPIEventsInstrumentor


class TestFastAPIEventsInstrumentor(TestBase):
    def setUp(self):
        super().setUp()

        self._app = self._create_app()
        self._client = TestClient(self._app)

    def _create_app(self):
        app = FastAPI()
        local_handler = LocalHandler()

        app.add_middleware(EventHandlerASGIMiddleware, handlers=[local_handler])

        FastAPIEventsInstrumentor().instrument()

        @local_handler.register(event_name="VISITOR_SPOTTED")
        async def handle_visitor_spotted(event):
            print(f"{event[0]} handled =)")
            dispatch("VISITOR_SPOTTED_HANDLED")

        @local_handler.register(event_name="VISITOR_SPOTTED_HANDLED")
        async def handle_visitor_spotted_handled(event):
            print(f"{event[0]} handled =)")

        @app.get("/")
        async def index():
            dispatch("VISITOR_SPOTTED")

        return app

    def test_instrumentation(self):
        self._client.get("/")

        spans = self.memory_exporter.get_finished_spans()
        span_names = [span._name for span in spans]
        self.assertIn("handling event VISITOR_SPOTTED", span_names)
        self.assertIn("handling event VISITOR_SPOTTED_HANDLED", span_names)
        self.assertIn("handling multiple events", span_names)
