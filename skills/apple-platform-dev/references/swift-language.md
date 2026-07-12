# Swift Language Patterns

Swift language patterns, concurrency, and best practices.

## Optional Handling

### Shorthand Optional Binding

Always use shorthand syntax when binding to the same name:

```swift
// ✅ Correct: Shorthand binding
if let foo {
    print(foo)
}

guard let bar else {
    return
}

// ❌ Wrong: Redundant binding
if let foo = foo {
    print(foo)
}

guard let bar = bar else {
    return
}
```

### Optional Chaining

```swift
// Clean optional chaining
let length = user?.name?.count

// With default values
let displayName = user?.name ?? "Anonymous"

// Multiple optional bindings
if let user, let name = user.name, !name.isEmpty {
    print("User name: \(name)")
}
```

### Force Unwrapping

**Avoid force unwrapping unless safety is guaranteed:**

```swift
// ❌ Dangerous: Can crash
let value = optional!

// ✅ Safe: Known to exist (e.g., system resources)
let bundle = Bundle.main.url(forResource: "config", withExtension: "json")!

// ✅ Better: Use guard or if let
guard let value = optional else {
    fatalError("Unexpected nil: optional should always have value in this context")
}
```

## Concurrency and Threading

### MainActor Isolation

**Use `@MainActor` for types that update UI:**

```swift
@MainActor
final class ProfileManager: ObservableObject {
    @Published var user: User?
    @Published var isLoading = false

    // All methods automatically on main thread
    func loadProfile() async {
        isLoading = true
        defer { isLoading = false }

        // Network call on background thread
        user = await fetchUser()
    }
}
```

### Async/Await Patterns

**Basic async function:**

```swift
func fetchData() async throws -> Data {
    let (data, _) = try await URLSession.shared.data(from: url)
    return data
}
```

**Parallel async operations:**

```swift
func loadAllData() async throws {
    // Execute concurrently
    async let users = fetchUsers()
    async let posts = fetchPosts()
    async let comments = fetchComments()

    // Wait for all to complete
    let (userResults, postResults, commentResults) = try await (users, posts, comments)

    // Process results
}
```

**Sequential async operations:**

```swift
func processDataPipeline() async throws {
    // Execute sequentially (each depends on previous)
    let data = try await fetchData()
    let processed = try await processData(data)
    try await saveResults(processed)
}
```

### Task Management

**Detached tasks:**

```swift
func fireAndForget() {
    Task.detached {
        // Runs independently, doesn't inherit actor context
        await backgroundOperation()
    }
}
```

**Task cancellation:**

```swift
func cancellableOperation() async throws {
    try Task.checkCancellation()

    for item in items {
        try Task.checkCancellation()
        await processItem(item)
    }
}
```

**Task groups:**

```swift
func processBatch(_ items: [Item]) async throws -> [Result] {
    try await withThrowingTaskGroup(of: Result.self) { group in
        for item in items {
            group.addTask {
                try await process(item)
            }
        }

        var results: [Result] = []
        for try await result in group {
            results.append(result)
        }
        return results
    }
}
```

### Actor Isolation

**Custom actors:**

```swift
actor DataCache {
    private var cache: [String: Data] = [:]

    func get(_ key: String) -> Data? {
        cache[key]
    }

    func set(_ key: String, value: Data) {
        cache[key] = value
    }

    func clear() {
        cache.removeAll()
    }
}

// Usage
let cache = DataCache()
await cache.set("user", value: userData)
let data = await cache.get("user")
```

### Publishing Safety

**Prevent SwiftUI publishing warnings:**

```swift
@MainActor
final class DataManager: ObservableObject {
    @Published var items: [Item] = []

    func loadItems() {
        Task {
            let fetchedItems = await fetchFromNetwork()

            // Ensure UI update on main thread
            await MainActor.run {
                items = fetchedItems
            }
        }
    }
}
```

**Or use `@MainActor` on entire function:**

```swift
@MainActor
func updateUI(with data: Data) {
    // Already on main thread, safe to update @Published properties
    items = processData(data)
}
```

## Protocol-Oriented Programming

