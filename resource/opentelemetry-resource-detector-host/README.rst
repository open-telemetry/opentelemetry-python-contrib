OpenTelemetry Host ID Resource Detector
=======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-resource-detector-host.svg
   :target: https://pypi.org/project/opentelemetry-resource-detector-host/

This library provides a custom `Resource Detector <https://opentelemetry.io/docs/specs/otel/resource/sdk/#detecting-resource-information-from-the-environment>`_
that sets the ``host.id`` resource attribute for a physical or virtual host, following the
`Host Resource Semantic Conventions <https://opentelemetry.io/docs/specs/semconv/resource/host/>`_.

The value is read from the non-privileged machine-id sources defined by the specification. It
complements the built-in host resource detector from the OpenTelemetry SDK, which only sets
``host.name`` and ``host.arch``.

Installation
------------

::

    pip install opentelemetry-resource-detector-host

---------------------------

Usage example for ``opentelemetry-resource-detector-host``

.. code-block:: python

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.resource.detector.host import (
        HostIdResourceDetector,
    )
    from opentelemetry.sdk.resources import get_aggregated_resources


    trace.set_tracer_provider(
        TracerProvider(
            resource=get_aggregated_resources(
                [
                    HostIdResourceDetector(),
                ]
            ),
        )
    )

Mappings
--------

The Host ID Resource Detector sets the ``host.id`` Resource Attribute from the following
non-privileged sources, depending on the operating system:

 * **Linux**: the contents of ``/etc/machine-id``, falling back to ``/var/lib/dbus/machine-id``.
 * **macOS**: the ``IOPlatformUUID`` value from ``ioreg -rd1 -c IOPlatformExpertDevice``.
 * **Windows**: the ``MachineGuid`` value under the ``HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Cryptography`` registry key.
 * **BSD**: the contents of ``/etc/hostid``, falling back to the output of ``kenv -q smbios.system.uuid``.

If no value can be read, the detector returns an empty resource and ``host.id`` is left unset. In
that case, the value can be provided explicitly through the ``OTEL_RESOURCE_ATTRIBUTES`` environment
variable.

References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Host Resource Semantic Conventions <https://opentelemetry.io/docs/specs/semconv/resource/host/>`_
