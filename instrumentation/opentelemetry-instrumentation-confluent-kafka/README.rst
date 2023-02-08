OpenTelemetry confluent-kafka Instrumentation
=============================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-confluent-kafka.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-confluent-kafka/

This library allows tracing requests made by the confluent-kafka library.

Installation
------------

::

    pip install opentelemetry-instrumentation-confluent-kafka


"""
Instrument confluent-kafka-python to report instrumentation-confluent-kafka produced and consumed messages

Usage
-----

::

    from opentelemetry.instrumentation.confluent_kafka import ConfluentKafkaInstrumentor
    from confluent_kafka import Producer, Consumer

    # Instrument kafka
    ConfluentKafkaInstrumentor().instrument()

    # report a span of type producer with the default settings
    conf1 = {'bootstrap.servers': "localhost:9092"}
    producer = Producer(conf1)
    producer.produce('my-topic',b'raw_bytes')
    conf2 = {'bootstrap.servers': "localhost:9092", 'group.id': "foo", 'auto.offset.reset': 'smallest'}
    # report a span of type consumer with the default settings
    consumer = Consumer(conf2)

    def basic_consume_loop(consumer, topics):
        try:
            consumer.subscribe(topics)
            running = True

            while running:
                msg = consumer.poll(timeout=1.0)

                if msg is None: continue
                if msg.error():

                    if msg.error().code() == KafkaError._PARTITION_EOF:

                        # End of partition event
                        sys.stderr.write(f"{msg.topic() [{msg.partition()}] reached end at offset {msg.offset()}}")

                    elif msg.error():
                        raise KafkaException(msg.error())

                else:
                    msg_process(msg)
        finally:
            # Close down consumer to commit final offsets.
            consumer.close()

    basic_consume_loop(consumer, "my-topic")
    ---

The _instrument method accepts the following keyword args:
tracer_provider (TracerProvider) - an optional tracer provider
instrument_producer (Callable) - a function with extra user-defined logic to be performed before sending the message
this function signature is:
def instrument_producer(producer: Producer, tracer_provider=None)
instrument_consumer (Callable) - a function with extra user-defined logic to be performed after consuming a message
this function signature is:
def instrument_consumer(consumer: Consumer, tracer_provider=None)
for example:

::
    from opentelemetry.instrumentation.confluent_kafka import ConfluentKafkaInstrumentor
    from confluent_kafka import Producer, Consumer

    inst = ConfluentKafkaInstrumentor()

    p = confluent_kafka.Producer({'bootstrap.servers': 'localhost:29092'})
    c = confluent_kafka.Consumer({
        'bootstrap.servers': 'localhost:29092',
        'group.id': 'mygroup',
        'auto.offset.reset': 'earliest'
    })

    # instrument confluent kafka with produce and consume hooks
    p = inst.instrument_producer(p, tracer_provider)
    c = inst.instrument_consumer(c, tracer_provider=tracer_provider)


    # Using kafka as normal now will automatically generate spans,
    # including user custom attributes added from the hooks
    conf = {'bootstrap.servers': "localhost:9092"}
    p.produce('my-topic',b'raw_bytes')
    msg = c.poll()

API
___
"""


References
----------

* `OpenTelemetry confluent-kafka/ Tracing <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/confluent-kafka/confluent-kafka.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
