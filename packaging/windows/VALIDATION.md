# Issue #2 validation ledger

This file separates **implemented gates** from **executed evidence** so repository preparation is not confused with a successful Windows package build.

## Implemented offline gates

The branch contains deterministic/static checks for:

- onedir PyInstaller shape;
- explicit collection of `nio` and `vodozemac`;
- pinned `matrix-nio`, PyInstaller, and PyInstaller hooks top-level inputs;
- build-manifest determinism and per-file SHA-256;
- no machine-specific package locations in the manifest;
- clean-source build default;
- no Matrix credentials in the build driver;
- direct packaged-helper memory-transport smoke;
- `.NET 8` packaged-helper invocation;
- process timeout and process-tree kill;
- caller cancellation propagation;
- bounded helper stdout;
- malformed response and request-ID mismatch rejection;
- concurrent stderr draining without exposing diagnostics to the consuming application.

## Evidence still required

Do not mark issue #2 complete until the following evidence exists from a Windows x64 environment:

```text
python_unit_tests=PASS
python_compile=PASS
matrix_e2ee_imports=PASS
dotnet_fake_helper_build=PASS
dotnet_process_conformance=PASS
pyinstaller_onedir_build=PASS
packaged_helper_direct_stdio_smoke=PASS
dotnet_to_packaged_helper_smoke=PASS
build_manifest_emitted=PASS
clean_windows_no_python_target_smoke=PASS
credential_values_exposed=false
```

The last clean-target test must run in an environment where `python`, `py`, and a preinstalled Matrix SDK are not prerequisites for executing `secure-messaging-helper.exe`. The .NET consumer may be framework-dependent during this MVP proof; only the Secure Messaging helper is required to be Python-runtime independent.

## Hosted CI caveat

At the time this branch was prepared, the personal GitHub account had already exhausted its included hosted Actions minutes. A red/no-run hosted check is therefore not equivalent to failed test execution. Record the exact execution environment and commands when independent validation is performed.
