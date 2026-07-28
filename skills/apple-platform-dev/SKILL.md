---
name: apple-platform-dev
description: Use this skill when working with Swift architecture, Metal, Core Data, concurrency, or iOS/macOS framework differences. Provides MVVM+Manager patterns, MainActor/async-await guidance, and common runtime error patterns. For SwiftUI code quality rules (15-line body, view structure) use the swift-quality skill; for Project.swift and project scaffolding use pink-lady-apple:apple-tuist; for Fastlane, signing, and TestFlight use pink-lady-apple:apple-release and pink-lady-apple:testflight-ship.
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

## Project generation, release, and signing live elsewhere

This skill is Swift and framework guidance only. The adjacent concerns each have
their own skill, and they are the authority — do not re-derive them here:

- **`pink-lady-apple:apple-tuist`** — `Project.swift` authoring, `tuist generate`,
  Info.plist and resource gotchas, the `.gitignore` for a Tuist repo.
- **`pink-lady-apple:apple-release`** — Fastlane, mise/Ruby pinning, code signing
  via `fastlane match`, macOS notarization.
- **`pink-lady-apple:testflight-ship`** — ASC API, TestFlight upload, beta groups
  and tester invitation.
- **`pink-lady-apple:debug-builds`** — Debug/Release separation and device installs.

Earlier versions of this file carried its own Fastlane, signing, and tester-setup
sections. They drifted out of sync with those skills — most damagingly by
prescribing automatic code signing, which `apple-release` documents as abandoned
because it fails silently in headless shells. The duplicates are gone; follow the
skills above.

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
- **`apple-config.md`** - the placeholder template for team ID, ASC key/issuer, device names. Fill it in privately; never commit real values here.

**Note**: Testing standards (Swift Testing patterns, XCTest migration) have moved to the **swift-quality** skill in swiftskim.

Load these references when detailed information is needed for specific domains.
