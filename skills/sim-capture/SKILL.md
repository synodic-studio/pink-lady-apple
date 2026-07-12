---
name: sim-capture
description: Use this skill whenever you need screenshots or video recordings of an iOS/iPadOS app. Always use the real iOS Simulator — never HTML mockups, never Playwright-rendered HTML. Covers booting, building, installing, seeding data, XCUITest automation via accessibilityIdentifier, capturing screenshots, recording video, and converting output.
---

# iOS Simulator Capture

**Rule zero: never use HTML mockups or Playwright to fake app screenshots or video. Always use the real app running in the real iOS Simulator.**

## Quick reference

```bash
SIM=<uuid>
BUNDLE=com.example.myapp.debug

# Boot
xcrun simctl boot $SIM

# Build for sim (via Tuist)
cd <project>
tuist generate --no-open
xcodebuild build-for-testing \
  -workspace App.xcworkspace -scheme App \
  -destination "id=$SIM" \
  -only-testing AppUITests \
  -derivedDataPath build/uitest

# Screenshot
xcrun simctl io $SIM screenshot out.png          # NOT simctl screenshot — that doesn't exist

# Video
xcrun simctl io $SIM recordVideo --force out.mp4 &
PID=$!
# ... run UITest ...
kill -SIGINT $PID          # SIGINT (not SIGTERM) triggers clean finalization + moov atom write
sleep 5                    # wait for "Wrote video to:" confirmation
ffmpeg -y -i out.mp4 -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -movflags +faststart final.mp4

# Dark mode
xcrun simctl ui $SIM appearance dark
```

## Finding simulators

```bash
xcrun simctl list devices available | grep -E "iPhone|iPad"
xcrun simctl list runtimes                    # check iOS 26 vs 18 etc.
```

Always prefer the latest available iOS runtime unless the project targets something older. iPhone 17 Pro Max = iOS 26.2 on this machine.

**Current device:** iPhone 17 Pro Max `9F41D449-2A75-4D7D-A339-A83A3364F096` (iOS 26.2)

## Bundle ID

Debug builds have a `.debug` suffix: `com.example.<appname>.debug`  
Check with: `xcrun simctl listapps $SIM 2>/dev/null | grep -A2 BundleIdentifier`

## The correct automation approach: XCUITest + accessibilityIdentifier

**Never use coordinate guessing, CGEventPost, or cliclick for navigation.** The reliable, maintainable approach is:

1. Add `.accessibilityIdentifier("some-id")` to SwiftUI views
2. In XCUITest: `app.buttons["some-id"].tap()`

### Adding accessibility identifiers

```swift
// ContentView.swift — toolbar buttons
Button { showSessions = true } label: { Image(systemName: "line.3.horizontal") }
    .accessibilityIdentifier("sessions-btn")

Button { showSettings = true } label: { Image(systemName: "slider.horizontal.3") }
    .accessibilityIdentifier("settings-btn")

// ChatListView.swift — list rows
Button { ... } label: { ... }
    .accessibilityIdentifier("session-row")
// Find in UITest: app.buttons.matching(identifier: "session-row").firstMatch
```

### UITest target (Project.swift with Tuist)

```swift
.target(
    name: "AppUITests",
    destinations: .iOS,
    product: .uiTests,
    bundleId: "com.example.myapp.uitests",
    deploymentTargets: .iOS("17.0"),
    sources: "Tests/AppUITests/**/*.swift",
    dependencies: [.target(name: "App")]
),
```

Add to scheme's test action:
```swift
testAction: .targets(["AppTests", "AppUITests"]),
```

### Making non-Button views findable in XCUITest

A `ZStack` or other layout container with a `DragGesture` (not a `Button`) appears in the accessibility tree as individual children — none carry the `.accessibilityIdentifier` you set on the outer container. XCUITest's `app.buttons["mic-btn"]` finds nothing.

Fix: add these three modifiers **before** `.accessibilityIdentifier`:
```swift
.accessibilityElement(children: .ignore)   // collapse ZStack into one node
.accessibilityAddTraits(.isButton)         // appear under app.buttons[…]
.accessibilityLabel("Hold to talk")        // VoiceOver label
.accessibilityIdentifier("mic-btn")
```

Without `.accessibilityElement(children: .ignore)`, the identifier is never assigned to a queryable node. Without `.accessibilityAddTraits(.isButton)`, the node is an `otherElement`, not a `button`.

### Trimming the home-screen overhead from recorded video

`xcodebuild test-without-building` takes ~5–8 seconds to connect to the simulator, plus the app itself launches from the home screen via UITest's `app.launch()`. This adds 13–16 seconds of home screen and loading animation at the start of every recording.

