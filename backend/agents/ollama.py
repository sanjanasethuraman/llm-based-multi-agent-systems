from .base import AgentProvider
import json
from urllib import request, error
from ollama import chat, ChatResponse

class OllamaProvider(AgentProvider):
    name = "OllamaProvider"
    MAX_ITERATIONS = 10

    def run(self, config, incoming, available_tools):        
        name = config.get("name", "Agent")
        model = config.get("model", "llama3.2:1b")
        base_url = config.get("baseUrl", "http://127.0.0.1:11434").rstrip("/")
        messages = [{"role": "system", "content": config.get("systemPrompt", "You are a helpful assistant.")}]
        messages.append({"role": "user", "content": incoming})
        ollama_tools = [self.ollama_schema(tool) for tool in available_tools]
        tool_registry = {
            tool.name: tool for tool in available_tools
        }
        
        for _ in range(self.MAX_ITERATIONS):
            print(f"Calling Ollama model '{model}' with messages: {messages} and tools: {ollama_tools}")
            response: ChatResponse = chat(
                model=model,
                messages=messages,
                options={"temperature": float(config.get("temperature", 0.2))},
                tools=ollama_tools,
            )
            messages.append(response.message)
            if response.message.tool_calls:
                for tool_call in response.message.tool_calls:
                    print(f"Tool call: {tool_call.function.name} with arguments {tool_call.function.arguments}")
                    tool = tool_registry.get(tool_call.function.name)
                    if tool is None:
                        continue
                    result = tool.execute(**tool_call.function.arguments)
                    messages.append({
                        "role": "tool",
                        "name": tool_call.function.name,
                        "content": json.dumps({"result": result}),
                    })
            else:
                print("No tool calls, breaking out of loop.")
                break
        return response.message.content


    
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