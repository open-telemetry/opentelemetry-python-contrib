oxeye_opentelemetry Util HTTP
=======================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/oxeye_opentelemetry-util-http.svg
   :target: https://pypi.org/project/oxeye_opentelemetry-util-http/


This library provides ASGI, WSGI middleware and other HTTP-related
functionality that is common to instrumented web frameworks (such as Django,
Starlette, FastAPI, etc.) to track requests timing through oxeye_opentelemetry.

Installation
------------

::

    pip install oxeye_opentelemetry-util-http


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
