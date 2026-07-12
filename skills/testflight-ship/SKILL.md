---
name: testflight-ship
description: Use when uploading an Apple app to TestFlight, especially first-time app setup or when adding internal testers. Covers the full end-to-end workflow from bundle ID registration through tester invitation — prevents the common failure mode where the build ships but the tester is never invited, leaving the user unable to install the app. Triggers on "ship to TestFlight", "upload iOS build", "add TestFlight tester", "new TestFlight app", "create app in ASC", "distribute internal build", "testflight internal group", and any phrase about making a build available to internal testers. For general Fastlane/notarize setup see synodic-apple:apple-release.
---

# TestFlight Ship

## Why this skill exists

Shipping an Apple app to TestFlight is a multi-step workflow and the last step — tester distribution — keeps being miscoded. The two specific ways it fails:

1. **Skipping the group creation step entirely** — upload reports success, build goes VALID, then nothing. "VALID" feels like success but the build is invisible to every tester.
2. **Creating a pretend-internal group** by omitting `isInternalGroup: true` on the `POST /betaGroups` — every API call returns 201, but the group is actually external and requires Beta App Review before anyone sees anything. Apple's docs describe the attribute as read-only which is misleading: it is read-only on PATCH, **writable on POST**.

### Defensive tools (not bugs, but still worth running)

A past incident initially looked like two more Apple bugs: `autoNotifyEnabled` defaulting to false and `betaTester.state` staying null even with `hasAccessToAllBuilds: true`. The actual root cause turned out to be a stale TestFlight invite on the user's phone from a prior session that was blocking the new invite from surfacing. Once the stale invite was cleared, the build appeared as expected.

The two helpers added during that debugging session (`auto-notify`, `ensure-invited`) are still kept and chained into the canonical Fastfile beta lane as defensive measures — they're idempotent and harmless on a healthy upload, and they unstick edge cases without needing manual ASC API calls. Don't claim "this is what Apple does wrong" — they're belt-and-suspenders for the rare case where Apple's auto-distribute or auto-notify hasn't kicked in yet.

This skill makes "ship to TestFlight" mean **tester-sees-the-build-on-their-phone**, not just **build-is-in-ASC**.

The workflow is:

1. One-time app setup (first time only per app) — one step (app record creation) requires the ASC web UI, the rest is API-automatable
2. Per-build Info.plist hygiene (baked in once, then automatic)
3. Build + upload via fastlane
4. **Create internal group + add tester** — internal groups with `hasAccessToAllBuilds` auto-receive every new VALID build; no explicit distribute step needed
5. Verify the build is visible to the tester

If this is your second/third/fourth build to an app that already exists, skip to step 3 and then step 4f only (verify). The internal group auto-distributes — no manual API call. Steps 4c and 4d are first-build-only.

## Companion skills

- **`synodic-apple:apple-release`** — broader Fastlane plumbing: Ruby pinning, `prices` relationship bug, `xcrun altool` fallback, macOS notarization. Read that first if setting up a new repo's release tooling.
- **`synodic-apple:apple-platform-dev`** — Tuist/SwiftUI conventions.
- **`synodic-apple:debug-builds`** — Debug/Release separation with distinct bundle IDs.

## Environment (the user's setup)

- ASC API key: `KEY_ID=<ASC_KEY_ID>`, `ISSUER_ID=<ASC_ISSUER_ID>`, key at `~/.appstoreconnect/private_keys/AuthKey_<ASC_KEY_ID>.p8`
- the user's tester info: email `tester@example.com`, first `<First>`, last `<Last>`
- Internal beta group naming convention: `InternalTesters`
- Ruby is mise-managed — run fastlane via `mise exec -- bundle exec fastlane <lane>` (or just `ship`, which wraps that plus match password + PAM guard)
- Tuist project — never open Xcode, always `tuist generate --no-open` before a build
- Signing via `fastlane match` with a shared cert repo at `<certs-repo>` (password: `pass show <match-password>`). See `apple-release` for the canonical signing setup.

