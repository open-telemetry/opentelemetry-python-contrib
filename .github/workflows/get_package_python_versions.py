from json import dumps
from configparser import ConfigParser
from os.path import join
from os import walk
from pathlib import Path
from re import compile as re_compile


tox_ini_paths = []

env_regex = re_compile(r"test-py\{([\w,]+)\}")
python_version_3_regex = re_compile(r"3\d\d?")

root_directory = str(Path(__file__).parents[2])

for root, directories, files in walk(root_directory):
    for file in files:
        if file == "tox.ini" and root_directory != root:
            tox_ini_paths.append(Path(join(root, file)))

config_parser = ConfigParser()

package_python_versions = []

for tox_ini_path in tox_ini_paths:
    config_parser.read(tox_ini_path)

    python_versions = []

    for env in config_parser["tox"]["envlist"].split():
        env_match = env_regex.match(env)

        if env_match is not None:
            for python_version in env_match.group(1).split(","):

                if python_version == "py3":
                    python_versions.append("pypy-3.8")

                elif python_version_3_regex.match(python_version):
                    python_versions.append(f"3.{python_version[1:]}")

                else:
                    raise Exception(
                        f"Invalid python version found in {tox_ini_path}: "
                        f"{python_version}"
                    )
            break

    if not python_versions:
        raise Exception(f"No python versions found in {tox_ini_path}")

    for python_version in python_versions:
        package_python_versions.append(
            {
                "tox_ini_directory": tox_ini_path.parent.name,
                "pyhon_version": python_version
            }
        )

# matrix_values = [{"os": "ubuntu-latest"}]
# matrix_values = [{"python_versions": ["py38", "py312"]}]
# python_versions = ["py38", "py312"]

# print(f"name=matrix::{dumps(matrix_values)}")

print(
    "::set-output name=package_python_versions::"
    f"{dumps(package_python_versions)}"
)
