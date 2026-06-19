# ASF Download Credential-Safe Design

> **Design only (Task 032).** This document specifies the credential-safety
> boundaries, download modes, and redaction rules for a *future* ASF Sentinel-1
> SLC download capability. **Nothing here is implemented.** No code under `src/`
> or `tests/` changes; no dependency is added; no network call is made; no ASF
> account, token, `.netrc`, or `.env` is read; and the current `insar-prep`
> remains an offline CLI MVP that does **not** download anything.

## 1. Scope and non-goals

### 1.1 Scope

- Define the credential-safety contract every future download task must obey.
- Define `dry-run` vs real-download boundaries.
- Define how sensitive data is kept out of logs, reports, CSVs, tracebacks,
  shell history, the smoke package, and CI logs.
- Define the allowed credential *sources* (as a future proposal) and the
  forbidden credential *practices* (binding immediately, even for design code).
- Propose the CLI surface and the Task 033+ implementation roadmap.

### 1.2 Non-goals (explicitly out of scope for Task 032)

- No downloader implementation, no login, no session handling.
- No `asf_search`, no `keyring`, no `requests`/`httpx`, no new dependency.
- No reading of `.netrc`, `.env`, environment variables, or interactive prompts.
- No real ASF URL access logic and no credential persistence.
- No new CLI argument and no change to the `prepare` workflow.
- This version does **not** promise that `insar-prep` can download ASF SLCs.
  Real download is deferred to a later, deliberate task.

## 2. Threat model

The asset to protect is the user's **NASA Earthdata Login (EDL/URS)** account,
which ASF requires for Sentinel-1 SLC download, plus any derived secrets (EDL
bearer token, session cookie, presigned data-pool/S3 URL). The design must
prevent each of the following leak paths:

| # | Leak path | Concrete risk |
|---|-----------|---------------|
| T1 | Username/password committed to Git | `.netrc` / `.env` / config JSON tracked by accident |
| T2 | Token/cookie/session written to logs | `app.log` / `task.log` / `events.jsonl` / `errors.log` |
| T3 | Credentials in JSON/Markdown/HTML/manifest/warnings | report or CSV echoes a secret-bearing URL or header |
| T4 | Credentials in a crash traceback | an exception `str()` includes a URL with a token query param |
| T5 | Credentials in shell history | password passed as a CLI flag |
| T6 | Credentials in the smoke package | a real account dropped into `smoke_package/` inputs |
| T7 | Credentials in GitHub Actions logs | a CI step echoes an env secret, or a real-download test runs in CI |
| T8 | Large SLC/zip/SAFE files committed | a real `.zip` / `.SAFE` accidentally staged and pushed |

Out of scope for this threat model: protecting against a fully compromised local
machine, OS keyring extraction by malware, or network MITM (TLS is assumed and
delegated to the future HTTP client).

## 3. Credential handling principles

These principles are binding for **all** future download code:

1. **No plaintext credentials inside the project directory.** Ever. Not in
   config JSON, not in workspace/project metadata, not in fixtures.
2. **Reports never contain credentials.** JSON, Markdown, and HTML reports are
   derived from the same `DataPreparationReport` object, which must never hold a
   secret field.
3. **`manifest.csv` / `warnings.csv` never contain credentials.** Their columns
   carry paths, statuses, codes, and messages — never tokens or auth headers.
4. **Logs must be redacted.** All file handlers already attach `_MaskingFilter`
   (see §6); download code must additionally avoid logging raw URLs/headers.
5. **Error messages must be redacted** before they reach a log, the report, or
   stdout/stderr (run user-facing/loggable strings through `mask_text`).
6. **Default mode is `dry-run`.** Doing nothing dangerous must be the default.
7. **Real download must be explicitly enabled** by the user, per invocation.
8. **Download tests must not hit the network by default** (socket monkeypatched;
   real-download tests are opt-in only — see §13).
9. **Credentials live only in memory** during a run and are never persisted by
   `insar-prep` itself; persistence (if any) is delegated to the OS keyring or a
   user-managed file *outside* the project tree.

## 4. Allowed credential sources (future proposal)

