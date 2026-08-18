## How to record tests cassettes

### Run the server

Checkout [opentelemetry-go](https://github.com/open-telemetry/opentelemetry-go) and build it with:

```
make
```

Then run the example server with:

```
./internal/examples/server/bin/server
```

### Record the cassettes

We are using `vcr.py` for recording HTTP responses from the server, it works by serializing the response in a yaml file and then replying
it. `vcr.py` will record a new cassettes only if it does not find it so to redo a recording you need to delete the recording in the
`cassettes/` directory.

Because of vcr.py issues with older urllib3 versions tests are skipped with Python older than 3.10.
