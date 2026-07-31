# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Includes work from:
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations


# Disable snake_case naming style so this class can match the sampling rules response from X-Ray
# pylint: disable=invalid-name,too-many-positional-arguments
class _SamplingRule:
    def __init__(
        self,
        Attributes: dict[str, str] | None = None,
        FixedRate: float | None = None,
        HTTPMethod: str | None = None,
        Host: str | None = None,
        Priority: int | None = None,
        ReservoirSize: int | None = None,
        ResourceARN: str | None = None,
        RuleARN: str | None = None,
        RuleName: str | None = None,
        ServiceName: str | None = None,
        ServiceType: str | None = None,
        URLPath: str | None = None,
        Version: int | None = None,
    ):
        self.Attributes = Attributes if Attributes is not None else {}
        self.FixedRate = FixedRate if FixedRate is not None else 0.0
        self.HTTPMethod = HTTPMethod if HTTPMethod is not None else ""
        self.Host = Host if Host is not None else ""
        # Default to value with lower priority than default rule
        self.Priority = Priority if Priority is not None else 10001
        self.ReservoirSize = ReservoirSize if ReservoirSize is not None else 0
        self.ResourceARN = ResourceARN if ResourceARN is not None else ""
        self.RuleARN = RuleARN if RuleARN is not None else ""
        self.RuleName = RuleName if RuleName is not None else ""
        self.ServiceName = ServiceName if ServiceName is not None else ""
        self.ServiceType = ServiceType if ServiceType is not None else ""
        self.URLPath = URLPath if URLPath is not None else ""
        self.Version = Version if Version is not None else 0

    def __lt__(self, other: "_SamplingRule") -> bool:
        if self.Priority == other.Priority:
            # String order priority example:
            # "A","Abc","a","ab","abc","abcdef"
            return self.RuleName < other.RuleName
        return self.Priority < other.Priority

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _SamplingRule):
            return False
        return (
            self.FixedRate == other.FixedRate
            and self.HTTPMethod == other.HTTPMethod
            and self.Host == other.Host
            and self.Priority == other.Priority
            and self.ReservoirSize == other.ReservoirSize
            and self.ResourceARN == other.ResourceARN
            and self.RuleARN == other.RuleARN
            and self.RuleName == other.RuleName
            and self.ServiceName == other.ServiceName
            and self.ServiceType == other.ServiceType
            and self.URLPath == other.URLPath
            and self.Version == other.Version
            and self.Attributes == other.Attributes
        )
