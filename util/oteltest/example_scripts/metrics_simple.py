from typing import Mapping, Optional, Sequence

from oteltest import OtelTest, Telemetry


def print_time(iterations):
    import time
    from opentelemetry import trace, metrics

    meter = metrics.get_meter("time-printer", "1.0")
    print(f"got meter: {meter}")
    counter = meter.create_counter(
        "loop-counter", unit="1", description="my desc"
    )
    print(f"got counter: {counter}")
    tracer = trace.get_tracer("my.tracer.name")
    print(f"got tracer: {tracer}")
    for i in range(iterations):
        time.sleep(1)
        counter.add(1)
        with tracer.start_as_current_span("my-span") as span:
            print(f"{i + 1}/{iterations} current time: {round(time.time())}")


class MyTest(OtelTest):

    def environment_variables(self) -> Mapping[str, str]:
        return {}

    def requirements(self) -> Sequence[str]:
        return "opentelemetry-distro", "opentelemetry-exporter-otlp-proto-grpc"

    def wrapper_command(self) -> str:
        return "opentelemetry-instrument"

    def on_start(self) -> Optional[float]:
        print("started")
        return None

    def on_stop(
        self, telemetry: Telemetry, stdout: str, stderr: str, returncode: int
    ) -> None:
        print(f"stopped: {stdout}")
        print(f"telemetry: {telemetry}")


if __name__ == "__main__":
    print_time(10)