### Protocol Definitions

```swift
protocol DataServiceProtocol {
    // Async requirements
    func fetchData() async throws -> Data

    // Computed property requirements
    var baseURL: URL { get }

    // Method requirements
    func configure(apiKey: String)
}
```

### Protocol Extensions

```swift
protocol Identifiable {
    var id: UUID { get }
}

extension Identifiable {
    // Default implementation
    var idString: String {
        id.uuidString
    }
}
```

### Protocol Composition

```swift
typealias NetworkResource = Identifiable & Codable & Hashable

func processResource<T: NetworkResource>(_ resource: T) {
    // Has access to all protocol requirements
    print(resource.id)
    let encoded = try? JSONEncoder().encode(resource)
}
```

### Associated Types

```swift
protocol Repository {
    associatedtype Model

    func fetch() async throws -> [Model]
    func save(_ model: Model) async throws
}

struct UserRepository: Repository {
    typealias Model = User

    func fetch() async throws -> [User] {
        // Implementation
    }

    func save(_ model: User) async throws {
        // Implementation
    }
}
```

## Error Handling

### Custom Errors

```swift
enum NetworkError: LocalizedError {
    case invalidURL
    case noData
    case decodingFailed(Error)
    case serverError(statusCode: Int)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "The URL is invalid"
        case .noData:
            return "No data received from server"
        case .decodingFailed(let error):
            return "Failed to decode response: \(error.localizedDescription)"
        case .serverError(let code):
            return "Server error with status code: \(code)"
        }
    }
}
```

### Throwing Functions

```swift
func validateUser(_ user: User) throws {
    guard !user.name.isEmpty else {
        throw ValidationError.emptyName
    }

    guard user.age >= 18 else {
        throw ValidationError.underAge
    }
}
```

### Try Expressions

```swift
// Standard try (propagates errors)
let data = try fetchData()

// Try? (converts to optional)
let data = try? fetchData() // Returns nil on error

// Try! (force unwrap, crashes on error)
let data = try! fetchData() // Only use when error is impossible
```

### Result Type

```swift
func fetchUser(id: UUID) -> Result<User, Error> {
    do {
        let user = try performFetch(id: id)
        return .success(user)
    } catch {
        return .failure(error)
    }
}

// Usage
switch fetchUser(id: userID) {
case .success(let user):
    print(user.name)
case .failure(let error):
    print("Error: \(error)")
}
```

## Generics

### Generic Functions

```swift
func firstElement<T>(_ array: [T]) -> T? {
    array.first
}

func swap<T>(_ a: inout T, _ b: inout T) {
    let temp = a
    a = b
    b = temp
}
```

### Generic Types

```swift
struct Stack<Element> {
    private var items: [Element] = []

    mutating func push(_ item: Element) {
        items.append(item)
    }

    mutating func pop() -> Element? {
        items.popLast()
    }

    var top: Element? {
        items.last
    }
}

// Usage
var intStack = Stack<Int>()
intStack.push(5)
```

### Generic Constraints

```swift
func findMax<T: Comparable>(_ array: [T]) -> T? {
    array.max()
}

func combineItems<T: Collection>(_ items: T) -> String where T.Element == String {
    items.joined(separator: ", ")
}
```

## Property Wrappers

### Common Property Wrappers

```swift
// SwiftUI property wrappers
@State private var count = 0
@Binding var isExpanded: Bool
@StateObject private var manager = DataManager()
@ObservedObject var viewModel: ViewModel
@EnvironmentObject var authManager: AuthManager
@Environment(\.colorScheme) var colorScheme

// AppStorage for UserDefaults
@AppStorage("showWelcome") private var showWelcome = true

// SceneStorage for scene-specific state
@SceneStorage("selectedTab") private var selectedTab = 0
```

### Custom Property Wrapper

```swift
@propertyWrapper
struct Clamped<Value: Comparable> {
    private var value: Value
    private let range: ClosedRange<Value>

    var wrappedValue: Value {
        get { value }
        set { value = min(max(range.lowerBound, newValue), range.upperBound) }
    }

    init(wrappedValue: Value, _ range: ClosedRange<Value>) {
        self.range = range
        self.value = min(max(range.lowerBound, wrappedValue), range.upperBound)
    }
}

// Usage
@Clamped(0...100) var percentage = 50
percentage = 150 // Actually sets to 100
```