The helper script `scripts/asc.py` in this skill wraps all the ASC API calls below with the env values pre-filled. Read it before reimplementing.

---

## Step 1 — First-time app setup

Only needed when the app doesn't exist in ASC yet.

### 1a. Register the bundle ID (API does this)

```bash
uv tool run --from authlib --with httpx python3 scripts/asc.py register-bundle \
  --identifier com.example.MyApp \
  --name "MyApp"
```

This POSTs to `/v1/bundleIds`. Works with API key auth. Returns the bundle ID record (e.g. `<bundle-record-id>`).

### 1b. Enable capabilities (API does this)

Each capability needed by the app (NFC, background modes, HealthKit, etc.) must be enabled on the bundle ID record BEFORE the first build, or provisioning profiles won't include them.

```bash
uv tool run --from authlib --with httpx python3 scripts/asc.py add-capability \
  --bundle-record <bundle-record-id> \
  --capability NFC_TAG_READING
```

Common capability values: `NFC_TAG_READING`, `ICLOUD`, `PUSH_NOTIFICATIONS`, `HEALTHKIT`, `IN_APP_PURCHASE`, `ASSOCIATED_DOMAINS`, `APP_GROUPS`.

### 1c. Create the app record (MANUAL — API is FORBIDDEN here)

**Apple does not permit app creation via API-key auth.** `POST /v1/apps` returns `403 FORBIDDEN_ERROR` — "The resource 'apps' does not allow 'CREATE'". This has been Apple's policy since the v1 API launched. The only paths to create an app are the ASC web UI or `fastlane produce` with Apple ID + 2FA (which the user can't handle via Telegram).

The correct play: prompt the user with exact field values, wait for confirmation.

> Go to **https://appstoreconnect.apple.com/apps** → click **+** → **New App**
>
> - Platform: **iOS** (or macOS)
> - Name: **MyApp**
> - Primary Language: **English (U.S.)**
> - Bundle ID: **com.example.MyApp** (select from dropdown — already registered)
> - SKU: **myapp-internal-001** (any unique string)
> - User Access: **Full Access**
>
> Reply "done" when the app appears in your ASC list.

**Do not proceed to step 2 until the user confirms.** If the app record doesn't exist, fastlane's `upload_to_testflight` will fail with an error that looks unrelated.

After confirmation, fetch the app ID for later steps:

```bash
uv tool run --from authlib --with httpx python3 scripts/asc.py find-app \
  --bundle-id com.example.MyApp
# → prints app id (e.g. <app-id>)
```

---

## Step 2 — Info.plist must-haves

Bake these into `Project.swift` (Tuist) so they survive regeneration and every future build passes validation. Don't rely on fastlane flags or post-upload API patches.

```swift
.target(
    name: "MyApp",
    bundleId: "com.example.MyApp",
    infoPlist: .extendingDefault(with: [
        "CFBundleDisplayName": "MyApp",
        "CFBundleVersion": "$(CURRENT_PROJECT_VERSION)",
        "CFBundleIconName": "AppIcon",                     // ← required for iOS 11+
        "ITSAppUsesNonExemptEncryption": false,             // ← export compliance
        "UILaunchScreen": .dictionary([:]),
        // ...usage descriptions, etc.
    ]),
    sources: ["MyApp/**"],
    resources: ["MyApp/Assets.xcassets"],                   // ← explicit, glob won't grab it
    entitlements: .file(path: "MyApp/MyApp.entitlements"),
)
```

### Why each one matters

- **`CFBundleIconName: AppIcon`** — altool rejects builds without this for iOS 11+ because apps must declare their asset-catalog icon name. Error if missing: `Missing Info.plist value. A value for the Info.plist key 'CFBundleIconName' is missing`.
- **`ITSAppUsesNonExemptEncryption: false`** — declares export compliance at build time. Without it, every new build lands in ASC "missing compliance" and can't be distributed until you PATCH the build record via API. Setting it to `false` is correct for any app that only uses OS-provided encryption (HTTPS, Keychain, CryptoKit primitives) — exempt under BIS 740.17(a)(5)(ii)(A). the user's apps should always be `false` by default.
- **`resources: ["MyApp/Assets.xcassets"]`** — Tuist's `sources:` glob doesn't pick up `.xcassets` bundles. If you forget this, the build succeeds but altool fails with `Missing required icon file. The bundle does not contain an app icon for iPhone / iPod Touch of exactly '120x120' pixels`.

