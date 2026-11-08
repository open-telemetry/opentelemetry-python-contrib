# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Generate a CycloneDX SBOM for the vendored packages."""

from __future__ import annotations

import json
import uuid
from collections.abc import Collection
from pathlib import Path

from cyclonedx.contrib.license.factories import LicenseFactory
from cyclonedx.model import HashAlgorithm, HashType
from cyclonedx.model.bom import Bom
from cyclonedx.model.component import Component, ComponentType
from cyclonedx.output.json import JsonV1Dot6
from cyclonedx.schema import SchemaVersion
from cyclonedx.validation.json import JsonStrictValidator
from packageurl import PackageURL

from opentelemetry.vendor.errors import VendorError
from opentelemetry.vendor.metadata import VendoredPackage


def write_sbom(packages: Collection[VendoredPackage], path: Path) -> None:
    """Write a CycloneDX 1.6 JSON SBOM describing ``packages`` to ``path``.

    The output is deterministic: syncing the same requirements twice produces
    an identical file.
    """
    ordered = sorted(packages, key=lambda package: package.name)
    license_factory = LicenseFactory()
    components = [_component(package, license_factory) for package in ordered]
    identity = "\n".join(f"{package.name} {package.version} {package.sha256}" for package in ordered)
    bom = Bom(
        components=components,
        serial_number=uuid.uuid5(uuid.NAMESPACE_URL, identity),
    )

    document = json.loads(JsonV1Dot6(bom).output_as_string())
    # The timestamp is optional; dropping it keeps re-syncs diff-free.
    document["metadata"].pop("timestamp", None)
    output = json.dumps(document, indent=2) + "\n"

    error = JsonStrictValidator(SchemaVersion.V1_6).validate_str(output)
    if error is not None:
        raise VendorError(f"generated SBOM is invalid: {error}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output)


def _component(package: VendoredPackage, license_factory: LicenseFactory) -> Component:
    purl = PackageURL(type="pypi", name=package.name, version=package.version)
    return Component(
        type=ComponentType.LIBRARY,
        name=package.name,
        version=package.version,
        purl=purl,
        bom_ref=purl.to_string(),
        hashes=[HashType(alg=HashAlgorithm.SHA_256, content=package.sha256)],
        licenses=[license_factory.make_from_string(package.license_expression)] if package.license_expression else None,
    )
