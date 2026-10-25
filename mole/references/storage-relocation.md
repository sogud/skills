# Storage relocation

Use this branch when the user asks to move storage or prevent developer caches
from filling the internal disk again. It does not promise that macOS and every
application will stop writing to the internal disk. Do not add scheduled cleanup,
a login agent, a mount service, or elevated access without separate authorization.

## Choose the destination and method

1. Discover the actual mounted volume, filesystem, ownership, free space, and
   existing contents. Reuse an appropriate cache directory; do not hardcode a
   personal volume name. Keep durable backups separate from disposable reports.
2. Inspect installed versions, native help, current configuration, aliases, and
   active users of each candidate. Query only relevant settings: config dumps
   can expose tokens or account identifiers. Read-only metadata and database
   counts usually suffice; do not inspect private messages or images.
3. Prefer a tool's persistent cache setting or an application's documented
   library relocation process. Replacing an app's entire sandbox with a symlink
   is not equivalent. Research version-specific support before promising a move.
4. Explain the capacity to reclaim, what stays on the source disk, and how the
   tool behaves if the external disk is absent. An external backup consumes
   destination space; a backup kept internally prevents equivalent reclamation.

Completion: every candidate has a known source, destination, data class, supported
method or clearly labeled workaround, verification method, and rollback copy.
Defer ambiguous libraries and active runtime directories instead of guessing.

## Developer caches: configure future writes

Use a user-selected absolute cache root (`CACHE_ROOT` below). Read the installed
tool's help before changing it. Back up existing settings without placing secrets
in a general report; preserve unrelated keys. Project settings and environment
variables may override user defaults.

| Tool | Persistent mechanism to inspect | Verify |
| --- | --- | --- |
| npm / npx | `npm config set cache="$CACHE_ROOT/npm" --location=user` | `npm config get cache`; a small local fixture or cache write, not package publishing |
| pnpm | `pnpm config set --global storeDir "$CACHE_ROOT/pnpm/store"` and `pnpm config set --global cacheDir "$CACHE_ROOT/pnpm"` on versions supporting these keys | Query both settings and `pnpm store path` from the home directory and a relevant project |
| Go | `go env -w GOCACHE="$CACHE_ROOT/go-build" GOMODCACHE="$CACHE_ROOT/go-mod"` | `go env GOENV GOCACHE GOMODCACHE`; a small local program with build artifacts on the destination |
| pip | `pip config --user set global.cache-dir "$CACHE_ROOT/pip"`, using the applicable Python installation | `python -m pip cache dir`; check another installed interpreter if configuration discovery differs |
| uv | Existing cache symlinks or the documented `cache-dir` / `UV_CACHE_DIR` setting | `uv cache dir` and resolve symlinks; prefer the same filesystem as its environments |
| Bun | Documented `install.cache.dir` or `BUN_INSTALL_CACHE_DIR` | `bun pm cache` inside a disposable directory with a minimal `package.json`, from a fresh shell |
| Homebrew | `HOMEBREW_CACHE` in the documented user `brew.env` file | `brew --cache` in a new invocation |

Important cases:

- Do not replace an already-working external cache configuration just for visual
  consistency. Existing pnpm projects can record their store location; changing
  it can require reinstalling dependencies. Inspect that impact first.
- A newly written setting is not proof it is effective. Bun can inherit npm's
  configured cache and override the intended Bun location; verify the result. If
  an environment override is needed, keep one authoritative setting and test a
  fresh shell. Existing processes keep their inherited environment.
- A global environment variable such as `XDG_CACHE_HOME` can redirect many
  unrelated tools. Prefer tool-specific settings rather than changing it broadly.
- Settings alone do not migrate existing modules. Preserve cached private or
  offline dependencies when practical; otherwise explain the required downloads.
- An old npx or Corepack cache may be a live runtime. Leave it until its users
  stop, even after future downloads have been redirected.

Completion: native queries resolve to the intended mounted destination, a relevant
small write or startup check succeeds, and any shell/process restart is stated.
Do not run real-account workflows, large builds, installs with lifecycle scripts,
or network-dependent tests merely to prove a cache path.

## Move existing files without losing the original

1. Ask the user to close apps that write the data; never kill unrelated processes.
   Confirm the intended active library, not just the first matching directory.
   If writers cannot be stopped, defer or use the application's documented
   consistent-backup procedure.
