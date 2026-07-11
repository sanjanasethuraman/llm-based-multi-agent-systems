import json, os, logging, time
from urllib import error, parse, request

from backend.mcp_registry import McpClientRegistry
from .base import AgentProvider

logger = logging.getLogger(__name__)
DEFAULT_HF_BASE_URL = "https://api-inference.huggingface.co"
DEFAULT_HF_ROUTER_URL = "https://router.huggingface.co/v1"
DEFAULT_HF_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"

MAX_ITERATIONS = 10

class HuggingFaceProvider(AgentProvider):
    name = "huggingface"

    async def run(self, config, incoming, mcp_registry: McpClientRegistry, available_tools):
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
        name = config.get("name", "Agent")
        model = config.get("model") or DEFAULT_HF_MODEL
        token = get_huggingface_token(config)
        base_url = normalize_huggingface_base_url(config.get("baseUrl"))

        if not token:
            return (
                f"[{name} | huggingface unavailable]\n"
                "No Hugging Face token was configured. Add a token in the agent settings "
                "or set HF_TOKEN / HUGGING_FACE_API_TOKEN before starting the server.",
                stats
            )
        provider_logs.append({
            "status": "info",
            "message": f"Hugging Face provider using model '{model}' with {len(available_tools)} available tool(s).",
        })

        # build messages
        messages = [{"role": "system", "content": config.get("systemPrompt", "You are a helpful assistant.")}]
        if isinstance(incoming, dict):
            msg_type = "user"
            for src, item in incoming.items():
                text = item.get("text") if isinstance(item, dict) else str(item)
                ntype = item.get("type") if isinstance(item, dict) else None
                if ntype == "input":    msg_type = "user"
                elif ntype == "agent":  msg_type = "assistant"
                elif ntype == "tool":   msg_type = "tool"
            messages.append({"role": msg_type, "content": text})
        else:
            if isinstance(incoming, str):
                messages.append({"role": "user", "content": incoming})
            else:
                try:
                    for part in incoming:
                        messages.append({"role": "user", "content": str(part)})
                except Exception:
                    messages.append({"role": "user", "content": str(incoming)})

        # build tool map from registry — same as OllamaProvider
        available = {(t["server_id"], t["tool_name"]) for t in available_tools}
        hf_tools = []
        tool_map = {}
        for server_id, client in mcp_registry.all_clients().items():
            for tool in await client.list_tools():
                if (server_id, tool.name) in available:
                    hf_tools.append(self._to_hf_schema(tool))
                    tool_map[tool.name] = (server_id, client)

        last_response = None

        for _ in range(MAX_ITERATIONS):
            payload = {
                "model": model,
                "messages": messages,
                "temperature": float(config.get("temperature", 0.2)),
                "max_tokens": int(config.get("maxNewTokens") or 1024),
                "reasoning_effort": "none"
            }
            if hf_tools:
                payload["tools"] = hf_tools
                payload["tool_choice"] = "auto"

            logger.info(f"{name} calling HuggingFace model '{model}'")

            try:
                start = time.perf_counter()
                data = json.dumps(payload).encode("utf-8")
                req = request.Request(
                    f"{base_url}/chat/completions",
                    data=data,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with request.urlopen(req, timeout=120) as response:
                    result = json.loads(response.read().decode("utf-8"))
                end = time.perf_counter()
                total_duration += int((end-start) * 1_000_000_000)
            except error.HTTPError as exc:
                detail = read_error_detail(exc)
                return f"[{name} | huggingface error] HTTP {exc.code}: {detail}", stats
            except Exception as exc:
                    return f"[{name} | huggingface error] {exc}", stats

            if not result.get("choices"):
                return f"[{name} | huggingface] Empty response.", stats

            logger.info(f"Huggingface response: {result}")
            choice = result["choices"][0]
            message = choice.get("message", {})
            last_response = message.get("content") or ""
            input_tokens += result["usage"]["prompt_tokens"]
            output_tokens += result["usage"]["completion_tokens"]

            # append assistant message
            messages.append({"role": "assistant", "content": last_response, "tool_calls": message.get("tool_calls")})

            calls = message.get("tool_calls") or []
            if not calls:
                logger.info("No tool calls, breaking out of loop.")
                provider_logs.append({
                    "status": "info",
                    "message": "Hugging Face returned no tool calls.",
                })
                break

            # process tool calls
            for tc in calls:
                fn = tc.get("function", {})
                tool_name = fn.get("name")
                provider_logs.append({
                        "status": "info",
                        "message": f"Hugging Face requested tool '{tool_name}' with arguments {json.dumps(fn.get('arguments') or {})}.",
                    })
                try:
                    arguments = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    arguments = {}

                logger.info(f"Tool call: {tool_name} with arguments {arguments}")

                if tool_name not in tool_map:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", tool_name),
                        "content": json.dumps({"error": f"Tool {tool_name} is not connected to this agent."}),
                    })
                    provider_logs.append({
                            "status": "warning",
                            "message": f"Hugging Face requested unknown tool '{tool_name}'.",
                        })
                    continue

                server_id, client = tool_map[tool_name]
                if str(server_id).startswith("sub-agent-"):
                    sub_agent_calls += 1
                    provider_logs.append({
                            "status": "info",
                            "message": f"Hugging Face requested sub-agent tool '{tool_name}' on server '{server_id}'.",
                        })
                else:
                    tool_calls += 1
                    provider_logs.append({
                            "status": "info",
                            "message": f"Hugging Face requested tool '{tool_name}' on server '{server_id}'.",
                        })

                called_tools.append({
                    "server_id": server_id,
                    "tool_name": tool_name,
                })

                tool_result = await client.call_tool(tool_name, arguments)
                logger.info(f"Tool result: {tool_result}")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", tool_name),
                    "content": json.dumps({"result": tool_result}),
                })
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
        return last_response, stats

    def _to_hf_schema(self, tool) -> dict:
        """Convert an MCP Tool object to HuggingFace's expected tool schema."""
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema,
            }
        }


