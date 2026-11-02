// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

use crate::proto::common::v1::{AnyValue, ArrayValue, KeyValue, KeyValueList, any_value};
use crate::proto::processcontext::v1development::ProcessContext;
use crate::proto::resource::v1::Resource;
use prost::Message;
use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyByteArray, PyBytes, PyDict, PyFloat, PyInt, PyString};

/// Maximum nesting of attribute mappings and sequences. Protobuf parsers commonly
/// limit message recursion to 100, and each nested mapping uses three levels
/// (`KeyValueList`, `KeyValue`, `AnyValue`), so deeper payloads may be unreadable.
const MAX_NESTING_DEPTH: usize = 32;

fn any_value_from_py(val: &Bound<'_, PyAny>, depth: usize) -> PyResult<AnyValue> {
    if val.is_none() {
        return Ok(AnyValue::default());
    }
    if val.is_instance_of::<PyBool>() {
        return Ok(AnyValue {
            value: Some(any_value::Value::BoolValue(val.extract()?)),
        });
    }
    if val.is_instance_of::<PyInt>() {
        return Ok(AnyValue {
            value: Some(any_value::Value::IntValue(val.extract()?)),
        });
    }
    if val.is_instance_of::<PyFloat>() {
        return Ok(AnyValue {
            value: Some(any_value::Value::DoubleValue(val.extract()?)),
        });
    }
    if val.is_instance_of::<PyString>() {
        return Ok(AnyValue {
            value: Some(any_value::Value::StringValue(val.extract()?)),
        });
    }
    // `bytes`/`bytearray` are `Sequence`s, so this must precede the Sequence
    // branch below or they would be expanded into an array of integers.
    if val.is_instance_of::<PyBytes>() || val.is_instance_of::<PyByteArray>() {
        return Ok(AnyValue {
            value: Some(any_value::Value::BytesValue(val.extract()?)),
        });
    }

    // Only containers recurse. Stopping here turns a cycle or excessive nesting
    // into an exception rather than a stack overflow.
    if depth >= MAX_NESTING_DEPTH {
        return Err(PyValueError::new_err(format!(
            "attributes are nested more than {MAX_NESTING_DEPTH} levels deep or contain a cycle"
        )));
    }

    let py = val.py();
    let collections_abc = py.import("collections.abc")?;

    if val.is_instance(collections_abc.getattr("Mapping")?.as_ref())? {
        return Ok(AnyValue {
            value: Some(any_value::Value::KvlistValue(KeyValueList {
                values: key_values_from_py(val, depth + 1)?,
            })),
        });
    }

    if val.is_instance(collections_abc.getattr("Sequence")?.as_ref())? {
        let values = val
            .try_iter()?
            .map(|item| any_value_from_py(&item?, depth + 1))
            .collect::<PyResult<_>>()?;
        return Ok(AnyValue {
            value: Some(any_value::Value::ArrayValue(ArrayValue { values })),
        });
    }

    let type_name: String = val.get_type().qualname()?.extract()?;
    Err(PyTypeError::new_err(format!(
        "unsupported attribute value type: {type_name}"
    )))
}

/// Convert a Python `Mapping[str, Any]` into a list of protobuf `KeyValue`s,
/// recursing into nested values via [`any_value_from_py`]. `depth` is the number
/// of containers enclosing `mapping`, `0` for top-level attributes.
pub fn key_values_from_py(mapping: &Bound<'_, PyAny>, depth: usize) -> PyResult<Vec<KeyValue>> {
    let py = mapping.py();
    let py_dict = py
        .import("builtins")?
        .getattr("dict")?
        .call1((mapping,))?
        .cast_into::<PyDict>()?;

    py_dict
        .iter()
        .map(|(key, val)| {
            Ok(KeyValue {
                key: key.str()?.extract()?,
                value: Some(any_value_from_py(&val, depth)?),
                ..Default::default()
            })
        })
        .collect()
}

pub fn resource_from_py(resource: &Bound<'_, PyAny>) -> PyResult<Resource> {
    Ok(Resource {
        attributes: key_values_from_py(&resource.getattr("attributes")?, 0)?,
        ..Default::default()
    })
}

pub fn encode_process_context(resource: Resource, attributes: Vec<KeyValue>) -> Vec<u8> {
    ProcessContext {
        resource: Some(resource),
        attributes,
    }
    .encode_to_vec()
}