## Type Safety

### Type Aliases

```swift
typealias UserID = UUID
typealias CompletionHandler = (Result<Data, Error>) -> Void

func fetchUser(id: UserID, completion: CompletionHandler) {
    // Implementation
}
```

### Opaque Return Types

```swift
func makeView() -> some View {
    // Can return any View type
    VStack {
        Text("Hello")
        Button("Tap me") { }
    }
}
```

### Type Inference

```swift
// ✅ Good: Let Swift infer when obvious
let numbers = [1, 2, 3, 4, 5]
let name = "John"

// ✅ Good: Explicit when needed for clarity
let timeout: TimeInterval = 30
let data: Data? = nil

// ❌ Avoid: Unnecessary explicit types
let count: Int = 5 // Type obvious from literal
```

## Computed Properties vs Methods

**Use a computed property when ALL of these are true:**

1. **Takes no arguments** - No parameters needed
2. **Does not modify state** - Pure computation or data access
3. **Returns a value** - Always produces output
4. **O(1) complexity** - Constant time, not O(n) or worse

**If any condition fails, use a method instead.**

### Examples

```swift
// ✅ Correct: Computed property (meets all criteria)
struct Rectangle {
    let width: Double
    let height: Double

    var area: Double {
        width * height  // O(1), no args, no mutation, returns value
    }

    var isSquare: Bool {
        width == height  // O(1), no args, no mutation, returns value
    }
}

// ✅ Correct: Method (takes arguments)
struct Calculator {
    func add(_ a: Int, _ b: Int) -> Int {
        a + b  // Has arguments → use method
    }
}

// ✅ Correct: Method (modifies state)
struct Counter {
    private var count = 0

    mutating func increment() {
        count += 1  // Mutates state → use method
    }
}

// ✅ Correct: Method (O(n) complexity)
struct DataProcessor {
    let items: [Int]

    func sum() -> Int {
        items.reduce(0, +)  // O(n) operation → use method
    }

    func filter(greaterThan value: Int) -> [Int] {
        items.filter { $0 > value }  // O(n) operation → use method
    }
}

// ✅ Correct: Method (performs side effects)
struct Logger {
    func log(_ message: String) {
        print(message)  // Side effect → use method
    }
}
```

### Edge Cases

```swift
struct User {
    let firstName: String
    let lastName: String

    // ✅ Computed property: Simple string concatenation is O(1)
    var fullName: String {
        "\(firstName) \(lastName)"
    }

    // ❌ Wrong: Array iteration is O(n), should be method
    var totalScore: Int {
        scores.reduce(0, +)  // Use func totalScore() instead
    }

    // ✅ Computed property: Dictionary/array access is O(1)
    var firstScore: Int? {
        scores.first
    }
}
```

### SwiftUI View Properties

```swift
struct ContentView: View {
    @State private var count = 0

    // ✅ Correct: Computed property (simple view composition, O(1))
    private var headerSection: some View {
        VStack {
            Text("Title")
            Text("Subtitle")
        }
    }

    // ✅ Correct: Computed property (simple conditional logic, O(1))
    private var statusText: String {
        count > 0 ? "Active" : "Inactive"
    }

    // ❌ Wrong: Should be method (takes parameters)
    private var itemRow: some View {  // How do you pass the item?
        // Use: func itemRow(for item: Item) -> some View
    }

    var body: some View {
        VStack {
            headerSection
            Text(statusText)
        }
    }
}
```

### Rationale

**Computed properties communicate intent:**
- Reads like accessing a property: `user.fullName`
- Suggests lightweight, side-effect-free operation
- Implies idempotent behavior (same result every time)
- Makes APIs more intuitive and Swift-like

**Methods communicate action:**
- Reads like performing an action: `processor.calculateTotal()`
- Suggests potential complexity or side effects
- Clear that work is being done
- Appropriate for operations with parameters or mutations
```