2. Check that the target does not contain a different library or cache. Do not
   merge or overwrite it. Record the original configuration and copy location.
3. Copy while preserving permissions, symlinks, extended attributes, resource
   forks, and quarantine information as applicable. On macOS, inspect `ditto`
   help for its preservation options. Keep the source intact during verification.
4. Compare file inventory, symlink targets, and per-file SHA-256 checksums. Check
   that the source did not change during the copy. For a database-backed library,
   use a consistent database and compare integrity and relevant counts. Avoid
   checkpointing or otherwise writing the source database just to inspect it.
5. Switch the application's native location, or use a compatibility symlink only
   for a known compatible, inactive runtime/cache. Verify old-path resolution and
   a disposable write or isolated startup. Preserve a recoverable original until
   the application-specific checks below are complete.
6. Retire the original only within the user's authorization and after successful
   verification. Prefer recoverable retirement for personal data. Recheck actual
   source-volume free space; do not report the copied bytes as space released.

If a cross-volume move fails partway, inspect the source, destination, backup and
any staging path before retrying. Go module-cache directories can be read-only:
copying may succeed while source retirement fails. Verify complete copies before
handling those residuals, use native cache tooling where applicable, and constrain
any recovery strictly to the recorded staging path. Do not retry a generic move
against a nonempty destination or use a broad recursive deletion.

Completion: the tool/app reads the intended copy, the retained source/backup and
any residuals are explicitly accounted for, and measured space matches the actual
retirement state. Copy failure leaves the original usable.

## Application-specific limits

### Photos library

Follow [Apple's relocation procedure](https://support.apple.com/en-us/108345).
The target must be suitable local APFS or Mac OS Extended (Journaled) storage,
not a Time Machine backup destination. Keep Photos closed while copying.

After checksum and database checks, open the external library. If applicable,
have the user confirm **Photos → Settings → General → Use as System Photo
Library**. An open database or successful launch does not prove that the system
library setting changed or that historical media is usable. Verify old photos,
videos and albums with the user before retiring the internal copy.
Pause on iCloud merge, re-upload, account or synchronization prompts; local
relocation does not authorize cloud-setting changes. Referenced originals outside
the library and iCloud originals not downloaded locally are not covered by copying
the library package. Never label a copied-but-retained library as reclaimed space.

### Browser program packages

Playwright and Puppeteer download directories can contain executables, not just
throwaway HTTP caches. Migrate them only when idle and preserve the expected path
or configure a supported download location. Keep user profiles and authentication
out of the migration. Test with disposable profiles and local content, terminate
only processes started for that test, and leave no background browser behind.

Compare any signature failure with the retained original before blaming the
copy. Do not strip quarantine, re-sign the browser, or disable sandbox/security
settings to force a test to pass. Record a pre-existing failure separately from
migration checks and report any behavior still unverified.

### Other application data

- [App Store settings](https://support.apple.com/guide/app-store/change-app-store-settings-mchlp2257/mac)
  document external APFS installation for qualifying large apps. Check the
  current threshold and installed macOS version. This concerns application
  binaries, not automatic relocation of existing Containers or app databases.
- [Docker Desktop settings](https://docs.docker.com/desktop/settings-and-maintenance/settings/)
  provide a disk-image location. Host bind mounts are separate. Protect active
  containers, persistent volumes and rollback environments; do not start a second
  runtime against shared data to test migration.
- WeChat backup destinations and its live chat database are different. Do not
  infer support for one from the other. APFS image/mount workarounds require a
  separate review, backup, permission and startup-service decision; do not run
  third-party installation scripts as part of ordinary cache cleanup.
- For Xcode, distinguish DerivedData, DeviceSupport, simulator device sets and
  installed runtime images. Read local `xcodebuild -help` and `xcrun simctl help`.
  `simctl --set` does not prove GUI integration; a download `-exportPath` does not
  specify the installed runtime location. Use [Apple's component guidance](https://developer.apple.com/documentation/xcode/downloading-and-installing-additional-xcode-components).
- For music/video apps, verify their own download-location setting. Moving
  downloads does not prove that caches, credentials or the whole sandbox moved.

## Report

Report only: measured space change; locations now used by future writes;
verification performed; originals/backups still retained; and the next required
user action. Separate completed migrations from copies awaiting app/UI acceptance.
Keep machine-specific paths, dates and progress out of this reusable skill.
