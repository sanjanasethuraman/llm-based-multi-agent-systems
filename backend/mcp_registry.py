import json
import time


MOCK_MCP_TOOLS = {
    "demo.weather": {
        "server": "demo",
        "name": "weather",
        "description": "Returns deterministic weather-like context for a city.",
        "schema": {"city": "string", "unit": "celsius|fahrenheit"},
    },
    "demo.lookup": {
        "server": "demo",
        "name": "lookup",
        "description": "Returns a deterministic project note for a topic.",
        "schema": {"topic": "string"},
    },
    "demo.score": {
        "server": "demo",
        "name": "score",
        "description": "Scores text with a deterministic presentation-readiness rubric.",
        "schema": {"text": "string"},
    },
}


def list_mcp_tools():
    return [
        {"id": tool_id, **metadata}
        for tool_id, metadata in sorted(MOCK_MCP_TOOLS.items())
    ]


def call_mcp_tool(tool_id, arguments=None, incoming=""):
    if tool_id not in MOCK_MCP_TOOLS:
        raise ValueError(f"MCP tool '{tool_id}' is not registered.")

    args = normalize_arguments(arguments)
    if tool_id == "demo.weather":
        city = args.get("city") or "Berlin"
        unit = args.get("unit") or "celsius"
        suffix = "C" if unit == "celsius" else "F"
        temperature = 18 if unit == "celsius" else 64
        result = f"Weather for {city}: {temperature}{suffix}, light wind, good conditions for a field demo."
    elif tool_id == "demo.lookup":
        topic = args.get("topic") or incoming or "visual multi-agent systems"
        result = (
            f"Lookup result for {topic}: emphasize visual orchestration, transparent execution, "
            "and provider/tool modularity."
        )
    elif tool_id == "demo.score":
        text = args.get("text") or incoming
        words = len(str(text).split())
        score = min(100, 60 + words)
        result = f"Presentation readiness score: {score}/100. Basis: {words} words of input context."
    else:
        result = f"MCP tool {tool_id} executed."

    return {
        "toolId": tool_id,
        "arguments": args,
        "result": result,
        "timestamp": round(time.time(), 3),
    }


def normalize_arguments(arguments):
    if isinstance(arguments, dict):
        return dict(arguments)
    if not arguments:
        return {}
    if isinstance(arguments, str):
        parsed = json.loads(arguments)
        if not isinstance(parsed, dict):
            raise ValueError("MCP arguments must be a JSON object.")
        return parsed
    raise ValueError("MCP arguments must be a JSON object.")
