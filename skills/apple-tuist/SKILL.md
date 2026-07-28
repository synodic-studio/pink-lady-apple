---
name: apple-tuist
description: Use when scaffolding a new Swift/iOS/macOS project, authoring or editing Project.swift, adding a target or scheme, running tuist generate/build, or debugging why an Info.plist key, app icon, or asset catalog is missing from a built app. Covers the Tuist manifest format, per-configuration build settings, the .gitignore for a generated project, and the silent-failure gotchas (INFOPLIST_KEY_* ignored, .xcassets not picked up by the sources glob). Triggers on "new Swift project", "set up Tuist", "add a target", "tuist generate", "Project.swift", "Info.plist key ignored", "missing app icon", "CFBundleIconName". For code signing and release lanes see pink-lady-apple:apple-release.
---

# Tuist Project Manifests

## Why this skill exists

Every Apple project here is Tuist-generated: `Project.swift` is the source of
truth and the `.xcodeproj` is a build artifact. That inverts a few Xcode habits,
and it has two silent-failure modes that cost real debugging time — build
settings that are accepted and ignored, and resources that are silently omitted
from the bundle. Both produce a green build and a broken app.

## Scaffolding a new project

**Never use `tuist init`.** It requires interactive terminal input and fails
under Mosh on Noora's `isatty()` check. Write `Project.swift` directly.

**`git init` first** — Tuist walks up for a `.git` directory to find the project
root. Without it, generation fails or resolves the wrong root.

```bash
git init
tuist generate --no-open   # generates .xcodeproj (gitignore it)
tuist build <TargetName>
```

**`--no-open` is mandatory, always.** `tuist generate` opens Xcode by default,
and opening Xcode on the build host is forbidden — it consumes resources and
blocks the machine. Never use `xcodebuild` directly either; Tuist wraps it.

## Starter `Project.swift`

Replace `AppName`, the bundle ID, and the team ID.

```swift
// swiftformat:disable acronyms
import ProjectDescription

let project = Project(
    name: "AppName",
    settings: .settings(base: [
        "DEVELOPMENT_TEAM": "<TEAM_ID>",
        "SWIFT_VERSION": "6.0",
        "SWIFT_STRICT_CONCURRENCY": "complete",
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
                "CFBundleIconName": "AppIcon",
                "ITSAppUsesNonExemptEncryption": false,
                "UIApplicationSceneManifest": ["UIApplicationSupportsMultipleScenes": false],
                "UILaunchScreen": [:],
            ]),
            sources: "Sources/AppName/**/*.swift",
            resources: ["Resources/**", "Sources/AppName/Assets.xcassets"],
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
                        "ASSETCATALOG_COMPILER_APPICON_NAME": "AppIcon-Debug",
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

**Do not set `CODE_SIGN_STYLE` or `CODE_SIGN_IDENTITY` in the manifest.** Signing
is owned by `fastlane match` at build time — see `pink-lady-apple:apple-release`.
Pinning an identity here fights the release lane and produces confusing
`exportArchive` failures.

Minimal `Resources/Assets.xcassets/Contents.json`:
`{"info":{"author":"xcode","version":1}}`

## The two silent failures

### `INFOPLIST_KEY_*` build settings are accepted and ignored

`.extendingDefault(with:)` makes Tuist generate an **explicit** `Info.plist`
file. Once that file exists, Xcode's `INFOPLIST_KEY_*` build settings — which
only apply when Xcode is synthesizing the plist — do nothing. They don't error.
They're just absent from the built app.

To drive a plist value from a build setting, reference it from the plist dict:

```swift
infoPlist: .extendingDefault(with: [
    "CFBundleDisplayName": "$(INFOPLIST_KEY_CFBundleDisplayName)",
]),
```

For a value that doesn't vary per configuration, skip the indirection and
hardcode it in the dict.

### `.xcassets` is not picked up by the `sources:` glob

Tuist's `sources:` only matches compilable sources. An asset catalog must be
named in `resources:` explicitly. Miss it and the build succeeds, then the
upload fails at validation:

```
Missing required icon file. The bundle does not contain an app icon for
iPhone / iPod Touch of exactly '120x120' pixels
```

Each target needs its **own** `Assets.xcassets` — catalogs can't be shared
across targets.

## Info.plist keys that block a TestFlight upload

Bake these into the manifest so they survive regeneration:

- **`CFBundleIconName: "AppIcon"`** — required for iOS 11+ when icons come from
  an asset catalog. Missing it fails validation with
  `Missing Info.plist value. A value for the Info.plist key 'CFBundleIconName' is missing`.
- **`ITSAppUsesNonExemptEncryption: false`** — declares export compliance at
  build time. Without it every build lands in ASC as "missing compliance" and
  can't be distributed until you PATCH the build record. `false` is correct for
  any app using only OS-provided encryption (HTTPS, Keychain, CryptoKit
  primitives), exempt under BIS 740.17(a)(5)(ii)(A).
- **`CFBundleVersion: "$(CURRENT_PROJECT_VERSION)"`** — the release lane bumps
  the build number by editing this setting, so the plist must reference it
  rather than hardcode a number.

## `.gitignore` for a Tuist repo

The generated project is an artifact — never commit it.

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

If the repo also uses Fastlane, `apple-release` scaffold step 4 adds the
`!.bundle/config` exception on top of this — apply both.

## Per-configuration settings

Anything that must differ between Debug and Release goes in `configurations:`,
not `base:`. The common cases are the bundle ID suffix, the app icon name, and
compilation conditions — all three are in the starter manifest above.

For the full Debug/Release convention (icon overlay generation, entitlements
split, SwiftData store isolation, device installs) see
**`pink-lady-apple:debug-builds`**.

## Related skills

- **`pink-lady-apple:apple-platform-dev`** — Swift architecture, concurrency, Metal, Core Data.
- **`pink-lady-apple:apple-release`** — Fastlane, Ruby pinning, signing via match, notarization.
- **`pink-lady-apple:testflight-ship`** — ASC API, upload, beta groups, testers.
- **`pink-lady-apple:debug-builds`** — Debug/Release separation and physical-device installs.
- **`swift-quality`** (in swiftskim) — SwiftUI code quality rules and linting.
