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
import logging
import os
import time

import mysql.connector
import psycopg2
import pymongo
import pyodbc
import redis
import valkey

MONGODB_COLLECTION_NAME = "test"
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "opentelemetry-tests")
MONGODB_HOST = os.getenv("MONGODB_HOST", "localhost")
MONGODB_PORT = int(os.getenv("MONGODB_PORT", "27017"))
MYSQL_DB_NAME = os.getenv("MYSQL_DB_NAME", "opentelemetry-tests")
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "testuser")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "testpassword")
POSTGRES_DB_NAME = os.getenv("POSTGRESQL_DB_NAME", "opentelemetry-tests")
POSTGRES_HOST = os.getenv("POSTGRESQL_HOST", "localhost")
POSTGRES_PASSWORD = os.getenv("POSTGRESQL_PASSWORD", "testpassword")
POSTGRES_PORT = int(os.getenv("POSTGRESQL_PORT", "5432"))
POSTGRES_USER = os.getenv("POSTGRESQL_USER", "testuser")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT ", "6379"))
VALKEY_HOST = os.getenv("VALKEY_HOST", "localhost")
VALKEY_PORT = int(os.getenv("VALKEY_PORT ", "16379"))
MSSQL_DB_NAME = os.getenv("MSSQL_DB_NAME", "opentelemetry-tests")
MSSQL_HOST = os.getenv("MSSQL_HOST", "localhost")
MSSQL_PORT = int(os.getenv("MSSQL_PORT", "1433"))
MSSQL_USER = os.getenv("MSSQL_USER", "sa")
MSSQL_PASSWORD = os.getenv("MSSQL_PASSWORD", "yourStrong(!)Password")
RETRY_COUNT = 5
RETRY_INITIAL_INTERVAL = 2  # Seconds

logger = logging.getLogger(__name__)


def retryable(func):
    def wrapper():
        # Try to connect to DB
        for i in range(RETRY_COUNT):
            try:
                func()
                return
            except Exception as ex:  # pylint: disable=broad-except
                # Exponential backoff
                backoff_interval = RETRY_INITIAL_INTERVAL * (2**i)
                logger.error(
                    "waiting for %s, retry %d/%d [%s]",
                    func.__name__,
                    i + 1,
                    RETRY_COUNT,
                    ex,
                )
            time.sleep(backoff_interval)
        raise Exception(f"waiting for {func.__name__} failed")

    return wrapper


@retryable
def check_pymongo_connection():
    client = pymongo.MongoClient(
        MONGODB_HOST, MONGODB_PORT, serverSelectionTimeoutMS=2000
    )
    db = client[MONGODB_DB_NAME]
    collection = db[MONGODB_COLLECTION_NAME]
    collection.find_one()
    client.close()


@retryable
def check_mysql_connection():
    connection = mysql.connector.connect(
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        database=MYSQL_DB_NAME,
    )
    connection.close()


@retryable
def check_postgres_connection():
    connection = psycopg2.connect(
        dbname=POSTGRES_DB_NAME,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
    )
    connection.close()


@retryable
def check_redis_connection():
    connection = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
    connection.hgetall("*")


@retryable
def check_valkey_connection():
    connection = valkey.Valkey(host=VALKEY_HOST, port=VALKEY_PORT)
    connection.hgetall("*")


def new_mssql_connection() -> pyodbc.Connection:
    connection = pyodbc.connect(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={MSSQL_HOST},"
        f"{MSSQL_PORT};DATABASE=master;UID={MSSQL_USER};TrustServerCertificate=yes;"
        f"PWD={MSSQL_PASSWORD};",
        autocommit=True,
    )
    return connection


@retryable
def check_mssql_connection():
    conn = new_mssql_connection()
    conn.close()


def setup_mssql_db():
    conn = new_mssql_connection()
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE [{MSSQL_DB_NAME}]")
    conn.close()


def check_docker_services_availability():
    # Check if Docker services accept connections
    check_pymongo_connection()
    check_mysql_connection()
    check_postgres_connection()
    check_redis_connection()
    check_valkey_connection()
    check_mssql_connection()
    setup_mssql_db()


check_docker_services_availability()
