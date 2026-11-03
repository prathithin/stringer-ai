import AVFoundation
import PhotosUI
import Speech
import SwiftUI

struct ContentView: View {
    @State private var question = "I have class at Klaus at 9:30, what's my move?"
    @State private var plan: StingerPlan?
    @State private var previousPlan: StingerPlan?
    @State private var isLoading = false
    @State private var errorText: String?
    @State private var isListening = false
    @State private var changedKeys: Set<String> = []
    @State private var speech: SpeechHelper?
    @State private var pickerItem: PhotosPickerItem?
    @State private var dayPlan: DayPlanResponse?
    @State private var showSchedule = false

    private let client = APIClient()

    var body: some View {
        NavigationStack {
            ZStack {
                GTTheme.ink.ignoresSafeArea()
                VStack(spacing: 0) {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 16) {
                            header
                            if let errorText {
                                Text(errorText)
                                    .font(.footnote)
                                    .foregroundStyle(.red.opacity(0.9))
                                    .padding(12)
                                    .background(Color.red.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
                            }
                            if isLoading {
                                ProgressView("Asking Grok…")
                                    .tint(GTTheme.gold)
                                    .foregroundStyle(.white)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 32)
                            }
                            if let plan {
                                planCards(plan)
                            } else if !isLoading {
                                emptyState
                            }
                        }
                        .padding(20)
                    }
                    composer
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    PhotosPicker(selection: $pickerItem, matching: .images) {
                        Image(systemName: "photo.on.rectangle")
                            .foregroundStyle(GTTheme.gold)
                    }
                    .accessibilityLabel("Upload schedule screenshot")
                }
            }
            .onChange(of: pickerItem) { _, item in
                guard let item else { return }
                Task { await uploadSchedule(item) }
            }
            .sheet(isPresented: $showSchedule) {
                if let dayPlan {
                    ScheduleSheet(dayPlan: dayPlan)
                }
            }
        }
        .preferredColorScheme(.dark)
        .onAppear {
            speech = SpeechHelper { text in
                question = text
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("STINGER")
                .font(.system(.caption, design: .rounded).weight(.bold))
                .tracking(2)
                .foregroundStyle(GTTheme.gold)
            Text("What's my move?")
                .font(.system(.largeTitle, design: .rounded).weight(.bold))
                .foregroundStyle(.white)
            Text("Leave-by times from live Stinger data and Grok.")
                .font(.system(.subheadline, design: .rounded))
                .foregroundStyle(.white.opacity(0.55))
        }
    }

    private var emptyState: some View {
        CardView(label: "Try this", systemImage: "sparkles") {
            Text("Ask in plain language. I’ll pick a bus, a stop, a walk fallback, and an on-time chance.")
                .font(.body)
                .foregroundStyle(.white.opacity(0.8))
        }
    }

    @ViewBuilder
    private func planCards(_ plan: StingerPlan) -> some View {
        if plan.usingRecentData {
            HStack(spacing: 8) {
                Image(systemName: "clock.arrow.circlepath")
                Text("Using recent data — live buses aren’t reporting right now.")
                    .font(.footnote.weight(.semibold))
            }
            .foregroundStyle(GTTheme.navy)
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(GTTheme.gold, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        }

        if plan.saferMode {
            Text("Exam / quiz — recommending the safer option.")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(GTTheme.gold)
        }

        CardView(label: "Leave by", systemImage: "clock.fill") {
            highlighted(plan.leaveBy, changed: changedKeys.contains("leave_by"))
                .font(.system(size: 36, weight: .bold))
                .foregroundStyle(.white)
        }
        CardView(label: "Bus & stop", systemImage: "bus.fill") {
            VStack(alignment: .leading, spacing: 4) {
                highlighted(plan.bus, changed: changedKeys.contains("bus"))
                    .font(.title2.weight(.semibold))
                    .foregroundStyle(.white)
                highlighted(plan.stop, changed: changedKeys.contains("stop"))
                    .font(.body)
                    .foregroundStyle(.white.opacity(0.7))
            }
        }
        HStack(spacing: 12) {
            CardView(label: "Walk instead", systemImage: "figure.walk") {
                highlighted("\(plan.walkingFallbackMinutes) min", changed: changedKeys.contains("walking_fallback_minutes"))
                    .font(.title.weight(.bold))
                    .foregroundStyle(.white)
            }
            CardView(label: "On time", systemImage: "checkmark.seal.fill") {
                highlighted("\(plan.probabilityPercent)%", changed: changedKeys.contains("on_time_probability"))
                    .font(.title.weight(.bold))
                    .foregroundStyle(.white)
            }
        }
        CardView(label: "Live on X", systemImage: "dot.radiowaves.left.and.right") {
            highlighted(plan.disruptionSummary, changed: changedKeys.contains("disruption_summary"))
                .font(.body)
                .foregroundStyle(.white.opacity(0.85))
        }
        CardView(label: "Why", systemImage: "text.alignleft") {
            Text(plan.reasoning)
                .font(.body)
                .foregroundStyle(.white.opacity(0.8))
        }

        Button {
            Task { await submit(recheck: true) }
        } label: {
            Label("Check again", systemImage: "arrow.clockwise")
                .font(.headline)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .foregroundStyle(GTTheme.navy)
                .background(GTTheme.gold, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        }
        .disabled(isLoading)
    }

    private func highlighted(_ text: String, changed: Bool) -> Text {
        Text(text)
            .underline(changed, color: GTTheme.gold)
    }

    private var composer: some View {
        VStack(spacing: 10) {
            HStack(spacing: 10) {
                TextField("I have class at Klaus at 9:30…", text: $question, axis: .vertical)
                    .lineLimit(1...4)
                    .padding(12)
                    .background(GTTheme.card, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .foregroundStyle(.white)
                Button {
                    toggleSpeech()
                } label: {
                    Image(systemName: isListening ? "mic.fill" : "mic")
                        .font(.title3)
                        .foregroundStyle(isListening ? GTTheme.navy : .white)
                        .frame(width: 44, height: 44)
                        .background(isListening ? GTTheme.gold : GTTheme.card, in: Circle())
                }
            }
            Button {
                Task { await submit(recheck: false) }
            } label: {
                Text("What's my move?")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .foregroundStyle(GTTheme.navy)
                    .background(GTTheme.gold, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
            .disabled(isLoading || question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .padding(16)
        .background(GTTheme.navy.opacity(0.92).ignoresSafeArea(edges: .bottom))
    }

    private func toggleSpeech() {
        guard let speech else { return }
        if isListening {
            speech.stop()
            isListening = false
        } else {
            speech.start()
            isListening = true
        }
    }

    @MainActor
    private func submit(recheck: Bool) async {
        isLoading = true
        errorText = nil
        do {
            let result = try await client.move(
                question: question,
                previous: recheck ? plan : nil
            )
            if recheck, let old = plan {
                changedKeys = diff(old, result)
            } else {
                changedKeys = []
            }
            previousPlan = plan
            plan = result
        } catch {
            errorText = error.localizedDescription
        }
        isLoading = false
    }

    @MainActor
    private func uploadSchedule(_ item: PhotosPickerItem) async {
        isLoading = true
        errorText = nil
        do {
            guard let data = try await item.loadTransferable(type: Data.self) else {
                throw APIError.decode
            }
            let result = try await client.uploadSchedule(image: data, filename: "schedule.jpg")
            dayPlan = result
            showSchedule = true
        } catch {
            errorText = error.localizedDescription
        }
        isLoading = false
        pickerItem = nil
    }

    private func diff(_ a: StingerPlan, _ b: StingerPlan) -> Set<String> {
        var keys = Set<String>()
        if a.leaveBy != b.leaveBy { keys.insert("leave_by") }
        if a.bus != b.bus { keys.insert("bus") }
        if a.stop != b.stop { keys.insert("stop") }
        if a.walkingFallbackMinutes != b.walkingFallbackMinutes { keys.insert("walking_fallback_minutes") }
        if abs(a.onTimeProbability - b.onTimeProbability) > 0.01 { keys.insert("on_time_probability") }
        if a.disruptionSummary != b.disruptionSummary { keys.insert("disruption_summary") }
        return keys
    }
}

struct ScheduleSheet: View {
    var dayPlan: DayPlanResponse

    var body: some View {
        NavigationStack {
            ZStack {
                GTTheme.ink.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        Text("Today’s leave-by plan")
                            .font(.system(.title2, design: .rounded).weight(.bold))
                            .foregroundStyle(.white)
                        ForEach(dayPlan.dayPlan) { item in
                            VStack(alignment: .leading, spacing: 10) {
                                Text(item.classInfo.name)
                                    .font(.system(.headline, design: .rounded))
                                    .foregroundStyle(GTTheme.gold)
                                Text("\(item.classInfo.startTime) · \(item.classInfo.building)")
                                    .font(.system(.subheadline, design: .rounded))
                                    .foregroundStyle(.white.opacity(0.7))
                                PlanSummary(plan: item.plan)
                            }
                        }
                    }
                    .padding(20)
                }
            }
            .navigationTitle("Schedule")
            .navigationBarTitleDisplayMode(.inline)
        }
        .preferredColorScheme(.dark)
    }
}

struct PlanSummary: View {
    var plan: StingerPlan

    var body: some View {
        CardView(label: "Leave by", systemImage: "clock.fill") {
            Text(plan.leaveBy)
                .font(.system(.title, design: .rounded).weight(.bold))
                .foregroundStyle(.white)
        }
        CardView(label: "Bus & stop", systemImage: "bus.fill") {
            VStack(alignment: .leading, spacing: 4) {
                Text(plan.bus)
                    .font(.system(.title3, design: .rounded).weight(.semibold))
                    .foregroundStyle(.white)
                Text(plan.stop)
                    .foregroundStyle(.white.opacity(0.7))
            }
        }
        if plan.usingRecentData {
            Text("Using recent data")
                .font(.system(.footnote, design: .rounded).weight(.semibold))
                .foregroundStyle(GTTheme.gold)
        }
    }
}

final class SpeechHelper {
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private let engine = AVAudioEngine()
    private let onText: (String) -> Void

    init(onText: @escaping (String) -> Void) {
        self.onText = onText
        SFSpeechRecognizer.requestAuthorization { _ in }
    }

    func start() {
        request = SFSpeechAudioBufferRecognitionRequest()
        guard let request, let recognizer else { return }
        let node = engine.inputNode
        let format = node.outputFormat(forBus: 0)
        node.removeTap(onBus: 0)
        node.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            request.append(buffer)
        }
        engine.prepare()
        try? engine.start()
        task = recognizer.recognitionTask(with: request) { [weak self] result, _ in
            if let text = result?.bestTranscription.formattedString {
                self?.onText(text)
            }
        }
    }

    func stop() {
        engine.stop()
        engine.inputNode.removeTap(onBus: 0)
        request?.endAudio()
        task?.cancel()
        task = nil
        request = nil
    }
}
