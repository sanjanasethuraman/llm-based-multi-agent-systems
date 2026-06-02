from .base import AgentProvider
import json
from urllib import request, error

class OllamaProvider(AgentProvider):
    name = "OllamaProvider"

    def run(self, config, incoming):        
        name = config.get("name", "Agent")
        model = config.get("model", "llama3.2:1b")
        base_url = config.get("baseUrl", "http://127.0.0.1:11434").rstrip("/")
        prompt = self.build_llm_prompt(config, incoming)
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": float(config.get("temperature", 0.2))},
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = request.Request(
                f"{base_url}/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(req, timeout=90) as response:
                result = json.loads(response.read().decode("utf-8"))
            return result.get("response", "").strip() or f"[{name} | ollama] Empty response from {model}."
        except error.URLError as exc:
            return (
                f"[{name} | ollama unavailable]\n"
                f"Could not reach Ollama at {base_url} for model {model}.\n"
                "Start Ollama and pull the model, for example: ollama pull llama3.2:1b\n"
                f"Details: {exc}"
            )
        except Exception as exc:
            return f"[{name} | ollama error]\n{exc}"


    
    def build_llm_prompt(self, config, incoming):
        system_prompt = config.get("systemPrompt", "You are a helpful assistant.")
        return (
            f"System instructions:\n{system_prompt}\n\n"
            f"Workflow input:\n{incoming}\n\n"
            "Respond with the result for this agent node."
        )