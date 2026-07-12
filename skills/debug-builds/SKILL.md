---
name: debug-builds
description: Use when setting up Debug/Release build separation for Apple apps, creating debug app icons, building to a physical device over the network, or configuring Tuist project settings for debug vs release. Also use when a debug build crashes on launch (likely entitlements or SwiftData schema mismatch).
---

# Debug Build Conventions

## Overview

Debug and Release builds coexist on device. They are distinguished by **icon**, not display name. Debug builds use a `.debug` bundle ID suffix and a visually distinct app icon with a "DEBUG" overlay.

## Build Separation Checklist

### Bundle ID
- Debug: `com.example.AppName.debug`
- Release: `com.example.AppName`
- Watch companion: update `WKCompanionAppBundleIdentifier` to match

### App Icon (NOT display name)
- **Display name is identical** for Debug and Release — do NOT append "Dev" or any suffix
- Create `AppIcon-Debug.appiconset` in the asset catalog with visual overlay:
  - Red corner triangle (top-right, ~30% of icon width)
  - Colorful "DEBUG" text banner at bottom on semi-transparent dark strip
- Set per-configuration in Tuist `Project.swift`:
  ```swift
  .debug(name: "Debug", settings: [
      "ASSETCATALOG_COMPILER_APPICON_NAME": "AppIcon-Debug",
      // ...
  ]),
  ```

### Generating the Debug Icon
```python
from PIL import Image, ImageDraw, ImageFont

img = Image.open("AppIcon.png").convert("RGBA")
overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
draw = ImageDraw.Draw(overlay)
w, h = img.size

# Red corner triangle — top-right
corner = int(w * 0.30)
draw.polygon([(w - corner, 0), (w, 0), (w, corner)], fill=(234, 67, 53, 240))

# Colorful "DEBUG" banner at bottom
debug_colors = [
    (220, 20, 60),   # D - crimson
    (0, 150, 50),    # E - green
    (30, 30, 140),   # B - navy
    (255, 165, 0),   # U - orange
    (0, 160, 160),   # G - teal
]
font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", int(w * 0.12))

# Dark banner
banner_h = int(h * 0.20)
draw.rectangle([(0, h - banner_h), (w, h)], fill=(0, 0, 0, 170))

# Draw each letter in a different color
text = "DEBUG"
char_widths = [draw.textbbox((0, 0), ch, font=font)[2] - draw.textbbox((0, 0), ch, font=font)[0] for ch in text]
spacing = int(w * 0.02)
total_w = sum(char_widths) + spacing * (len(text) - 1)
x = (w - total_w) // 2
y = h - banner_h + (banner_h - int(w * 0.12)) // 2 - int(w * 0.01)
for i, ch in enumerate(text):
    draw.text((x, y), ch, font=font, fill=(*debug_colors[i], 255))
    x += char_widths[i] + spacing

Image.alpha_composite(img, overlay).save("AppIcon-Debug.png")
```

Write `Contents.json` alongside it:
```json
{
  "images": [{"filename": "AppIcon-Debug.png", "idiom": "universal", "platform": "ios", "size": "1024x1024"}],
  "info": {"author": "xcode", "version": 1}
}
```

### Display Name in Tuist
Tuist's `.extendingDefault(with:)` generates an explicit Info.plist, so `INFOPLIST_KEY_*` build settings are **silently ignored**. To use a build-setting-driven value, reference it in the infoPlist dict:

```swift
infoPlist: .extendingDefault(with: [
    "CFBundleDisplayName": "$(INFOPLIST_KEY_CFBundleDisplayName)",
    // ...
]),
```

Since Debug and Release use the same display name, just hardcode it.

### Entitlements
- Use separate `AppNameDebug.entitlements` for Debug
- Only include capabilities the debug build actually needs
- If a capability requires specific provisioning (CloudKit container IDs, push notification environments), verify it works with your debug provisioning profile

### SwiftData Store
- Debug: `ModelConfiguration("debug", isStoredInMemoryOnly: false)`
- Release: `ModelConfiguration(isStoredInMemoryOnly: false, groupContainer: .automatic)`
- This isolates data between Debug and Release installs

## Building to Physical Device

<iphone-name> is accessible over the network via Tailscale from anywhere.

### Build + Install Flow
```bash
# 1. Generate project (ALWAYS --no-open)
tuist generate --no-open

# 2. Build for device
xcodebuild -workspace App.xcworkspace -scheme App \
  -destination 'platform=iOS,name=<iphone-name>' build

# 3. Install on device
xcrun devicectl device install app \
  --device 5E90F31F-28DF-5983-B145-6F425B8A46BF \
  "/path/to/DerivedData/.../Debug-iphoneos/App.app"
```

### Always Test on Simulator First
```bash
# Build for sim
xcodebuild -workspace App.xcworkspace -scheme App \
  -destination 'platform=iOS Simulator,id=F2CA4CF3-384E-49D8-BB89-37C55C592192' build

# Install and launch
xcrun simctl install F2CA4CF3-... .../Debug-iphonesimulator/App.app
xcrun simctl launch F2CA4CF3-... com.example.AppName.debug
```

Never deploy to device without first confirming no crash on simulator.

### Device Troubleshooting
- **"no DDI" / developer disk error**: `xcrun devicectl manage pair --device <UUID>`
- **"device not found"**: Use `<iphone-name>` (xcodebuild name), not Tailscale name (`enterprise`)
- **Crash after switching branches**: Uninstall app first (`xcrun devicectl device uninstall app --device <UUID> <bundleID>`) — leftover SwiftData store from another branch causes schema mismatch

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| "Dev" in display name | Use icon overlay instead — display names are fragile with Tuist |
| `tuist generate` without `--no-open` | Always `--no-open` — Xcode opening is forbidden |
| Deploy to device without sim test | Sim test first — device crashes are harder to diagnose |
| Install over old branch's data | Uninstall first when switching branches |
| `INFOPLIST_KEY_*` with Tuist | Use plist dict reference `"$(BUILD_SETTING)"` instead |
