from configparser import ConfigParser
from os.path import join
from pathlib import Path
from re import compile as re_compile
from jinja2 import Environment, FileSystemLoader


tox_ini_paths = []

test_env_regex = re_compile(
    r"py(?P<pypy>py)?3(\{(?P<cpython_versions>[\w,]+)\})?-test-"
    r"(?P<name>[-\w]+\w)-?(\{(?P<test_versions>[\d,]+)\})?"
)

short_regex = re_compile(r"-test-")
tox_ini_path = join(str(Path(__file__).parents[2]), "tox.ini")
config_parser = ConfigParser()
config_parser.read(tox_ini_path)

long_regex_counter = 0
short_regex_counter = 0

envs = {}

for env in config_parser["tox"]["envlist"].split():
    env = env.strip()

    if env.startswith(";"):
        continue

    test_env_regex_match = test_env_regex.match(env)
    short_regex_match = short_regex.search(env)

    if test_env_regex_match is not None:
        long_regex_counter += 1

        env_dict = test_env_regex_match.groupdict()
        env_dict_name = env_dict["name"]

        if env_dict_name not in envs.keys():
            envs[env_dict_name] = []

        python_test_versions = {"python_versions": [], "test_versions": []}

        if env_dict["pypy"] is not None:
            python_test_versions["python_versions"].append("py3")

        if env_dict["cpython_versions"] is not None:
            (
                python_test_versions["python_versions"].
                extend(
                    [
                        f"3{cpython_version}"
                        for cpython_version
                        in env_dict["cpython_versions"].split(",")
                    ]
                )
            )

        if env_dict["test_versions"] is not None:
            (
                python_test_versions["test_versions"].
                extend(env_dict["test_versions"].split(","))
            )

        envs[env_dict_name].append(python_test_versions)

    if short_regex_match is not None:
        short_regex_counter += 1

assert short_regex_counter == long_regex_counter

sorted_envs = []

for key, value in envs.items():
    sorted_envs.append([key, value])

sorted_envs = sorted(sorted_envs)

jobs = []


def get_os_alias(os):
    return os.replace("-latest", "")


def get_python_version_alias(python_version):
    if python_version == "py3":
        return "pypy-3.8"

    return f"3.{python_version.replace('3', '')}"


for os in ["ubuntu-latest"]:

    for env_name, python_test_versions in sorted_envs:

        for python_test_version in python_test_versions:

            for python_version in python_test_version["python_versions"]:

                tox_env = f"py{python_version}-test-{env_name}"

                if python_test_version["test_versions"]:
                    for test_version in python_test_version["test_versions"]:

                        jobs.append(
                            {
                                "tox_env": f"{tox_env}-{test_version}",
                                "python_version": (
                                    f"{get_python_version_alias(python_version)}"
                                ),
                                "os": os,
                                "ui_name": (
                                    f"{env_name}-{test_version} "
                                    f"{get_python_version_alias(python_version)} "
                                    f"{get_os_alias(os)}"
                                ),
                                "name": (
                                    f"{env_name}_"
                                    f"{test_version}_"
                                    f"{python_version}_"
                                    f"{os}"
                                )
                            }
                        )

                else:
                    jobs.append(
                        {
                            "tox_env": f"{tox_env}",
                            "python_version": (
                                f"{get_python_version_alias(python_version)}"
                            ),
                            "os": os,
                            "ui_name": (
                                f"{env_name} "
                                f"{get_python_version_alias(python_version)} "
                                f"{get_os_alias(os)}"
                            ),
                            "name": (
                                f"{env_name}_"
                                f"{python_version}_"
                                f"{os}"
                            )
                        }
                    )

current_directory_path = Path(__file__).parent

with open(current_directory_path.joinpath("tests.yml"), "w") as test_yml_file:
    test_yml_file.write(
        Environment(
            loader=FileSystemLoader(current_directory_path)
        ).get_template("tests.yml.j2").render(**locals())
    )