Design only — none of these are implemented in Task 032. Proposed priority order
for a later `credential source abstraction` (Task 035):

- **Option A — OS keyring (preferred).** Read EDL credentials from the platform
  secret store via a future optional dependency (`keyring`), behind an interface
  so the rest of the code never sees the raw secret beyond the auth boundary.
- **Option B — Environment variables.** e.g. `EARTHDATA_USERNAME` /
  `EARTHDATA_PASSWORD` or `EARTHDATA_TOKEN`, read at the auth boundary only,
  never echoed, never written back to disk.
- **Option C — Interactive prompt.** Prompt at runtime (no echo for the
  password), held in memory for the session only.
- **Option D — User-managed `.netrc` outside the project directory.** The
  standard `machine urs.earthdata.nasa.gov` entry in the user's home, read by the
  future HTTP client — **never** copied into the repo or workspace.

Explicit source-level rules:

- **`.env` is not the default scheme** and is never committed; if ever supported
  it must live outside the repo and be opt-in.
- **Usernames/passwords are never written into config JSON.**
- **Credentials are never written into workspace/project metadata** (the
  `Workspace`/`Project`/`Region` models stay credential-free).

## 5. Forbidden credential practices

Binding now, including in any design/stub/example code:

- ❌ Hard-code username / password / token anywhere.
- ❌ Write credentials to any report (JSON/Markdown/HTML).
- ❌ Write credentials to `manifest.csv` / `warnings.csv`.
- ❌ Print credentials to stdout or stderr.
- ❌ Commit `.env`.
- ❌ Commit `.netrc`.
- ❌ Commit cookie / session files.
- ❌ Put credentials in command examples (docs use placeholders only).
- ❌ Add real user credentials to fixtures (tests use fakes only).

To make T1/T6/T8 hard to violate, `.gitignore` should (in the implementing task)
explicitly cover `.netrc`, `.env`, `*.env`, `*.token`, `*.key`, cookie/session
files, and large SAR artifacts (`*.zip`, `*.SAFE`, `*.tif`); the
`docs/release_readiness_v0_1_0.md` hygiene checklist already greps for several of
these and should be extended alongside the downloader.

## 6. Logging and report redaction

### 6.1 Reuse the existing primitives

The download feature must **reuse**, not reinvent, the current redaction stack in
`src/insar_prep/core/logging.py`:

- `mask_secret(value)` — keeps only the last 4 characters (`****ABCD`).
- `mask_text(text)` — regex redaction of `key<sep>value` for the keys
  `token`, `password`, `passwd`, `pwd`, `secret`, `api_key`/`apikey`, `cookie`,
  `authorization` in plain, `key=value`, and JSON `"key":"value"` forms.
- `_MaskingFilter` — already attached to every file handler, so anything logged
  through the project loggers is masked at write time.
- Reports/CSVs are already passed through `mask_text` before being written to
  disk, so the same guarantee extends to JSON/Markdown/HTML/manifest/warnings.

### 6.2 Known coverage gaps to close in Task 034

The current `_SECRET_KEY_RE` does **not** yet cover several ASF/EDL-specific
shapes. The redaction-tests task (Task 034) must extend `mask_text` and prove the
following are masked:

- **Bearer tokens after a space**: `Authorization: Bearer <token>` currently
  masks only the word `Bearer`, not the token that follows it.
- **Cookie values**: `Cookie: <name>=<value>; ...` (session/CSRF values).
- **Presigned data-pool / S3 / CloudFront query params**: `X-Amz-Signature`,
  `X-Amz-Credential`, `X-Amz-Security-Token`, `Signature`, `AWSAccessKeyId`,
  generic `?...&token=...` and `&code=...` query strings.
- **URL userinfo**: `https://user:pass@host/...`.
- **`.netrc` lines**: `machine urs.earthdata.nasa.gov login <u> password <p>`
  (the `login`/`machine` keywords are not yet recognized).
- **EDL redirect URLs**: the 302 from `datapool.asf.alaska.edu` to a temporary
  signed URL must be treated as a secret and never logged verbatim.

### 6.3 Redaction acceptance criteria (for the future downloader)

The downloader implementation must include tests proving:

