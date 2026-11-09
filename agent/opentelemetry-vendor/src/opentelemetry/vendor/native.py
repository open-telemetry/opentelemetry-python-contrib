# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""The ``build-native`` command: build vendored packages' native extensions from their sdists.

The pure-Python vendor tree (from ``sync``) is committed. For platform-specific wheels,
``build-native`` downloads each configured distribution's hash-pinned sdist, applies its native
patches (which move the extension and the module names compiled into it under the vendor
namespace), builds it with PEP 517 in a temporary virtual environment and copies the resulting
stable-ABI (``abi3``) extensions into the vendor tree. ``build-native --clean`` restores the
committed state.
"""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import zipfile
from collections.abc import Collection
from pathlib import Path, PurePosixPath

from opentelemetry.vendor import output
from opentelemetry.vendor.checks import EXTENSION_SUFFIXES, NATIVE_MODULE_NAMES, check_findings, find_native_issues
from opentelemetry.vendor.config import NativeConfig, VendorConfig
from opentelemetry.vendor.download import download_sdist
from opentelemetry.vendor.errors import VendorError
from opentelemetry.vendor.metadata import canonicalize_name
from opentelemetry.vendor.patches import VendorPatch, apply_patches, read_patches
from opentelemetry.vendor.sbom import add_native_build
from opentelemetry.vendor.sync import read_requirements

_STATE_DIR = Path("build", "opentelemetry-vendor")
_MANIFEST = "native.json"
_SBOM_BACKUP = "sbom.cdx.json"


def build_native(config: VendorConfig) -> list[Path]:
    """Build the native extensions of every ``config.native`` distribution into the vendor tree.

    Returns the extension files written. On failure, the tree is restored with ``clean_native``.
    """
    _check_interpreter(config.python_version)
    clean_native(config, quiet=True)
    if not config.native:
        raise VendorError("no native builds configured ([tool.opentelemetry-vendor.native.<distribution>])")
    names = _vendored_names(config)
    requirements = {_requirement_name(line): line for line in read_requirements(config.requirements)}
    state = config.project_dir / _STATE_DIR
    manifest: dict[str, object] = {"extensions": [], "sbom_backup": None}
    try:
        state.mkdir(parents=True, exist_ok=True)
        if config.sbom_file is not None and config.sbom_file.exists():
            shutil.copy2(config.sbom_file, state / _SBOM_BACKUP)
            manifest["sbom_backup"] = _SBOM_BACKUP
        _write_manifest(state, manifest)

        written: list[Path] = []
        for name, native in sorted(config.native.items()):
            if name not in requirements:
                raise VendorError(f"native build {name!r} is not pinned in {config.requirements}")
            extensions, sdist_sha256, patches = _build(config, name, native, requirements[name])
            written += extensions
            manifest["extensions"] = sorted(path.relative_to(config.destination).as_posix() for path in written)
            _write_manifest(state, manifest)
            if config.sbom_file is not None:
                relative = [path.relative_to(config.destination).as_posix() for path in extensions]
                add_native_build(config.sbom_file, name, sdist_sha256, relative, patches)

        for finding in check_findings(
            find_native_issues(config.destination, names, config.namespace, written),
            config.allow,
            (NATIVE_MODULE_NAMES,),
        ):
            output.detail(f"allowed {finding.kind} {finding.path}@{finding.line}: {finding.code}")
        output.step(f"Checked {output.plural(len(written), 'native extension')}")
        if config.sbom_file is not None:
            output.step("Updated SBOM with the native builds")
        return written
    except BaseException:
        clean_native(config, quiet=True)
        raise


def clean_native(config: VendorConfig, *, quiet: bool = False) -> None:
    """Remove the extensions written by ``build_native`` and restore the committed SBOM."""
    state = config.project_dir / _STATE_DIR
    manifest_path = state / _MANIFEST
    if not manifest_path.exists():
        if not quiet:
            output.step("No native build to clean")
        return
    manifest = json.loads(manifest_path.read_text())
    for relative in manifest["extensions"]:
        extension = config.destination / relative
        extension.unlink(missing_ok=True)
        output.detail(f"removed {relative}")
        # Remove directories that only existed for the extension.
        for parent in extension.parents:
            if parent == config.destination or any(parent.iterdir()):
                break
            parent.rmdir()
    if manifest["sbom_backup"] and config.sbom_file is not None:
        shutil.copy2(state / manifest["sbom_backup"], config.sbom_file)
        (state / manifest["sbom_backup"]).unlink()
    manifest_path.unlink()
    if not any(state.iterdir()):
        state.rmdir()
    if not quiet:
        count = output.plural(len(manifest["extensions"]), "native extension")
        output.step(f"Cleaned {count} and restored the SBOM")


def _build(
    config: VendorConfig, name: str, native: NativeConfig, requirement: str
) -> tuple[list[Path], str, list[VendorPatch]]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        with output.status(f"Downloading the {name} sdist…"):
            sdist = download_sdist(requirement, root / "sdist")
        sdist_sha256 = hashlib.sha256(sdist.read_bytes()).hexdigest()
        output.step(f"Downloaded sdist {sdist.name}")

        source = _extract(sdist, root / "src")
        patches = read_patches(native.patches)
        if patches:
            apply_patches(source, patches)
            output.step(f"Applied {output.plural(len(patches), 'native patch', 'native patches')} to {name}")

        with output.status(f"Building {name}…"):
            wheel = _build_wheel(source, native.build_requirements, root / "build")
        extensions = _install_extensions(wheel, config)
        for extension in extensions:
            output.detail(f"built {extension.relative_to(config.destination).as_posix()}")
        output.step(f"Built {output.plural(len(extensions), 'extension')} for {name}")
        return extensions, sdist_sha256, patches


def _check_interpreter(python_version: str) -> None:
    current = f"{sys.version_info.major}.{sys.version_info.minor}"
    if platform.python_implementation() != "CPython" or current != python_version:
        raise VendorError(
            f"build-native must run on CPython {python_version} (running {platform.python_implementation()} "
            f"{current}): stable-ABI (abi3) extensions are compiled against the oldest supported Python"
        )
    if sysconfig.get_config_var("Py_GIL_DISABLED"):
        raise VendorError(
            "build-native can't run on a free-threaded interpreter: abi3 extensions don't support it, "
            "and free-threaded Pythons use the pure-Python agent wheel"
        )


def _vendored_names(config: VendorConfig) -> set[str]:
    """Top-level vendored module and package names, from the synced tree."""
    names = set()
    for child in config.destination.iterdir():
        if child.name in config.protected_files or child.name.startswith((".", "__")):
            continue
        if child.is_dir() and any(child.rglob("*.py")):
            names.add(child.name)
        elif child.suffix == ".py":
            names.add(child.stem)
    if not names:
        raise VendorError(f"{config.destination} has no vendored packages; run opentelemetry-vendor sync first")
    return names


def _requirement_name(line: str) -> str:
    name = line.split(maxsplit=1)[0]
    for separator in "=<>!~;[@ ":
        name = name.split(separator, 1)[0]
    return canonicalize_name(name)


def _extract(sdist: Path, dest: Path) -> Path:
    """Safely extract ``sdist`` into ``dest`` and return its single top-level directory."""
    dest.mkdir(parents=True)
    if sdist.name.endswith(".zip"):
        with zipfile.ZipFile(sdist) as archive:
            members = archive.namelist()
            _check_members(sdist, members)
            archive.extractall(dest)
    else:
        with tarfile.open(sdist) as archive:
            members = archive.getmembers()
            _check_members(sdist, [member.name for member in members])
            for member in members:
                if not (member.isfile() or member.isdir()):
                    raise VendorError(f"{sdist.name} contains a link or special file: {member.name}")
            if hasattr(tarfile, "data_filter"):
                archive.extractall(dest, filter="data")
            else:
                archive.extractall(dest)  # members checked above
    tops = list(dest.iterdir())
    if len(tops) != 1 or not tops[0].is_dir():
        raise VendorError(f"{sdist.name} must contain a single top-level directory")
    return tops[0]


def _check_members(sdist: Path, names: Collection[str]) -> None:
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise VendorError(f"{sdist.name} contains an unsafe path: {name}")


def _build_wheel(source: Path, build_requirements: Path, work: Path) -> Path:
    """Build ``source`` into a wheel with PEP 517, in a venv with the hash-pinned build requirements."""
    venv = work / "venv"
    _run([sys.executable, "-m", "venv", str(venv)], "creating the build environment")
    python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    pip = [str(python), "-m", "pip", "--disable-pip-version-check"]
    _run(
        [*pip, "install", "--no-deps", "--require-hashes", "-r", str(build_requirements)],
        "installing the build requirements",
    )
    wheels = work / "wheels"
    _run(
        [*pip, "wheel", "--no-deps", "--no-build-isolation", "--wheel-dir", str(wheels), str(source)],
        f"building {source.name}",
    )
    built = sorted(wheels.glob("*.whl"))
    if len(built) != 1:
        raise VendorError(f"building {source.name} produced {len(built)} wheels")
    return built[0]


def _install_extensions(wheel: Path, config: VendorConfig) -> list[Path]:
    """Copy the namespaced extensions from ``wheel`` into the vendor tree."""
    prefix = config.namespace.replace(".", "/") + "/"
    written = []
    with zipfile.ZipFile(wheel) as archive:
        for member in sorted(archive.namelist()):
            if not member.startswith(prefix) or not member.endswith(EXTENSION_SUFFIXES):
                continue
            relative = member[len(prefix) :]
            if not (".abi3." in PurePosixPath(relative).name or relative.endswith(".pyd")):
                raise VendorError(f"{wheel.name}: {member} isn't a stable-ABI (abi3) extension")
            target = config.destination / relative
            # e.g. google/_upb only holds the extension: an implicit namespace package.
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(member))
            target.chmod(0o755)
            written.append(target)
    if not written:
        raise VendorError(f"{wheel.name} contains no extension under {prefix} (check the native patches)")
    return written


def _run(command: list[str], action: str) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    output.detail(result.stdout.strip())
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-30:])
        raise VendorError(f"{action} failed (exit code {result.returncode}):\n{tail}")


def _write_manifest(state: Path, manifest: dict[str, object]) -> None:
    (state / _MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
