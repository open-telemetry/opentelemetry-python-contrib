## Recording calls

If you need to record calls you need to export the `OPENAI_API_KEY` as environment variable.
Since tox blocks environment variables by default you need to override its configuration to let them pass:

```
export TOX_OVERRIDE=testenv.pass_env=OPENAI_API_KEY
```

We are not adding it to tox.ini because of security concerns.
