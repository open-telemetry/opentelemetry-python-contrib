from argparse import ArgumentParser
from pathlib import Path
import re
import tomllib


def get_dependencies(pyproject) -> set[str]:
    return set(
        map(
            lambda dependency: re.sub(r"\[[^\]]+\]", "", dependency),
            pyproject["project"]["dependencies"],
        )
    )


def get_workspace_sources(pyproject) -> set[str]:
    return set(
        map(
            lambda package_and_properties: package_and_properties[0],
            filter(
                lambda package_and_properties: package_and_properties[1].get(
                    "workspace", False
                ),
                pyproject["tool"]["uv"]["sources"].items(),
            ),
        )
    )


def explore_package_members(pyproject, root_path) -> dict[str, Path]:
    paths_to_explore: list[Path] = sum(
        list(
            map(
                lambda member: list(root_path.glob(f"./{member}")),
                pyproject["tool"]["uv"]["workspace"]["members"],
            )
        ),
        [],
    )
    members = {}
    for potential_member_root_path in paths_to_explore:
        pyproject_member_path = potential_member_root_path / "pyproject.toml"
        if pyproject_member_path.is_file():
            with open(pyproject_member_path, "rb") as f:
                pyproject_member = tomllib.load(f)
            members[pyproject_member["project"]["name"]] = (
                potential_member_root_path
            )
    return members


def main(contrib_pyproject_path, core_pyproject_path):
    with open(contrib_pyproject_path, "rb") as f:
        pyproject_contrib = tomllib.load(f)

    with open(core_pyproject_path, "rb") as f:
        pyproject_core = tomllib.load(f)

    contrib_dependencies = get_dependencies(pyproject_contrib)
    contrib_workspace_sources = get_workspace_sources(pyproject_contrib)

    contrib_non_workspace_dependencies = (
        contrib_dependencies - contrib_workspace_sources
    )

    core_root_path = core_pyproject_path.parent
    core_members = explore_package_members(pyproject_core, core_root_path)

    for contrib_non_workspace_dependency in contrib_non_workspace_dependencies:
        if contrib_non_workspace_dependency in core_members:
            pyproject_contrib["tool"]["uv"]["sources"][
                contrib_non_workspace_dependency
            ] = {
                "path": Path.cwd().absolute()
                / core_pyproject_path.parent
                / core_members[contrib_non_workspace_dependency],
                "editable": True,
            }

    print("[tool.uv.sources]")

    def map_toml_value(value: str | bool | Path):
        if isinstance(value, (str, Path)):
            return f'"{value}"'
        if isinstance(value, bool):
            return "true" if value else "false"
        return value

    for source, properties in pyproject_contrib["tool"]["uv"][
        "sources"
    ].items():
        properties_str = ", ".join(
            map(
                lambda prop_and_value: (
                    f"{prop_and_value[0]} = {map_toml_value(prop_and_value[1])}"
                ),
                properties.items(),
            )
        )
        print(f"{source} = {{ {properties_str} }}")


if __name__ == "__main__":
    parser = ArgumentParser()

    parser.add_argument(
        "--contrib-pyproject-path",
        "-icontrib",
        required=True,
        help="Path to the pyproject.toml of the contrib repository",
    )
    parser.add_argument(
        "--core-pyproject-path",
        "-icore",
        required=True,
        help="Path to the pyproject.toml of the core repository",
    )

    args = parser.parse_args()

    main(Path(args.contrib_pyproject_path), Path(args.core_pyproject_path))
