import Foundation

enum APIError: LocalizedError {
    case badURL
    case server(String)
    case decode

    var errorDescription: String? {
        switch self {
        case .badURL: return "Could not reach the local backend."
        case .server(let m): return m
        case .decode: return "The assistant returned an unexpected shape."
        }
    }
}

actor APIClient {
    // Simulator talks to the Mac. ATS allows local networking via Info.plist.
    static let baseURL = URL(string: "http://127.0.0.1:8765")!

    func move(question: String, previous: StingerPlan?) async throws -> StingerPlan {
        var req = URLRequest(url: Self.baseURL.appendingPathComponent("move"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 90
        var body: [String: Any] = ["question": question]
        if let previous {
            let data = try JSONEncoder().encode(previous)
            body["previous_plan"] = try JSONSerialization.jsonObject(with: data)
        }
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await URLSession.shared.data(for: req)
        guard let http = response as? HTTPURLResponse else { throw APIError.badURL }
        if http.statusCode >= 400 {
            throw APIError.server(Self.errorMessage(from: data, status: http.statusCode))
        }
        do {
            return try JSONDecoder().decode(StingerPlan.self, from: data)
        } catch {
            throw APIError.decode
        }
    }

    func uploadSchedule(image: Data, filename: String) async throws -> DayPlanResponse {
        var req = URLRequest(url: Self.baseURL.appendingPathComponent("schedule"))
        req.httpMethod = "POST"
        req.timeoutInterval = 180
        let boundary = "Boundary-\(UUID().uuidString)"
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
        body.append(image)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        req.httpBody = body
        let (data, response) = try await URLSession.shared.data(for: req)
        guard let http = response as? HTTPURLResponse else { throw APIError.badURL }
        if http.statusCode >= 400 {
            throw APIError.server(Self.errorMessage(from: data, status: http.statusCode))
        }
        do {
            return try JSONDecoder().decode(DayPlanResponse.self, from: data)
        } catch {
            throw APIError.decode
        }
    }

    private static func errorMessage(from data: Data, status: Int) -> String {
        if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            if let detail = obj["detail"] as? String { return detail }
            if let detail = obj["detail"] as? [[String: Any]] {
                return detail.compactMap { $0["msg"] as? String }.joined(separator: " ")
            }
        }
        return String(data: data, encoding: .utf8) ?? "HTTP \(status)"
    }
}
