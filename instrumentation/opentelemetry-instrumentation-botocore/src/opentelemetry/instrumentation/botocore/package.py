# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

_instruments_botocore = ("botocore~=1.0",)
_instruments_aiobotocore = ("aiobotocore~=2.0",)

_instruments = ()
_instruments_any = (*_instruments_botocore, *_instruments_aiobotocore)
