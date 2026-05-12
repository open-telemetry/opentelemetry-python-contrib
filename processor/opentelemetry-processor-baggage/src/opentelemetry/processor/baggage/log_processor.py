# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from typing import Sequence, Union

from opentelemetry.baggage import get_all as get_all_baggage
from opentelemetry.processor.baggage.processor import BaggageKeyPredicateT
from opentelemetry.sdk._logs import LogRecordProcessor, ReadWriteLogRecord

BaggageKeyPredicate = Union[
    BaggageKeyPredicateT, Sequence[BaggageKeyPredicateT]
]


class BaggageLogProcessor(LogRecordProcessor):
    """
    The BaggageLogProcessor reads entries stored in Baggage
    from the current context and adds the baggage entries' keys and
    values to the log record as attributes on emit.

    Add this log processor to a logger provider.

    ⚠ Warning ⚠️

    Do not put sensitive information in Baggage.

    To repeat: a consequence of adding data to Baggage is that the keys and
    values will appear in all outgoing HTTP headers from the application.
    """

    def __init__(
        self,
        baggage_key_predicate: BaggageKeyPredicate,
        max_baggage_attributes: int = 128,
    ) -> None:
        if callable(baggage_key_predicate):
            self._predicates = [baggage_key_predicate]
        else:
            self._predicates = list(baggage_key_predicate)
        self._max_baggage_attributes = max_baggage_attributes

    def _matches(self, key: str) -> bool:
        return any(predicate(key) for predicate in self._predicates)

    def on_emit(self, log_record: ReadWriteLogRecord) -> None:
        """Add baggage entries as log record attributes on emit.

        Baggage keys are filtered using the provided predicate(s).
        If a baggage key already exists in the log record attributes,
        it will not be overwritten to avoid collisions with attributes
        added by stdlib logging, calls to logging.emit, or custom
        LogRecordProcessors. At most max_baggage_attributes baggage
        entries will be added.
        """
        baggage = get_all_baggage()
        count = 0
        for key, value in baggage.items():
            if count >= self._max_baggage_attributes:
                break
            if self._matches(key):
                if key not in log_record.log_record.attributes:
                    log_record.log_record.attributes[key] = value
                    count += 1

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True
