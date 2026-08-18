# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from celery import Celery

from opentelemetry import baggage


class Config:
    result_backend = "rpc"
    broker_backend = "memory"


app = Celery(broker="memory:///")
app.config_from_object(Config)


class CustomError(Exception):
    pass


@app.task
def task_add(num_a, num_b):
    return num_a + num_b


@app.task
def task_raises():
    raise CustomError("The task failed!")


@app.task
def task_returns_baggage():
    return dict(baggage.get_all())
