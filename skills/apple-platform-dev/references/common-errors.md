# Common Error Patterns

Common Swift and SwiftUI error patterns with solutions.

## ClosedRange Invalid Bounds

### Problem

Creating a ClosedRange where lower bound exceeds upper bound causes a runtime crash:

```swift
// ❌ Crashes when diameter > width
let diameter = 100
let width = 80
let range = (diameter/2) ... (width - diameter/2) // CRASH: 50...(-10)
```

### Solution

Always validate range bounds before creating ClosedRange:

```swift
// ✅ Safe: Validate before creating range
let diameter = 100
let width = 80
let minValue = diameter / 2
let maxValue = width - diameter / 2

let range: ClosedRange<Int> = if minValue >= maxValue {
    // Return single-value range when invalid
    let center = (minValue + maxValue) / 2
    center...center
} else {
    minValue...maxValue
}
```

### Prevention Pattern

**Create a safe range builder:**

```swift
extension ClosedRange where Bound: Comparable {
    static func safe(_ lowerBound: Bound, _ upperBound: Bound) -> ClosedRange<Bound> {
        if lowerBound > upperBound {
            return upperBound...upperBound
        }
        return lowerBound...upperBound
    }
}

// Usage
let range = ClosedRange.safe(minValue, maxValue)
```

## AppStorage Validation

### Problem

AppStorage persists values between app launches, but persisted values can become invalid:

```swift
struct SettingsView: View {
    @AppStorage("selectedIndex") private var selectedIndex = 0

    var body: some View {
        // Crashes if selectedIndex is out of range
        Text(items[selectedIndex])
    }
}
```

**Scenarios leading to invalid values:**
- Array size decreased between versions
- Valid range changed in app update
- Manual modification of UserDefaults
- Data corruption

### Solution

Add init to validate and correct persisted values:

```swift
struct SettingsView: View {
    @AppStorage("selectedIndex") private var selectedIndex = 0

    private let items = ["One", "Two", "Three"]

    init() {
        // Validate and correct if needed
        if selectedIndex < 0 || selectedIndex >= items.count {
            selectedIndex = 0
        }
    }

    var body: some View {
        Text(items[selectedIndex]) // Now safe
    }
}
```

### Prevention Pattern

**Create validated AppStorage wrapper:**

```swift
@propertyWrapper
struct ValidatedAppStorage<Value: Comparable & Codable> {
    private let key: String
    private let defaultValue: Value
    private let range: ClosedRange<Value>

    init(wrappedValue: Value, _ key: String, _ range: ClosedRange<Value>) {
        self.key = key
        self.defaultValue = wrappedValue
        self.range = range
    }

    var wrappedValue: Value {
        get {
            guard let stored = UserDefaults.standard.object(forKey: key) as? Value else {
                return defaultValue
            }
            // Clamp to valid range
            return min(max(range.lowerBound, stored), range.upperBound)
        }
        set {
            let clamped = min(max(range.lowerBound, newValue), range.upperBound)
            UserDefaults.standard.set(clamped, forKey: key)
        }
    }
}

// Usage
@ValidatedAppStorage("volume", 0...100) private var volume = 50
```

## Constraint Violations

### Problem

UI allows users to enter values that violate constraints:

```swift
struct CircleEditor: View {
    @State private var diameter: Double = 50
    @State private var containerWidth: Double = 100

    var body: some View {
        VStack {
            Slider(value: $diameter, in: 0...200) // Can exceed container
            Slider(value: $containerWidth, in: 0...200) // Can be less than diameter
            Circle()
                .frame(width: diameter, height: diameter) // May overflow container
                .frame(width: containerWidth) // CONSTRAINT VIOLATION
        }
    }
}
```

### Solution

Add validation at multiple layers:

#### 1. UI Layer - Prevent Invalid Input

```swift
struct CircleEditor: View {
    @State private var diameter: Double = 50
    @State private var containerWidth: Double = 100

    var body: some View {
        VStack {
            // Diameter can't exceed container
            Slider(value: $diameter, in: 0...containerWidth)
            Slider(value: $containerWidth, in: diameter...200)
        }
        .onChange(of: containerWidth) {
            // Adjust diameter if container shrinks
            if diameter > containerWidth {
                diameter = containerWidth
            }
        }
    }
}
```

#### 2. Model Layer - Validate on Creation

```swift
struct CircleConfiguration {
    let diameter: Double
    let containerWidth: Double

    init(diameter: Double, containerWidth: Double) throws {
        guard diameter > 0 else {
            throw ValidationError.invalidDiameter
        }
        guard containerWidth > 0 else {
            throw ValidationError.invalidContainerWidth
        }
        guard diameter <= containerWidth else {
            throw ValidationError.diameterExceedsContainer
        }

        self.diameter = diameter
        self.containerWidth = containerWidth
    }
}
```

#### 3. Persistence Layer - Validate Before/After Storage

```swift
@MainActor
final class CircleManager: ObservableObject {
    @Published var configuration: CircleConfiguration?

    func save(_ config: CircleConfiguration) throws {
        // Validate before saving
        try config.validate()

        // Save to persistence
        try persistenceService.save(config)
    }

    func load() throws {
        let config = try persistenceService.load()

        // Validate after loading
        try config.validate()

        configuration = config
    }
}
```

