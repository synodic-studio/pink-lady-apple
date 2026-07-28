---
name: apple-release
description: Use this skill when setting up, running, or debugging Apple platform release automation — Fastlane + mise + bundler, iOS TestFlight uploads, macOS Developer ID notarize + custom distribution, the fastlane 2.205 'prices' bug, Ruby version cliffs, and xcrun altool fallbacks. Triggers on "ship to TestFlight", "add fastlane", "upload iOS build", "notarize macOS app", "release lane broken", "fastlane prices error", "asc api key", and similar.
---

# Apple Release Automation

## Why this skill exists

Every Apple app needs the same release plumbing: Fastlane + a pinned Ruby + ASC API key auth + a repeatable lane. This skill captures the pattern so a fresh repo can get productionized in one pass, and so that when Fastlane breaks (it will), the fix path is already known.

The big landmines this skill prevents:

1. **The `prices` relationship bug** — fastlane ≤ 2.212.1 crashes on any ASC App lookup with `'prices' is not a valid relationship name`. Apple removed the relationship from the API in March 2023; old Spaceship code had it hard-coded. One app hit this shipping 2026-04-10. Fix: bump to `>= 2.212.2`. Full writeup in `references/fastlane-history.md`.
2. **The Ruby 2.6 / 2.7 cliff** — system macOS Ruby is 2.6. Fastlane after `2.226.0` requires Ruby `>= 2.7`. So on system Ruby you can only use `2.212.2 ≤ fastlane ≤ 2.226.0`. With modern Ruby (via mise) you can use current stable.
3. **Cache / Spaceship stale state** — when fastlane's build-lookup bombs during upload, the IPA is usually already signed on disk. `xcrun altool --upload-app` is the escape hatch — still fully supported by Apple for App Store uploads (only notarization subcommands were deprecated per TN3147).
4. **The "uploaded but invisible" trap** — fastlane reports success and the build goes VALID in ASC, but no internal beta group exists, so the build never reaches the tester's phone. **`fastlane beta` succeeding is NOT shipping.** The `pink-lady-apple:testflight-ship` skill is the required follow-up — see "After every successful beta upload" below. One app's build 1 (2026-05-03) hit this exact failure: upload reported `🎉 finished successfully`, ASC said VALID, but the tester's phone showed nothing because no `InternalTesters` group existed yet.
5. **Defensive post-upload chain: auto-notify + add-build-to-group + ensure-invited** — `templates/Fastfile-ios.tmpl` chains all three (each `--app-id APP_ID`, no hard-coded group id) after `upload_to_testflight`. The load-bearing one is **`add-build-to-group`**: an internal group with `hasAccessToAllBuilds=false` does NOT receive new builds automatically, so without an explicit link the build goes VALID in ASC but never reaches a single device. This was silently missing from the template for months and is the #1 cause of "you didn't add me again" — the build uploads, the lane reports success, and the tester stays on an old build. `add-build-to-group` now POSTs the link, **verifies it by reading the group's build list** (Apple disallows `GET /builds/{id}/betaGroups`, so verify via the group, not the build), **retries** for ~36s while ASC associates, and **exits non-zero if it never lands** so the lane fails loudly instead of silently. All three commands are idempotent and auto-resolve the internal group from `--app-id`. If a tester reports nothing, run `group-builds --group-id <id>` first — if the build isn't listed, the link failed; re-run `add-build-to-group --app-id <APP_ID>`.

## After every successful beta upload — REQUIRED

Treat `fastlane beta` (or `ship`) finishing successfully as a midpoint. The four mandatory follow-ups are:

1. **Run `pink-lady-apple:testflight-ship` step 4** — first build per app needs 4c (create internal group) + 4d (add tester). Subsequent builds just need 4f (verify with `group-builds`, `list-testers`). The `list-groups --app-id <id>` check is the canary: if only an external group exists (`internal=False`), create the internal group.
2. **Bump the build number** — `mise exec -- bundle exec fastlane bump_build`. ASC rejects duplicates.
3. **Commit** the bump, `Gemfile.lock`, and any Project.swift / Fastfile changes.
4. **Push** to the working branch.

