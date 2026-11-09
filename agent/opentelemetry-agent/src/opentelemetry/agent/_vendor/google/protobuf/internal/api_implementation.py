# Protocol Buffers - Google's data interchange format
# Copyright 2008 Google Inc.  All rights reserved.
#
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file or at
# https://developers.google.com/open-source/licenses/bsd
"""Determine which implementation of the protobuf API is used in this process."""

import os
import sys
import warnings

_GOOGLE3_PYTHON_UPB_DEFAULT = True


def _ApiVersionToImplementationType(api_version):
  if api_version == 2:
    return 'cpp'
  if api_version == 1:
    raise ValueError('api_version=1 is no longer supported.')
  if api_version == 0:
    return 'python'
  return None


# Only the vendored upb extension is considered (platform builds of the agent include it;
# the pure-Python build doesn't). Never probe for the application's google._upb /
# google.protobuf.pyext by their top-level names, and don't follow
# PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION, which configures the application's protobuf
# (e.g. "cpp" would make descriptor.py import the missing vendored pyext._message).
try:
  # pylint: disable=g-import-not-at-top
  from opentelemetry.agent._vendor.google._upb import _message as _c_module

  _implementation_type = 'upb'
except ImportError:
  _implementation_type = 'python'
  _c_module = None

# Detect if serialization should be deterministic by default
try:
  # The presence of this module in a build allows the proto implementation to
  # be upgraded merely via build deps.
  #
  # NOTE: Merely importing this automatically enables deterministic proto
  # serialization for C++ code, but we still need to export it as a boolean so
  # that we can do the same for `_implementation_type == 'python'`.
  #
  # NOTE2: It is possible for C++ code to enable deterministic serialization by
  # default _without_ affecting Python code, if the C++ implementation is not in
  # use by this module.  That is intended behavior, so we don't actually expose
  # this boolean outside of this module.
  #
  # pylint: disable=g-import-not-at-top,unused-import
  from opentelemetry.agent._vendor.google.protobuf import enable_deterministic_proto_serialization

  _python_deterministic_proto_serialization = True
except ImportError:
  _python_deterministic_proto_serialization = False


# Usage of this function is discouraged. Clients shouldn't care which
# implementation of the API is in use. Note that there is no guarantee
# that differences between APIs will be maintained.
# Please don't use this function if possible.
def Type():
  return _implementation_type


# For internal use only
def IsPythonDefaultSerializationDeterministic():
  return _python_deterministic_proto_serialization
