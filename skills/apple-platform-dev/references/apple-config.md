# Apple Development Configuration

Template for your project's Apple/Swift development configuration. Fill in the
placeholder values (`<TEAM_ID>`, `<ASC_KEY_ID>`, `<ASC_ISSUER_ID>`, device names)
with your own, and keep the filled-in copy in a private location — not in a
shared toolkit repo.

**This file is configuration only.** Procedures live in the skills that own them,
and those skills are authoritative. Earlier revisions of this file duplicated
their content and drifted out of sync — prescribing `tuist init`, automatic code
signing, a `groupType: INTERNAL` attribute that does not exist, and an explicit
build-to-group link that Apple rejects with a 422. All of that is removed. If you
need a procedure, go to:

- **`pink-lady-apple:apple-tuist`** — `Project.swift`, targets, schemes, Info.plist keys
- **`pink-lady-apple:apple-release`** — Fastlane, Ruby pinning, signing via match, notarization
- **`pink-lady-apple:testflight-ship`** — ASC API, uploads, beta groups, testers
- **`pink-lady-apple:debug-builds`** — Debug/Release separation and device installs
- **`pink-lady-apple:sim-capture`** — simulator screenshots and video
- **`swift-quality`** (in swiftskim) — formatting, linting, custom SwiftSyntax rules

## Apple Devices

- **iPhone 15 Pro** — named `<iphone-name>`. Available as a network build destination (no USB required).
- **Apple Watch** — named `<watch-name>`. Paired with `<iphone-name>`.

## App Store Connect API

- Issuer ID: `<ASC_ISSUER_ID>`
- Key ID: `<ASC_KEY_ID>`
- Key file: `~/.appstoreconnect/private_keys/AuthKey_<ASC_KEY_ID>.p8`
- Team ID: `<TEAM_ID>`

**JWT auth (Python).** Use `authlib` for ES256 signing — PyJWT lacks ES256
without extra deps.

```python
from authlib.jose import jwt
header = {"alg": "ES256", "kid": KEY_ID, "typ": "JWT"}
payload = {"iss": ISSUER_ID, "exp": int(time.time()) + 15 * 60, "aud": "appstoreconnect-v1"}
token = jwt.encode(header, payload, private_key)
```

`testflight-ship/scripts/asc.py` already wraps this — reuse it rather than
re-inlining the boilerplate.

**Reading the ASC API docs.** The rendered doc pages are JavaScript-built, so
fetching the `developer.apple.com/documentation/...` URL returns an empty shell.
The underlying DocC JSON *is* fetchable and contains the full schema:

```
https://developer.apple.com/tutorials/data/documentation/appstoreconnectapi/<page-slug>.json
```

Better still, ask the API itself. A deliberately malformed POST reports the exact
permitted operations for a resource:

```
403 "The resource 'ciProducts' does not allow 'CREATE'.
     Allowed operations are: DELETE, GET_COLLECTION, GET_INSTANCE"
```

That is primary-source and beats any doc page.

**Resource hierarchy** (for listing metadata):

- `apps` → `appInfos` → `appInfoLocalizations` (name, subtitle, privacy URL)
- `apps` → `appStoreVersions` → `appStoreVersionLocalizations` (description, keywords, promo text, URLs)
- `apps` → `appStoreVersions` → `appStoreVersionLocalizations` → `appScreenshotSets` → `appScreenshots`
- `apps` → `ageRatingDeclarations` (PATCH with `NONE` / `INFREQUENT_OR_MILD` / `FREQUENT_OR_INTENSE`)

**Screenshot upload is a 3-step process:**

1. **Reserve** — POST `/appScreenshots` with `fileName`, `fileSize`, and the screenshot-set relationship. Returns an upload-operations array.
2. **Upload** — PUT each chunk to the URL in upload operations with `Content-Type: application/octet-stream` plus the given `Content-Length` and offset headers. Most screenshots fit in one chunk.
3. **Commit** — PATCH `/appScreenshots/{id}` with `uploaded: true` and `sourceFileChecksum` (MD5 hex of the whole file).

**Screenshot display types** (for `screenshotDisplayType` on a screenshot set):

- `APP_IPHONE_67` — 6.7" (iPhone 17 Pro Max, 16 Pro Max, 15 Pro Max): **1320x2868**
- `APP_IPHONE_65` — 6.5" (iPhone 16 Plus, 15 Plus, 14 Plus): **1284x2778**
- `APP_IPHONE_61` — 6.1" displays
- `APP_IPAD_PRO_3GEN_129` — 12.9" iPad Pro
- `APP_IPAD_PRO_3GEN_11` — 11" iPad Pro

**Gotchas:**

- `ageRatingDeclarations` PATCH: omit the deprecated `seventeenPlus` attribute or you get a 409.
- `*.json` in `.gitignore` can swallow asset-catalog JSON files — `git add -f` them.

## Encryption Export Compliance

Every app must declare encryption usage via `ITSAppUsesNonExemptEncryption`. For
apps using only Apple-provided encryption (URLSession/TLS, ATS, Keychain,
CryptoKit primitives) set it to `false` — exempt under BIS 740.17(a)(5)(ii)(A).
This eliminates the manual compliance prompt on every submission. Apps
implementing custom cryptography need `true` and possibly an ERN filing.

Set it in the Tuist manifest so it survives regeneration — see
`pink-lady-apple:apple-tuist`.

## Xcode MCP Server — DISABLED

The `swift-lsp@claude-plugins-official` plugin (which uses `xcrun mcpbridge`) is
**disabled**. It launches the Xcode GUI, prompts for agent permissions, and
conflicts with the CLI-first workflow.

**Do not use Xcode MCP tools, and never open or remote-control Xcode.** All
builds, tests, and project management go through:

- `tuist build` / `tuist test` for Tuist-managed projects
- `tuist generate --no-open` to produce an `.xcodeproj` when one is needed
- `Project.swift` for adding targets, schemes, and dependencies

`xcodebuild` is invoked only by Tuist and Fastlane on your behalf, plus the
device/simulator install flows in `debug-builds`. Don't reach for it directly.

The one standing exception is Xcode Cloud onboarding: creating the `ciProduct`
and granting Apple access to the SCM repo cannot be done through any API, so it
requires a one-time GUI session by the Account Holder.

## Swift Quality Commands

Run before returning control after any Swift change:

- `swiftformat-smart .` — format with smart config discovery
- `swiftlint-smart .` — lint with smart config discovery
- `swiftlintcustom-smart .` — custom SwiftSyntax rules

Then `tuist build` and fix every error. Never return control with a failing
build. These binaries live in `<swiftskim-path>/` and are exposed as shell
aliases; the `swift-quality` skill documents the rules they enforce.