The Fastfile `beta` lane already runs the defensive `auto-notify` + `ensure-invited` helpers, so you don't have to invoke them manually unless shipping ad-hoc.

Don't report "shipped" until `group-builds` shows the new build and `list-testers` lists the tester. "ASC shows VALID" alone is not enough.

## The canonical stack

For any new Apple app (iOS or macOS):

| Layer | Pin | Notes |
|---|---|---|
| Ruby | `3.3.11` via mise | Pinned in `.mise.toml` |
| Bundler | latest | Installed into mise-managed Ruby |
| Fastlane | `~> 2.232` | Current stable, requires Ruby ≥ 2.7 |
| Gem path | `vendor/bundle` | Via `.bundle/config`, project-local, not global |
| ASC auth | API key `.p8` | `~/.appstoreconnect/private_keys/AuthKey_<ASC_KEY_ID>.p8` |
| ASC issuer | `<ASC_ISSUER_ID>` | Shared across all your apps |
| ASC key id | `<ASC_KEY_ID>` | Shared across all your apps |
| Team ID | `<TEAM_ID>` | <Team Name>, shared |

Invocation from any repo (iOS uses the `ship` wrapper — see below):

```bash
cd <project-dir>
ship                                         # iOS: `ship` wrapper does the PAM + mise + MATCH_PASSWORD plumbing
mise exec -- bundle exec fastlane mac ship   # macOS: build + notarize + distribute (no ship wrapper yet)
mise exec -- bundle exec fastlane beta_probe # iOS: 10-sec ASC health check (no build)
```

The `mise exec --` prefix is load-bearing — it activates the repo-local `.mise.toml` and puts mise-managed Ruby + bundler on PATH, so `bundle exec fastlane` resolves to the pinned fastlane, not whatever is on system Ruby.

### `ship` command (iOS)

`~/.local/bin/ship` is the universal iOS TestFlight wrapper. It:

1. Checks the shell's audit UID — aborts with a clear message if the
   shell has no PAM session (Claude Code, non-interactive). The user
   must run from a real mosh/ssh shell; see `~/.zprofile`'s auto-re-exec
   via `login -fpq`.
2. Exports `MATCH_PASSWORD` from `pass show <match-password>`.
3. Runs `mise exec -- bundle exec fastlane beta` (or a specified lane),
   teeing output to `/tmp/ship-<app>-<lane>.log`.

So "ship to TestFlight" for any iOS app is literally: `cd` to
the project, `ship`. Done.

## Platform split: iOS vs macOS

Both share the infrastructure files (`.mise.toml`, `Gemfile`, `.bundle/config`, `fastlane/Appfile`). Only the `fastlane/Fastfile` lanes differ.

### iOS — TestFlight upload

Uses `match` + `build_app` + `upload_to_testflight`. Single `beta` lane. Signing is manual against the match-generated profile — see "Signing" below; automatic signing does not work headlessly. `templates/Fastfile-ios.tmpl` is the reference implementation.

Always includes a `beta_probe` lane that calls `latest_testflight_build_number` against ASC — runs in under 10 seconds, exercises the exact Spaceship code path that was broken in 2.205.1, so it's a perfect canary before a real upload.

### macOS — Developer ID + notarize + custom distribution

Uses `build_mac_app` + `notarize`. Typically followed by a project-specific `deploy` lane that uploads the stapled zip to whatever delivery channel the app uses (a macOS app uses a deploy-worker Cloudflare Worker). See `templates/Fastfile-macos.tmpl` for the `release` + `deploy` + `ship` pattern.

## When to use this skill

