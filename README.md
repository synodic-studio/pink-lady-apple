# pink-lady-apple

Apple platform toolchain for Claude Code — a single-plugin marketplace exposing
**`pink-lady-apple`**: iOS/macOS development patterns, Fastlane/TestFlight release
automation, simulator capture, and debug-build workflows.

## Install

```bash
claude plugins marketplace add synodic-studio/pink-lady-apple
claude plugins install pink-lady-apple@pink-lady-apple
```

## Skills

- **apple-platform-dev** — Swift/Metal/Core Data architecture, MVVM+Manager, concurrency.
- **apple-tuist** — `Project.swift` authoring, `tuist generate`, and the two silent failures (inert `INFOPLIST_KEY_*`, unbundled `.xcassets`).
- **apple-release** — Fastlane + mise + bundler, iOS TestFlight, macOS notarize, the `prices`/Ruby-version landmines.
- **testflight-ship** — end-to-end TestFlight upload + internal-tester invitation (the step that keeps getting missed).
- **debug-builds** — Debug/Release separation with distinct bundle IDs and debug icons.
- **xcode-cloud** — Apple-hosted CI: `ci_scripts` hooks, the ciWorkflows/ciBuildRuns API, and the Tuist-workspace-is-gitignored collision.
- **app-store-listing** — public listing: metadata, screenshots, categories, age rating, the first-version `No data` bug.
- **sim-capture** — iOS Simulator screenshots and video via XCUITest.

## Configuration

These skills use placeholders (`<TEAM_ID>`, `<ASC_KEY_ID>`, `<ASC_ISSUER_ID>`,
`<iphone-name>`, etc.) instead of hardcoded values. Fill them in with your own,
and keep the filled-in copy in a **private** location — not in a shared toolkit
repo. See `skills/apple-platform-dev/references/apple-config.md` for the template.

## Demo

`scripts/demo.sh` is a four-beat walkthrough for a screen share: one encoded
trap quoted verbatim, a live count of how much of the plugin is failure
knowledge, the skill's Ruby-floor claims checked against rubygems in real time,
and the install/inventory/token-cost handoff. It reads only public data and
needs no credentials. `--auto` runs it unattended, `--cleanup` clears the
fetched response, `-h` prints the full header. Settings: `scripts/demo.env.example`.

## Related

- **swiftskim** — SwiftUI code-quality rules + SwiftSyntax linting (the `swift-quality` skill). Referenced by `apple-platform-dev` for code-quality guidance.
