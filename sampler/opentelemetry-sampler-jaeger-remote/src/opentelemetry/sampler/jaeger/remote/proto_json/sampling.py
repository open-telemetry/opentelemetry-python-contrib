# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# AUTO-GENERATED from "sampling.proto"
# DO NOT EDIT MANUALLY

from __future__ import annotations

import builtins
import dataclasses
import enum
import functools
import typing

_dataclass = functools.partial(dataclasses.dataclass, slots=True)

from . import _json_codec


@typing.final
class SamplingStrategyType(enum.IntEnum):
    """
    Generated from protobuf enum SamplingStrategyType
    """

    PROBABILISTIC = 0
    RATE_LIMITING = 1

@typing.final
@_dataclass
class ProbabilisticSamplingStrategy(_json_codec.JsonMessage):
    """
    Generated from protobuf message ProbabilisticSamplingStrategy
    """

    samplingRate: builtins.float | None = 0.0

    def to_dict(self) -> builtins.dict[builtins.str, typing.Any]:
        """
        Convert this message to a dictionary with lowerCamelCase keys.

        Returns:
            Dictionary representation following OTLP JSON encoding
        """
        _result = {}
        if self.samplingRate:
            _result["samplingRate"] = _json_codec.encode_float(self.samplingRate)
        return _result

    @builtins.classmethod
    def from_dict(cls, data: builtins.dict[builtins.str, typing.Any]) -> "ProbabilisticSamplingStrategy":
        """
        Create from a dictionary with lowerCamelCase keys.

        Args:
            data: Dictionary representation following OTLP JSON encoding

        Returns:
            ProbabilisticSamplingStrategy instance
        """
        _json_codec.validate_type(data, builtins.dict, "data")
        _args = {}

        if (_value := data.get("samplingRate")) is not None:
            _args["samplingRate"] = _json_codec.decode_float(_value, "samplingRate")

        return cls(**_args)


@typing.final
@_dataclass
class RateLimitingSamplingStrategy(_json_codec.JsonMessage):
    """
    Generated from protobuf message RateLimitingSamplingStrategy
    """

    maxTracesPerSecond: builtins.int | None = 0

    def to_dict(self) -> builtins.dict[builtins.str, typing.Any]:
        """
        Convert this message to a dictionary with lowerCamelCase keys.

        Returns:
            Dictionary representation following OTLP JSON encoding
        """
        _result = {}
        if self.maxTracesPerSecond:
            _result["maxTracesPerSecond"] = self.maxTracesPerSecond
        return _result

    @builtins.classmethod
    def from_dict(cls, data: builtins.dict[builtins.str, typing.Any]) -> "RateLimitingSamplingStrategy":
        """
        Create from a dictionary with lowerCamelCase keys.

        Args:
            data: Dictionary representation following OTLP JSON encoding

        Returns:
            RateLimitingSamplingStrategy instance
        """
        _json_codec.validate_type(data, builtins.dict, "data")
        _args = {}

        if (_value := data.get("maxTracesPerSecond")) is not None:
            _json_codec.validate_type(_value, builtins.int, "maxTracesPerSecond")
            _args["maxTracesPerSecond"] = _value

        return cls(**_args)


@typing.final
@_dataclass
class OperationSamplingStrategy(_json_codec.JsonMessage):
    """
    Generated from protobuf message OperationSamplingStrategy
    """

    operation: builtins.str | None = ""
    probabilisticSampling: ProbabilisticSamplingStrategy | None = None

    def to_dict(self) -> builtins.dict[builtins.str, typing.Any]:
        """
        Convert this message to a dictionary with lowerCamelCase keys.

        Returns:
            Dictionary representation following OTLP JSON encoding
        """
        _result = {}
        if self.operation:
            _result["operation"] = self.operation
        if self.probabilisticSampling:
            _result["probabilisticSampling"] = self.probabilisticSampling.to_dict()
        return _result

    @builtins.classmethod
    def from_dict(cls, data: builtins.dict[builtins.str, typing.Any]) -> "OperationSamplingStrategy":
        """
        Create from a dictionary with lowerCamelCase keys.

        Args:
            data: Dictionary representation following OTLP JSON encoding

        Returns:
            OperationSamplingStrategy instance
        """
        _json_codec.validate_type(data, builtins.dict, "data")
        _args = {}

        if (_value := data.get("operation")) is not None:
            _json_codec.validate_type(_value, builtins.str, "operation")
            _args["operation"] = _value
        if (_value := data.get("probabilisticSampling")) is not None:
            _args["probabilisticSampling"] = ProbabilisticSamplingStrategy.from_dict(_value)

        return cls(**_args)