### Asset catalog

Each target needs its OWN `Assets.xcassets` — you can't share across targets. For internal tools where aesthetics don't matter, copying another target's icon is fine:

```bash
mkdir -p MyApp/Assets.xcassets/AppIcon.appiconset
cp OtherApp/Assets.xcassets/AppIcon.appiconset/AppIcon.png MyApp/Assets.xcassets/AppIcon.appiconset/
cp OtherApp/Assets.xcassets/AppIcon.appiconset/Contents.json MyApp/Assets.xcassets/AppIcon.appiconset/
cat > MyApp/Assets.xcassets/Contents.json <<'EOF'
{ "info" : { "author" : "xcode", "version" : 1 } }
EOF
```

### NFC apps: use TAG only, not NDEF

For apps using Core NFC, the entitlement format key changed. In iOS 18.2+ SDK 26.2, Apple disallows `NDEF` in `com.apple.developer.nfc.readersession.formats` — altool rejects the upload with `Invalid entitlement for core nfc framework … 'NDEF is disallowed'`. Use `TAG` alone; it now covers both `NFCTagReaderSession` AND `NFCNDEFReaderSession`.

```xml
<key>com.apple.developer.nfc.readersession.formats</key>
<array>
    <string>TAG</string>
</array>
```

Removing NDEF is the **modern correct path**, not a regression. Apple's new model is: the entitlement grants session-class access, not format access; the session API itself handles the format.

---

## Step 3 — Build + upload via fastlane

For a new app, add a lane to `fastlane/Fastfile`. Pattern for a project with multiple apps in the same workspace:

```ruby
desc "Build MyApp and upload to TestFlight (internal only)"
lane :beta_myapp do
  sh("cd .. && tuist generate --no-open")

  build_app(
    workspace: "ParentProject.xcworkspace",
    scheme: "MyApp",
    configuration: "Release",
    export_method: "app-store",
    clean: true,
    output_directory: "build/fastlane",
    output_name: "MyApp.ipa",
    include_bitcode: false,
    include_symbols: true,
    xcargs: "-allowProvisioningUpdates",
    export_options: {
      signingStyle: "automatic",
    },
  )

  api_key = app_store_connect_api_key(
    key_id: "<ASC_KEY_ID>",
    issuer_id: "<ASC_ISSUER_ID>",
    key_filepath: File.expand_path("~/.appstoreconnect/private_keys/AuthKey_<ASC_KEY_ID>.p8"),
    duration: 1200,
    in_house: false,
  )

  upload_to_testflight(
    api_key: api_key,
    app_identifier: "com.example.MyApp",         # required when multiple apps share a workspace
    ipa: "build/fastlane/MyApp.ipa",
    skip_waiting_for_build_processing: false,   # wait for VALID
    skip_submission: true,                      # internal only, no app review
    distribute_external: false,
    notify_external_testers: false,
    changelog: "What's new in this build.",
  )
end
```

### Build number sync — CURRENT_PROJECT_VERSION must match TestFlight

`CURRENT_PROJECT_VERSION` in `Project.swift` (Tuist) is baked into the IPA as `CFBundleVersion`. TestFlight assigns its own sequential build number on upload and uses this value — so if your local counter is behind (e.g. from prior builds uploaded outside this session), the mismatch is immediately visible to testers.

**Rule:** the `bump_build` Fastlane lane must query TestFlight for the latest build version before incrementing. Pattern:

```ruby
tf_latest_str = sh(
  "uv tool run --from authlib --with httpx python3 #{asc_script} build-status --app-id #{app_id} --limit 1 2>&1 | head -1 | grep -oE 'build [0-9]+' | awk '{print $2}'",
  log: false,
).strip
tf_latest = tf_latest_str.to_i
next_build = [tf_latest, local_current].max + 1
```

