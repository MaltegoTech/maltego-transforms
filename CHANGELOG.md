# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Fixed
- `IntegrationClient._call_httpx_method` no longer raises a bare, untyped
  `MaltegoException` for unhandled 4xx upstream responses. HTTP 429 (rate
  limit) now maps to `MaltegoHTTPDataProviderUnavailable`; all other
  unhandled non-2xx codes map to `MaltegoHTTPDataProviderInvalidResponse`
  instead of the previous untyped exception, so connectors relying on typed
  exception handling can distinguish and react to these cases correctly.

## 1.0.0 - 2026-07-07

Initial public release of the `maltego-transforms` Python SDK.
