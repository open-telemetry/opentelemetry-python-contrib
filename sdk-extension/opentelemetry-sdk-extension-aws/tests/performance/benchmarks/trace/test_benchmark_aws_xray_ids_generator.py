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

from flaky import flaky

from opentelemetry.sdk.extension.aws.trace import AwsXRayIdGenerator

id_generator = AwsXRayIdGenerator()


@flaky(max_runs=3, min_passes=1)
def test_generate_xray_trace_id(benchmark):
    benchmark(id_generator.generate_trace_id)


@flaky(max_runs=3, min_passes=1)
def test_generate_xray_span_id(benchmark):
    benchmark(id_generator.generate_span_id)
