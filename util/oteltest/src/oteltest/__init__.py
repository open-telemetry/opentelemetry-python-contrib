# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import abc
import dataclasses
import json
from typing import List, Mapping, Optional, Sequence

from oteltest.telemetry import Telemetry


class OtelTest(abc.ABC):
    """
    Abstract base class for tests using OtelTest. No need to instantiate or call it -- just define a subclass of
    OtelTest anywhere in your script.

    The first three methods are for configuration and the second two are callbacks.

    When you run the `oteltest` command against your script, a new Python virtual environment is created with the
    configuration specified by this class's implementation. The two callbacks are then run, but not in the subprocess
    of the script, rather in the process of the oteltest command.
    """

    @abc.abstractmethod
    def environment_variables(self) -> Mapping[str, str]:
        """
        Return a mapping of environment variables to their values. These will become the env vars for your script.
        """

    @abc.abstractmethod
    def requirements(self) -> Sequence[str]:
        """
        Return a sequence of requirements for the script. Each string should be formatted as for `pip install`.
        """

    @abc.abstractmethod
    def wrapper_command(self) -> str:
        """
        Return a wrapper command to run the script. For example, return 'opentelemetry-instrument' for
        `opentelemetry-instrument python my_script.py`. Return an empty string for`python my_script.py`.
        """

    @abc.abstractmethod
    def on_start(self) -> Optional[float]:
        """
        Called immediately after the script has started.

        You can add client code here to call your server and have it produce telemetry.
        Note: you may need to sleep or check for liveness first!
        Note: this method will run in the Python virtual environment of `oteltest`, not that of the script.

        Return a float indicating how long to wait in seconds for the script to finish. Once that time has elapsed,
        the subprocess running the script will be force terminated. Or return `None` to allow the script to finish on
        its own, in which case the script should shut itself down.
        """

    @abc.abstractmethod
    def on_stop(
        self, tel: Telemetry, stdout: str, stderr: str, returncode: int
    ) -> None:
        """
        Called immediately after the script has ended. Passed in are both the telemetry otelsink received while the
        script was running and the output of the script (stdout, stderr, returncode).
        """
