---
name: apple-platform-dev
description: Use this skill when working with Swift architecture, Metal, Core Data, or iOS/macOS platform development. Provides MVVM+Manager patterns, concurrency patterns, and platform-specific guidance. For SwiftUI code quality rules (15-line body, view structure), use the swift-quality skill instead.
---

# Apple Platform Dev

## Overview

This skill provides architectural and platform-specific guidance for Swift development across iOS and macOS. For code quality rules and SwiftUI view patterns, see the **swift-quality** skill in swiftskim.

## Core Philosophy

When working with Swift, prioritize:

- **Type Safety** - Leverage Swift's type system to prevent errors at compile time
- **Extension-Based Design** - Add functionality through extensions
- **Protocol Orientation** - Depend on abstractions, not concrete types
- **YAGNI Enforcement** - Only implement what's explicitly requested

## Architecture: MVVM + Manager

### Pattern Overview

```
View ←→ ViewModel ←→ Manager(s) ←→ Services/APIs
```

- **View**: SwiftUI view, minimal logic, observes ViewModel
- **ViewModel**: `@Observable` or `ObservableObject`, owns business logic for one screen
- **Manager**: Shared state/logic across screens (e.g., `AuthManager`, `DataManager`)
- **Service**: Stateless utilities (networking, persistence)

### Key Principles

- ViewModels don't talk to each other directly
- Managers are injected via environment or init
- Services are stateless and can be static or injected

See `references/architecture.md` for detailed patterns and examples.

## Concurrency Patterns

### MainActor Isolation

- Use `@MainActor` on manager classes that update UI state
- Use `@MainActor` on functions that must run on main thread
- Leverage async/await for non-blocking operations

```swift
@MainActor
final class AuthManager: ObservableObject {
    @Published var isAuthenticated = false

    func login() async throws {
        let result = try await authService.authenticate()
        isAuthenticated = result.success  // Safe - on MainActor
    }
}
```

### Async/Await

- Prefer structured concurrency with `async let` for parallel work
- Use `Task` for fire-and-forget async operations from sync context
- Use `TaskGroup` for dynamic parallel operations

See `references/swift-language.md` for detailed concurrency patterns.

## Platform-Specific Guidance

### Metal Integration

- Use for GPU-accelerated image processing
- Compute shaders for parallel data processing
- Render pipelines for custom graphics

### Core Data

- Use `@FetchRequest` for SwiftUI integration
- Prefer `NSPersistentContainer` setup
- Consider CloudKit sync for cross-device data

### iOS vs macOS

- Use `#if os(iOS)` / `#if os(macOS)` for platform-specific code
- Consider minimum deployment targets (iOS 15+, macOS 12+)
- Use `.focusable()` and keyboard navigation for macOS

See `references/platform-specifics.md` for detailed integration patterns.

## Common Error Patterns

### ClosedRange Crashes

```swift
// Crashes if lowerBound > upperBound
let range = min...max  // ❌ Dangerous

// Safe approach
let range = min <= max ? min...max : max...min  // ✅
```

### AppStorage Validation

```swift
@AppStorage("volume")
private var volume = 50  // Always validate on use

var safeVolume: Int {
    min(max(volume, 0), 100)  // Clamp to valid range
}
```

See `references/common-errors.md` for comprehensive error patterns and solutions.

## Tuist Workflow

