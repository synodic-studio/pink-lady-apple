# Platform-Specific Patterns

Platform-specific patterns for Metal, Core Data, and iOS/macOS development.

## Platform Targeting

### Minimum Deployment Targets

Standard minimum versions across projects:

```swift
// Package.swift
platforms: [
    .iOS(.v15),
    .macOS(.v12)
]
```

### Swift Version

Target Swift 6.0 for future-proofing:

```swift
// Package.swift
swiftLanguageVersions: [.v6]
```

## Metal Integration

### Metal-First Processing

For GPU-accelerated operations, prioritize Metal over CPU processing.

**When to use Metal:**
- Image processing operations
- Real-time video processing (30+ FPS requirement)
- Parallel computations on large datasets
- Mathematical transformations on matrices/vectors

### Metal Command Buffer Reuse

Reuse Metal resources for performance:

```swift
@MainActor
final class MetalEngine {
    private let device: MTLDevice
    private let commandQueue: MTLCommandQueue
    private let library: MTLLibrary

    init() throws {
        guard let device = MTLCreateSystemDefaultDevice() else {
            throw MetalError.deviceNotAvailable
        }
        guard let commandQueue = device.makeCommandQueue() else {
            throw MetalError.commandQueueCreationFailed
        }

        self.device = device
        self.commandQueue = commandQueue
        self.library = try device.makeDefaultLibrary()
    }

    func processFrame(_ texture: MTLTexture) async throws -> MTLTexture {
        guard let commandBuffer = commandQueue.makeCommandBuffer() else {
            throw MetalError.commandBufferCreationFailed
        }

        // Create compute command encoder
        guard let computeEncoder = commandBuffer.makeComputeCommandEncoder() else {
            throw MetalError.encoderCreationFailed
        }

        // Set up compute pipeline and textures
        computeEncoder.setTexture(texture, index: 0)
        // ... configure compute pass

        computeEncoder.endEncoding()

        commandBuffer.commit()
        commandBuffer.waitUntilCompleted()

        return outputTexture
    }
}
```

### Metal Texture Management

Efficient texture handling for real-time processing:

```swift
final class TexturePool {
    private let device: MTLDevice
    private var availableTextures: [MTLTexture] = []

    init(device: MTLDevice) {
        self.device = device
    }

    func getTexture(width: Int, height: Int) -> MTLTexture? {
        // Reuse available texture if size matches
        if let texture = availableTextures.first(where: {
            $0.width == width && $0.height == height
        }) {
            availableTextures.removeAll { $0 === texture }
            return texture
        }

        // Create new texture
        let descriptor = MTLTextureDescriptor.texture2DDescriptor(
            pixelFormat: .rgba8Unorm,
            width: width,
            height: height,
            mipmapped: false
        )
        descriptor.usage = [.shaderRead, .shaderWrite]

        return device.makeTexture(descriptor: descriptor)
    }

    func returnTexture(_ texture: MTLTexture) {
        availableTextures.append(texture)
    }
}
```

### Metal Compute Shaders

Example compute shader for image processing:

```metal
#include <metal_stdlib>
using namespace metal;

kernel void grayscale(
    texture2d<float, access::read> inputTexture [[texture(0)]],
    texture2d<float, access::write> outputTexture [[texture(1)]],
    uint2 gid [[thread_position_in_grid]]
) {
    if (gid.x >= outputTexture.get_width() || gid.y >= outputTexture.get_height()) {
        return;
    }

    float4 color = inputTexture.read(gid);
    float gray = dot(color.rgb, float3(0.299, 0.587, 0.114));

    outputTexture.write(float4(gray, gray, gray, color.a), gid);
}
```

### Performance Considerations

**Real-time Processing (30+ FPS):**
- Reuse Metal command buffers and textures
- Minimize CPU-GPU data transfers
- Use async operations to avoid blocking main thread
- Profile with Instruments to identify bottlenecks

**Memory Management:**
- Pool textures to avoid allocation overhead
- Release unused resources promptly
- Monitor memory usage in Instruments

## Core Data

### Core Data Stack Setup

```swift
final class PersistenceController {
    static let shared = PersistenceController()

    let container: NSPersistentContainer

    init(inMemory: Bool = false) {
        container = NSPersistentContainer(name: "AppModel")

        if inMemory {
            container.persistentStoreDescriptions.first?.url = URL(fileURLWithPath: "/dev/null")
        }

        container.loadPersistentStores { description, error in
            if let error = error {
                fatalError("Core Data failed to load: \(error.localizedDescription)")
            }
        }

        container.viewContext.automaticallyMergesChangesFromParent = true
    }
}
```

### SwiftUI Integration

```swift
@main
struct MyApp: App {
    let persistenceController = PersistenceController.shared

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(\.managedObjectContext, persistenceController.container.viewContext)
        }
    }
}

struct ContentView: View {
    @Environment(\.managedObjectContext) private var viewContext

    @FetchRequest(
        sortDescriptors: [NSSortDescriptor(keyPath: \Item.timestamp, ascending: true)],
        animation: .default
    )
    private var items: FetchedResults<Item>

    var body: some View {
        List(items) { item in
            Text(item.name ?? "Unnamed")
        }
    }
}
```

