# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest
from opentelemetry.util.http import redact_query_parameters

class TestRedactSensitiveInfo(unittest.TestCase):
    def test_redact_goog_signature(self):
        url = "https://www.example.com/path?color=blue&X-Goog-Signature=secret"
        self.assertEqual(redact_query_parameters(url), "https://www.example.com/path?color=blue&X-Goog-Signature=REDACTED")
    
    def test_no_redaction_needed(self):
        url = "https://www.example.com/path?color=blue&query=secret"
        self.assertEqual(redact_query_parameters(url), "https://www.example.com/path?color=blue&query=secret")
    
    def test_no_query_parameters(self):
        url = "https://www.example.com/path"
        self.assertEqual(redact_query_parameters(url), "https://www.example.com/path")
    
    def test_empty_query_string(self):
        url = "https://www.example.com/path?"
        self.assertEqual(redact_query_parameters(url), "https://www.example.com/path?")
    
    def test_empty_url(self):
        url = ""
        self.assertEqual(redact_query_parameters(url), "")
    
    def test_redact_aws_access_key_id(self):
        url = "https://www.example.com/path?color=blue&AWSAccessKeyId=secrets" 
        self.assertEqual(redact_query_parameters(url), "https://www.example.com/path?color=blue&AWSAccessKeyId=REDACTED")
    
    def test_api_key_not_in_redact_list(self):
        url = "https://www.example.com/path?api_key=secret%20key&user=john"
        self.assertNotEqual(redact_query_parameters(url), "https://www.example.com/path?api_key=REDACTED&user=john")
    
    def test_password_key_not_in_redact_list(self):
        url = "https://api.example.com?key=abc&password=123&user=admin"
        self.assertNotEqual(redact_query_parameters(url), "https://api.example.com?key=REDACTED&password=REDACTED&user=admin")
    
    def test_url_with_at_symbol_in_path_and_query(self):
        url = "https://github.com/p@th?foo=b@r"
        self.assertEqual(redact_query_parameters(url), "https://github.com/p@th?foo=b@r")
    
    def test_aws_access_key_with_real_format(self):
        url = "https://microsoft.com?AWSAccessKeyId=AKIAIOSFODNN7" 
        self.assertEqual(redact_query_parameters(url), "https://microsoft.com?AWSAccessKeyId=REDACTED")
    
    def test_signature_parameter(self):
        url = "https://service.com?sig=39Up9jzHkxhuIhFE9594DJxe7w6cIRCg0V6ICGS0" 
        self.assertEqual(redact_query_parameters(url), "https://service.com?sig=REDACTED")
    
    def test_signature_with_url_encoding(self):
        url = "https://service.com?Signature=39Up9jzHkxhuIhFE9594DJxe7w6cIRCg0V6ICGS0%3A377" 
        self.assertEqual(redact_query_parameters(url), "https://service.com?Signature=REDACTED")