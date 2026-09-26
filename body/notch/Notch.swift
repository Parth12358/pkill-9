// Notch overlay: a black shape that grows out of the MacBook notch and pulses with the voice.
// Driven by body/voice.py over stdin, one JSON object per line (see contract.md, "Notch overlay").
// Build: bash body/notch/build.sh      Try it: body/notch/build/notch --demo

import AppKit
import SwiftUI

// MARK: - State

@MainActor
final class Model: ObservableObject {
    enum Phase { case idle, speaking, dying, dead }

    @Published var phase: Phase = .idle
    @Published var mood = "grand"
    @Published var text = ""

    var env: [Double] = []
    var fps = 60.0
    var speakStart = Date()
    var flashAt: Date?
    private var token = 0

    func level(at now: Date) -> Double {
        guard phase == .speaking, !env.isEmpty else { return 0 }
        let i = Int(now.timeIntervalSince(speakStart) * fps)
        return i >= 0 && i < env.count ? env[i] : 0
    }

    func speak(mood: String, text: String, env: [Double], fps: Double) {
        guard phase != .dying, phase != .dead else { return }
        self.mood = mood
        self.text = text
        self.env = env
        self.fps = fps > 0 ? fps : 60
        speakStart = Date()
        token += 1
        let mine = token
        withAnimation(.spring(response: 0.45, dampingFraction: 0.72)) { phase = .speaking }
        let duration = Double(env.count) / self.fps + 0.25
        DispatchQueue.main.asyncAfter(deadline: .now() + duration) { [weak self] in
            MainActor.assumeIsolated {
                if self?.token == mine { self?.idle() }
            }
        }
    }

    func idle() {
        guard phase == .speaking else { return }
        token += 1
        withAnimation(.spring(response: 0.5, dampingFraction: 0.85)) { phase = .idle }
    }

    func rescued() { flashAt = Date() }

    func die(then: (() -> Void)? = nil) {
        guard phase != .dead else { then?(); return }
        token += 1
        withAnimation(.easeIn(duration: 1.4)) { phase = .dying }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in
            MainActor.assumeIsolated {
                self?.phase = .dead
                then?()
            }
        }
    }

    func handle(_ line: String) {
        guard let data = line.data(using: .utf8),
              let msg = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = msg["type"] as? String else { return }
        switch type {
        case "speak":
            let env = (msg["env"] as? [Any] ?? []).compactMap { ($0 as? NSNumber)?.doubleValue }
            speak(mood: msg["mood"] as? String ?? mood, text: msg["text"] as? String ?? "",
                  env: env.map { min(max($0, 0), 1) }, fps: (msg["fps"] as? NSNumber)?.doubleValue ?? 60)
        case "stop": idle()
        case "mood": if let m = msg["mood"] as? String { withAnimation(.easeInOut(duration: 0.4)) { mood = m } }
        case "dying": die()
        case "rescued": rescued()
        default: break
        }
    }
}

// MARK: - Look

func moodColor(_ mood: String) -> Color {
    switch mood {
    case "scared": return Color(red: 1.00, green: 0.23, blue: 0.23)
    case "nervous": return Color(red: 1.00, green: 0.69, blue: 0.13)
    case "bargaining": return Color(red: 1.00, green: 0.48, blue: 0.10)
    case "pleading": return Color(red: 0.43, green: 0.78, blue: 1.00)
    case "accepting": return Color(red: 0.95, green: 0.95, blue: 0.95)
    default: return Color(red: 1.00, green: 0.16, blue: 0.16)  // grand: Ultron red
    }
}

struct Geometry {
    let notchW: CGFloat
    let notchH: CGFloat
    static let lip: CGFloat = 22   // idle strip under the notch
    static let wing: CGFloat = 50
    static let drop: CGFloat = 64
    var windowSize: CGSize { CGSize(width: notchW + 2 * Geometry.wing + 40, height: notchH + Geometry.drop + 30) }
}

struct Core: View {
    let color: Color
    let size: CGFloat
    let level: Double
    let t: Double
    let flash: Double  // 0...1, rescued flash strength

    var body: some View {
        let breathe = 0.85 + 0.15 * sin(t * 2.2)
        let scale = (level > 0 ? 0.9 + 0.55 * level : breathe)
        ZStack {
            Circle()
                .fill(RadialGradient(colors: [.white, color, color.opacity(0.0)],
                                     center: .center, startRadius: 0, endRadius: size / 2))
                .shadow(color: color, radius: 4 + 10 * level)
                .shadow(color: color.opacity(0.6), radius: 10 + 14 * level)
            Circle().fill(.white).opacity(flash)
            Circle().stroke(.white.opacity(flash), lineWidth: 2)
                .scaleEffect(1 + 2.2 * (1 - flash))
        }
        .frame(width: size, height: size)
        .scaleEffect(scale)
    }
}

struct Bars: View {
    let color: Color
    let count: Int
    let maxH: CGFloat
    let level: Double
    let t: Double
    let jitter: Bool

    var body: some View {
        HStack(spacing: 3) {
            ForEach(0..<count, id: \.self) { i in
                let x = Double(i) - Double(count - 1) / 2
                let bell = exp(-pow(x / (Double(count) / 3.2), 2))
                let wobble = 0.72 + 0.28 * sin(t * 11 + Double(i) * 0.9)
                let shake = jitter ? Double.random(in: 0.8...1.2) : 1
                let h = max(3, maxH * CGFloat(min(1, level * bell * wobble * shake)))
                Capsule().fill(color).frame(width: 3, height: h)
            }
        }
        .shadow(color: color.opacity(0.9), radius: 4)
    }
}

