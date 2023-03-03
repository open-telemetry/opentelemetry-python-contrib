import aiobotocore.awsrequest
import aiobotocore.endpoint
import pytest


class MockedAWSResponse(aiobotocore.awsrequest.AioAWSResponse):
    """
    Patch aiobotocore to work with moto
    See https://github.com/aio-libs/aiobotocore/issues/755
    """

    def __init__(self, response):
        self._response = response
        self.headers = response.headers
        self.raw = response.raw
        self.raw.raw_headers = {
            k.encode("utf-8"): str(v).encode("utf-8")
            for k, v in response.headers.items()
        }.items()
        self.status_code = response.status_code

    async def _content_prop(self):
        return self._response.content


@pytest.fixture(autouse=True, scope="session")
def patch_aiobotocore_endpoint():
    original = aiobotocore.endpoint.convert_to_response_dict

    def patched(http_response, operation_model):
        return original(MockedAWSResponse(http_response), operation_model)

    aiobotocore.endpoint.convert_to_response_dict = patched


@pytest.fixture(autouse=True, scope="session")
def patch_aiobotocore_retryhandler():
    original = aiobotocore.retryhandler.AioCRC32Checker._check_response

    def patched(self, attempt_number, response):
        return original(self, attempt_number, [MockedAWSResponse(response[0])])

    aiobotocore.retryhandler.AioCRC32Checker._check_response = patched
