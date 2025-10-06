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

from opentelemetry.metrics import Histogram, Meter


class Instruments:
    """
    Manages OpenTelemetry metrics instruments for GenAI telemetry.
    """

    def __init__(self, meter: Meter):
        self.operation_duration_histogram: Histogram = meter.create_histogram(
            name="gen_ai.client.operation.duration",
            unit="s",
            description="Duration of GenAI client operations",
        )
        self.token_usage_histogram: Histogram = meter.create_histogram(
            name="gen_ai.client.token.usage",
            unit="{token}",
            description="Number of input and output tokens used",
        )
        # Agentic AI metrics
        self.workflow_duration_histogram: Histogram = meter.create_histogram(
            name="gen_ai.workflow.duration",
            unit="s",
            description="Duration of GenAI workflows",
        )
        self.agent_duration_histogram: Histogram = meter.create_histogram(
            name="gen_ai.agent.duration",
            unit="s",
            description="Duration of agent operations",
        )
        self.task_duration_histogram: Histogram = meter.create_histogram(
            name="gen_ai.task.duration",
            unit="s",
            description="Duration of task executions",
        )