## SwiftUI Publishing Warnings

### Problem

Updating `@Published` properties outside main thread:

```swift
@MainActor
final class DataManager: ObservableObject {
    @Published var items: [Item] = []

    func loadItems() {
        Task {
            let fetchedItems = await fetchFromNetwork()
            items = fetchedItems // ⚠️ Warning: Publishing changes from background thread
        }
    }
}
```

### Solution 1: Use @MainActor on Function

```swift
@MainActor
final class DataManager: ObservableObject {
    @Published var items: [Item] = []

    @MainActor
    func loadItems() async {
        let fetchedItems = await fetchFromNetwork()
        items = fetchedItems // ✅ Safe: Already on main thread
    }
}
```

### Solution 2: Explicit Main Thread Dispatch

```swift
@MainActor
final class DataManager: ObservableObject {
    @Published var items: [Item] = []

    func loadItems() {
        Task {
            let fetchedItems = await fetchFromNetwork()

            await MainActor.run {
                items = fetchedItems // ✅ Safe: Explicit main thread
            }
        }
    }
}
```

## Memory Leaks with Closures

### Problem

Strong reference cycles in closures:

```swift
class DataManager {
    var items: [Item] = []
    var onUpdate: (() -> Void)?

    func startObserving() {
        onUpdate = {
            self.processItems() // ❌ Strong reference to self
        }
    }

    func processItems() {
        // Process items
    }
}
```

### Solution

Use capture lists with `[weak self]` or `[unowned self]`:

```swift
class DataManager {
    var items: [Item] = []
    var onUpdate: (() -> Void)?

    func startObserving() {
        onUpdate = { [weak self] in
            self?.processItems() // ✅ Weak reference, breaks cycle
        }
    }

    func processItems() {
        // Process items
    }
}
```

**When to use weak vs unowned:**

```swift
// Use [weak self] when self might be deallocated
onUpdate = { [weak self] in
    guard let self else { return }
    self.processItems()
}

// Use [unowned self] when self is guaranteed to outlive closure
onUpdate = { [unowned self] in
    self.processItems() // Crashes if self is deallocated (use with caution)
}
```

## Force Unwrapping Crashes

### Problem

Force unwrapping nil optionals:

```swift
let user = users.first(where: { $0.id == targetID })!
print(user.name) // ❌ Crashes if no matching user
```

### Solution

Use safe unwrapping:

```swift
// ✅ Guard let
guard let user = users.first(where: { $0.id == targetID }) else {
    print("User not found")
    return
}
print(user.name)

// ✅ If let
if let user = users.first(where: { $0.id == targetID }) {
    print(user.name)
}

// ✅ Optional chaining
print(users.first(where: { $0.id == targetID })?.name ?? "Unknown")
```

## Type Mismatch in Codable

### Problem

JSON structure doesn't match Codable type:

```swift
struct User: Codable {
    let id: UUID
    let name: String
    let age: Int
}

// JSON has age as String: {"id": "...", "name": "John", "age": "25"}
let user = try JSONDecoder().decode(User.self, from: data) // ❌ Decoding error
```

### Solution

Use custom decoding:

```swift
struct User: Codable {
    let id: UUID
    let name: String
    let age: Int

    enum CodingKeys: String, CodingKey {
        case id, name, age
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(UUID.self, forKey: .id)
        name = try container.decode(String.self, forKey: .name)

        // Handle age as String or Int
        if let ageInt = try? container.decode(Int.self, forKey: .age) {
            age = ageInt
        } else if let ageString = try? container.decode(String.self, forKey: .age),
                  let ageInt = Int(ageString) {
            age = ageInt
        } else {
            throw DecodingError.dataCorruptedError(
                forKey: .age,
                in: container,
                debugDescription: "Age must be Int or String representing Int"
            )
        }
    }
}
```

## SwiftUI State Not Updating

### Problem

Mutating nested properties doesn't trigger view updates:

```swift
struct Item: Identifiable {
    let id: UUID
    var name: String
}

struct ListView: View {
    @State private var items: [Item] = []

    var body: some View {
        List(items) { item in
            Text(item.name)
        }
        .onAppear {
            items[0].name = "Updated" // ❌ View doesn't update
        }
    }
}
```

### Solution

Trigger objectWillChange manually or reassign the entire array:

```swift
struct ListView: View {
    @State private var items: [Item] = []

    var body: some View {
        List(items) { item in
            Text(item.name)
        }
        .onAppear {
            // ✅ Reassign entire array
            var updatedItems = items
            updatedItems[0].name = "Updated"
            items = updatedItems
        }
    }
}
```

Or use a class with ObservableObject:

```swift
class Item: Identifiable, ObservableObject {
    let id: UUID
    @Published var name: String

    init(id: UUID, name: String) {
        self.id = id
        self.name = name
    }
}

struct ListView: View {
    @State private var items: [Item] = []

    var body: some View {
        List(items) { item in
            Text(item.name)
        }
        .onAppear {
            items[0].name = "Updated" // ✅ Now triggers update
        }
    }
}
```
