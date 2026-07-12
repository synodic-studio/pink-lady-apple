# Architecture Patterns

Architectural patterns and design principles for Swift and SwiftUI applications.

## MVVM + Manager Pattern

The primary architectural pattern for SwiftUI applications combining MVVM with observable manager objects.

### Structure

**Views** - SwiftUI components with skimmable 12-line bodies
**Managers** - ObservableObject classes handling business logic and state
**Protocols** - Abstractions for dependency injection and testing

### Manager Example

```swift
@MainActor
final class DataManager: ObservableObject {
    // Published state
    @Published var items: [Item] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    // Dependencies (injected via protocols)
    private var service: DataServiceProtocol?

    // Configuration
    func configure(service: DataServiceProtocol) {
        self.service = service
    }

    // Business logic
    func loadItems() async {
        isLoading = true
        defer { isLoading = false }

        do {
            items = try await service?.fetchItems() ?? []
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
```

### View with Manager

```swift
struct ItemListView: View {
    @StateObject private var manager = DataManager()

    var body: some View {
        List(manager.items) { item in
            ItemRow(item: item)
        }
        .task {
            await manager.loadItems()
        }
    }
}
```

## Protocol-Oriented Design

### Dependency Injection

Managers depend on protocols, not concrete types:

```swift
// Protocol defining service contract
protocol DataServiceProtocol {
    func fetchItems() async throws -> [Item]
    func saveItem(_ item: Item) async throws
}

// Concrete implementation
struct RemoteDataService: DataServiceProtocol {
    func fetchItems() async throws -> [Item] {
        // Network implementation
    }

    func saveItem(_ item: Item) async throws {
        // Network implementation
    }
}

// Mock for testing
struct MockDataService: DataServiceProtocol {
    var itemsToReturn: [Item] = []

    func fetchItems() async throws -> [Item] {
        itemsToReturn
    }

    func saveItem(_ item: Item) async throws {
        // Mock implementation
    }
}
```

### Configuration Pattern

Use `configure()` methods for dependency injection:

```swift
@MainActor
final class ProfileManager: ObservableObject {
    private var authService: AuthServiceProtocol?
    private var dataService: DataServiceProtocol?

    func configure(
        authService: AuthServiceProtocol,
        dataService: DataServiceProtocol
    ) {
        self.authService = authService
        self.dataService = dataService
    }
}

// In app initialization:
let manager = ProfileManager()
manager.configure(
    authService: RemoteAuthService(),
    dataService: RemoteDataService()
)
```

## Extension-Based Design

Add functionality through extensions rather than inheritance or wrappers.

### Core Utility Extensions

```swift
// Extend existing types
extension Array {
    /// Returns the element at the specified index if it's within bounds, otherwise nil.
    subscript(safe index: Index) -> Element? {
        indices.contains(index) ? self[index] : nil
    }
}

// Usage
let items = [1, 2, 3]
let value = items[safe: 5] // Returns nil instead of crashing
```

### Package Organization

Core utilities organized as extension-based packages:

```
utility-kit/
├── Sources/
│   └── UtilityKit/
│       ├── Array+Extensions.swift
│       ├── Collection+Extensions.swift
│       ├── String+Extensions.swift
│       └── SwiftUI+Extensions.swift
└── Package.swift
```

**Benefits:**
- Zero dependencies
- Composable functionality
- No wrapper types needed
- Seamless integration with existing types

## Package Modularization

### Incremental Approach

**Strategy**: Move types in small batches with validation at each step.

1. **Start with foundation types** - Simple types with no dependencies
2. **Add 3-5 types per batch** - Small enough to track, large enough to make progress
3. **Build and test after each batch** - Catch issues early
4. **Complex types and protocols later** - After foundation is stable

### Example Progression

```
Batch 1: Foundation Types
- BasicError.swift
- Constants.swift
- Configuration.swift

Batch 2: Extensions
- String+Extensions.swift
- Array+Extensions.swift

Batch 3: Data Structures
- Fraction.swift
- Percent.swift

Batch 4: Protocols
- DataServiceProtocol.swift
- AuthServiceProtocol.swift

Batch 5: Complex Types
- DataManager.swift (depends on protocols)
- NetworkClient.swift (depends on protocols and data structures)
```

