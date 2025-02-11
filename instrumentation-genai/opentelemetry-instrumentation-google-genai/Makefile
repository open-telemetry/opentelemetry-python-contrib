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

.PHONY: all test install clean

all: build test

test:
	./tools/test.sh

./dist/opentelemetry_instrumentation_google_genai-0.0.1-py3-none-any.whl: ./src/opentelemetry/instrumentation/google_genai/*.py
	./tools/build.sh

build: ./dist/opentelemetry_instrumentation_google_genai-0.0.1-py3-none-any.whl

install: ./dist/opentelemetry_instrumentation_google_genai-0.0.1-py3-none-any.whl
	pip install ./dist/opentelemetry_instrumentation_google_genai-0.0.1-py3-none-any.whl

clean:
	rm -rf .test
	rm -rf .build
	rm -rf build
	rm -rf dist