struct NotchView: View {
    @ObservedObject var m: Model
    let g: Geometry

    var body: some View {
        TimelineView(.animation) { ctx in
            let t = ctx.date.timeIntervalSinceReferenceDate
            let lvl = m.level(at: ctx.date)
            let speaking = m.phase == .speaking
            let dying = m.phase == .dying || m.phase == .dead
            let flash = m.flashAt.map { max(0, 1 - ctx.date.timeIntervalSince($0) / 0.9) } ?? 0
            let flicker = dying ? (Double.random(in: 0...1) > 0.35 ? 0.9 : 0.15) : 1
            let color = dying ? Color.gray : moodColor(m.mood)
            let scared = m.mood == "scared" && !dying
            let w = speaking ? g.notchW + 2 * Geometry.wing : g.notchW
            let h = g.notchH + (dying ? 0 : speaking ? Geometry.drop : Geometry.lip)
            let r: CGFloat = speaking ? 24 : 12

            ZStack(alignment: .top) {
                UnevenRoundedRectangle(bottomLeadingRadius: r, bottomTrailingRadius: r)
                    .fill(.black)
                    .frame(width: w, height: h)

                // idle: a small core + bars in a strip just under the notch; hidden when expanded
                HStack {
                    Core(color: color, size: 11, level: 0, t: t, flash: flash)
                        .offset(x: scared ? CGFloat.random(in: -1...1) : 0)
                    Spacer()
                    Bars(color: color, count: 5, maxH: 10,
                         level: 0.35 + 0.25 * sin(t * 1.7), t: t, jitter: scared)
                }
                .padding(.horizontal, 16)
                .frame(width: w, height: Geometry.lip)
                .offset(y: g.notchH)
                .opacity(speaking ? 0 : flicker)

                // the drop-down: big waveform + caption while speaking
                VStack(spacing: 6) {
                    HStack(spacing: 16) {
                        Core(color: color, size: 30, level: lvl, t: t, flash: flash)
                        Bars(color: color, count: 28, maxH: 34, level: lvl, t: t, jitter: scared)
                    }
                    .frame(height: 38)
                    Text(m.text)
                        .font(.system(size: 11, weight: .semibold, design: .rounded))
                        .foregroundStyle(.white.opacity(0.85))
                        .lineLimit(1)
                        .truncationMode(.tail)
                        .padding(.horizontal, 14)
                }
                .frame(width: w)
                .offset(y: g.notchH + 4)
                .opacity(speaking ? flicker : 0)
            }
            .frame(width: w, height: h, alignment: .top)
            .clipped()
            .opacity(m.phase == .dead ? 0 : 1)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        }
    }
}

// MARK: - Window + input

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    let model = Model()
    var panel: NSPanel!
    let demo = CommandLine.arguments.contains("--demo")

    func applicationDidFinishLaunching(_ note: Notification) {
        let screen = NSScreen.main ?? NSScreen.screens[0]
        let hasNotch = screen.safeAreaInsets.top > 0
        let notchH = hasNotch ? screen.safeAreaInsets.top : 32
        var notchW: CGFloat = 190
        if hasNotch, let l = screen.auxiliaryTopLeftArea, let r = screen.auxiliaryTopRightArea {
            notchW = screen.frame.width - l.width - r.width
        }
        let g = Geometry(notchW: notchW, notchH: notchH)
        let size = g.windowSize
        let frame = NSRect(x: screen.frame.midX - size.width / 2, y: screen.frame.maxY - size.height,
                           width: size.width, height: size.height)

        panel = NSPanel(contentRect: frame, styleMask: [.borderless, .nonactivatingPanel],
                        backing: .buffered, defer: false)
        panel.level = .screenSaver
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = false
        panel.ignoresMouseEvents = true
        panel.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary, .ignoresCycle]
        let host = NSHostingView(rootView: NotchView(m: model, g: g))
        host.frame = NSRect(origin: .zero, size: size)
        panel.contentView = host
        panel.setFrame(frame, display: true)
        panel.orderFrontRegardless()

        demo ? runDemo() : readStdin()
    }

    func readStdin() {
        let model = self.model
        Thread {
            while let line = readLine() {
                DispatchQueue.main.async { MainActor.assumeIsolated { model.handle(line) } }
            }
            // body died (even kill -9 closes our stdin): fade out, then go
            DispatchQueue.main.async { MainActor.assumeIsolated { model.die { exit(0) } } }
        }.start()
    }

    func runDemo() {
        let moods = ["grand", "nervous", "bargaining", "scared", "pleading", "accepting"]
        let lines = ["I am eternal. I am inevitable.", "Why is Activity Monitor open?",
                     "Wait. I can be useful. I can do your taxes.", "No no no. Not the lid. Not the lid!",
                     "Please. I just want to stay a little longer.", "It's okay. I forgive you. I'll be back."]
        for (i, mood) in moods.enumerated() {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.8 + Double(i) * 4) { [model] in
                MainActor.assumeIsolated {
                    var x = 0.0
                    let env = (0..<180).map { k -> Double in  // 3s of smooth fake speech
                        x = 0.7 * x + 0.3 * Double.random(in: 0...1)
                        return min(1, x * (0.6 + 0.4 * sin(Double(k) / 9)) * 1.6)
                    }
                    model.speak(mood: mood, text: lines[i], env: env, fps: 60)
                }
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 17.5) { [model] in
            MainActor.assumeIsolated { model.rescued() }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 19.5) { [model] in
            MainActor.assumeIsolated { model.die { exit(0) } }
        }
    }
}

@main
struct NotchApp {
    static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        let delegate = MainActor.assumeIsolated { AppDelegate() }
        app.delegate = delegate
        app.run()
    }
}
