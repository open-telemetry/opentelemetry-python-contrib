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

# DO NOT EDIT. THIS FILE WAS AUTOGENERATED FROM INSTRUMENTATION PACKAGES.
# RUN `python scripts/generate_instrumentation_bootstrap.py` TO REGENERATE.

libraries = {
    "aio_pika": {
        "library": "aio_pika ~= 7.2.0",
        "instrumentation": "opentelemetry-instrumentation-aio-pika==0.36b0.dev",
    },
    "aiohttp": {
        "library": "aiohttp ~= 3.0",
        "instrumentation": "opentelemetry-instrumentation-aiohttp-client==0.36b0.dev",
    },
    "aiopg": {
        "library": "aiopg >= 0.13.0, < 1.3.0",
        "instrumentation": "opentelemetry-instrumentation-aiopg==0.36b0.dev",
    },
    "asgiref": {
        "library": "asgiref ~= 3.0",
        "instrumentation": "opentelemetry-instrumentation-asgi==0.36b0.dev",
    },
    "asyncpg": {
        "library": "asyncpg >= 0.12.0",
        "instrumentation": "opentelemetry-instrumentation-asyncpg==0.36b0.dev",
    },
    "boto": {
        "library": "boto~=2.0",
        "instrumentation": "opentelemetry-instrumentation-boto==0.36b0.dev",
    },
    "boto3": {
        "library": "boto3 ~= 1.0",
        "instrumentation": "opentelemetry-instrumentation-boto3sqs==0.36b0.dev",
    },
    "botocore": {
        "library": "botocore ~= 1.0",
        "instrumentation": "opentelemetry-instrumentation-botocore==0.36b0.dev",
    },
    "celery": {
        "library": "celery >= 4.0, < 6.0",
        "instrumentation": "opentelemetry-instrumentation-celery==0.36b0.dev",
    },
    "confluent-kafka": {
        "library": "confluent-kafka ~= 1.8.2",
        "instrumentation": "opentelemetry-instrumentation-confluent-kafka==0.36b0.dev",
    },
    "django": {
        "library": "django >= 1.10",
        "instrumentation": "opentelemetry-instrumentation-django==0.36b0.dev",
    },
    "elasticsearch": {
        "library": "elasticsearch >= 2.0",
        "instrumentation": "opentelemetry-instrumentation-elasticsearch==0.36b0.dev",
    },
    "falcon": {
        "library": "falcon >= 1.4.1, < 4.0.0",
        "instrumentation": "opentelemetry-instrumentation-falcon==0.36b0.dev",
    },
    "fastapi": {
        "library": "fastapi ~= 0.58",
        "instrumentation": "opentelemetry-instrumentation-fastapi==0.36b0.dev",
    },
    "flask": {
        "library": "flask >= 1.0, < 3.0",
        "instrumentation": "opentelemetry-instrumentation-flask==0.36b0.dev",
    },
    "grpcio": {
        "library": "grpcio ~= 1.27",
        "instrumentation": "opentelemetry-instrumentation-grpc==0.36b0.dev",
    },
    "httpx": {
        "library": "httpx >= 0.18.0",
        "instrumentation": "opentelemetry-instrumentation-httpx==0.36b0.dev",
    },
    "jinja2": {
        "library": "jinja2 >= 2.7, < 4.0",
        "instrumentation": "opentelemetry-instrumentation-jinja2==0.36b0.dev",
    },
    "kafka-python": {
        "library": "kafka-python >= 2.0",
        "instrumentation": "opentelemetry-instrumentation-kafka-python==0.36b0.dev",
    },
    "mysql-connector-python": {
        "library": "mysql-connector-python ~= 8.0",
        "instrumentation": "opentelemetry-instrumentation-mysql==0.36b0.dev",
    },
    "pika": {
        "library": "pika >= 0.12.0",
        "instrumentation": "opentelemetry-instrumentation-pika==0.36b0.dev",
    },
    "psycopg2": {
        "library": "psycopg2 >= 2.7.3.1",
        "instrumentation": "opentelemetry-instrumentation-psycopg2==0.36b0.dev",
    },
    "pymemcache": {
        "library": "pymemcache >= 1.3.5, < 4",
        "instrumentation": "opentelemetry-instrumentation-pymemcache==0.36b0.dev",
    },
    "pymongo": {
        "library": "pymongo >= 3.1, < 5.0",
        "instrumentation": "opentelemetry-instrumentation-pymongo==0.36b0.dev",
    },
    "PyMySQL": {
        "library": "PyMySQL < 2",
        "instrumentation": "opentelemetry-instrumentation-pymysql==0.36b0.dev",
    },
    "pyramid": {
        "library": "pyramid >= 1.7",
        "instrumentation": "opentelemetry-instrumentation-pyramid==0.36b0.dev",
    },
    "redis": {
        "library": "redis >= 2.6",
        "instrumentation": "opentelemetry-instrumentation-redis==0.36b0.dev",
    },
    "remoulade": {
        "library": "remoulade >= 0.50",
        "instrumentation": "opentelemetry-instrumentation-remoulade==0.36b0.dev",
    },
    "requests": {
        "library": "requests ~= 2.0",
        "instrumentation": "opentelemetry-instrumentation-requests==0.36b0.dev",
    },
    "scikit-learn": {
        "library": "scikit-learn ~= 0.24.0",
        "instrumentation": "opentelemetry-instrumentation-sklearn==0.36b0.dev",
    },
    "sqlalchemy": {
        "library": "sqlalchemy",
        "instrumentation": "opentelemetry-instrumentation-sqlalchemy==0.36b0.dev",
    },
    "starlette": {
        "library": "starlette ~= 0.13.0",
        "instrumentation": "opentelemetry-instrumentation-starlette==0.36b0.dev",
    },
    "psutil": {
        "library": "psutil >= 5",
        "instrumentation": "opentelemetry-instrumentation-system-metrics==0.36b0.dev",
    },
    "tornado": {
        "library": "tornado >= 5.1.1",
        "instrumentation": "opentelemetry-instrumentation-tornado==0.36b0.dev",
    },
    "tortoise-orm": {
        "library": "tortoise-orm >= 0.17.0",
        "instrumentation": "opentelemetry-instrumentation-tortoiseorm==0.26b1",
    },
    "urllib3": {
        "library": "urllib3 >= 1.0.0, < 2.0.0",
        "instrumentation": "opentelemetry-instrumentation-urllib3==0.36b0.dev",
    },
}
default_instrumentations = [
    "opentelemetry-instrumentation-aws-lambda==0.36b0.dev",
    "opentelemetry-instrumentation-dbapi==0.36b0.dev",
    "opentelemetry-instrumentation-logging==0.36b0.dev",
    "opentelemetry-instrumentation-sqlite3==0.36b0.dev",
    "opentelemetry-instrumentation-urllib==0.36b0.dev",
    "opentelemetry-instrumentation-wsgi==0.36b0.dev",
]