Fix: trim with `ffmpeg -ss <offset> -i raw.mp4 …` at conversion time. Inspect frames at 2fps first (`ffmpeg -vf fps=2 frames/frame_%04d.png`) to find the exact second the app first shows content, then trim there. Adjust narration timestamps to be relative to the trimmed video start.

### Narration overlay (Google TTS + ffmpeg adelay)

```bash
uv run --with google-auth --with httpx --with requests python3 narrate.py \
    --video raw.mp4 --out final.mp4
```

- Voice: `en-US-Chirp3-HD-Schedar`, rate 0.92
- Credentials: `pass show <tts-service-account>` → service account JSON → Bearer token
- Timing: `(start_ms, text)` tuples, relative to the **trimmed** video start
- ffmpeg `adelay={ms}|{ms}` per clip, `amix=inputs=N:duration=longest` to combine, then mux into video with `-c:v copy -c:a aac -shortest`
- `requests` package is required alongside `google-auth` (google-auth's transport layer imports it)

### Mocking mic input with a launch argument

For apps with hold-to-record mic buttons, real audio recording in a headless simulator is unreliable (no mic hardware). Add a `--uitesting-mock-turn` launch argument instead:

**App changes (TalkViewModel.swift):**
```swift
private(set) var isMockRecording = false
var isCapturing: Bool { recorder.isRecording || isMockRecording }

func startRecording() {
    if CommandLine.arguments.contains("--uitesting-mock-turn") {
        isMockRecording = true          // triggers red-button animation
    } else {
        try? AudioSessionManager.configure()
        try? recorder.start()
    }
}

func mockTurn(chat: Chat) {
    isMockRecording = false
    isProcessing = true                 // shows "Thinking…" bubble
    Task {
        try? await Task.sleep(nanoseconds: 1_500_000_000)
        _appendTurn(TurnItem(transcript: "...", reply: "..."), chat: chat)
        isProcessing = false
    }
}
```

**App changes (TalkButtonView.swift):**
- Replace `vm.recorder.isRecording` with `vm.isCapturing` everywhere in `micCircle`
- Use `vm.isCapturing` in `.animation(value:)` and `.onChanged` guard
- In `.onEnded`, branch: `isMockCapture ? vm.mockTurn(chat:) : Task { await vm.stopAndSend(...) }`
- Add `.accessibilityIdentifier("mic-btn")` to `holdToTalkButton`
- Bypass permission check when `isMockCapture`: `if permission == .granted || isMockCapture { holdToTalkButton }`

**UITest (CaptureTests.swift):**
```swift
app.launchArguments = ["--uitesting-mock-turn"]
app.launch()

let micBtn = app.buttons["mic-btn"]
if micBtn.waitForExistence(timeout: 5) {
    micBtn.press(forDuration: 2.5)  // DragGesture: onChanged→red, onEnded→mockTurn
    sleep(4)                        // 1.5s thinking + 1s response settle
}
screenshot("sim-talk")              // captures transcript + reply bubbles
```

Result: video shows mic button turning red → waveform icon → "Thinking…" bubble → response — without any real audio hardware or server.

### CaptureTests.swift pattern

```swift
import XCTest

final class CaptureTests: XCTestCase {
    var app: XCUIApplication!  // NOT stored property init — Swift 6 @MainActor constraint

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launch()
    }

    // Writes PNG to /tmp/pv-captures/ — UITest runner is a host (macOS) process,
    // FileManager writes to the host filesystem
    private func screenshot(_ name: String) {
        let dir = URL(fileURLWithPath: "/tmp/pv-captures")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let shot = XCUIScreen.main.screenshot()
        try? shot.pngRepresentation.write(to: dir.appendingPathComponent("\(name).png"))
    }

    func testCaptureScreenshots() throws {
        _ = app.wait(for: .runningForeground, timeout: 10)
        sleep(2)

        // Open sessions list
        let sessionsBtn = app.buttons["sessions-btn"]
        XCTAssert(sessionsBtn.waitForExistence(timeout: 5))
        sessionsBtn.tap()
        sleep(1)
        screenshot("sim-sessions")

        // Tap first session
        let firstRow = app.buttons.matching(identifier: "session-row").firstMatch
        if firstRow.waitForExistence(timeout: 5) {
            firstRow.tap()
            sleep(2)
        }
        screenshot("sim-talk")

        // Open settings
        let settingsBtn = app.buttons["settings-btn"]
        XCTAssert(settingsBtn.waitForExistence(timeout: 5))
        settingsBtn.tap()
        sleep(1)
        screenshot("sim-settings")

        app.buttons["Done"].tap()
        sleep(1)
    }
}
```

### Swift 6 gotchas

- Never `let app = XCUIApplication()` as a stored property — `init()` is `@MainActor` and the initializer runs in a nonisolated context → compiler error with `SWIFT_STRICT_CONCURRENCY = complete`
- Use `var app: XCUIApplication!` and initialize in `setUpWithError()`
- `Process` is NOT available in iOS UITest targets (even though the runner is macOS). Use `XCUIScreen.main.screenshot().pngRepresentation` + `FileManager` instead
- `XCUIScreen.main`, `.screenshot()`, `.pngRepresentation`, `app.buttons`, `.tap()` etc. generate Swift 6 warnings in nonisolated context, but they're warnings not errors — the build succeeds and the test runs correctly

### Running the full capture pipeline

```bash
SIM="9F41D449-2A75-4D7D-A339-A83A3364F096"
BUNDLE="com.example.MyApp.debug"

# 1. Dark mode + inject data + relaunch
xcrun simctl ui "$SIM" appearance dark
python3 inject_turns.py          # or whatever data seeding script
xcrun simctl terminate "$SIM" "$BUNDLE" 2>/dev/null || true
sleep 1
xcrun simctl launch "$SIM" "$BUNDLE"
sleep 5

# 2. Build UITest target
cd /path/to/project
tuist generate --no-open
xcodebuild build-for-testing \
  -workspace App.xcworkspace -scheme App \
  -destination "id=$SIM" \
  -only-testing AppUITests \
  -derivedDataPath build/uitest

# 3. Start recording
xcrun simctl io "$SIM" recordVideo --force /tmp/raw.mp4 &
RECPID=$!
sleep 1

# 4. Run UITest
xcodebuild test-without-building \
  -workspace App.xcworkspace -scheme App \
  -destination "id=$SIM" \
  -only-testing "AppUITests/CaptureTests/testCaptureScreenshots" \
  -derivedDataPath build/uitest \
  2>&1 | grep -E "Test Case|Executed|passed|failed"

# 5. Finalize recording (SIGINT writes moov atom)
kill -SIGINT "$RECPID"
sleep 5     # wait for "Wrote video to:" message

# 6. Convert video
ffmpeg -y -i /tmp/raw.mp4 \
  -c:v libx264 -crf 20 -preset slow -pix_fmt yuv420p -movflags +faststart \
  -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" \
  /path/to/output.mp4

# 7. Copy screenshots
cp /tmp/pv-captures/sim-*.png /path/to/static/images/
```

## Setting UserDefaults

Simple string values — use `xcrun simctl spawn`:
```bash
xcrun simctl spawn $SIM defaults write $BUNDLE serverURL "http://localhost:8800"
```

Binary/data values (e.g. JSON-encoded `[TurnItem]`) — `defaults write` can't handle these. Write directly to the plist:

```python
import json, plistlib, uuid, subprocess
from pathlib import Path

SIM = "9F41D449-2A75-4D7D-A339-A83A3364F096"
BUNDLE = "com.example.MyApp.debug"

CONTAINER = Path(
    subprocess.check_output(
        ["xcrun", "simctl", "get_app_container", SIM, BUNDLE, "data"]
    ).decode().strip()
)
PLIST = CONTAINER / f"Library/Preferences/{BUNDLE}.plist"

turns = [{"id": str(uuid.uuid4()), "transcript": "...", "reply": "..."}]

data = plistlib.loads(PLIST.read_bytes()) if PLIST.exists() else {}
data["turns.<chatID>"] = json.dumps(turns).encode()
PLIST.write_bytes(plistlib.dumps(data))

# Relaunch app to pick up the new plist
subprocess.run(["xcrun", "simctl", "terminate", SIM, BUNDLE])
```

## After capture: updating your site

Screenshots go to `static/images/<project>/sim-<screen>.png`.  
Video goes to `static/video/<project>-walkthrough.mp4`.  

Wire into Hugo page with shortcodes (check existing pages for the right shortcode names).  
Commit and push both assets and the updated `.md` file in one step.

## What NOT to do

- **Never** generate screenshots from HTML mockups rendered by Playwright or any headless browser
- **Never** use `xcrun simctl screenshot` — the correct subcommand is `xcrun simctl io <device> screenshot`
- **Never** rely on coordinate tapping (cliclick, CGEventPost) for navigation — use `accessibilityIdentifier` + XCUITest
- **Never** use `defaults write` for binary/Data-type UserDefaults keys — it silently fails; use the plist approach above
- **Never** `kill -SIGTERM` (plain `kill`) a `simctl io recordVideo` process — it dies without writing the moov atom and produces an unplayable file. Always use `kill -SIGINT`
