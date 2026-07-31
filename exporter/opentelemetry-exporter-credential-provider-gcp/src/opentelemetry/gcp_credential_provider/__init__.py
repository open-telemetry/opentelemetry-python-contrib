# Copyright 2025 Google LLC
# SPDX-License-Identifier: Apache-2.0

import google.auth
import grpc
import requests
from google.auth.transport.grpc import AuthMetadataPlugin
from google.auth.transport.requests import AuthorizedSession, Request

# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false


def create_google_grpc_credentials() -> grpc.ChannelCredentials:
    credentials, _ = google.auth.default()
    return grpc.composite_channel_credentials(
        grpc.ssl_channel_credentials(),
        grpc.metadata_call_credentials(
            AuthMetadataPlugin(credentials=credentials, request=Request())
        ),
    )


def create_google_authorized_session() -> requests.Session:
    credentials, _ = google.auth.default()
    return AuthorizedSession(credentials)
