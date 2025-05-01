## Recording calls

If you need to record calls you may need to export authentication variables and the default region as environment
variables in order to have the code work properly. The recorded tests assume the region us-east-1, so ensure that
AWS_DEFAULT_REGION is set accordingly when recording new calls.
Since tox blocks environment variables by default you need to override its configuration to let them pass:

```
export TOX_OVERRIDE=testenv.pass_env=AWS_ACCESS_KEY_ID,AWS_SECRET_ACCESS_KEY,AWS_SESSION_TOKEN,AWS_DEFAULT_REGION
```

We are not adding it to tox.ini because of security concerns.
