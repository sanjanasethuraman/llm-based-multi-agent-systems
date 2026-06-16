from .base import AgentProvider
import json
import asyncio
from urllib import request, error
from ollama import chat, ChatResponse
from backend.mcp_registry import McpClientRegistry

class OllamaProvider(AgentProvider):
    name = "OllamaProvider"
    MAX_ITERATIONS = 10

    async def run(self, config, incoming, mcp_registry: McpClientRegistry, available_tools: list[dict]):
        tool_calls = 0
        model = config.get("model", "llama3.2:1b")
        messages = [{"role": "system", "content": config.get("systemPrompt", "You are a helpful assistant.")}] 

        if isinstance(incoming, dict):
            type = "user"
            for src, item in incoming.items():
                text = item.get("text") if isinstance(item, dict) else str(item)
                label = item.get("label") if isinstance(item, dict) else None
                ntype = item.get("type") if isinstance(item, dict) else None
                if ntype == "input":
                    type = "user"
                elif ntype == "agent":
                    type = "assistant"
                elif ntype == "tool":
                    type = "tool"
            messages.append({"role": type, "content": text})
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
        ollama_tools = []
        tool_map = {}
        for server_id, client in mcp_registry.all_clients().items():
            for tool in await client.list_tools():
                if (server_id, tool.name) in available:
                    ollama_tools.append(self._to_ollama_schema(tool))
                    tool_map[tool.name] = (server_id, client)
        
        for _ in range(self.MAX_ITERATIONS):
            print(f"Calling Ollama model '{model}' with messages: {messages} and tools: {ollama_tools}")
            response: ChatResponse = chat(
                model=model,
                messages=messages,
                options={"temperature": float(config.get("temperature", 0.2))},
                tools=ollama_tools,
                think=config.get("think", False),
                stream=False,
            )
            messages.append(response.message)
            if response.message.tool_calls:
                for tool_call in response.message.tool_calls:
                    tool_calls += 1
                    name = tool_call.function.name
                    print(f"Tool call: {name} with arguments {tool_call.function.arguments}")
                    if name not in tool_map:
                        print(f"Tool '{name}' not in available tools, skipping.")
                        messages.append({
                            "role": "tool",
                            "name": name,
                            "content": json.dumps({"error": f"Tool {name} is not connected to this agent."}),
                        })
                        continue
                    server_id, client = tool_map[name]
                    result = await client.call_tool(name, tool_call.function.arguments or {})
                    
                    messages.append({
                        "role": "tool",
                        "name": tool_call.function.name,
                        "content": json.dumps({"result": result}),
                    })
            else:
                print("No tool calls, breaking out of loop.")
                break
        return response.message.content, tool_calls
    
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