def get_huggingface_token(config=None):
    config = config or {}
    token = (
        config.get("huggingFaceToken")
        or config.get("hfToken")
        or os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGING_FACE_API_TOKEN")
        or ""
    ).strip()
    if token.lower().startswith("bearer "):
        return token[7:].strip()
    return token


def normalize_huggingface_base_url(base_url=None):
    endpoint = (base_url or DEFAULT_HF_ROUTER_URL).rstrip("/")
    if endpoint == DEFAULT_HF_BASE_URL:
        return DEFAULT_HF_ROUTER_URL
    return endpoint


def parse_huggingface_chat_completion(result):
    if isinstance(result, dict):
        if result.get("error"):
            raise ValueError(result["error"])
        choices = result.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            return str(message.get("content") or choices[0].get("text") or "").strip()
    return ""


def stringify_incoming(incoming):
    if isinstance(incoming, dict):
        parts = []
        for item in incoming.values():
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
            elif item:
                parts.append(str(item))
        return "\n\n".join(parts)
    return str(incoming or "")


def check_huggingface_status(model=None, token=None, base_url=None):
    account_token = normalize_huggingface_token(token) or get_huggingface_token()
    endpoint = normalize_huggingface_base_url(base_url)
    status = {
        "available": False,
        "baseUrl": endpoint,
        "model": model or "",
        "tokenConfigured": bool(account_token),
        "account": None,
        "modelAvailable": False,
        "message": "",
    }

    if not account_token:
        status["message"] = "No Hugging Face token configured."
        return status

    headers = {"Authorization": f"Bearer {account_token}"}
    try:
        account_req = request.Request(
            "https://huggingface.co/api/whoami-v2",
            headers=headers,
            method="GET",
        )
        with request.urlopen(account_req, timeout=8) as response:
            account = json.loads(response.read().decode("utf-8"))
        status["account"] = account.get("name") or account.get("fullname") or "linked"
        status["available"] = True
    except error.HTTPError as exc:
        status["message"] = f"Token check failed with HTTP {exc.code}: {read_error_detail(exc)}"
        return status
    except Exception as exc:
        status["message"] = str(exc)
        return status

    if not model:
        status["message"] = "Hugging Face account linked."
        return status

    try:
        model_req = request.Request(
            f"https://huggingface.co/api/models/{parse.quote(model, safe='/')}",
            headers=headers,
            method="GET",
        )
        with request.urlopen(model_req, timeout=8) as response:
            model_info = json.loads(response.read().decode("utf-8"))
        status["modelAvailable"] = True
        status["pipelineTag"] = model_info.get("pipeline_tag")
        status["message"] = "Hugging Face account and model linked."
    except error.HTTPError as exc:
        status["message"] = f"Account linked, but model check failed with HTTP {exc.code}: {read_error_detail(exc)}"
    except Exception as exc:
        status["message"] = f"Account linked, but model check failed: {exc}"
    return status


def read_error_detail(exc):
    try:
        body = exc.read().decode("utf-8")
        payload = json.loads(body)
        return payload.get("error") or payload.get("message") or body
    except Exception:
        return str(exc)


def normalize_huggingface_token(token):
    token = (token or "").strip()
    if token.lower().startswith("bearer "):
        return token[7:].strip()
    return token
