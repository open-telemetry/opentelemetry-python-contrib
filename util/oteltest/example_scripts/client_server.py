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

from oteltest import OtelTest, Telemetry

from typing import Mapping, Optional, Sequence

import time

PORT = 8909
HOST = "127.0.0.1"

if __name__ == "__main__":
    # local import so flask not req'd to load this script
    from flask import Flask, jsonify

    app = Flask(__name__)


    @app.route("/")
    def home():
        return jsonify({"library": "flask"})


    app.run(port=PORT, host=HOST)


class FlaskTest(OtelTest):
    def environment_variables(self) -> Mapping[str, str]:
        return {}

    def requirements(self) -> Sequence[str]:
        return (
            "opentelemetry-distro",
            "opentelemetry-exporter-otlp-proto-grpc",
            "opentelemetry-instrumentation-flask",
            "flask==2.3.3",
            "jsonify",
        )

    def wrapper_command(self) -> str:
        return "opentelemetry-instrument"

    def on_start(self) -> Optional[float]:
        import http.client

        # Todo: replace this sleep with a liveness check!
        time.sleep(10)

        conn = http.client.HTTPConnection(HOST, PORT)
        conn.request("GET", "/")
        print("response:", conn.getresponse().read().decode())
        conn.close()

        # The return value of on_script_start() tells oteltest the number of seconds to wait for the script to
        # finish. In this case, we indicate 30 (seconds), which, once elapsed, will cause the script to be terminated,
        # if it's still running. If we return `None` then the script will run indefinitely.
        return 30

    def on_stop(
        self, telemetry: Telemetry, stdout: str, stderr: str, returncode: int
    ) -> None:
        print(f"on_stop: telemetry: {telemetry}")