**Never use `tuist init`** — it requires interactive terminal input and fails under Mosh (Noora's `isatty()` check). Write `Project.swift` directly instead. `git init` the repo first — Tuist requires `.git` to find the root.

```bash
git init
tuist generate --no-open   # generates .xcodeproj (gitignore it)
tuist build <TargetName>
```

**Starter `Project.swift`** (replace `AppName`, bundle ID, team ID):

```swift
// swiftformat:disable acronyms
import ProjectDescription

let project = Project(
    name: "AppName",
    settings: .settings(base: [
        "DEVELOPMENT_TEAM": "<TEAM_ID>",
        "SWIFT_VERSION": "6.0",
        "SWIFT_STRICT_CONCURRENCY": "complete",
        "CODE_SIGN_STYLE": "Automatic",
        "CODE_SIGN_IDENTITY": "Apple Development",
    ]),
    targets: [
        .target(
            name: "AppName",
            destinations: .iOS,
            product: .app,
            bundleId: "com.example.app-name",
            deploymentTargets: .iOS("17.0"),
            infoPlist: .extendingDefault(with: [
                "CFBundleShortVersionString": "$(MARKETING_VERSION)",
                "CFBundleVersion": "$(CURRENT_PROJECT_VERSION)",
                "ITSAppUsesNonExemptEncryption": false,
                "UIApplicationSceneManifest": ["UIApplicationSupportsMultipleScenes": false],
                "UILaunchScreen": [:],
            ]),
            sources: "Sources/AppName/**/*.swift",
            resources: "Resources/**",
            settings: .settings(
                base: [
                    "ASSETCATALOG_COMPILER_APPICON_NAME": "AppIcon",
                    "ASSETCATALOG_COMPILER_GLOBAL_ACCENT_COLOR_NAME": "AccentColor",
                    "MARKETING_VERSION": "1.0.0",
                    "CURRENT_PROJECT_VERSION": "1",
                ],
                configurations: [
                    .debug(name: "Debug", settings: [
                        "PRODUCT_BUNDLE_IDENTIFIER": "com.example.app-name.debug",
                        "SWIFT_ACTIVE_COMPILATION_CONDITIONS": "DEBUG",
                    ]),
                    .release(name: "Release", settings: [
                        "PRODUCT_BUNDLE_IDENTIFIER": "com.example.app-name",
                    ]),
                ]
            )
        ),
        .target(
            name: "AppNameTests",
            destinations: .iOS,
            product: .unitTests,
            bundleId: "com.example.app-name-tests",
            deploymentTargets: .iOS("17.0"),
            sources: "Tests/AppNameTests/**/*.swift",
            dependencies: [.target(name: "AppName")]
        ),
    ],
    schemes: [
        .scheme(
            name: "AppName",
            shared: true,
            buildAction: .buildAction(targets: ["AppName"]),
            testAction: .targets(["AppNameTests"]),
            runAction: .runAction(configuration: "Debug", executable: "AppName")
        ),
    ]
)
```

Minimal `Resources/Assets.xcassets/Contents.json`: `{"info":{"author":"xcode","version":1}}`

**`.gitignore` for Tuist projects:**
```
*.xcodeproj
*.xcworkspace
.DS_Store
.build/
DerivedData/
.tuist-build/
vendor/
.bundle/
fastlane/report.xml
fastlane/screenshots/
fastlane/test_output/
```

## Fastlane & TestFlight

### Setup (one-time per new app)

**1. Ruby setup.** System Ruby 2.6 is read-only. Use mise-managed Ruby — it activates automatically in an interactive terminal, but Claude Code's headless shell needs `mise exec --` as a prefix:
```bash
# One-time install (headless OK):
bundle config set --local path vendor/bundle && bundle install

# From an interactive terminal:
bundle exec fastlane beta

# From Claude Code / headless:
mise exec -- bundle exec fastlane beta
```
Add `.ruby-version` containing `3.3.11` to the repo root. That's all — mise picks it up.

**2. App icon required.** Apple rejects uploads with no icon. Must have a real PNG at `Resources/Assets.xcassets/AppIcon.appiconset/AppIcon.png` (1024×1024) with `filename` set in `Contents.json`. A solid-color placeholder is fine for TestFlight:
```python
# Generate placeholder icon:
python3 -c "
import struct, zlib
def png(w,h,r,g,b):
    def chunk(t,d): c=zlib.crc32(t+d)&0xffffffff; return struct.pack('>I',len(d))+t+d+struct.pack('>I',c)
    raw=b''.join(b'\x00'+bytes([r,g,b]*w) for _ in range(h))
    ihdr=struct.pack('>IIBBBBB',w,h,8,2,0,0,0)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',ihdr)+chunk(b'IDAT',zlib.compress(raw,9))+chunk(b'IEND',b'')
open('Resources/Assets.xcassets/AppIcon.appiconset/AppIcon.png','wb').write(png(1024,1024,30,120,200))
"
```
Then in `Contents.json`, add `"filename": "AppIcon.png"` to the image entry.

**3. Create the app record first.** The ASC API cannot create apps (returns 403). Before the first upload, go to appstoreconnect.apple.com → My Apps → `+` → New App and create the record. This is a one-time web step; all subsequent builds are fully headless. Do NOT try `fastlane produce` headlessly — it requires an Apple ID login, not just an API key.

**4. Code signing.** Automatic signing (`CODE_SIGN_STYLE = "Automatic"`) with `-allowProvisioningUpdates DEVELOPMENT_TEAM=<TEAM_ID>` in `xcargs` handles cert and profile management. Do NOT set `CODE_SIGN_IDENTITY` at the project base level — only Xcode should pick that.

The login keychain locks when no GUI session is active. Unlock it at the start of the beta lane so `-allowProvisioningUpdates` can write new cert keys headlessly:
```ruby
sh("security unlock-keychain -p \"$(pass show <login-password>)\" ~/Library/Keychains/login.keychain-db")
```

If a cert has a missing private key, revoke it via ASC API (`DELETE /v1/certificates/<id>`) and clear stale provisioning profiles (`rm ~/Library/Developer/Xcode/UserData/Provisioning\ Profiles/*.mobileprovision`). With the keychain unlocked, `-allowProvisioningUpdates` will create a fresh cert and store the key on the next build. If the same cert is already on ASC with no key, `xcodebuild` will NOT auto-revoke it — you must revoke via API first.

**5. Adding testers.** Two flows:

**Account holder / ASC team members → internal group.** Create the group, add the build, then explicitly add each tester. The account holder is NOT automatically in the group — must be added via their app-scoped `betaTester` ID. The trick: you can't add a betaTester record from another app. First, create any betaTester record for them on this app (e.g. via the external-group flow), then use that ID to add to the internal group. Delete the external group after.
```bash
JWT=<generate as usual>
APP_ID=<from ASC>
BUILD_ID=<from: curl -s -H "Authorization: Bearer $JWT" "https://api.appstoreconnect.apple.com/v1/builds?filter[app]=$APP_ID&limit=1" | jq -r '.data[0].id'>

# 1. Create internal group and add build
GROUP=$(curl -s -X POST -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"data":{"type":"betaGroups","attributes":{"name":"Internal Testers","isInternalGroup":true},"relationships":{"app":{"data":{"type":"apps","id":"'$APP_ID'"}}}}}' \
  https://api.appstoreconnect.apple.com/v1/betaGroups | jq -r '.data.id')

curl -s -X POST -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"data":[{"type":"builds","id":"'$BUILD_ID'"}]}' \
  "https://api.appstoreconnect.apple.com/v1/betaGroups/$GROUP/relationships/builds"

# 2. Create a betaTester record for this app (bootstraps the app-scoped ID)
TESTER_ID=$(curl -s -X POST -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"data":{"type":"betaTesters","attributes":{"email":"<tester-email>","firstName":"<first>","lastName":"<last>"},"relationships":{"betaGroups":{"data":[{"type":"betaGroups","id":"'$GROUP'"}]}}}}' \
  https://api.appstoreconnect.apple.com/v1/betaTesters | jq -r '.data.id')
echo "betaTester ID: $TESTER_ID"

# 3. Verify
curl -s -H "Authorization: Bearer $JWT" \
  "https://api.appstoreconnect.apple.com/v1/betaGroups/$GROUP/betaTesters" \
  | jq '.data[] | {id:.id, email:.attributes.email}'
```

**External testers → external group + explicit invite.** Requires Beta App Review before distribution. Create a fresh `betaTester` record per app (IDs are app-scoped, don't reuse across apps).
```bash
EXT_GROUP=$(curl -s -X POST -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"data":{"type":"betaGroups","attributes":{"name":"External Testers","isInternalGroup":false,"publicLinkEnabled":false},"relationships":{"app":{"data":{"type":"apps","id":"'$APP_ID'"}}}}}' \
  https://api.appstoreconnect.apple.com/v1/betaGroups | jq -r '.data.id')

curl -s -X POST -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"data":[{"type":"builds","id":"'$BUILD_ID'"}]}' \
  "https://api.appstoreconnect.apple.com/v1/betaGroups/$EXT_GROUP/relationships/builds"

curl -s -X POST -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"data":{"type":"betaTesters","attributes":{"email":"<tester-email>","firstName":"<first>","lastName":"<last>"},"relationships":{"betaGroups":{"data":[{"type":"betaGroups","id":"'$EXT_GROUP'"}]}}}}' \
  https://api.appstoreconnect.apple.com/v1/betaTesters | jq '{id:.data.id,email:.data.attributes.email,error:.errors}'
```

### Fastfile pattern

```ruby
default_platform(:ios)
ASC_KEY_ID    = "<ASC_KEY_ID>"
ASC_ISSUER_ID = "<ASC_ISSUER_ID>"
ASC_KEY_PATH  = File.expand_path("~/.appstoreconnect/private_keys/AuthKey_<ASC_KEY_ID>.p8")

platform :ios do
  lane :beta do
    sh("cd .. && tuist generate --no-open")
    api_key = app_store_connect_api_key(
      key_id: ASC_KEY_ID, issuer_id: ASC_ISSUER_ID, key_filepath: ASC_KEY_PATH,
      duration: 1200, in_house: false,
    )
    build_app(
      workspace: "AppName.xcworkspace",
      scheme: "AppName",
      configuration: "Release",
      export_method: "app-store",
      clean: true,
      output_directory: "build/fastlane",
      output_name: "AppName.ipa",
      include_bitcode: false,
      include_symbols: true,
      xcargs: "-allowProvisioningUpdates DEVELOPMENT_TEAM=<TEAM_ID>",
      export_options: { method: "app-store", signingStyle: "automatic", teamID: "<TEAM_ID>" },
    )
    upload_to_testflight(
      api_key: api_key,
      ipa: "build/fastlane/AppName.ipa",
      skip_waiting_for_build_processing: false,
      skip_submission: true,
      distribute_external: false,
      notify_external_testers: false,
    )
  end
end
```

## When to Use This Skill

Activate this skill when:
- Designing app architecture (MVVM, managers, services)
- Working with async/await and concurrency
- Integrating Metal, Core Data, or platform-specific frameworks
- Discussing Swift architecture patterns
- Debugging common Swift/iOS/macOS errors

**Note**: For SwiftUI code quality (15-line body rule, view structure order, refactoring strategies) and Swift Testing standards, use the **swift-quality** skill instead.

## Resources

### references/

Detailed documentation for in-depth guidance:

- **`architecture.md`** - MVVM+Manager pattern, protocol-oriented design, package modularization
- **`swift-language.md`** - Optionals, concurrency, MainActor isolation, async/await
- **`common-errors.md`** - Error patterns and solutions
- **`platform-specifics.md`** - Metal integration, Core Data usage, iOS/macOS targeting

**Note**: Testing standards (Swift Testing patterns, XCTest migration) have moved to the **swift-quality** skill in swiftskim.

Load these references when detailed information is needed for specific domains.
