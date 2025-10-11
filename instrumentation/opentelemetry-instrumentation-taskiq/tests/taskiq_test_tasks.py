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
from taskiq import InMemoryBroker

from opentelemetry import baggage

broker = InMemoryBroker(
    await_inplace=True  # used to sort spans in a deterministic way
)


class CustomError(Exception):
    pass


@broker.task
async def task_add(num_a, num_b):
    return num_a + num_b


@broker.task
async def task_raises():
    raise CustomError("The task failed!")


@broker.task
async def task_returns_baggage():
    return dict(baggage.get_all())