#[cfg(test)]
mod tests {
    use super::{MAX_NESTING_DEPTH, encode_process_context};
    use crate::proto::common::v1::{AnyValue, KeyValue, KeyValueList, any_value};
    use crate::proto::processcontext::v1development::ProcessContext;
    use crate::proto::resource::v1::Resource;
    use prost::Message;

    fn string_kv(key: &str, value: &str) -> KeyValue {
        KeyValue {
            key: key.into(),
            value: Some(AnyValue {
                value: Some(any_value::Value::StringValue(value.into())),
            }),
            ..Default::default()
        }
    }

    #[test]
    fn encode_empty_resource_roundtrip() {
        let bytes = encode_process_context(Resource::default(), vec![]);
        let ctx = ProcessContext::decode(bytes.as_slice()).unwrap();
        assert!(ctx.resource.is_some());
        assert!(ctx.resource.unwrap().attributes.is_empty());
        assert!(ctx.attributes.is_empty());
    }

    #[test]
    fn encode_with_additional_attributes_roundtrip() {
        let resource = Resource {
            attributes: vec![string_kv("service.name", "my-service")],
            ..Default::default()
        };
        let bytes =
            encode_process_context(resource, vec![string_kv("deployment.environment", "prod")]);
        let ctx = ProcessContext::decode(bytes.as_slice()).unwrap();

        // Resource attributes and the additional attributes are kept separate.
        let resource_attrs = ctx.resource.unwrap().attributes;
        assert_eq!(resource_attrs.len(), 1);
        assert_eq!(resource_attrs[0].key, "service.name");

        assert_eq!(ctx.attributes.len(), 1);
        assert_eq!(ctx.attributes[0].key, "deployment.environment");
        assert!(matches!(
            ctx.attributes[0].value.as_ref().unwrap().value,
            Some(any_value::Value::StringValue(ref s)) if s == "prod"
        ));
    }

    #[test]
    fn encode_resource_with_string_attribute_roundtrip() {
        let resource = Resource {
            attributes: vec![KeyValue {
                key: "service.name".into(),
                value: Some(AnyValue {
                    value: Some(any_value::Value::StringValue("my-service".into())),
                }),
                ..Default::default()
            }],
            ..Default::default()
        };
        let bytes = encode_process_context(resource, vec![]);
        let ctx = ProcessContext::decode(bytes.as_slice()).unwrap();
        let attrs = ctx.resource.unwrap().attributes;
        assert_eq!(attrs.len(), 1);
        assert_eq!(attrs[0].key, "service.name");
        assert!(matches!(
            attrs[0].value.as_ref().unwrap().value,
            Some(any_value::Value::StringValue(ref s)) if s == "my-service"
        ));
    }

    #[test]
    fn encode_resource_with_bytes_attribute_roundtrip() {
        let resource = Resource {
            attributes: vec![KeyValue {
                key: "raw".into(),
                value: Some(AnyValue {
                    value: Some(any_value::Value::BytesValue(vec![1, 2, 3])),
                }),
                ..Default::default()
            }],
            ..Default::default()
        };
        let bytes = encode_process_context(resource, vec![]);
        let ctx = ProcessContext::decode(bytes.as_slice()).unwrap();
        let attrs = ctx.resource.unwrap().attributes;
        assert_eq!(attrs.len(), 1);
        assert!(matches!(
            attrs[0].value.as_ref().unwrap().value,
            Some(any_value::Value::BytesValue(ref b)) if b == &[1, 2, 3]
        ));
    }

    #[test]
    fn encode_resource_at_nesting_limit_is_decodable() {
        let mut kv = string_kv("leaf", "value");
        for _ in 0..MAX_NESTING_DEPTH {
            kv = KeyValue {
                key: "nested".into(),
                value: Some(AnyValue {
                    value: Some(any_value::Value::KvlistValue(KeyValueList {
                        values: vec![kv],
                    })),
                }),
                ..Default::default()
            };
        }
        let resource = Resource {
            attributes: vec![kv],
            ..Default::default()
        };
        let bytes = encode_process_context(resource, vec![]);
        ProcessContext::decode(bytes.as_slice()).unwrap();
    }
}
