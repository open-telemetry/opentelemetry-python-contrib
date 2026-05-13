# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
from os import environ
from typing import Optional

from ._constants import (
    _AKS_ARM_NAMESPACE_ID,
    _FUNCTIONS_WORKER_RUNTIME,
    _WEBSITE_OWNER_NAME,
    _WEBSITE_RESOURCE_GROUP,
    _WEBSITE_SITE_NAME,
)


def _is_on_aks() -> bool:
    return environ.get(_AKS_ARM_NAMESPACE_ID) is not None


def _is_on_app_service() -> bool:
    return environ.get(_WEBSITE_SITE_NAME) is not None


def _is_on_functions() -> bool:
    return environ.get(_FUNCTIONS_WORKER_RUNTIME) is not None


def _can_ignore_vm_detect() -> bool:
    return _is_on_aks() or _is_on_app_service() or _is_on_functions()


def _get_azure_resource_uri() -> Optional[str]:
    website_site_name = environ.get(_WEBSITE_SITE_NAME)
    website_resource_group = environ.get(_WEBSITE_RESOURCE_GROUP)
    website_owner_name = environ.get(_WEBSITE_OWNER_NAME)

    subscription_id = website_owner_name
    if website_owner_name and "+" in website_owner_name:
        subscription_id = website_owner_name[0 : website_owner_name.index("+")]

    if not (website_site_name and website_resource_group and subscription_id):
        return None

    return f"/subscriptions/{subscription_id}/resourceGroups/{website_resource_group}/providers/Microsoft.Web/sites/{website_site_name}"
