OpenTelemetry Host Resource Detector
====================================

This package detects the host identifier from the Linux ``machine-id`` files
and exposes it as the ``host.id`` resource attribute.

Installation
------------

::

    pip install opentelemetry-resource-detector-host

Usage
-----

::

    from opentelemetry.resource.detector.host import HostIdResourceDetector
    from opentelemetry.sdk.resources import get_aggregated_resources

    resource = get_aggregated_resources([HostIdResourceDetector()])

The detector checks ``/etc/machine-id`` first, then
``/var/lib/dbus/machine-id``. If neither file is available, it returns an
empty resource.
