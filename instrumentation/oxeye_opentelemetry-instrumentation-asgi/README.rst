oxeye_opentelemetry ASGI Instrumentation
==================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/oxeye_opentelemetry-instrumentation-asgi.svg
   :target: https://pypi.org/project/oxeye_opentelemetry-instrumentation-asgi/


This library provides a ASGI middleware that can be used on any ASGI framework
(such as Django, Starlette, FastAPI or Quart) to track requests timing through oxeye_opentelemetry.

Installation
------------

::

    pip install oxeye_opentelemetry-instrumentation-asgi


Usage (Quart)
-------------

.. code-block:: python

    from quart import Quart
    from oxeye_opentelemetry.instrumentation.asgi import oxeye_opentelemetryMiddleware

    app = Quart(__name__)
    app.asgi_app = oxeye_opentelemetryMiddleware(app.asgi_app)

    @app.route("/")
    async def hello():
        return "Hello!"

    if __name__ == "__main__":
        app.run(debug=True)


Usage (Django 3.0)
------------------

Modify the application's ``asgi.py`` file as shown below.

.. code-block:: python

    import os
    from django.core.asgi import get_asgi_application
    from oxeye_opentelemetry.instrumentation.asgi import oxeye_opentelemetryMiddleware

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'asgi_example.settings')

    application = get_asgi_application()
    application = oxeye_opentelemetryMiddleware(application)


Usage (Raw ASGI)
----------------

.. code-block:: python

    from oxeye_opentelemetry.instrumentation.asgi import oxeye_opentelemetryMiddleware

    app = ...  # An ASGI application.
    app = oxeye_opentelemetryMiddleware(app)


References
----------

* `oxeye_opentelemetry Project <https://oxeye_opentelemetry.io/>`_
* `oxeye_opentelemetry Python Examples <https://github.com/ox-eye/oxeye_opentelemetry-python/tree/main/docs/examples>`_
