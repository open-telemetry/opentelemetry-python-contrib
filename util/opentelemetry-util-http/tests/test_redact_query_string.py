# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import unittest

from opentelemetry.util.http import (
    PARAMS_TO_REDACT,
    redact_query_parameters,
    redact_query_string,
)


class TestRedactQueryString(unittest.TestCase):
    def test_redacts_every_sensitive_param(self):
        for param in PARAMS_TO_REDACT:
            with self.subTest(param=param):
                self.assertEqual(
                    redact_query_string(f"color=blue&{param}=secret"),
                    f"color=blue&{param}=REDACTED",
                )

    def test_redacts_multiple_params_in_one_query(self):
        self.assertEqual(
            redact_query_string("file=a.txt&Signature=SUPERSECRET&AWSAccessKeyId=AKIA123"),
            "file=a.txt&Signature=REDACTED&AWSAccessKeyId=REDACTED",
        )

    def test_no_redaction_needed(self):
        query = "color=blue&query=secret"
        self.assertEqual(redact_query_string(query), query)

    def test_empty_query_string(self):
        self.assertEqual(redact_query_string(""), "")

    def test_preserves_valueless_and_blank_params(self):
        self.assertEqual(
            redact_query_string("flag&a=&b=1&Signature=s"),
            "flag&a=&b=1&Signature=REDACTED",
        )

    def test_preserves_percent_encoding_of_other_params(self):
        self.assertEqual(
            redact_query_string("b=1%20x&path=%2Ffoo&Signature=s"),
            "b=1%20x&path=%2Ffoo&Signature=REDACTED",
        )

    def test_preserves_repeated_params(self):
        self.assertEqual(
            redact_query_string("a=1&a=2&Signature=s"),
            "a=1&a=2&Signature=REDACTED",
        )

    def test_redacts_repeated_sensitive_param(self):
        self.assertEqual(
            redact_query_string("Signature=one&Signature=two"),
            "Signature=REDACTED&Signature=REDACTED",
        )

    def test_param_name_without_separator_is_not_redacted(self):
        # `Signature` here is a valueless param, there is nothing to redact.
        self.assertEqual(redact_query_string("Signature"), "Signature")

    def test_redacts_percent_encoded_param_name(self):
        # `%53` decodes to `S`, so this is the `Signature` key. The name must
        # be reported exactly as it was sent, only the value is replaced.
        self.assertEqual(
            redact_query_string("%53ignature=secret"),
            "%53ignature=REDACTED",
        )

    def test_redacts_fully_percent_encoded_param_name(self):
        self.assertEqual(
            redact_query_string("color=blue&%53%69gnature=secret"),
            "color=blue&%53%69gnature=REDACTED",
        )

    def test_percent_encoded_name_matches_redact_query_parameters(self):
        # The helper feeding `url.query` must not be weaker than the one
        # feeding `url.full`, or the same span reports two different answers.
        self.assertNotIn("secret", redact_query_string("%53ignature=secret"))
        self.assertNotIn("secret", redact_query_parameters("/p?%53ignature=secret"))

    def test_match_is_case_sensitive(self):
        # Query parameter names are case sensitive and the semantic
        # conventions list the exact keys to redact.
        self.assertEqual(redact_query_string("SIGNATURE=secret"), "SIGNATURE=secret")

    def test_does_not_parse_the_value_as_a_url(self):
        # A value that would break urlparse must still be handled.
        self.assertEqual(
            redact_query_string("next=//exa[mple&Signature=s"),
            "next=//exa[mple&Signature=REDACTED",
        )

    def test_returns_str(self):
        self.assertIsInstance(redact_query_string("Signature=s"), str)
