# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


def attach_span(
    span_registry, message_id, span_and_activation, is_publish=False
):
    span_registry[(message_id, is_publish)] = span_and_activation


def detach_span(span_registry, message_id, is_publish=False):
    span_registry.pop((message_id, is_publish))


def retrieve_span(span_registry, message_id, is_publish=False):
    return span_registry.get((message_id, is_publish), (None, None))


def get_operation_name(hook_name, retry_count):
    if hook_name == "before_process_message":
        return (
            "remoulade/process"
            if retry_count == 0
            else f"remoulade/process(retry-{retry_count})"
        )
    if hook_name == "before_enqueue":
        return (
            "remoulade/send"
            if retry_count == 0
            else f"remoulade/send(retry-{retry_count})"
        )
    return ""
