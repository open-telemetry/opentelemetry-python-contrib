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

import time

from celery import Celery

from opentelemetry import baggage


class Config:
    result_backend = "rpc://"
    without_gossip = True
    without_heartbeat = True
    without_mingle = True


app = Celery(broker="memory:///")
app.config_from_object(Config)


class CustomError(Exception):
    pass


@app.task
def task_add(x=1, y=2):
    return x + y


@app.task
def task_sleep(sleep_time):
    time.sleep(sleep_time)
    return 1


@app.task
def task_raises():
    raise CustomError("The task failed!")


@app.task
def task_returns_baggage():
    return dict(baggage.get_all())