### Access Levels

**Explicit access control is required:**

```swift
// ✅ Correct: Explicit public for package API
public struct User {
    public let id: UUID
    public let name: String

    public init(id: UUID, name: String) {
        self.id = id
        self.name = name
    }
}

// ✅ Correct: Internal for package implementation
struct ValidationRule {
    let check: (String) -> Bool
}

// ✅ Correct: Private for internal details
private func validateFormat(_ input: String) -> Bool {
    // Implementation
}
```

### Build Validation

When encountering errors:

1. **Clean build** - Product → Clean Build Folder
2. **Reopen Xcode** - Close and reopen project
3. **Check imports** - "No such module" errors require Package.swift updates
4. **Verify dependencies** - Ensure Package.swift includes all dependencies

### When Not to Modularize

**Don't force bad moves:**

- If concurrency issues arise, revert and keep in main app
- Complex interdependencies indicate types belong together
- UI-specific code tightly coupled to app structure
- Types requiring extensive app-specific configuration

Foundation-first principle: Move simple types before complex protocols and implementations.

## Zero-Dependency Design

### Philosophy

Where possible, create packages with zero external dependencies:

- Reduces maintenance burden
- Eliminates version conflicts
- Improves build times
- Simplifies integration

### Example: utility-kit

The utility-kit package demonstrates zero-dependency design:

```swift
// Package.swift
let package = Package(
    name: "utility-kit",
    platforms: [
        .iOS(.v15),
        .macOS(.v12)
    ],
    products: [
        .library(name: "UtilityKit", targets: ["UtilityKit"])
    ],
    dependencies: [], // Zero dependencies
    targets: [
        .target(name: "UtilityKit", dependencies: [])
    ]
)
```

All functionality provided through extensions and lightweight types.

## Manager Responsibilities

### What Managers Should Handle

- **State Management** - `@Published` properties for UI state
- **Business Logic** - Validation, calculations, transformations
- **Data Coordination** - Fetching, caching, synchronization
- **Service Integration** - Calling APIs, databases, file systems
- **Error Handling** - Converting errors to user-facing messages

### What Managers Should NOT Handle

- **View Layout** - That's the view's responsibility
- **UI State** - Transient UI state stays in views with `@State`
- **Navigation** - Navigation state typically managed by views or navigation coordinator
- **Presentation Logic** - How to display data (formatting, colors) belongs in views

### Example: Well-Scoped Manager

```swift
@MainActor
final class WeatherManager: ObservableObject {
    // State
    @Published var currentWeather: Weather?
    @Published var forecast: [ForecastDay] = []
    @Published var isLoading = false

    // Dependencies
    private let service: WeatherServiceProtocol

    init(service: WeatherServiceProtocol) {
        self.service = service
    }

    // Business logic
    func loadWeather(for location: Location) async {
        isLoading = true
        defer { isLoading = false }

        async let current = service.fetchCurrentWeather(for: location)
        async let upcoming = service.fetchForecast(for: location)

        do {
            currentWeather = try await current
            forecast = try await upcoming
        } catch {
            // Handle error
        }
    }
}
```

## Testing Architecture

### Testable Manager Design

```swift
// Manager with protocol dependencies
@MainActor
final class UserManager: ObservableObject {
    @Published var user: User?
    private let service: UserServiceProtocol

    init(service: UserServiceProtocol) {
        self.service = service
    }

    func loadUser(id: UUID) async throws {
        user = try await service.fetchUser(id: id)
    }
}

// Test with mock service
@Test
func testLoadUser() async throws {
    let mockService = MockUserService()
    mockService.userToReturn = User.sample

    let manager = UserManager(service: mockService)
    try await manager.loadUser(id: User.sample.id)

    #expect(manager.user?.id == User.sample.id)
}
```
