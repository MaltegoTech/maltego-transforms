# Benchmarks

This directory contains lightweight local benchmark harnesses for SDK readiness work.
They are executable measurements, not pytest assertions for normal CI. The pytest
coverage in `src/tests/performance/` only verifies that each harness runs and emits
the expected JSON shape.

The scripts live here instead of `resources/` because they are developer tooling,
not packaged configuration, certificates, icons, or fixture resources.

The repository does not currently depend on a benchmark framework such as
`pytest-benchmark` or `asv`. If the SDK later adopts one, these harnesses should be
ported into that framework rather than maintained as a parallel convention.

Benchmark numbers are local, single-machine evidence. They are useful for comparing
the same commands on the same machine, but they are not CI-enforced performance
claims and should be described in PRs with the commit SHAs, commands, and machine
context used for the run.

## Running

Run benchmarks from the repository root with the same environment used for the SDK
test suite.

```bash
poetry run python benchmarks/fastapi_serialization.py --iterations 200 --output /private/tmp/sdk-55552-after.json
poetry run python benchmarks/http_compression.py --compression off --output /private/tmp/sdk-55553-before.json
poetry run python benchmarks/http_compression.py --compression gzip --output /private/tmp/sdk-55553-after.json
```

For before/after work, run the same command on the base branch and on the feature
branch. Keep iteration counts and local environment stable, and record the command,
branch, commit SHA, machine context, and summary metrics in the PR description or
the associated readiness notes.

Each JSON output includes the benchmark name, generation timestamp, Python runtime,
platform string, and relevant package versions so copied summaries can be traced
back to the local run.

Generated JSON should stay out of source control by default. Use `/private/tmp` or
another local artifact location while iterating. If a future change needs durable
baselines in the repository, add that convention deliberately with reviewed files
under this directory.

## Harnesses

`fastapi_serialization.py` measures representative v3 JSON endpoint latency through
`starlette.testclient.TestClient`. It reports package versions, payload size,
request count, total time, requests per second, and median milliseconds per
endpoint.

`http_compression.py` measures representative v3 JSON response wire size with
compression disabled and enabled. It reports package versions, plain bytes, wire
bytes, the source used for wire-byte measurement, compression ratio, response
encoding, and preservation of headers that the SDK clients rely on. If a gzip
response does not include `Content-Length`, the harness reports a
`decoded-body-fallback` source because `TestClient` exposes decompressed body bytes.
