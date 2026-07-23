# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

_instruments = ("crewai >= 1.15.5",)
# NOTE: only 1.15.5 has actually been tested against so far. The lower bound
# is set to that exact version deliberately, not a guess at an older
# compatible one -- widen it only after real testing against an older
# release, per tests/requirements.oldest.txt.
