# Blob Uploader Library (Experimental)

The Blob Uploader library provides an experimental way to
"write-aside" large or sensitive payloads to a blob storage
system, while retaining references to the written-aside destination
in the operations backend where telemetry is being written.

This is particularly intended for the use case of request/response
logging, where typical telemetry backends may be unsuitable for
writing this data, either due to size reasons or due to privacy
reasons. GenAI multi-modal prompt/response logging is a particularly
salient motivation for this feature, though general HTTP request/
response logging is another situation where this is applicable.

## Usage: Instrumentation Library

Instrumentation libraries should provide general hooks for handling
requests/responses (or other large blobs) that should be only
conditionally included in telemetry signals. The hooks should provide
enough context to allow a user of the instrumentation library to
conditionally choose what to do with the content including but not
limited to: dropping, including in the telemetry signal, or writing
to a BlobUploader and retaining a reference to the destination URI.

For example:

```

class RequestHook(abc.ABC):

  @abc.abstractmethod
  def handle_request(self, context, signal, request):
    pass


class ResponseHook(abc.ABC):

  @abc.abstractmethod:
  def handle_response(self, context, signal, response):
    pass


class FooInstrumentationLibrary:

  def __init__(self,
     # ...,
     request_hook: Optional[RequestHook]=None,
     response_hook: Optional[ResponseHook]=None,
     # ...)

  ...
```


## Usage: User of Instrumentation Library

Users of instrumentation libraries can use the Blob Uploader
libraries to implement relevant request/response hooks.

For example:

```
from opentelemetry.instrumentation._blobupload.api import ( 
    NOT_PROVIDED,
    Blob,
    BlobUploaderProvider,
    get_blob_uploader,
    set_blob_uploader_provider)


class MyBlobUploaderRequestHook(RequestHook):
  # ...

  def handle_request(self, context, signal, request):
    if not self.should_uploader(context):
      return
    use_case = self.select_use_case(context, signal)
    uploader = get_blob_uploader(use_case)
    blob = Blob(
        request.raw_bytes,
        content_type=request.content_type,
        labels=self.generate_blob_labels(context, signal, request))
    uri = uploader.upload_async(blob)
    if uri == NOT_UPLOADED:
      return
    signal.attributes[REQUEST_ATTRIBUTE] = uri

  # ...

class MyBlobUploaderProvider(BlobUploaderProvider):

  def get_blob_uploader(self, use_case=None):
    # ...


def main():
  set_blob_uploader_provider(MyBlobUploaderProvider())
  instrumentation_libary = FooInstrumentationLibrary(
      # ...,
      request_hook=MyBlobUploaderRequestHook(),
      # ...
  )
  # ...

```

## Future Work

As can be seen from the above usage examples, there is quite a
bit of common boilerplate both for instrumentation libraries (e.g.
defining the set of hook interfaces) and for consumers of those
instrumentation libraries (e.g. implementing variants of those hook
interfaces that make use of the BlobUploader libraries).

A potential future improvement would be to define a common set of
hook interfaces for this use case that can be be reused across
instrumentation libraries and to provide simple drop-in
implementations of those hooks that make use of BlobUploader.

Beyond this, boilerplate to define a custom 'BlobUploaderProvider'
could be reduced by expanding the capabilities of the default
provider, so that most common uses are covered with a minimal
set of environment variables (if optional deps are present).
