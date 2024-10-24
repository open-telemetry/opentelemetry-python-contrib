from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        with open(
            Path(__file__).parent.parent.parent.parent.joinpath("tox.ini")
        ) as tox_ini_file_0:
            with open(
                Path(__file__).parent.joinpath(
                    "src/generate_workflows_lib/tox.ini"
                ),
                "w",
            ) as tox_ini_file_1:
                tox_ini_file_1.write(tox_ini_file_0.read())
