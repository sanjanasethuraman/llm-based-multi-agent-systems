from backend.agents.proxy_tool_client import ProxyToolClient

from .base import AgentProvider
import json
from ollama import chat, ChatResponse
import logging
import asyncio

logger = logging.getLogger(__name__)

class OllamaProvider(AgentProvider):
    name = "OllamaProvider"
    MAX_ITERATIONS = 10

    async def run(self, config, incoming, mcp_registry, available_tools: list[dict]):
        stats = {
            "toolCalls": 0,
            "subAgentCalls": 0,
            "calledTools": [],
            "providerLogs": [],
            "totalDuration": 0,
            "inputTokens": 0,
            "outputTokens": 0,
        }
        sub_agent_stats = {}
        tool_calls = 0
        sub_agent_calls = 0
        called_tools = []
        provider_logs = []
        total_duration = 0
        input_tokens = 0
        output_tokens = 0
        model = config.get("model", "llama3.2:1b")
        messages = [{"role": "system", "content": config.get("systemPrompt", "You are a helpful assistant.")}] 

        provider_logs.append({
            "status": "info",
            "message": f"Ollama provider using model '{model}' with {len(available_tools)} available tool(s).",
        })

        if isinstance(incoming, dict):
            role_type = "user"
            text = ""
            for src, item in incoming.items():
                text = item.get("text") if isinstance(item, dict) else str(item)
                label = item.get("label") if isinstance(item, dict) else None
                ntype = item.get("type") if isinstance(item, dict) else None
                if ntype == "input":
                    role_type = "user"
                elif ntype == "agent":
                    role_type = "assistant"
                elif ntype == "tool":
                    role_type = "tool"
            messages.append({"role": role_type, "content": text})
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
        tool_map = {str : (str, ProxyToolClient)}
        for server_id, client in mcp_registry.all_clients().items():
            for tool in await client.list_tools():
                logger.debug(f"available tool: {server_id}: {tool.name}")
                if (server_id, tool.name) in available:
                    ollama_tools.append(self._to_ollama_schema(tool))
                    tool_map[tool.name] = (server_id, client)
        
        for _ in range(self.MAX_ITERATIONS):
            logger.info(f"{config.get('name')} calling Ollama model '{model}' with messages: {messages} and tools: {ollama_tools}")
            response: ChatResponse = chat(
                model=model,
                messages=messages,
                options={"temperature": float(config.get("temperature", 0.2))},
                tools=ollama_tools,
                think=config.get("think", False),
                stream=False,
            )
            logger.info(f"Response: {response}")
            
            total_duration += response.total_duration
            input_tokens += response.prompt_eval_count
            output_tokens += response.eval_count

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
                        raw = await asyncio.wait_for(
                            client.call_tool(name, tool_call.function.arguments or {}),
                            timeout=300.0
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"Tool call {name} timed out")
                        raw = {"error": "Tool call timed out"}

                    if isinstance(raw, str):
                        try:
                            parsed = json.loads(raw)
                            if isinstance(parsed, dict) and "text" in parsed and "stats" in parsed:
                                raw = parsed
                        except (json.JSONDecodeError, TypeError):
                            pass

                    if isinstance(raw, dict) and "stats" in raw:
                        sub_stats = raw["stats"]
                        tool_calls += sub_stats.get("toolCalls", 0)
                        sub_agent_calls += sub_stats.get("subAgentCalls", 0) + 1
                        called_tools.extend(sub_stats.get("calledTools", []))
                        provider_logs.extend(sub_stats.get("providerLogs", []))
                        sub_agent_stats.setdefault(server_id, {
                            "totalDuration": 0,
                            "inputTokens": 0,
                            "outputTokens": 0,
                        })

                        sub_agent_stats[server_id]["totalDuration"] += sub_stats.get("totalDuration", 0)
                        sub_agent_stats[server_id]["inputTokens"] += sub_stats.get("inputTokens", 0)
                        sub_agent_stats[server_id]["outputTokens"] += sub_stats.get("outputTokens", 0)
                       
                        result_text = raw.get("result", "")
                        provider_logs.append({
                            "status": "info",
                            "message": f"Sub-agent '{name}' completed with {sub_stats.get('toolCalls', 0)} tool call(s) and {sub_stats.get('subAgentCalls', 0)} sub-agent call(s).",
                        })
                    elif isinstance(raw, dict) and "error" in raw:
                        result_text = json.dumps(raw)
                    else:
                        result_text = str(raw) if raw is not None else ""
                    
                    messages.append({
                        "role": "tool",
                        "name": tool_call.function.name,
                        "content": json.dumps({"result": result_text}),
                    })
            else:
                logger.info("No tool calls, breaking out of loop.")
                provider_logs.append({
                    "status": "info",
                    "message": "Ollama returned no tool calls.",
                })
                break
        stats.update({
            "toolCalls": tool_calls,
            "subAgentCalls": sub_agent_calls,
            "calledTools": called_tools,
            "providerLogs": provider_logs,
            "totalDuration": total_duration,
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "subAgentStats": sub_agent_stats | {}
        })
        return response.message.content, stats
    
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
