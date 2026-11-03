"""Grok (xAI) function-calling loop with live X search and structured JSON."""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

from openai import OpenAI

from campus import BUILDINGS, DEFAULT_ORIGIN, resolve_building, walking_fallback_minutes
from transloc import get_arrivals, get_uncertainty

CHAT_MODEL = "grok-4.3"
VISION_MODEL = "grok-4.7"

# grok-4.3: current fast chat + vision-capable model (aliases include grok-4-fast).
# reasoning_effort=none keeps latency low for the live "what's my move?" loop.
# grok-4.7: flagship, used for schedule screenshot vision when that path is hit.

EASTERN = ZoneInfo("America/New_York")

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "leave_by": {
            "type": "string",
            "description": "Clock time the student should walk to the stop, e.g. 9:12 AM",
        },
        "bus": {
            "type": "string",
            "description": "Recommended Stinger route name, or Walk if bus is not the pick",
        },
        "stop": {
            "type": "string",
            "description": "Board at this stop",
        },
        "walking_fallback_minutes": {
            "type": "integer",
            "description": "Door-to-door walk time if they skip the bus",
        },
        "on_time_probability": {
            "type": "number",
            "description": "0-1 chance of arriving on time given the ETA uncertainty range",
        },
        "disruption_summary": {
            "type": "string",
            "description": "One line on disruptions, or 'No live disruptions found'",
        },
        "reasoning": {
            "type": "string",
            "description": "Short plain-language why this is the move",
        },
        "using_recent_data": {
            "type": "boolean",
            "description": "True when TransLoc had no live vehicles and snapshot data was used",
        },
        "safer_mode": {
            "type": "boolean",
            "description": "True when the class is an exam/quiz and the safer option was chosen",
        },
    },
    "required": [
        "leave_by",
        "bus",
        "stop",
        "walking_fallback_minutes",
        "on_time_probability",
        "disruption_summary",
        "reasoning",
        "using_recent_data",
        "safer_mode",
    ],
    "additionalProperties": False,
}