This takes `max(TestFlight latest, local)` so it's safe whether local is ahead or behind. Never just increment the local number blindly.

### Why the explicit flags matter

- **`xcargs: "-allowProvisioningUpdates"`** — tells Xcode to regenerate the provisioning profile when capabilities change. Without it, you hit `Provisioning profile "iOS Team Provisioning Profile: *" doesn't include the <Capability> capability` even after you've enabled the capability on the bundle ID record. The wildcard profile is cached and won't update on its own.
- **`export_options: { signingStyle: "automatic" }`** — lets the export step (archive → IPA) use automatic signing. Without it, `exportArchive No profiles for 'com.example.MyApp' were found` because a distribution profile doesn't exist yet.
- **`app_identifier:`** in `upload_to_testflight` — required when the workspace has multiple apps, otherwise fastlane guesses and uploads to the wrong one.

Run it:

```bash
cd <project-dir>
ship beta_myapp     # or just `ship` if the lane is named `beta`
```

The `ship` wrapper (`~/.local/bin/ship`) handles the PAM audit check,
sets `MATCH_PASSWORD` from pass, and runs `mise exec -- bundle exec
fastlane <lane>` with output teed to `/tmp/ship-<app>-<lane>.log`.

---

## Step 4 — Group + tester setup (THE STEP THAT KEEPS GETTING MISSED)

After `upload_to_testflight` reports success and the build shows `processingState=VALID`, the build is **invisible** to every tester until an internal beta group with `hasAccessToAllBuilds: true` exists on this app AND that group has testers attached. First build only: you have to create the group and attach the tester. Subsequent builds: the group auto-picks them up — nothing to do except verify.

If you stop after `fastlane finished successfully 🎉` on a first build without doing steps 4c and 4d, you have not shipped. You have parked a bitstream in Apple's CDN.

### 4a. Verify the build is VALID

```bash
uv tool run --from authlib --with httpx python3 scripts/asc.py build-status \
  --app-id <app-id>
# → build 50: processingState=VALID expired=False
```

If `processingState` is still `PROCESSING`, wait 30-60 seconds and retry. If it's `INVALID`, check email for the compliance issue.

**If the build NEVER shows up at all** (no record after ~15 min, `upload_to_testflight` still printing "Waiting for the build to show up"): stop waiting. This is a **processing rejection**, and Apple only reports it by **email to the ASC account holder** — there is no ASC API endpoint for post-upload ITMS errors (a rejected build creates no record, so `build-status` shows nothing). **Ask the user to check their email** for an "App Store Connect — we noticed one or more issues" message; it names the exact `ITMS-90xxx` error. Kill the fastlane waiter (it will hang for hours), fix the cause, bump the build number, and re-upload. See the gotcha table for the common ITMS errors.

### 4b. Declare export compliance on the build record (only needed if Info.plist was missing `ITSAppUsesNonExemptEncryption`)

If you baked in `ITSAppUsesNonExemptEncryption: false` per step 2, skip this — the compliance declaration rides along with the build automatically. If not:

```bash
uv tool run --from authlib --with httpx python3 scripts/asc.py declare-compliance \
  --build-id <build-id> \
  --uses-non-exempt-encryption false
```

Missing this declaration is why EXTERNAL group distribution fails with `Build is not in an externally assignable state`. (Internal groups with `hasAccessToAllBuilds` auto-distribute regardless of compliance state, but you still want compliance declared so you never trip over it later.)

### 4c. Create the INTERNAL beta group (FIRST BUILD ONLY — API WORKS)

You *can* create an internal group via the API, but the key is passing the two magic attributes **at creation time** — they appear to be read-only on PATCH but are writable on POST:

```
POST /v1/betaGroups
{
  "data": {
    "type": "betaGroups",
    "attributes": {
      "name": "InternalTesters",
      "isInternalGroup": true,          ← CRITICAL
      "hasAccessToAllBuilds": true      ← CRITICAL (enables auto-distribution)
    },
    "relationships": {
      "app": {"data": {"type": "apps", "id": "<app_id>"}}
    }
  }
}
```

