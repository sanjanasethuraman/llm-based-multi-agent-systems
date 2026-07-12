from .base import AgentProvider
import json
from ollama import chat, ChatResponse
import logging
import asyncio

logger = logging.getLogger(__name__)


def _coerce_think(value):
    """Interpret the Think option, tolerating legacy string values ("true"/"false")."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return bool(value)


class OllamaProvider(AgentProvider):
    name = "OllamaProvider"
    MAX_ITERATIONS = 10

    async def run(self, config, incoming, mcp_registry, available_tools: list[dict]):
        tool_calls = 0
        sub_agent_calls = 0
        called_tools = []
        provider_logs = []
        model = config.get("model", "llama3.2:1b")
        messages = [{"role": "system", "content": config.get("systemPrompt", "You are a helpful assistant.")}] 

        provider_logs.append({
            "status": "info",
            "message": f"Ollama provider using model '{model}' with {len(available_tools)} available tool(s).",
        })

        if isinstance(incoming, dict):
            parts = []
            for src, item in incoming.items():
                text = item.get("text") if isinstance(item, dict) else str(item)
                label = item.get("label") if isinstance(item, dict) else src
                ntype = item.get("type") if isinstance(item, dict) else "node"
                if text:
                    parts.append(f"From {label} ({ntype}, {src}):\n{text}")
            messages.append({
                "role": "user",
                "content": "\n\n".join(parts) or "Continue the workflow using the available context.",
            })
        else:
            # fallback for legacy string/list incoming formats
            if isinstance(incoming, str):
                messages.append({"role": "user", "content": incoming})
            else:
                try:
                    for part in incoming:
                        messages.append({"role": "user", "content": str(part)})
                except Exception:
                    messages.append({"role": "user", "content": str(incoming)})

        available = {(tool["server_id"], tool["tool_name"]) for tool in available_tools}
        logger.debug(f"available: {available}")
        ollama_tools = []
        tool_map = {}
        for server_id, client in mcp_registry.all_clients().items():
            for tool in await client.list_tools():
                logger.debug(f"available tool: {server_id}: {tool.name}")
                if (server_id, tool.name) in available:
                    ollama_tools.append(self._to_ollama_schema(tool))
                    tool_map[tool.name] = (server_id, client)
        
        think_enabled = _coerce_think(config.get("think", False))

        for _ in range(self.MAX_ITERATIONS):
            logger.info(f"{config.get('name')} calling Ollama model '{model}' with messages: {messages} and tools: {ollama_tools}")
            try:
                # Run the blocking Ollama call off the event loop so a slow or
                # stalled model does not freeze the whole backend.
                response: ChatResponse = await asyncio.to_thread(
                    chat,
                    model=model,
                    messages=messages,
                    options={"temperature": float(config.get("temperature", 0.2))},
                    tools=ollama_tools,
                    think=think_enabled,
                    stream=False,
                )
            except Exception as exc:
                logger.exception("Ollama chat call failed")
                hint = ""
                if think_enabled:
                    hint = (
                        f" Thinking mode is enabled, but model '{model}' may not support it. "
                        "Use a reasoning model (e.g. deepseek-r1, qwen3) or turn Think off."
                    )
                message = f"Ollama chat failed for model '{model}': {exc}.{hint}"
                provider_logs.append({"status": "error", "message": message})
                return f"[Ollama error] {message}", tool_calls, sub_agent_calls, called_tools, provider_logs
            logger.info(f"Response: {response}")
            messages.append(response.message)
            if response.message.tool_calls:
                for tool_call in response.message.tool_calls:
                    name = tool_call.function.name
                    logger.info(f"Tool call: {name} with arguments {tool_call.function.arguments}")
                    provider_logs.append({
                        "status": "info",
                        "message": f"Ollama requested tool '{name}' with arguments {json.dumps(tool_call.function.arguments or {})}.",
                    })
                    if name not in tool_map:
                        messages.append({
                            "role": "tool",
                            "name": name,
                            "content": json.dumps({"error": f"Tool {name} is not connected to this agent."}),
                        })
                        provider_logs.append({
                            "status": "warning",
                            "message": f"Ollama requested unknown tool '{name}'.",
                        })
                        continue
                    server_id, client = tool_map[name]
                    # Distinguish between normal tools and sub-agent tools by server id
                    if str(server_id).startswith("sub-agent-"):
                        sub_agent_calls += 1
                        provider_logs.append({
                            "status": "info",
                            "message": f"Ollama requested sub-agent tool '{name}' on server '{server_id}'.",
                        })
                    else:
                        tool_calls += 1
                        provider_logs.append({
                            "status": "info",
                            "message": f"Ollama requested tool '{name}' on server '{server_id}'.",
                        })

                    called_tools.append({
                        "server_id": server_id,
                        "tool_name": name,
                    })

                    try:
                        result = await asyncio.wait_for(
                            client.call_tool(name, tool_call.function.arguments or {}),
                            timeout=300.0
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"Tool call {name} timed out")
                        result = {"error": "Tool call timed out"}
                    
                    messages.append({
                        "role": "tool",
                        "name": tool_call.function.name,
                        "content": json.dumps({"result": result}),
                    })
            else:
                logger.info("No tool calls, breaking out of loop.")
                provider_logs.append({
                    "status": "info",
                    "message": "Ollama returned no tool calls.",
                })
                break
        content = (response.message.content or "").strip()
        if not content:
            provider_logs.append({
                "status": "warning",
                "message": "Ollama returned an empty message.",
            })
        return content, tool_calls, sub_agent_calls, called_tools, provider_logs
    
    def _to_ollama_schema(self, tool) -> dict:
        """Convert an MCP Tool object to Ollama's expected tool schema."""
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema,
            }
        }
