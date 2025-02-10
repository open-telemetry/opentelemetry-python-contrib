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