TOOLS = [
    {"type": "x_search", "from_date": date.today().isoformat()},
    {
        "type": "function",
        "name": "get_arrivals",
        "description": "Live (or recent snapshot) Stinger arrivals for a stop name substring, e.g. 'Klaus Building', 'West Village', 'Student Center'.",
        "parameters": {
            "type": "object",
            "properties": {
                "stop_name": {
                    "type": "string",
                    "description": "Stop name or fragment used by GT TransLoc",
                }
            },
            "required": ["stop_name"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_building_info",
        "description": "Nearest Stinger stop and walking minutes from that stop to a GT building. Also returns a campus walking-fallback time from a named origin (default West Village).",
        "parameters": {
            "type": "object",
            "properties": {
                "building": {
                    "type": "string",
                    "description": "Building name such as Klaus, Clough, CRC, Student Center",
                },
                "origin": {
                    "type": "string",
                    "description": "Where the student is now. Default West Village.",
                },
            },
            "required": ["building"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_uncertainty",
        "description": "ETA uncertainty range in minutes for a Stinger route (Gold, Red, Blue, Green, Clough).",
        "parameters": {
            "type": "object",
            "properties": {
                "route": {"type": "string", "description": "Route name or id"}
            },
            "required": ["route"],
            "additionalProperties": False,
        },
    },
]


FUNCTION_TOOLS = [t for t in TOOLS if t["type"] == "function"]


def xai_key() -> str:
    key = (os.getenv("XAI_API_KEY") or "").strip()
    if not key or key == "xai-your-key-here":
        return ""
    return key


def _client() -> OpenAI:
    key = xai_key()
    if not key:
        raise RuntimeError("XAI_API_KEY is not set in backend/.env")
    return OpenAI(api_key=key, base_url="https://api.x.ai/v1", timeout=40.0)


def _get_building_info(building: str, origin: str | None = None) -> dict:
    info = resolve_building(building)
    origin = origin or DEFAULT_ORIGIN
    if not info:
        return {
            "error": f"Unknown building '{building}'",
            "known_buildings": [v["name"] for v in BUILDINGS.values()],
        }
    return {
        "building": info["name"],
        "nearest_stop": info["nearest_stop"],
        "walk_from_stop_minutes": info["walk_from_stop_minutes"],
        "origin": origin,
        "walking_fallback_minutes": walking_fallback_minutes(origin, info["id"]),
    }


def _run_tool(name: str, args: dict) -> dict:
    if name == "get_arrivals":
        return get_arrivals(args.get("stop_name", ""))
    if name == "get_building_info":
        return _get_building_info(args.get("building", ""), args.get("origin"))
    if name == "get_uncertainty":
        return get_uncertainty(args.get("route", ""))
    return {"error": f"Unknown tool {name}"}


def _system_prompt(now: datetime) -> str:
    return f"""You are Stinger Assistant for Georgia Tech students.
Current local time: {now.strftime("%A %Y-%m-%d %I:%M %p %Z")}.

Always call get_building_info, get_arrivals (origin stop AND destination stop), and get_uncertainty before answering.
Call every needed tool in parallel on the first turn. Keep disruption_summary to one sentence; use "No live disruptions found" unless a tool result says otherwise.

Assume origin is West Village if the student does not say where they are.

Compute leave_by as: class start minus (bus ETA to origin stop wait? NO: time to walk to the boarding stop + wait until the bus + ride + walk from alighting stop to building), with a 2 minute buffer.
If they are already near the destination, walking may be better.

on_time_probability: treat the bus ETA as a uniform range of ETA ± uncertainty minutes. Probability that (leave now following this plan) arrives by class time. Clamp to [0.05, 0.99].

If the class is an exam or quiz, pick the safer option even if slower (usually walking, or an earlier bus). Set safer_mode true.

If using_recent_data is true in any tool result, set using_recent_data true in the final JSON.

Final answer MUST match the JSON schema. Do not chat in prose.
"""


def _extract_output_text(response) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text
    chunks = []
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) != "message":
            continue
        for part in getattr(item, "content", None) or []:
            t = getattr(part, "text", None) or getattr(part, "input_text", None)
            if t:
                chunks.append(t)
    return "".join(chunks)


_PLAN_TEXT_FORMAT = {
    "format": {
        "type": "json_schema",
        "name": "stinger_plan",
        "strict": True,
        "schema": PLAN_SCHEMA,
    }
}


def plan_from_question(question: str) -> dict:
    client = _client()
    now = datetime.now(EASTERN)

    # Two Grok round-trips max. Live X search is the timeout source — skipped.
    response = client.responses.create(
        model=CHAT_MODEL,
        reasoning={"effort": "none"},
        instructions=_system_prompt(now),
        input=[{"role": "user", "content": question}],
        tools=FUNCTION_TOOLS,
        tool_choice="required",
        parallel_tool_calls=True,
    )

    used_recent = False
    fn_calls = [
        item
        for item in (response.output or [])
        if getattr(item, "type", None) == "function_call"
    ]
    outputs = []
    for item in fn_calls:
        args = json.loads(item.arguments or "{}")
        result = _run_tool(item.name, args)
        if result.get("using_recent_data"):
            used_recent = True
        outputs.append(
            {
                "type": "function_call_output",
                "call_id": item.call_id,
                "output": json.dumps(result),
            }
        )
    if not outputs:
        outputs = [
            {
                "role": "user",
                "content": "Return the plan JSON now from campus knowledge and any tool results.",
            }
        ]

    response = client.responses.create(
        model=CHAT_MODEL,
        reasoning={"effort": "none"},
        previous_response_id=response.id,
        input=outputs,
        text=_PLAN_TEXT_FORMAT,
    )
    raw = _extract_output_text(response).strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.find("{") :]
    data = json.loads(raw)
    if used_recent:
        data["using_recent_data"] = True
    data["model"] = CHAT_MODEL
    return data


def schedule_from_image(image_b64: str, mime: str = "image/png") -> dict:
    """Vision path for feature 2 — structured class list from a screenshot."""
    client = _client()
    schema = {
        "type": "object",
        "properties": {
            "classes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "building": {"type": "string"},
                        "start_time": {"type": "string"},
                        "end_time": {"type": "string"},
                        "is_exam_or_quiz": {"type": "boolean"},
                    },
                    "required": [
                        "name",
                        "building",
                        "start_time",
                        "end_time",
                        "is_exam_or_quiz",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["classes"],
        "additionalProperties": False,
    }
    response = client.responses.create(
        model=VISION_MODEL,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Extract each class from this Georgia Tech schedule screenshot as JSON.",
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:{mime};base64,{image_b64}",
                    },
                ],
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "class_schedule",
                "strict": True,
                "schema": schema,
            }
        },
    )
    return json.loads(_extract_output_text(response))
