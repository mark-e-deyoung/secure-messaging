# Windows helper packaging

Issue #2 packages the current Python reference/helper as a bounded, self-contained `win-x64` helper directory for consumers that must not depend on a separately installed Python runtime or Matrix SDK.

## Contract

The consumer-facing contract remains `protocol/stdio-v1.md`: launch `secure-messaging-helper.exe --stdio-once`, write one JSON request line, read one JSON response line, then the helper exits. The application does not receive Matrix credentials or crypto state.

The first accepted packaging shape is **PyInstaller onedir**, not onefile. The directory shape keeps native Matrix E2EE dependencies inspectable and avoids extracting a temporary runtime on every helper invocation. A onefile optimization is deferred until the onedir artifact has passed clean-target acceptance.

## Build inputs

The build requires:

- 64-bit Windows;
- CPython 3.11 available through `py -3.11` on the build workstation only;
- .NET 8 SDK for the consumer conformance smoke;
- Git;
- network access only for the Python package installation step unless the dependencies are already supplied by an approved local package cache.

Top-level packaging dependencies are pinned in `build-requirements.txt`. The generated `build-manifest.json` records the complete resolved Python distribution inventory as well as every file in the packaged bundle with SHA-256 and byte size.

The target machine does **not** need Python installed.

## Build and acceptance

From a clean checkout of the intended source commit:

```powershell
.\packaging\windows\Build-WindowsHelper.ps1
```

The build fails closed on a dirty working tree unless `-AllowDirty` is explicitly supplied for a diagnostic, non-release build.

A successful run performs these gates in order:

1. verify 64-bit CPython 3.11;
2. create a disposable build virtual environment;
3. install the pinned top-level packaging requirements;
4. prove `nio` and `vodozemac` import together;
5. run Python unit tests and compile checks;
6. build the PyInstaller onedir bundle;
7. generate `build-manifest.json` with source/provenance and per-file SHA-256;
8. launch the packaged EXE directly with `SECURE_MESSAGING_TEST_TRANSPORT=memory` and a disposable state directory;
9. run the `.NET 8` conformance executable with `SECURE_MESSAGING_HELPER_PATH` pointing at that packaged EXE;
10. copy only the validated bundle to `artifacts/windows-helper/secure-messaging-helper/`.

No Matrix account, access token, pickle key, room, Synapse server, AU data, or network request is required for the two packaged-helper smoke tests.

## Artifact contents

Expected output shape:

```text
artifacts/windows-helper/
  secure-messaging-helper/
    secure-messaging-helper.exe
    build-manifest.json
    _internal/
      ... frozen Python and Matrix E2EE dependencies ...
```

`build-manifest.json` is intentionally free of timestamps and absolute machine paths so manifests from independent builds can be compared meaningfully. Byte-for-byte bundle reproducibility is not yet claimed.

## State and credential boundary

The executable's install/extraction directory is never its state directory. Runtime state remains under the helper's normal per-user state location (or an explicitly supplied `SECURE_MESSAGING_STATE_DIR` for tests/controlled operation). Build artifacts must never contain access tokens, Matrix device stores, recovery keys, room keys, application-private data, or a populated runtime state directory.

## Clean-target gate still required

Repository preparation alone does not prove the artifact is self-contained. Before issue #2 closes, a produced bundle must be copied to a clean Windows x64 environment without Python installed and must pass both the direct stdio smoke and the `.NET 8` consumer launch. Record only sanitized hashes/versions/results; do not publish endpoint credentials or crypto state.