- URL query tokens are masked.
- `Authorization` headers are masked.
- `Cookie` headers are masked.
- Username/password are masked.
- Earthdata/ASF session information never enters any report.

## 7. Download modes

Three logical modes; **only the planning side is in scope for Task 033**, and the
default is always safe:

```text
DRY_RUN        # default: build a download plan only, no network, no files
PLAN_ONLY      # alias/explicit form of the planning output (machine-readable)
REAL_DOWNLOAD  # future: actually fetch SLCs; requires explicit opt-in + creds
```

A simplified CLI surface (see §12) collapses these to:

```text
--download-mode dry-run   # default
--download-mode real      # explicit; future task only
```

Mode rules:

- **Default is `dry-run`.**
- **`dry-run` only generates a download plan; it never touches the network.**
- **`real` must be explicitly specified** by the user.
- **`real` requires credentials** (resolved via §4 sources at the auth boundary).
- **`real` does not run in CI by default.**
- **`real`-mode tests must be manually enabled** (opt-in marker — see §13).

## 8. Dry-run behavior (Task 033 target)

The dry-run planner (future Task 033) should, from the parsed cart `Scene`s:

- Generate **planned download entries** (one per SLC granule) as a lightweight,
  serializable plan (mirroring the intent of the existing `DownloadTask` model,
  without requiring a full job/region context).
- Show, per task: **expected filename**, **local output path**, and **whether a
  credential is required** (boolean), with **no secret values**.
- **Not access the network.**
- **Not create large files** (no `.zip` / `.SAFE`; at most tiny plan artifacts).
- Optionally **write to the manifest/report** as new rows/sections (a
  `download` section), consistent with the existing offline outputs.

Proposed output location (design): the planner writes its plan files under
`<output_dir>/asf_download_plan/` (`asf_download_plan.json` +
`asf_download_plan.csv`), and records each scene's *intended* SLC target as
`<output_dir>/02_slc/<expected_filename>`, mirroring the existing
`05_atmosphere` / `06_sarscape_ready` / `07_reports` numbered-subdir convention.
The dry-run only records the *intended* paths; it creates none of the data files
and never creates the `02_slc/` directory.

## 9. Real-download behavior (future task — design only)

Specified now so the implementing task has a checklist; **not** implemented here:

- **Resume / partial download** support.
- **Temporary file** written as `<name>.part`.
- **Atomic rename** to the final name only after a complete, verified download.
- **File-size check** against the expected/Content-Length size.
- **Checksum / manifest verification** when ASF provides one (e.g. MD5).
- **Retry with backoff** on transient failures.
- **Rate limiting** to respect ASF/EDL service limits.
- **Interrupted-download recovery** (re-detect `.part`, resume or restart).
- **User cancellation** handled cleanly (no corrupt final files left behind).
- **Disk-space precheck** before starting large transfers.
- **Duplicate-file handling** (skip/verify already-complete targets).

All of the above must operate **without** ever logging a secret-bearing URL,
header, or cookie (see §6).

## 10. File integrity and resume strategy

- A target is **complete** only when: the temporary `.part` finished, the size
  matches, the checksum (if available) matches, and the atomic rename succeeded.
- A target is **resumable** when a `.part` exists and the server supports range
  requests; otherwise it is restarted.
- The `manifest.csv` `download` rows should record per-target **status**
  (`PLANNED` / `READY` / `INCOMPLETE` / `FAILED`), the **path**, and a
  non-sensitive **note** — never a URL containing a token.
- Integrity state is derived from files on disk and the plan, so a re-run is
  idempotent: already-complete targets are detected and skipped.

## 11. Error handling

- Reuse `InsarPrepError` and its typed subclasses; add download-specific
  `ErrorCode` values (e.g. a `DLD0xx` family) in the implementing task.
- **Every** user-facing or loggable error string is passed through `mask_text`
  before it leaves the auth boundary, so a token in a failed URL cannot surface
  in a traceback, log, report, or stdout/stderr.
- Distinguish **credential errors** (missing/invalid EDL login → actionable
  "configure your Earthdata credentials" message, no secret echoed) from
  **transport errors** (timeouts, 5xx → retry/backoff) and **integrity errors**
  (size/checksum mismatch → discard `.part`, retry).
