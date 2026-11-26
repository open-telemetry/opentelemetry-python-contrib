# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


class RecordingHook:
    """Callable hook used by sync and async client tests."""

    def __init__(self, attr_name=None, raises=False):
        self.calls = 0
        self.attr_name = attr_name
        self.raises = raises

    def __call__(self, span, _value):
        self.calls += 1
        if self.raises:
            raise RuntimeError("Hook exception")  # pylint: disable=broad-exception-raised
        if self.attr_name:
            span.set_attribute(self.attr_name, True)


def set_span_attribute(attr_name, value_getter, span, value):
    """Set a span attribute, with the value getter bound by functools.partial."""
    span.set_attribute(attr_name, value_getter(value))
