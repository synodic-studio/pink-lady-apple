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

- **apple-platform-dev** — Swift/Metal/Core Data architecture, Tuist conventions, ASC API patterns.
- **apple-release** — Fastlane + mise + bundler, iOS TestFlight, macOS notarize, the `prices`/Ruby-version landmines.
- **testflight-ship** — end-to-end TestFlight upload + internal-tester invitation (the step that keeps getting missed).
- **debug-builds** — Debug/Release separation with distinct bundle IDs and debug icons.
- **sim-capture** — iOS Simulator screenshots and video via XCUITest.

## Configuration

These skills use placeholders (`<TEAM_ID>`, `<ASC_KEY_ID>`, `<ASC_ISSUER_ID>`,
`<iphone-name>`, etc.) instead of hardcoded values. Fill them in with your own,
and keep the filled-in copy in a **private** location — not in a shared toolkit
repo. See `skills/apple-platform-dev/references/apple-config.md` for the template.

## Related

- **swiftskim** — SwiftUI code-quality rules + SwiftSyntax linting (the `swift-quality` skill). Referenced by `apple-platform-dev` for code-quality guidance.