@typing.final
@_dataclass
class PerOperationSamplingStrategies(_json_codec.JsonMessage):
    """
    Generated from protobuf message PerOperationSamplingStrategies
    """

    defaultSamplingProbability: builtins.float | None = 0.0
    defaultLowerBoundTracesPerSecond: builtins.float | None = 0.0
    perOperationStrategies: builtins.list[OperationSamplingStrategy] = dataclasses.field(default_factory=builtins.list)
    defaultUpperBoundTracesPerSecond: builtins.float | None = 0.0

    def to_dict(self) -> builtins.dict[builtins.str, typing.Any]:
        """
        Convert this message to a dictionary with lowerCamelCase keys.

        Returns:
            Dictionary representation following OTLP JSON encoding
        """
        _result = {}
        if self.defaultSamplingProbability:
            _result["defaultSamplingProbability"] = _json_codec.encode_float(self.defaultSamplingProbability)
        if self.defaultLowerBoundTracesPerSecond:
            _result["defaultLowerBoundTracesPerSecond"] = _json_codec.encode_float(self.defaultLowerBoundTracesPerSecond)
        if self.perOperationStrategies:
            _result["perOperationStrategies"] = _json_codec.encode_repeated(self.perOperationStrategies, lambda _v: _v.to_dict())
        if self.defaultUpperBoundTracesPerSecond:
            _result["defaultUpperBoundTracesPerSecond"] = _json_codec.encode_float(self.defaultUpperBoundTracesPerSecond)
        return _result

    @builtins.classmethod
    def from_dict(cls, data: builtins.dict[builtins.str, typing.Any]) -> "PerOperationSamplingStrategies":
        """
        Create from a dictionary with lowerCamelCase keys.

        Args:
            data: Dictionary representation following OTLP JSON encoding

        Returns:
            PerOperationSamplingStrategies instance
        """
        _json_codec.validate_type(data, builtins.dict, "data")
        _args = {}

        if (_value := data.get("defaultSamplingProbability")) is not None:
            _args["defaultSamplingProbability"] = _json_codec.decode_float(_value, "defaultSamplingProbability")
        if (_value := data.get("defaultLowerBoundTracesPerSecond")) is not None:
            _args["defaultLowerBoundTracesPerSecond"] = _json_codec.decode_float(_value, "defaultLowerBoundTracesPerSecond")
        if (_value := data.get("perOperationStrategies")) is not None:
            _args["perOperationStrategies"] = _json_codec.decode_repeated(_value, lambda _v: OperationSamplingStrategy.from_dict(_v), "perOperationStrategies")
        if (_value := data.get("defaultUpperBoundTracesPerSecond")) is not None:
            _args["defaultUpperBoundTracesPerSecond"] = _json_codec.decode_float(_value, "defaultUpperBoundTracesPerSecond")

        return cls(**_args)


@typing.final
@_dataclass
class SamplingStrategyResponse(_json_codec.JsonMessage):
    """
    Generated from protobuf message SamplingStrategyResponse
    """

    strategyType: SamplingStrategyType | builtins.int | None = 0
    probabilisticSampling: ProbabilisticSamplingStrategy | None = None
    rateLimitingSampling: RateLimitingSamplingStrategy | None = None
    operationSampling: PerOperationSamplingStrategies | None = None

    def to_dict(self) -> builtins.dict[builtins.str, typing.Any]:
        """
        Convert this message to a dictionary with lowerCamelCase keys.

        Returns:
            Dictionary representation following OTLP JSON encoding
        """
        _result = {}
        if self.strategyType:
            _result["strategyType"] = builtins.int(self.strategyType)
        if self.probabilisticSampling:
            _result["probabilisticSampling"] = self.probabilisticSampling.to_dict()
        if self.rateLimitingSampling:
            _result["rateLimitingSampling"] = self.rateLimitingSampling.to_dict()
        if self.operationSampling:
            _result["operationSampling"] = self.operationSampling.to_dict()
        return _result

    @builtins.classmethod
    def from_dict(cls, data: builtins.dict[builtins.str, typing.Any]) -> "SamplingStrategyResponse":
        """
        Create from a dictionary with lowerCamelCase keys.

        Args:
            data: Dictionary representation following OTLP JSON encoding

        Returns:
            SamplingStrategyResponse instance
        """
        _json_codec.validate_type(data, builtins.dict, "data")
        _args = {}

        if (_value := data.get("strategyType")) is not None:
            _json_codec.validate_type(_value, builtins.int, "strategyType")
            _args["strategyType"] = SamplingStrategyType(_value)
        if (_value := data.get("probabilisticSampling")) is not None:
            _args["probabilisticSampling"] = ProbabilisticSamplingStrategy.from_dict(_value)
        if (_value := data.get("rateLimitingSampling")) is not None:
            _args["rateLimitingSampling"] = RateLimitingSamplingStrategy.from_dict(_value)
        if (_value := data.get("operationSampling")) is not None:
            _args["operationSampling"] = PerOperationSamplingStrategies.from_dict(_value)

        return cls(**_args)


@typing.final
@_dataclass
class SamplingStrategyParameters(_json_codec.JsonMessage):
    """
    Generated from protobuf message SamplingStrategyParameters
    """

    serviceName: builtins.str | None = ""

    def to_dict(self) -> builtins.dict[builtins.str, typing.Any]:
        """
        Convert this message to a dictionary with lowerCamelCase keys.

        Returns:
            Dictionary representation following OTLP JSON encoding
        """
        _result = {}
        if self.serviceName:
            _result["serviceName"] = self.serviceName
        return _result

    @builtins.classmethod
    def from_dict(cls, data: builtins.dict[builtins.str, typing.Any]) -> "SamplingStrategyParameters":
        """
        Create from a dictionary with lowerCamelCase keys.

        Args:
            data: Dictionary representation following OTLP JSON encoding

        Returns:
            SamplingStrategyParameters instance
        """
        _json_codec.validate_type(data, builtins.dict, "data")
        _args = {}

        if (_value := data.get("serviceName")) is not None:
            _json_codec.validate_type(_value, builtins.str, "serviceName")
            _args["serviceName"] = _value

        return cls(**_args)