- Failures are **non-fatal to the offline pipeline**: a failed/blocked download
  is reported as a `WARNING`/`ERROR` row, never a crash of `prepare`.

## 12. CLI design proposal

Two routes were considered:

- **Route 1 — fold downloads into `prepare`** (`prepare ... --download-mode ...`).
- **Route 2 — separate, dedicated download subcommands.**

```text
# Offline dry-run planner (Task 033, default-safe, no credentials):
insar-prep plan-asf-downloads --cart ... --output-dir ...

# Future real download (separate, later task; requires explicit opt-in + creds):
insar-prep download-asf --cart ... --output-dir ... \
  --download-mode real --credential-source keyring
```

**Recommendation: Route 2 (dedicated subcommands).** The offline dry-run planner
ships as its own `plan-asf-downloads` subcommand (Task 033) so it never touches
`prepare`'s offline guarantees, and the future credentialed real download lives
in a separate `download-asf` subcommand gated by `--download-mode real`. Keeping
network/credential logic out of `prepare` preserves the offline stability and
test guarantees of the existing workflow and makes the dangerous surface explicit
and easy to gate in CI. The CLI must **never** accept a password as a flag (T5);
the password comes only from §4 sources, never the command line.

## 13. Test strategy

The future downloader must ship with tests that are safe by construction:

- **Unit tests use fake credentials only** (e.g. `EARTHDATA_TOKEN="fake-...."`).
- **No real credentials** anywhere in the suite or fixtures.
- **No network by default** — `socket.socket` / `socket.create_connection`
  monkeypatched to raise, matching the existing e2e pattern in
  `tests/e2e/test_prepare_workflow.py`.
- **A fake provider / fake downloader** simulates responses, redirects, ranges,
  and failures deterministically.
- **Redaction tests** assert tokens/headers/cookies/URLs are masked (§6.3).
- **Failure tests** cover credential, transport, and integrity errors.
- **A manual integration-test marker** (e.g. `@pytest.mark.real_download`) gates
  any test that would touch ASF; it is **opt-in only** and **excluded from CI**.
- **Real-download tests run only when a developer explicitly enables them** with
  their own credentials, outside CI.

## 14. Task breakdown

Proposed sequencing after this design:

- **Task 033 — ASF download dry-run planner.** A `plan-asf-downloads` subcommand
  that builds a planned download list from cart scenes (expected filename,
  intended `02_slc/` path, credential-required flag) and writes
  `asf_download_plan.json` + `asf_download_plan.csv`. Offline; no network, no
  credentials, no large files.
- **Task 034 — Credential redaction hardening.** Extend `mask_text` to cover the
  §6.2 gaps (bearer/cookie/session/presigned-URL query/userinfo/`.netrc`) and
  prove, with fake secrets only, that reports/logs/CSVs/stdout never leak them.
- **Task 035 — Fake downloader provider and no-network guard.** Define the
  downloader interface (`AsfDownloader` / `DownloadRequest` / `DownloadResult`)
  and a `FakeAsfDownloader` (success/failure/interrupted, no real `.zip`/`.SAFE`,
  no network); `RealAsfDownloader` stays a `NotImplemented` stub. Add
  socket-monkeypatched no-network guard tests.
- **Task 036 — Windows exe smoke test for the dry-run planner.** Rebuild the
  one-file exe and extend the smoke package to verify `plan-asf-downloads`
  produces the plan JSON/CSV with no `.zip`/`.SAFE`, offline.

A **real ASF download experiment** (actual EDL-authenticated fetch) is **not**
part of this sequence: it must be a separate, later task, run only behind the
opt-in marker with the user's explicit authorization, and never in CI.

---

**Summary.** Task 032 only *designs* a credential-safe ASF download path: default
`dry-run`, explicit opt-in for real download, credentials confined to memory and
to sources outside the repo, and strict redaction across logs, reports, and CSVs
(reusing `mask_secret` / `mask_text` / `_MaskingFilter` and closing the known
gaps). No downloader, login, credential read, dependency, or business-code change
is part of this task.
