from .base import AgentProvider
import json
from urllib import request, error
from ollama import chat, ChatResponse

class OllamaProvider(AgentProvider):
    name = "OllamaProvider"
    MAX_ITERATIONS = 10

    def run(self, config, incoming, available_tools):
        tool_calls = 0
        name = config.get("name", "Agent")
        model = config.get("model", "llama3.2:1b")
        base_url = config.get("baseUrl", "http://127.0.0.1:11434").rstrip("/")
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

        # available_tools now contains metadata dicts; extract tool objects
        ollama_tools = []
        tool_registry = {}
        for tool in available_tools:
            tool_obj = None
            if isinstance(tool, dict):
                tool_obj = tool.get("tool")
            else:
                tool_obj = tool
            if not tool_obj:
                continue
            ollama_tools.append(self.ollama_schema(tool_obj))
            tool_registry[tool_obj.name] = tool_obj
        
        for _ in range(self.MAX_ITERATIONS):
            print(f"Calling Ollama model '{model}' with messages: {messages} and tools: {ollama_tools}")
            response: ChatResponse = chat(
                model=model,
                messages=messages,
                options={"temperature": float(config.get("temperature", 0.2))},
                tools=ollama_tools,
                stream=False,
            )
            messages.append(response.message)
            if response.message.tool_calls:
                for tool_call in response.message.tool_calls:
                    tool_calls += 1
                    print(f"Tool call: {tool_call.function.name} with arguments {tool_call.function.arguments}")
                    tool = tool_registry.get(tool_call.function.name)
                    if tool is None:
                        continue
                    try:
                        result = tool.execute(**tool_call.function.arguments)
                    except TypeError:
                        args = tool_call.function.arguments or {}
                        if len(args) == 1:
                            result = tool.execute(list(args.values())[0])
                        else:
                            result = tool.execute(**args)
                    messages.append({
                        "role": "tool",
                        "name": tool_call.function.name,
                        "content": json.dumps({"result": result}),
                    })
            else:
                print("No tool calls, breaking out of loop.")
                break
        return response.message.content, tool_calls


    
    def build_llm_prompt(self, config, incoming):
        system_prompt = config.get("systemPrompt", "You are a helpful assistant.")
        return (
            f"System instructions:\n{system_prompt}\n\n"
            f"Workflow input:\n{incoming}\n\n"
            "Respond with the result for this agent node."
        )
    
    def ollama_schema(self, tool):
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
        }