Via the helper script:

```bash
uv tool run --from authlib --with httpx python3 scripts/asc.py create-internal-group \
  --app-id <app-id> \
  --name InternalTesters
```

If you forget `isInternalGroup: true` and `hasAccessToAllBuilds: true`, you get an external group that requires Beta App Review — that's the failure mode. Apple's API docs describe both attributes as read-only, which is misleading — read-only on PATCH, writable on POST. Creating without these flags is not a reversible error: you have to delete the group and recreate.

### 4d. Add the tester(s) to the group

For internal groups, testers are created as `betaTester` records with the group relationship — same endpoint as external, just scoped to an internal group. The group stays internal (`isInternalGroup=true`) after attaching betaTesters.

```bash
uv tool run --from authlib --with httpx python3 scripts/asc.py add-tester \
  --group-id <group-id> \
  --email tester@example.com \
  --first-name <First> \
  --last-name <Last>
```

Tester records are per-app — you cannot reuse a tester record from a different app. If creating one returns `409 STATE_ERROR`, that's a stale record somewhere; delete and retry.

### 4e. Distribution for internal groups

**Normal case — `hasAccessToAllBuilds: true`.** No explicit distribute step needed. Internal groups with this flag auto-receive every new VALID build. `POST /v1/builds/{id}/relationships/betaGroups` with an internal group target actually returns 422; the right answer is to do nothing and let Apple auto-distribute.

