def attach_span(span_registry, message_id, span, is_publish=False):
    span_registry[(message_id, is_publish)] = span


def detach_span(span_registry, message_id, is_publish=False):
    span_registry.pop((message_id, is_publish))


def retrieve_span(span_registry, message_id, is_publish=False):
    return span_registry.get((message_id, is_publish), (None, None))
