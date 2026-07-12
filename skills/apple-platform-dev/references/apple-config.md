# Apple Development Configuration

Template for your project's Apple/Swift development configuration. Fill in the placeholder values (`<TEAM_ID>`, `<ASC_KEY_ID>`, `<ASC_ISSUER_ID>`, device names, etc.) with your own, and keep the filled-in copy in a private location — not in a shared toolkit repo.

## Apple Devices

- **iPhone 15 Pro** — named `<iphone-name>`. Available as a network build destination in Xcode (no USB required).
- **Apple Watch** — named `<watch-name>`. Paired with <iphone-name>.

## Tuist for New Swift Projects

**All new Swift/iOS/macOS projects use Tuist** (`tuist init`) instead of creating Xcode projects via GUI. This enables fully CLI-driven project management -- critical for Telegram-based workflows where Xcode GUI is inaccessible.

**Why Tuist:**
- `tuist init` replaces "File > New Project"
- Adding targets, schemes, and dependencies is editing a Swift manifest (`Project.swift`), not clicking through Xcode GUI
- Build settings are code-reviewable, not buried in pbxproj XML
- `tuist generate` produces the .xcodeproj when needed for Xcode debugging/previews

**Key commands:**
- `tuist init --name AppName --platform ios` -- new project
- `tuist generate` -- generate .xcodeproj from manifests
- `tuist build` -- build without opening Xcode
- `tuist test` -- run tests without opening Xcode
- `tuist share` -- generate preview link (org-scoped, no TestFlight delay)

**Rules:**
- Do NOT tell the user to open Xcode GUI to add targets/schemes -- use Tuist manifests
- Xcode is still needed for debugging, SwiftUI previews, and simulator interaction
- TestFlight remains the distribution path for non-developer testers

## App Store Connect API

- Issuer ID: <ASC_ISSUER_ID>
- Key ID: <ASC_KEY_ID>
- Key file: ~/.appstoreconnect/private_keys/AuthKey_<ASC_KEY_ID>.p8
- Team ID: <TEAM_ID>

**JWT Auth (Python):** Use `authlib` for ES256 JWT signing (PyJWT lacks ES256 without extra deps). Pattern:
```python
from authlib.jose import jwt
header = {"alg": "ES256", "kid": KEY_ID, "typ": "JWT"}
payload = {"iss": ISSUER_ID, "exp": int(time.time()) + 15 * 60, "aud": "appstoreconnect-v1"}
token = jwt.encode(header, payload, private_key)
```

**API Resource Hierarchy:**
- `apps` -> `appInfos` -> `appInfoLocalizations` (name, subtitle, privacy URL)
- `apps` -> `appStoreVersions` -> `appStoreVersionLocalizations` (description, keywords, promotional text, support/marketing URLs)
- `apps` -> `appStoreVersions` -> `appStoreVersionLocalizations` -> `appScreenshotSets` -> `appScreenshots`
- Age rating: `apps` -> `ageRatingDeclarations` (PATCH with NONE / INFREQUENT_OR_MILD / FREQUENT_OR_INTENSE)

**Screenshot Upload (3-step process):**
1. **Reserve**: POST to `/appScreenshots` with `fileName`, `fileSize`, and screenshot set relationship. Returns upload operations array.
2. **Upload chunks**: PUT each chunk to the URL in upload operations, with `Content-Type: application/octet-stream` and required headers (`Content-Length`, offset). Most screenshots fit in one chunk.
3. **Commit**: PATCH to `/appScreenshots/{id}` with `uploaded: true` and `sourceFileChecksum` (MD5 hex of entire file).

**Screenshot Display Types** (use for `screenshotDisplayType` when creating screenshot sets):
- `APP_IPHONE_67` — 6.7" (iPhone 17 Pro Max, 16 Pro Max, 15 Pro Max): **1320x2868**
- `APP_IPHONE_65` — 6.5" (iPhone 16 Plus, 15 Plus, 14 Plus): **1284x2778**
- `APP_IPHONE_61` — 6.1" displays
- `APP_IPAD_PRO_3GEN_129` — 12.9" iPad Pro
- `APP_IPAD_PRO_3GEN_11` — 11" iPad Pro

**TestFlight via API:**
1. Upload build: `xcodebuild archive` then `xcodebuild -exportArchive` with `-allowProvisioningUpdates` flag
2. Create beta group: POST to `/betaGroups` with `{"groupType": "INTERNAL", "name": "...", "app": relationship}`
3. Add tester: POST to `/betaTesters` with email and beta group relationship
4. **Explicitly add build to group**: POST to `/betaGroups/{groupId}/relationships/builds` with build ID. This step is required — groups don't automatically get access to builds even with `hasAccessToAllBuilds`.
5. Create beta build localization: POST to `/betaBuildLocalizations` with `whatsNew` text and build relationship
6. As account holder, the user sees TestFlight builds directly in the TestFlight app without needing an email invite

