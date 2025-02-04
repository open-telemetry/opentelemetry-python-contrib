# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: opentelemetry/exporter/prometheus_remote_write/gen/types.proto
# Protobuf Python Version: 5.29.3
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC,
    5,
    29,
    3,
    '',
    'opentelemetry/exporter/prometheus_remote_write/gen/types.proto'
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from opentelemetry.exporter.prometheus_remote_write.gen.gogoproto import gogo_pb2 as opentelemetry_dot_exporter_dot_prometheus__remote__write_dot_gen_dot_gogoproto_dot_gogo__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n>opentelemetry/exporter/prometheus_remote_write/gen/types.proto\x12\nprometheus\x1aGopentelemetry/exporter/prometheus_remote_write/gen/gogoproto/gogo.proto\"\xf8\x01\n\x0eMetricMetadata\x12\x33\n\x04type\x18\x01 \x01(\x0e\x32%.prometheus.MetricMetadata.MetricType\x12\x1a\n\x12metric_family_name\x18\x02 \x01(\t\x12\x0c\n\x04help\x18\x04 \x01(\t\x12\x0c\n\x04unit\x18\x05 \x01(\t\"y\n\nMetricType\x12\x0b\n\x07UNKNOWN\x10\x00\x12\x0b\n\x07\x43OUNTER\x10\x01\x12\t\n\x05GAUGE\x10\x02\x12\r\n\tHISTOGRAM\x10\x03\x12\x12\n\x0eGAUGEHISTOGRAM\x10\x04\x12\x0b\n\x07SUMMARY\x10\x05\x12\x08\n\x04INFO\x10\x06\x12\x0c\n\x08STATESET\x10\x07\"*\n\x06Sample\x12\r\n\x05value\x18\x01 \x01(\x01\x12\x11\n\ttimestamp\x18\x02 \x01(\x03\"U\n\x08\x45xemplar\x12\'\n\x06labels\x18\x01 \x03(\x0b\x32\x11.prometheus.LabelB\x04\xc8\xde\x1f\x00\x12\r\n\x05value\x18\x02 \x01(\x01\x12\x11\n\ttimestamp\x18\x03 \x01(\x03\"\x8f\x01\n\nTimeSeries\x12\'\n\x06labels\x18\x01 \x03(\x0b\x32\x11.prometheus.LabelB\x04\xc8\xde\x1f\x00\x12)\n\x07samples\x18\x02 \x03(\x0b\x32\x12.prometheus.SampleB\x04\xc8\xde\x1f\x00\x12-\n\texemplars\x18\x03 \x03(\x0b\x32\x14.prometheus.ExemplarB\x04\xc8\xde\x1f\x00\"$\n\x05Label\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t\"1\n\x06Labels\x12\'\n\x06labels\x18\x01 \x03(\x0b\x32\x11.prometheus.LabelB\x04\xc8\xde\x1f\x00\"\x82\x01\n\x0cLabelMatcher\x12+\n\x04type\x18\x01 \x01(\x0e\x32\x1d.prometheus.LabelMatcher.Type\x12\x0c\n\x04name\x18\x02 \x01(\t\x12\r\n\x05value\x18\x03 \x01(\t\"(\n\x04Type\x12\x06\n\x02\x45Q\x10\x00\x12\x07\n\x03NEQ\x10\x01\x12\x06\n\x02RE\x10\x02\x12\x07\n\x03NRE\x10\x03\"|\n\tReadHints\x12\x0f\n\x07step_ms\x18\x01 \x01(\x03\x12\x0c\n\x04\x66unc\x18\x02 \x01(\t\x12\x10\n\x08start_ms\x18\x03 \x01(\x03\x12\x0e\n\x06\x65nd_ms\x18\x04 \x01(\x03\x12\x10\n\x08grouping\x18\x05 \x03(\t\x12\n\n\x02\x62y\x18\x06 \x01(\x08\x12\x10\n\x08range_ms\x18\x07 \x01(\x03\"\x8b\x01\n\x05\x43hunk\x12\x13\n\x0bmin_time_ms\x18\x01 \x01(\x03\x12\x13\n\x0bmax_time_ms\x18\x02 \x01(\x03\x12(\n\x04type\x18\x03 \x01(\x0e\x32\x1a.prometheus.Chunk.Encoding\x12\x0c\n\x04\x64\x61ta\x18\x04 \x01(\x0c\" \n\x08\x45ncoding\x12\x0b\n\x07UNKNOWN\x10\x00\x12\x07\n\x03XOR\x10\x01\"a\n\rChunkedSeries\x12\'\n\x06labels\x18\x01 \x03(\x0b\x32\x11.prometheus.LabelB\x04\xc8\xde\x1f\x00\x12\'\n\x06\x63hunks\x18\x02 \x03(\x0b\x32\x11.prometheus.ChunkB\x04\xc8\xde\x1f\x00\x42\x08Z\x06prompbb\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'opentelemetry.exporter.prometheus_remote_write.gen.types_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  _globals['DESCRIPTOR']._loaded_options = None
  _globals['DESCRIPTOR']._serialized_options = b'Z\006prompb'
  _globals['_EXEMPLAR'].fields_by_name['labels']._loaded_options = None
  _globals['_EXEMPLAR'].fields_by_name['labels']._serialized_options = b'\310\336\037\000'
  _globals['_TIMESERIES'].fields_by_name['labels']._loaded_options = None
  _globals['_TIMESERIES'].fields_by_name['labels']._serialized_options = b'\310\336\037\000'
  _globals['_TIMESERIES'].fields_by_name['samples']._loaded_options = None
  _globals['_TIMESERIES'].fields_by_name['samples']._serialized_options = b'\310\336\037\000'
  _globals['_TIMESERIES'].fields_by_name['exemplars']._loaded_options = None
  _globals['_TIMESERIES'].fields_by_name['exemplars']._serialized_options = b'\310\336\037\000'
  _globals['_LABELS'].fields_by_name['labels']._loaded_options = None
  _globals['_LABELS'].fields_by_name['labels']._serialized_options = b'\310\336\037\000'
  _globals['_CHUNKEDSERIES'].fields_by_name['labels']._loaded_options = None
  _globals['_CHUNKEDSERIES'].fields_by_name['labels']._serialized_options = b'\310\336\037\000'
  _globals['_CHUNKEDSERIES'].fields_by_name['chunks']._loaded_options = None
  _globals['_CHUNKEDSERIES'].fields_by_name['chunks']._serialized_options = b'\310\336\037\000'
  _globals['_METRICMETADATA']._serialized_start=152
  _globals['_METRICMETADATA']._serialized_end=400
  _globals['_METRICMETADATA_METRICTYPE']._serialized_start=279
  _globals['_METRICMETADATA_METRICTYPE']._serialized_end=400
  _globals['_SAMPLE']._serialized_start=402
  _globals['_SAMPLE']._serialized_end=444
  _globals['_EXEMPLAR']._serialized_start=446
  _globals['_EXEMPLAR']._serialized_end=531
  _globals['_TIMESERIES']._serialized_start=534
  _globals['_TIMESERIES']._serialized_end=677
  _globals['_LABEL']._serialized_start=679
  _globals['_LABEL']._serialized_end=715
  _globals['_LABELS']._serialized_start=717
  _globals['_LABELS']._serialized_end=766
  _globals['_LABELMATCHER']._serialized_start=769
  _globals['_LABELMATCHER']._serialized_end=899
  _globals['_LABELMATCHER_TYPE']._serialized_start=859
  _globals['_LABELMATCHER_TYPE']._serialized_end=899
  _globals['_READHINTS']._serialized_start=901
  _globals['_READHINTS']._serialized_end=1025
  _globals['_CHUNK']._serialized_start=1028
  _globals['_CHUNK']._serialized_end=1167
  _globals['_CHUNK_ENCODING']._serialized_start=1135
  _globals['_CHUNK_ENCODING']._serialized_end=1167
  _globals['_CHUNKEDSERIES']._serialized_start=1169
  _globals['_CHUNKEDSERIES']._serialized_end=1266
# @@protoc_insertion_point(module_scope)