- **"Set up fastlane in <repo>"** — stamp the templates, run `mise install`, run `bundle install`, run `fastlane beta_probe` to verify. Follow the "Scaffold procedure" below.
- **"Ship <iOS app> to TestFlight"** — cd to the repo, run `mise exec -- bundle exec fastlane beta`, THEN invoke `pink-lady-apple:testflight-ship` step 4 (group + tester setup), THEN bump+commit+push. Skipping the testflight-ship hand-off is the most common iOS shipping bug. If `fastlane beta` fails on Spaceship, check the troubleshooting section below.
- **"Ship <macOS app>"** — cd to the repo, run `mise exec -- bundle exec fastlane mac ship` (or whatever the repo's combined lane is called).
- **Error message contains `prices`**, or `latest_testflight_build_number` fails, or `upload_to_testflight` crashes during app lookup — see "The `prices` bug" below. Almost always fixed by bumping fastlane and running `bundle update fastlane`.
- **Error message contains `required_ruby_version`** or `unsupported Ruby version` — the repo is trying to load a fastlane version that needs newer Ruby than the current interpreter. Either upgrade Ruby via mise or cap fastlane.

## Scaffold procedure

When asked to "add fastlane to <repo>" or "set up TestFlight automation", follow this exactly — copy-paste each step, don't improvise.

### Step 1: Detect platform

Read the repo's top-level `Project.swift` (Tuist) or `.xcodeproj` to determine:
- iOS (TestFlight destination) — use `templates/Fastfile-ios.tmpl`
- macOS (Developer ID + custom distribution) — use `templates/Fastfile-macos.tmpl`

### Step 2: Stamp the infra files

Write these four files verbatim from the templates (no placeholders yet — the iOS ones are fully static):

- `.mise.toml` ← `templates/mise.toml.tmpl`
- `Gemfile` ← `templates/Gemfile.tmpl`
- `.bundle/config` ← `templates/bundle-config.tmpl`
- `fastlane/Appfile` ← `templates/Appfile.tmpl` (substitute `APP_IDENTIFIER`)

### Step 3: Stamp the Fastfile

If the repo already has a `fastlane/Fastfile` (e.g., with a `screenshots` lane), APPEND the beta lane from the template. Do not overwrite. If no Fastfile exists, write the full template.

For iOS, substitute `APP_IDENTIFIER` in the `latest_testflight_build_number` call in the `beta_probe` lane.

For macOS, substitute `PROJECT`, `SCHEME`, `BUNDLE_ID`, and the deploy destination (this varies — a macOS app uses `deploy.example.com`).

### Step 4: Update `.gitignore`

Append (or verify) these entries:

```
vendor/bundle/
.bundle/*
!.bundle/config
```

The `!.bundle/config` exception is intentional — it lets `bundle install` resolve the `vendor/bundle` path on a fresh clone without requiring `bundle config set`.

### Step 5: Install and verify

```bash
cd <repo>
mise trust .mise.toml            # first time only
mise install                     # installs Ruby 3.3.11 if not present
mise exec -- gem install bundler --no-document
mise exec -- bundle config set --local path vendor/bundle
mise exec -- bundle install      # installs fastlane + deps into vendor/bundle
```

### Step 6: Smoke test

For iOS:
```bash
mise exec -- bundle exec fastlane beta_probe
```
Should print `ASC reachable — latest TestFlight build: N` in under 10 seconds.

For macOS:
```bash
mise exec -- bundle exec fastlane mac --list
```
Should print the available lanes without errors.

### Step 7: Commit

Commit these files (plus `Gemfile.lock` which bundler created):

```
.mise.toml
Gemfile
Gemfile.lock
.bundle/config
.gitignore (updated)
fastlane/Appfile
fastlane/Fastfile (new or updated)
```

Do NOT commit `vendor/bundle/` (gitignored) or `fastlane/README.md` (auto-regenerated).

## Troubleshooting

### `'prices' is not a valid relationship name`

Root cause: you're on fastlane ≤ 2.212.1 and hitting Apple's post-March-2023 API.

Fix:
```bash
cd <repo>
# If Gemfile is pinned low, bump it:
sed -i '' 's/gem "fastlane".*/gem "fastlane", "~> 2.232"/' Gemfile
mise exec -- bundle update fastlane
mise exec -- bundle exec fastlane beta_probe
```

If you cannot bump (stuck on system Ruby 2.6 and don't want mise), cap at `~> 2.226` which is the last Ruby-2.6-compatible version with the fix.

If you need to ship RIGHT NOW and can't wait for a bundle update, use altool:
```bash
xcrun altool --upload-app \
  -f build/fastlane/<AppName>.ipa \
  -t ios \
  --apiKey <ASC_KEY_ID> \
  --apiIssuer <ASC_ISSUER_ID>
```
This is Apple-supported. See `references/altool-status.md`.

### `required_ruby_version` or `Gem::InstallError: fastlane requires Ruby version >= 2.7`

The fastlane version you pinned requires newer Ruby than what's active.

Check active Ruby: `mise exec -- ruby --version`

If it's still 2.6, the repo is missing `.mise.toml` or mise isn't activated. Scaffold step 2 + `mise trust` + `mise install`.

If you don't want mise, cap fastlane: `gem "fastlane", "~> 2.226"` in the Gemfile.

### `Latest upload for version ... build: N` shows an OLD build

Your upload succeeded but ASC is eventually consistent — wait 60–180 seconds and re-query. Don't assume the upload failed.

### Build processing stuck at PROCESSING

Normal — takes anywhere from 2 to 20 minutes. Use the `verify-asc-build.py` pattern (inline in the Fastfile via `sh()`) to poll.

Never claim "uploaded successfully" in a status report until ASC shows `VALID` state. This is a global rule in this automation.

### `claude plugins update` reports "already at latest version"

The plugin cache is comparing against the CACHED marketplace metadata, not the live remote. Refresh the marketplace first:
```bash
claude plugins marketplace update pink-lady-apple
claude plugins update pink-lady-apple@pink-lady-apple
```

If that STILL doesn't pick up the new version, force-reinstall:
```bash
claude plugins uninstall pink-lady-apple@pink-lady-apple
claude plugins install pink-lady-apple@pink-lady-apple
```

### Still seeing a `pink-lady` marketplace or plugin

The repo, marketplace, and plugin were all renamed `pink-lady` → `pink-lady-apple`
at v2.0.0. `update` cannot cross that rename — the old names point at a repo path
that no longer resolves. Drop the old registration and re-add:
```bash
claude plugins uninstall pink-lady@pink-lady
claude plugins marketplace remove pink-lady
claude plugins marketplace add synodic-studio/pink-lady-apple
claude plugins install pink-lady-apple@pink-lady-apple
```

Skill references also moved namespace: `pink-lady:testflight-ship` is now
`pink-lady-apple:testflight-ship`.

## The `prices` bug — summary

Full writeup in `references/fastlane-history.md`. One-sentence version: Apple removed the `prices` relationship from the `apps` resource in the App Store Connect API during the March 2023 pricing overhaul; fastlane's Spaceship had it hard-coded in `ESSENTIAL_INCLUDES`; [PR #21187](https://github.com/fastlane/fastlane/pull/21187) removed it in fastlane 2.212.2.

Every fastlane version from 2.205.1 (our old pin) through 2.212.1 is broken. The window that works on system Ruby 2.6 is `2.212.2 ≤ fastlane ≤ 2.226.0`. With modern Ruby via mise, use current stable (`~> 2.232`).

## Signing: `fastlane match` (as of 2026-04-14)

All iOS apps sign via `fastlane match` with a shared team-wide
store. The cert is the same for every app under team `<TEAM_ID>`;
match generates one provisioning profile per bundle ID.

**Why we switched to match (was: automatic signing via ExportOptions):**
headless mosh/ssh shells on macOS have `auid=-1` and the Security
framework refuses to read user keychain prefs without a valid PAM
audit session. Automatic signing with Xcode's cert lookup fails
silently. Match imports the cert on-demand into login.keychain (via
its own helpers) and passes `--keychain` explicitly to codesign, so
it works from any PAM-logged-in shell without GUI setup.

### Setup (one-time per Mac)

- Bare git repo at `<certs-repo>/` — stores encrypted
  certs + profiles for all Internal apps.
- Password stored in pass as `<match-password>` (44-char
  random) — retrieved by the `ship` command.
- First `ship` per app auto-generates cert + profile and commits them
  to the store. Subsequent runs just fetch.

### Per-app Matchfile

Every app's `fastlane/Matchfile` is the same shape:

```ruby
git_url(ENV["MATCH_GIT_URL"] || File.expand_path("<certs-repo>"))
storage_mode("git")
type("appstore")
app_identifier([
  "com.example.<APP>",
  "com.example.<APP>.<extension>",
])
team_id("<TEAM_ID>")
api_key_path("/tmp/asc_key.json")
```

The beta lane calls an `ensure_asc_key_json` helper that serializes the
ASC API `.p8` into `/tmp/asc_key.json` (Matchfile needs a file path,
not a Ruby object), then `match(type: "appstore")` non-readonly so the
store self-populates on first use.

The build step uses manual signing with the match-generated profile
names (`match AppStore <bundle-id>`). See your app's `fastlane/Fastfile`
for the reference implementation.

### Remote storage

Currently the match git repo is local-only (`<certs-repo>`).
When `gh` re-auths and a private GitHub repo exists, flip the
`MATCH_GIT_URL` env var to the remote URL and `git remote add origin +
push` the local repo. No Matchfile edits needed.

## App Store listing (metadata + screenshots + submission prep)

TestFlight (`beta`) is separate from staging the public **App Store listing**.
For "fill out the metadata", "upload screenshots", "get it ready for review", or
"set categories/age rating" — see **`references/app-store-listing.md`**. The load-
bearing gotcha: `upload_to_app_store` throws a bare `No data` on the categories
step of a **first** app version, so text metadata and screenshots go through
`deliver` (split into two lanes) while categories, content rights, age rating, and
the build link go through the ASC API directly. A full listing can be staged with
`submit_for_review: false`; only the final submit and the App Privacy attestation
need a human. Apps keep their metadata as a
`fastlane/metadata/en-US/` deliver structure with a `push_metadata` lane.

## What this skill does NOT do

- **No screenshot automation templates** — every app's UI test suite is different. Copy the capture approach from a reference app (`CaptureTests` → `/tmp` PNGs, seeded mock data, `-serverURL` launch arg) but don't try to share the lane.
- **No cross-repo CI** — the org is direct-commit-to-develop with local pre-push hooks. Fastlane lanes run locally on the build machine. There is no GitHub Actions equivalent.
- **No project generation** — `Project.swift`, targets, schemes, and the Info.plist keys that gate a successful upload belong to **`pink-lady-apple:apple-tuist`**. This skill assumes the project already generates and builds.

## File layout in the skill

```
skills/apple-release/
├── SKILL.md                          (this file)
├── templates/
│   ├── mise.toml.tmpl                (ruby 3.3.11)
│   ├── Gemfile.tmpl                  (fastlane ~> 2.232)
│   ├── bundle-config.tmpl            (BUNDLE_PATH: vendor/bundle)
│   ├── Appfile.tmpl                  (bundle ID + team ID)
│   ├── Fastfile-ios.tmpl             (beta + beta_probe lanes)
│   └── Fastfile-macos.tmpl           (release + deploy + ship lanes)
└── references/
    ├── fastlane-history.md           (the prices bug, Ruby cliff, full sources)
    ├── altool-status.md              (still supported for App Store, deprecated for notarization only)
    └── app-store-listing.md          (metadata/screenshots/ASC-API; the first-version "No data" bug)
```
