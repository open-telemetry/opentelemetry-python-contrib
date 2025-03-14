



Usage:
```

from opentelemetry.samplers.aws.aws_xray_remote_sampler import AwsXRayRemoteSampler

trace.set_tracer_provider(TracerProvider(sampler=ParentBased(xray_sampler)))
tracer = trace.get_tracer(__name__)


```