**Common Gotchas:**
- `ageRatingDeclarations` PATCH: Don't include deprecated `seventeenPlus` attribute (causes 409)
- Export archive needs `-allowProvisioningUpdates` for automatic signing
- App icon in Xcode requires `Contents.json` in `.xcassets/AppIcon.appiconset/` AND `INFOPLIST_KEY_CFBundleIconName = AppIcon` in build settings
- `*.json` in `.gitignore` can block asset catalog JSON files — use `git add -f`
- ASC API docs are JavaScript-rendered, so WebFetch can't read them; use web search instead

### App Store Screenshots via Simulator

**Workflow for capturing screenshots programmatically:**
1. Add demo mode support to the app via launch arguments (e.g., `--seed-demo-data`)
2. Add tab/screen navigation launch arguments (e.g., `--show-episodes`, `--show-profile`)
3. Boot simulator, install app, launch with arguments, capture:

```bash
# Boot simulator
xcrun simctl boot "iPhone 17 Pro Max"

# Build and install
xcodebuild -project App.xcodeproj -scheme App -sdk iphonesimulator \
  -destination "id=SIMULATOR_UDID" -derivedDataPath /tmp/build build
xcrun simctl install SIMULATOR_UDID /tmp/build/Build/Products/Debug-iphonesimulator/App.app

# Launch with demo data and specific screen
xcrun simctl launch SIMULATOR_UDID com.example.BundleId --seed-demo-data --show-episodes

# Wait for UI to settle, then capture
sleep 3
xcrun simctl io SIMULATOR_UDID screenshot /path/to/screenshot.png
```

**Key points:**
- `simctl io` supports `screenshot` but NOT touch/tap events — use launch arguments to navigate to screens
- iPhone 17 Pro Max produces 1320x2868 (6.7" display type)
- Older simulators may not support high minimum deployment targets — use the latest device models
- Screenshots upload to ASC via the 3-step process above, associated with an `appScreenshotSet` for the correct display type

## Debug/Release Build Separation

All Apple apps must separate Debug and Release builds so Xcode installs and TestFlight/App Store installs coexist on device. **Use the `debug-builds` skill for full conventions.** Summary:

- **Bundle ID**: Append `.debug` to Debug config (`com.example.AppName.debug` vs `com.example.AppName`)
- **App Icon**: Use `AppIcon-Debug` asset with red corner triangle + colorful "DEBUG" overlay. **Do NOT use a different display name** — the icon is the differentiator
- **SwiftData Store**: Use a named `ModelConfiguration("debug", ...)` in Debug vs default in Release, so data is isolated
- **Entitlements**: Use a separate `AppNameDebug.entitlements` for Debug — only include capabilities the debug build actually needs
- **Watch apps**: Update companion bundle ID (`WKCompanionAppBundleIdentifier`) and watch bundle ID to match the `.debug` parent

This prevents TestFlight installs from overwriting debug builds and vice versa, and keeps their data sandboxes completely independent.

## Encryption Export Compliance

All Apple apps must declare encryption usage via `ITSAppUsesNonExemptEncryption` in Info.plist. For apps that only use standard Apple encryption (HTTPS/TLS via URLSession, ATS, etc.) and no custom cryptographic algorithms, set this to `NO`:

```xml
<key>ITSAppUsesNonExemptEncryption</key>
<false/>
```

This eliminates the manual export compliance prompt in App Store Connect on every submission. If an app implements custom encryption (beyond what Apple frameworks provide), this needs to be `YES` and may require an ERN filing.

## Xcode MCP Server — DISABLED

The `swift-lsp@claude-plugins-official` plugin (which uses `xcrun mcpbridge`) is **disabled**. It launches Xcode GUI, prompts for agent permissions, and conflicts with the CLI-first workflow.

**Do NOT use Xcode MCP tools.** All builds, tests, and project management go through:
- `tuist build` / `tuist test` for Tuist-managed projects
- `xcodebuild` CLI for legacy .xcodeproj projects
- Tuist manifests (`Project.swift`) for adding targets, schemes, dependencies

Xcode GUI is only for the user's manual use (debugging, SwiftUI previews, simulator interaction). Claude should never open or remote-control Xcode.

## Critical Swift Development Workflow

**MANDATORY before returning control after Swift changes:**
1. Run the three smart Swift quality commands:
   - `swiftformat-smart .` - Format code with smart config discovery
   - `swiftlint-smart .` - Lint code with smart config discovery
   - `swiftlintcustom-smart .` - Run custom SwiftSyntax rules
2. Run `xcodebuild -project *.xcodeproj -scheme [SchemeName] -configuration Debug`
3. Fix any build errors - NEVER return control with failing builds

**Swift Quality Commands:**
- All commands support `--help` for detailed usage
- Smart config discovery finds appropriate configs automatically
- Commands work from any directory in any project
- Available globally via shell aliases to native Swift binaries in `<swiftskim-path>/`