**Edge case — `hasAccessToAllBuilds: false`.** Some internal groups (e.g. an app's "Internal Testers" group, group ID `<group-id>`) are flagged internal but have `hasAccessToAllBuilds: false`. These do NOT auto-receive builds and require an explicit link. Use `add-build-to-group` from the betaGroups side (not `distribute`, which refuses internal groups):

```bash
uv tool run --from authlib --with httpx python3 scripts/asc.py add-build-to-group \
  --app-id <app-id> \
  --group-id <group-id>
# Resolved latest build: v<N> (<build-id>)
# Build <build-id> added to group <group-id>
# 409 = already linked (idempotent)
```

To check which applies: `group-details --group-id <id>` — look at `hasAccessToAllBuilds`. If false, run `add-build-to-group` after every upload.

External groups DO need explicit distribution via `distribute` (see below).

### 4e-bis. Enable autoNotify (REQUIRED — or testers don't get pinged)

`buildBetaDetail.autoNotifyEnabled` defaults to **false** on every new upload. With it false, the build is technically distributed to internal testers (the group membership grants access) but TestFlight never pushes a notification to anyone's phone — the tester would have to manually open TestFlight and pull-to-refresh to discover the build.

PATCH it true after every upload:

```bash
uv tool run --from authlib --with httpx python3 scripts/asc.py auto-notify \
  --app-id <app-id>
# resolves to the most recent build for the app and PATCHes
# Build <id>: autoNotifyEnabled=True internalBuildState=IN_BETA_TESTING
```

Or pass `--build-id <build-id>` directly. The canonical Fastfile beta lane in `apple-release/templates/Fastfile-ios.tmpl` calls this automatically after `upload_to_testflight` returns — copy that pattern into any new app's Fastfile.

### 4e-ter. Force tester invites via individualTesters (REQUIRED — or state stays null)

Even with autoNotify on, internal-group `hasAccessToAllBuilds: true` does NOT actually trigger per-tester invites. The tester's `betaTester.state` stays `null` and TestFlight delivers nothing. Apple's docs imply otherwise; the API behavior disagrees.

The fix is to explicitly POST every internal-group tester to the build's `individualTesters` relationship — that flips `state` to `INVITED`, which is what TestFlight actually checks before pushing.

```bash
uv tool run --from authlib --with httpx python3 scripts/asc.py ensure-invited \
  --app-id <app-id>
# Latest build: v<N> (<build-id>)
# Internal groups: ['InternalTesters']
# Testers linked to build <build-id>:
#   tester@example.com state=INVITED
```

Idempotent — Apple returns `409 STATE_ERROR: Tester(s) cannot be assigned` when the link already exists, which the script treats as success. Run after `auto-notify` on every upload. The canonical Fastfile beta lane chains both calls.

### 4f. Verify — confirm the build is visible to the group and the tester is present

```bash
uv tool run --from authlib --with httpx python3 scripts/asc.py group-details \
  --group-id <group-id>
# Should show isInternalGroup=True hasAccessToAllBuilds=True

uv tool run --from authlib --with httpx python3 scripts/asc.py group-builds \
  --group-id <group-id>
# Should list build 50 as VALID

uv tool run --from authlib --with httpx python3 scripts/asc.py list-testers \
  --group-id <group-id>
# Should list the tester's email
```

All three must show the expected output. If any is empty or off, something upstream failed — don't claim "shipped" until all three check out.

### 4g. What the tester experiences

TestFlight on iOS refreshes internal builds every ~1-5 minutes after they go VALID **provided `autoNotifyEnabled` is true** (step 4e-bis). With autoNotify on, iOS pushes a notification to the tester within minutes of the build becoming available. If the tester already has the app installed from a previous build, iOS auto-notifies them of the update. If this is the FIRST build for this app for this tester, they get an email invite to install TestFlight (if they don't have it) and then the app.

Without autoNotify, none of the above happens automatically — the tester has to manually open TestFlight and pull-to-refresh.

Tell the user: "DD NFC build N is on TestFlight internal, distributed to InternalTesters which includes your account. Open TestFlight and pull to refresh." Verify via API first (step 4f); only then tell him.

### 4h. EXTERNAL groups (rarely needed — only if you want public beta or outside-team testers)

External groups require:
- A privacy policy URL on the app
- Beta App Review on every first build (24-72h wait)
- `distribute_external: true` in fastlane `upload_to_testflight`

Only go external when you specifically need testers who aren't on the ASC team. Internal apps are team-internal by default — skip this unless the user says otherwise.

If you DO need external: POST /betaGroups without `isInternalGroup`, POST /betaTesters with emails, then POST /builds/{id}/relationships/betaGroups to distribute (explicit distribution IS required for external, unlike internal).

---

## Step 5 — Tell the user what you did

Be specific. Don't say "shipped" or "uploaded". Say:

> Build 50 of MyApp is on TestFlight (ASC app id <app-id>), VALID, distributed to InternalTesters group. You're in the tester list — check TestFlight, you should see the build and get an invite email.

This lets the user immediately verify from his phone whether the invite arrived. If he has to ask "is it on my phone?", you failed step 4.

---

## Subsequent builds (second, third, ... Nth)

For any build after the first one to an existing app:

1. Step 2 Info.plist hygiene is already baked in — nothing to do.
2. Run `ship` (or `ship beta_myapp` if the lane name isn't `beta`).
3. Do step 4a (verify VALID).
4. Do step 4e-bis (`auto-notify --app-id <id>`) and step 4e-ter (`ensure-invited --app-id <id>`) — both reset on every upload. The canonical Fastfile beta lane runs them automatically; only run manually if you're shipping ad-hoc.
5. Do step 4f (list-testers + group-builds) as the final sanity check. `group-builds` should now show the new build, and `individualTesters` on the new build should show every tester at `state=INVITED`.

Steps 4c and 4d are first-build-only. If you're about to run them for a second build, stop and look up the existing group id first (`list-groups`).

---

## Gotcha reference

| Symptom | Cause | Fix |
|---|---|---|
| `POST /apps 403 FORBIDDEN_ERROR` | Apple forbids app creation via API keys | Have user create in ASC web UI (step 1c) |
| `Provisioning profile "iOS Team Provisioning Profile: *" doesn't include the <X> capability` | Cached wildcard profile lacks new capability | `rm ~/Library/MobileDevice/Provisioning\ Profiles/*.mobileprovision` + `-allowProvisioningUpdates` |
| `exportArchive No profiles for '<bundle-id>' were found` | No distribution profile exists yet | Add `export_options: { signingStyle: "automatic" }` to `build_app` |
| `Missing required icon file … 120x120` | `.xcassets` not in Tuist `resources:` | Add `resources: ["Target/Assets.xcassets"]` |
| `Missing Info.plist value … CFBundleIconName` | Asset-catalog-only icons need this key for iOS 11+ | Add `"CFBundleIconName": "AppIcon"` to infoPlist |
| `Invalid entitlement for core nfc framework … NDEF is disallowed` | iOS 18.2+ SDK deprecated NDEF in readersession.formats | Remove `<string>NDEF</string>` — `TAG` covers it |
| `Build is not in an externally assignable state` | Missing export compliance declaration | Bake `ITSAppUsesNonExemptEncryption: false` into Info.plist, or PATCH build record |
| Tester add returns `409 STATE_ERROR` | Tried to reuse a tester from another app | Create a new tester record scoped to this app |
| Build uploaded successfully, tester never sees it on phone | Group was created without `isInternalGroup: true` so it's external | Delete the group, recreate with both `isInternalGroup: true` and `hasAccessToAllBuilds: true` in the POST attributes |
| Build VALID, group internal, tester attached, but tester gets no TestFlight push (build only appears on manual pull-to-refresh) | `buildBetaDetail.autoNotifyEnabled` defaulted to false on upload | Run `auto-notify --app-id <id>` to PATCH it true. Bake the call into the Fastfile beta lane so future uploads always notify (see `apple-release/templates/Fastfile-ios.tmpl`). |
| All checks pass (group internal, hasAccessToAllBuilds true, tester attached, autoNotify enabled), `betaTester.state` stays `null`, TestFlight still delivers nothing | `hasAccessToAllBuilds` does NOT actually trigger per-tester invites — Apple's docs disagree with the API | Run `ensure-invited --app-id <id>` to POST testers to `/builds/{id}/relationships/individualTesters`. Idempotent (409 STATE_ERROR is fine). Chain after `auto-notify` in the Fastfile beta lane. |
| Group's `isInternalGroup` is `false` despite intent | You forgot to pass `isInternalGroup: true` at creation time | Delete, recreate with the attribute set on POST (it's read-only on PATCH but writable on POST — not what Apple's docs imply) |
| `POST /builds/{id}/relationships/betaGroups` returns `422 "Cannot add internal group to a build"` | You tried to explicitly distribute to an internal group | Don't. Internal groups with `hasAccessToAllBuilds: true` auto-receive all VALID builds. |
| **Upload succeeds ("Successfully uploaded the new binary") but the build NEVER appears** — no record in `build-status` / `preReleaseVersions.builds` after 15+ min, not even `PROCESSING` | Apple **rejected it during post-upload processing**. The reason is emailed to the ASC account holder; there is **no ASC API** for it (a rejected build creates no build record). | **Check the account email** for an "App Store Connect / We noticed one or more issues" message → it names the ITMS-90xxx error. Fix, bump the build number, re-upload. Kill the `upload_to_testflight` waiter — it will hang for hours on a build that will never appear. |
| `ITMS-90683: Missing purpose string in Info.plist` (emailed after upload) | The binary (often a dependency or a framework you link, e.g. Speech/SiriKit) references an API that needs a privacy purpose string, even if you don't call it directly | Add the named `NS*UsageDescription` key to the app target's Info.plist. **Speech recognition needs BOTH `NSSpeechRecognitionUsageDescription` and `NSMicrophoneUsageDescription`** — add both together or you'll get a second rejection on the mic key. Grep the code for the API (`SFSpeechRecognizer`, etc.) to write an honest string. |

## Resources in this skill

- `scripts/asc.py` — ASC API helper with the user's credentials pre-wired. Reuse this instead of re-inlining JWT + httpx boilerplate into each session.
- `references/api-endpoints.md` — the raw curl-equivalent request shapes for each ASC endpoint used here, for when you need to go beyond what `asc.py` exposes.
