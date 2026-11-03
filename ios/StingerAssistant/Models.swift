import Foundation

struct StingerPlan: Codable, Equatable {
    var leaveBy: String
    var bus: String
    var stop: String
    var walkingFallbackMinutes: Int
    var onTimeProbability: Double
    var disruptionSummary: String
    var reasoning: String
    var usingRecentData: Bool
    var saferMode: Bool
    var model: String?

    enum CodingKeys: String, CodingKey {
        case leaveBy = "leave_by"
        case bus, stop
        case walkingFallbackMinutes = "walking_fallback_minutes"
        case onTimeProbability = "on_time_probability"
        case disruptionSummary = "disruption_summary"
        case reasoning
        case usingRecentData = "using_recent_data"
        case saferMode = "safer_mode"
        case model
    }

    var probabilityPercent: Int {
        Int((onTimeProbability * 100).rounded())
    }
}

struct ExtractedClass: Codable, Identifiable, Equatable {
    var name: String
    var building: String
    var startTime: String
    var endTime: String
    var isExamOrQuiz: Bool

    var id: String { "\(name)-\(startTime)" }

    enum CodingKeys: String, CodingKey {
        case name, building
        case startTime = "start_time"
        case endTime = "end_time"
        case isExamOrQuiz = "is_exam_or_quiz"
    }
}

struct DayPlanItem: Codable, Identifiable, Equatable {
    var classInfo: ExtractedClass
    var plan: StingerPlan

    var id: String { classInfo.id }

    enum CodingKeys: String, CodingKey {
        case classInfo = "class"
        case plan
    }
}

struct DayPlanResponse: Codable, Equatable {
    var classes: [ExtractedClass]
    var dayPlan: [DayPlanItem]

    enum CodingKeys: String, CodingKey {
        case classes
        case dayPlan = "day_plan"
    }
}
