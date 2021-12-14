from django.core.wsgi import get_wsgi_application
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware

application = get_wsgi_application()
