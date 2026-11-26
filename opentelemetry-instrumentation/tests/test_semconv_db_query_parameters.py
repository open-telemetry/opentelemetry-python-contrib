# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Sequence
from typing import Any
from unittest import TestCase

from opentelemetry.instrumentation._semconv import (
    _DB_STATEMENT_PARAMETERS,
    _set_db_query_parameters,
    _StabilityMode,
)
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_QUERY_PARAMETER_TEMPLATE,
)


class ParameterWithFailingStr:
    def __repr__(self) -> str:
        return "<ParameterWithFailingStr>"

    def __str__(self) -> str:
        raise ValueError("str is not available for this value")


class ParameterWithFailingRepr:
    def __repr__(self) -> str:
        raise ValueError("repr is not available for this value")


class ParametersWithFailingBool(Sequence):
    def __init__(self, values: tuple[Any, ...]) -> None:
        self._values = values

    def __bool__(self) -> bool:
        raise ValueError("the truth value of these parameters is ambiguous")

    def __getitem__(self, index: int) -> Any:
        return self._values[index]

    def __len__(self) -> int:
        return len(self._values)


class TestSetDbQueryParametersFailures(TestCase):
    def test_skips_value_whose_str_fails(self):
        result = {}
        _set_db_query_parameters(
            result,
            ("jdoe", ParameterWithFailingStr(), 42),
            sem_conv_opt_in_mode=_StabilityMode.DATABASE,
        )
        self.assertEqual(
            result,
            {
                f"{DB_QUERY_PARAMETER_TEMPLATE}.0": "jdoe",
                f"{DB_QUERY_PARAMETER_TEMPLATE}.2": "42",
            },
        )

    def test_skips_legacy_blob_whose_str_fails(self):
        result = {}
        _set_db_query_parameters(
            result,
            (ParameterWithFailingRepr(),),
            sem_conv_opt_in_mode=_StabilityMode.DEFAULT,
        )
        self.assertEqual(result, {})

    def test_dup_keeps_legacy_blob_when_a_value_str_fails(self):
        result = {}
        _set_db_query_parameters(
            result,
            ("jdoe", ParameterWithFailingStr()),
            sem_conv_opt_in_mode=_StabilityMode.DATABASE_DUP,
        )
        self.assertEqual(
            result,
            {
                _DB_STATEMENT_PARAMETERS: "('jdoe', <ParameterWithFailingStr>)",
                f"{DB_QUERY_PARAMETER_TEMPLATE}.0": "jdoe",
            },
        )

    def test_captures_parameters_whose_bool_fails(self):
        result = {}
        _set_db_query_parameters(
            result,
            ParametersWithFailingBool(("jdoe", 42)),
            sem_conv_opt_in_mode=_StabilityMode.DATABASE,
        )
        self.assertEqual(
            result,
            {
                f"{DB_QUERY_PARAMETER_TEMPLATE}.0": "jdoe",
                f"{DB_QUERY_PARAMETER_TEMPLATE}.1": "42",
            },
        )

    def test_empty_sequence_captures_nothing(self):
        result = {}
        _set_db_query_parameters(
            result,
            (),
            sem_conv_opt_in_mode=_StabilityMode.DATABASE,
        )
        self.assertEqual(result, {})

    def test_empty_mapping_captures_nothing(self):
        result = {}
        _set_db_query_parameters(
            result,
            {},
            sem_conv_opt_in_mode=_StabilityMode.DATABASE,
        )
        self.assertEqual(result, {})