### Background Context Operations

```swift
final class DataManager {
    private let container: NSPersistentContainer

    init(container: NSPersistentContainer) {
        self.container = container
    }

    func performBackgroundTask<T>(_ block: @escaping (NSManagedObjectContext) throws -> T) async throws -> T {
        try await withCheckedThrowingContinuation { continuation in
            container.performBackgroundTask { context in
                do {
                    let result = try block(context)
                    continuation.resume(returning: result)
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    func importData(_ items: [ItemData]) async throws {
        try await performBackgroundTask { context in
            for itemData in items {
                let item = Item(context: context)
                item.name = itemData.name
                item.timestamp = itemData.timestamp
            }

            try context.save()
        }
    }
}
```

## iOS-Specific Patterns

### Safe Area Handling

```swift
struct ContentView: View {
    var body: some View {
        VStack {
            Text("Content")
        }
        .safeAreaInset(edge: .bottom) {
            BottomToolbar()
        }
    }
}
```

### Keyboard Management

```swift
struct TextEntryView: View {
    @State private var text = ""
    @FocusState private var isFocused: Bool

    var body: some View {
        VStack {
            TextField("Enter text", text: $text)
                .focused($isFocused)
                .textFieldStyle(.roundedBorder)

            Button("Done") {
                isFocused = false // Dismiss keyboard
            }
        }
        .padding()
    }
}
```

### Navigation Patterns (iOS 16+)

```swift
struct AppView: View {
    @State private var navigationPath = NavigationPath()

    var body: some View {
        NavigationStack(path: $navigationPath) {
            HomeView()
                .navigationDestination(for: User.self) { user in
                    UserDetailView(user: user)
                }
                .navigationDestination(for: Post.self) { post in
                    PostDetailView(post: post)
                }
        }
    }
}
```

## macOS-Specific Patterns

### Window Management

```swift
@main
struct MyApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
        .windowStyle(.hiddenTitleBar)
        .windowResizability(.contentSize)

        Settings {
            SettingsView()
        }
    }
}
```

### Menu Bar Integration

```swift
@main
struct MyApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
        .commands {
            CommandMenu("Custom") {
                Button("Action") {
                    performAction()
                }
                .keyboardShortcut("k", modifiers: .command)
            }
        }
    }
}
```

### Full-Screen Mode

```swift
struct DisplayView: View {
    @State private var isFullScreen = false

    var body: some View {
        VStack {
            Text("Content")
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.black)
        .onAppear {
            // Enter full-screen mode
            NSApplication.shared.mainWindow?.toggleFullScreen(nil)
        }
    }
}
```

## Cross-Platform Patterns

### Conditional Compilation

```swift
#if os(iOS)
import UIKit
typealias PlatformColor = UIColor
#elseif os(macOS)
import AppKit
typealias PlatformColor = NSColor
#endif

extension PlatformColor {
    static var systemBackground: PlatformColor {
        #if os(iOS)
        return UIColor.systemBackground
        #elseif os(macOS)
        return NSColor.windowBackgroundColor
        #endif
    }
}
```

### Platform-Specific Views

```swift
struct PlatformSpecificView: View {
    var body: some View {
        #if os(iOS)
        NavigationView {
            ContentView()
        }
        .navigationViewStyle(.stack)
        #elseif os(macOS)
        NavigationSplitView {
            SidebarView()
        } detail: {
            ContentView()
        }
        #endif
    }
}
```

### Available Attributes

```swift
@available(iOS 16, macOS 13, *)
struct ModernView: View {
    var body: some View {
        // Use iOS 16+ / macOS 13+ features
        Text("Modern UI")
            .fontDesign(.rounded)
    }
}

struct AdaptiveView: View {
    var body: some View {
        if #available(iOS 16, macOS 13, *) {
            ModernView()
        } else {
            LegacyView()
        }
    }
}
```

## Performance Optimization

### Lazy Loading

```swift
struct ListWithLazyLoading: View {
    let items: [Item]

    var body: some View {
        ScrollView {
            LazyVStack {
                ForEach(items) { item in
                    ItemRow(item: item)
                }
            }
        }
    }
}
```

### Drawing Performance

```swift
struct OptimizedView: View {
    var body: some View {
        Canvas { context, size in
            // Efficient custom drawing
            context.fill(
                Path(ellipseIn: CGRect(origin: .zero, size: size)),
                with: .color(.blue)
            )
        }
    }
}
```

### Background Tasks

```swift
struct DataLoadingView: View {
    @StateObject private var manager = DataManager()

    var body: some View {
        ContentView(data: manager.data)
            .task {
                await manager.loadData()
            }
            .refreshable {
                await manager.refresh()
            }
    }
}
```
