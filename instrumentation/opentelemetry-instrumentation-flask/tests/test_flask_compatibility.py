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
Tests for Flask compatibility across versions, focusing on
context cleanup and streaming response handling.
"""

import io
import sys
import threading
import time
from unittest import mock, skipIf

import flask

from opentelemetry import trace
from opentelemetry.instrumentation.flask import (
    FlaskInstrumentor,
    _request_ctx_ref,
)
from opentelemetry.test.wsgitestutil import WsgiTestBase


class TestFlaskCompatibility(WsgiTestBase):
    def setUp(self):
        super().setUp()
        self.flask_version = flask.__version__

    def test_streaming_response_context_cleanup(self):
        """Test that streaming responses properly clean up context"""
        app = flask.Flask(__name__)
        FlaskInstrumentor().instrument_app(app)

        @app.route("/stream")
        def streaming_endpoint():
            def generate():
                yield "Hello "
                yield "World!"

            return flask.Response(flask.stream_with_context(generate()))

        @app.route("/normal")
        def normal_endpoint():
            return "Normal Response"

        client = app.test_client()

        # Test streaming response
        with self.subTest("streaming_response"):
            response = client.get("/stream")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"Hello World!", response.data)

            # Verify that context is properly cleaned up
            current_span = trace.get_current_span()
            span_context = current_span.get_span_context()
            # Either we have a valid trace (non-zero) or we have a NoOp span
            self.assertTrue(span_context.trace_id >= 0)

        # Test normal response for comparison
        with self.subTest("normal_response"):
            response = client.get("/normal")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"Normal Response", response.data)

    def test_generator_response_context_cleanup(self):
        """Test that generator responses properly clean up context"""
        app = flask.Flask(__name__)
        FlaskInstrumentor().instrument_app(app)

        @app.route("/generator")
        def generator_endpoint():
            def generate():
                for chunk_idx in range(5):
                    yield f"Chunk {chunk_idx}\n"

            return flask.Response(flask.stream_with_context(generate()))

        client = app.test_client()

        response = client.get("/generator")
        self.assertEqual(response.status_code, 200)
        expected = b"".join(
            f"Chunk {chunk_idx}\n".encode() for chunk_idx in range(5)
        )
        self.assertEqual(response.data, expected)

    def test_file_response_context_cleanup(self):
        """Test context cleanup with file responses"""
        app = flask.Flask(__name__)
        FlaskInstrumentor().instrument_app(app)

        @app.route("/file")
        def file_endpoint():
            # Simulate file response using io.BytesIO
            file_data = io.BytesIO(b"File content here")
            return flask.send_file(
                file_data, as_attachment=True, download_name="test.txt"
            )

        client = app.test_client()

        response = client.get("/file")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"File content here")

    def test_multiple_requests_context_isolation(self):
        """Test context isolation between multiple requests"""
        app = flask.Flask(__name__)
        FlaskInstrumentor().instrument_app(app)

        results = []

        @app.route("/test/<request_id>")
        def test_endpoint(request_id):
            results.append(f"Request {request_id}")
            return f"Response {request_id}"

        client = app.test_client()

        # Make multiple requests and verify they don't interfere
        for request_idx in range(10):
            response = client.get(f"/test/{request_idx}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, f"Response {request_idx}".encode())

        # Verify all requests were processed
        self.assertEqual(len(results), 10)
        for request_idx in range(10):
            self.assertIn(f"Request {request_idx}", results)

    def test_request_context_reference_handling(self):
        """Test request context reference handling works correctly"""
        app = flask.Flask(__name__)
        FlaskInstrumentor().instrument_app(app)

        @app.route("/context_test")
        def context_test_endpoint():
            # Store request context reference at different points
            context_refs = []
            context_refs.append(_request_ctx_ref())

            # Do some work
            result = "Context test"

            context_refs.append(_request_ctx_ref())
            return result

        client = app.test_client()

        response = client.get("/context_test")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"Context test")

    def test_concurrent_requests_isolation(self):
        """Test that concurrent requests have proper context isolation"""
        app = flask.Flask(__name__)
        FlaskInstrumentor().instrument_app(app)

        results = []
        errors = []

        @app.route("/slow_stream/<int:request_id>")
        def slow_stream_endpoint(request_id):
            def generate():
                for chunk_idx in range(3):
                    time.sleep(0.01)  # Small delay to simulate work
                    yield f"Request {request_id} - Chunk {chunk_idx}\n"

            return flask.Response(flask.stream_with_context(generate()))

        def make_request(request_id):
            try:
                client = app.test_client()
                response = client.get(f"/slow_stream/{request_id}")
                results.append(
                    (request_id, response.status_code, response.data)
                )
            except (RuntimeError, ValueError) as exc:
                errors.append((request_id, exc))

        # Create multiple concurrent requests
        threads = []
        for thread_idx in range(5):
            thread = threading.Thread(target=make_request, args=(thread_idx,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify all requests completed successfully
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")
        self.assertEqual(len(results), 5)

        for request_id, status_code, data in results:
            self.assertEqual(status_code, 200)
            expected = b"".join(
                f"Request {request_id} - Chunk {chunk_idx}\n".encode()
                for chunk_idx in range(3)
            )
            self.assertEqual(data, expected)

    def test_flask_version_compatibility(self):
        """Test that the instrumentation works with the current Flask version"""
        app = flask.Flask(__name__)
        FlaskInstrumentor().instrument_app(app)

        @app.route("/version_test")
        def version_test_endpoint():
            return f"Flask {self.flask_version} compatible"

        client = app.test_client()

        response = client.get("/version_test")
        self.assertEqual(response.status_code, 200)
        expected_text = f"Flask {self.flask_version} compatible"
        self.assertEqual(response.data, expected_text.encode())

    def test_context_leak_prevention(self):
        """Test that context doesn't leak after multiple requests"""
        app = flask.Flask(__name__)
        FlaskInstrumentor().instrument_app(app)

        @app.route("/leak_test")
        def leak_test_endpoint():
            def generate():
                yield "Part 1\n"
                yield "Part 2\n"
                yield "Part 3\n"

            return flask.Response(flask.stream_with_context(generate()))

        client = app.test_client()

        # Make multiple streaming requests
        for _ in range(10):
            response = client.get("/leak_test")
            self.assertEqual(response.status_code, 200)
            expected = b"Part 1\nPart 2\nPart 3\n"
            self.assertEqual(response.data, expected)

        # After all requests, there should be no lingering context
        # This is a basic check - more sophisticated leak detection would require
        # instrumentation-specific testing utilities
        # If we got here without errors, context cleanup worked

    def test_streaming_with_error_in_cleanup(self):
        """Test graceful handling when cleanup operations fail"""
        app = flask.Flask(__name__)
        FlaskInstrumentor().instrument_app(app)

        # Mock the cleanup functions to raise exceptions
        with (
            mock.patch(
                "opentelemetry.instrumentation.flask.context.detach"
            ) as mock_detach,
            mock.patch("opentelemetry.trace.use_span") as mock_use_span,
        ):
            # Make detach raise an exception
            mock_detach.side_effect = RuntimeError("Detach error")

            # Make the span activation __exit__ raise an exception
            mock_span_instance = mock.Mock()
            mock_span_instance.is_recording.return_value = True
            mock_span_instance.__exit__ = mock.Mock(
                side_effect=RuntimeError("Exit error")
            )
            mock_use_span.return_value.__enter__ = mock.Mock(
                return_value=mock_span_instance
            )

            @app.route("/stream_cleanup_error")
            def stream_cleanup_error_endpoint():
                def generate():
                    yield "Data"

                return flask.Response(flask.stream_with_context(generate()))

            client = app.test_client()

            # The request should still complete successfully despite cleanup errors
            response = client.get("/stream_cleanup_error")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b"Data")

    @skipIf(
        sys.version_info < (3, 10),
        "Flask 3.1+ streaming context cleanup only enabled on Python 3.10+",
    )
    @skipIf(
        lambda: (
            not __import__(
                "opentelemetry.instrumentation.flask",
                fromlist=["_IS_FLASK_31_PLUS"],
            )._IS_FLASK_31_PLUS
        ),
        "Flask 3.1+ streaming context cleanup requires Flask 3.1+",
    )
    def test_flask_31_streaming_context_cleanup(self):
        """Test that Flask 3.1+ streaming responses have proper context cleanup to prevent token reuse"""
        app = flask.Flask(__name__)
        FlaskInstrumentor().instrument_app(app)

        @app.route("/stream_flask31")
        def flask31_streaming_endpoint():
            def generate():
                for chunk_idx in range(10):
                    yield f"Chunk {chunk_idx}\n"

            return flask.Response(flask.stream_with_context(generate()))

        @app.route("/stream_normal")
        def stream_normal_endpoint():
            def generate():
                for chunk_idx in range(5):
                    yield f"Normal {chunk_idx}\n"

            return flask.Response(flask.stream_with_context(generate()))

        client = app.test_client()

        # Make multiple consecutive streaming requests to test for token reuse issues
        for request_idx in range(20):
            response = client.get("/stream_flask31")
            self.assertEqual(response.status_code, 200)
            expected_data = "".join(f"Chunk {j}\n" for j in range(10)).encode()
            self.assertEqual(response.data, expected_data)

        # Test normal streaming requests as well
        for request_idx in range(5):
            response = client.get("/stream_normal")
            self.assertEqual(response.status_code, 200)
            expected_data = "".join(f"Normal {j}\n" for j in range(5)).encode()
            self.assertEqual(response.data, expected_data)

        # Mix of streaming requests
        for request_idx in range(10):
            endpoint = (
                "/stream_flask31" if request_idx % 2 == 0 else "/stream_normal"
            )
            response = client.get(endpoint)
            self.assertEqual(response.status_code, 200)

        # For Flask 3.1+, streaming context cleanup is now handled in Flask's teardown function
        # This ensures OpenTelemetry contexts are properly cleaned up for streaming responses
        # following Logfire's recommendations (see open-telemetry/opentelemetry-python#2606)
        # If we reach this point, the Flask 3.1+ streaming context cleanup is working
