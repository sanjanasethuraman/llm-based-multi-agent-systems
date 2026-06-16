import json
import os
from urllib import error, parse, request

from .base import AgentProvider


DEFAULT_HF_BASE_URL = "https://api-inference.huggingface.co"
DEFAULT_HF_ROUTER_URL = "https://router.huggingface.co/v1"
DEFAULT_HF_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"


class HuggingFaceProvider(AgentProvider):
    name = "huggingface"

    async def run(self, config, incoming, mcp_client, available_tools):
        name = config.get("name", "Agent")
        model = config.get("model") or DEFAULT_HF_MODEL
        token = get_huggingface_token(config)
        base_url = normalize_huggingface_base_url(config.get("baseUrl"))
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": config.get("systemPrompt", "You are a helpful assistant."),
                },
                {"role": "user", "content": incoming},
            ],
            "temperature": float(config.get("temperature", 0.2)),
            "max_tokens": int(config.get("maxNewTokens") or 512),
        }

        if not token:
            return (
                f"[{name} | huggingface unavailable]\n"
                "No Hugging Face token was configured. Add a token in the agent settings "
                "or set HF_TOKEN / HUGGING_FACE_API_TOKEN before starting the server."
            )

        try:
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
            text = parse_huggingface_chat_completion(result)
            return text or f"[{name} | huggingface] Empty response from {model}."
        except error.HTTPError as exc:
            detail = read_error_detail(exc)
            return (
                f"[{name} | huggingface error]\n"
                f"Model: {model}\n"
                f"HTTP {exc.code}: {detail}"
            )
        except error.URLError as exc:
            return (
                f"[{name} | huggingface unavailable]\n"
                f"Could not reach Hugging Face Inference API for model {model}.\n"
                f"Details: {exc}"
            )
        except Exception as exc:
            return f"[{name} | huggingface error]\n{exc}"


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
