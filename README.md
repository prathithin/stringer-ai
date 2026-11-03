# Stinger Assistant

iOS app that answers: **when should I leave to make it to class on time?**

SwiftUI → FastAPI → GT TransLoc + xAI Grok (function calling, live X search, structured JSON).

## Models

- **Chat / “what’s my move?”:** `grok-4.3` with `reasoning.effort = none`. It is the current fast, vision-capable Grok (aliases include the retired `grok-4-fast` slugs). Low latency for tool loops + X search.
- **Schedule screenshot (feature 2):** `grok-4.7`, the flagship vision-capable model.

## Run the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # paste XAI_API_KEY
uvicorn app:app --reload --host 127.0.0.1 --port 8765
```

The xAI key lives only in `backend/.env`. It is gitignored.

**Required:** paste a real `XAI_API_KEY` from [console.x.ai](https://console.x.ai). Until that is set, `/move` and screenshot vision cannot run — Grok calls are never faked. TransLoc is already live.

## Run the iOS app

This Mac currently has Command Line Tools only (no Xcode.app), so the simulator cannot be launched from here. On a machine with Xcode:

1. Start the backend on port 8765.
2. Open `ios/StingerAssistant.xcodeproj`.
3. Run on the **iOS Simulator** (localhost is the Mac). `NSAllowsLocalNetworking` is set for ATS.

## TransLoc

Live feed: `https://gatech.transloc.com/Services/JSONPRelay.svc` (`GetRoutes`, `GetStops`, `GetMapVehiclePoints`, `GetRouteStopArrivals`).

If no vehicles are reporting, arrivals come from `backend/data/transloc_snapshot.csv` (real Gold-route snapshot from the existing repo). The UI shows **Using recent data**.

ETA uncertainty is a **configured ±4 minutes** (`ETA_UNCERTAINTY_MINUTES`), labelled `CONFIGURED_DEFAULT` in code — not a trained model.

## Campus lookup

Hardcoded buildings: Klaus, Clough/CULC, CRC, Student Center, College of Computing, Howey, Instructional Center, Scheller. Default origin: West Village.
