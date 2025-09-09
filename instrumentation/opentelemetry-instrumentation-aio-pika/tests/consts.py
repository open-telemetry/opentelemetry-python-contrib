from argparse import Namespace

from aio_pika import __version__ as aiopika_version
from yarl import URL

AIOPIKA_VERSION_INFO = tuple(int(v) for v in aiopika_version.split("."))
MESSAGE_ID = "meesage_id"
CORRELATION_ID = "correlation_id"
MESSAGING_SYSTEM_VALUE = "rabbitmq"
EXCHANGE_NAME = "exchange_name"
QUEUE_NAME = "queue_name"
ROUTING_KEY = "routing_key"
SERVER_HOST = "localhost"
SERVER_PORT = 1234
SERVER_USER = "guest"
SERVER_PASS = "guest"
SERVER_URL = URL(
    f"amqp://{SERVER_USER}:{SERVER_PASS}@{SERVER_HOST}:{SERVER_PORT}/"
)
CONNECTION_7 = Namespace(connection=Namespace(url=SERVER_URL))
CONNECTION_8 = Namespace(url=SERVER_URL)
CHANNEL_7 = Namespace(connection=CONNECTION_7, loop=None)
CHANNEL_8 = Namespace(connection=CONNECTION_8, loop=None)
MESSAGE = Namespace(
    properties=Namespace(
        message_id=MESSAGE_ID, correlation_id=CORRELATION_ID, headers={}
    ),
    exchange=EXCHANGE_NAME,
    headers={},
)
