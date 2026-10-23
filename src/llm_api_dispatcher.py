"""
Direct LLM API Dispatcher (MAN-009).
Formats and dispatches screenshot annotations directly to Anthropic Claude,
OpenAI GPT-4o, or Google Gemini vision APIs.
"""

from __future__ import annotations
import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from base64_data_uri_exporter import file_to_data_uri
except ImportError:
    from .base64_data_uri_exporter import file_to_data_uri

try:
    from enterprise_config import load_enterprise_config, is_cloud_egress_blocked
except ImportError:
    try:
        from .enterprise_config import load_enterprise_config, is_cloud_egress_blocked
    except Exception:
        load_enterprise_config = None
        is_cloud_egress_blocked = None


SUPPORTED_PROVIDERS = ("anthropic", "openai", "gemini")


class CloudEgressBlockedError(PermissionError):
    """
    Raised when cloud network egress is prohibited by Enterprise Air-Gapped Zero-Cloud policy.
    """
    pass


def is_cloud_egress_killswitch_active(
    config_path: Optional[Union[str, Path]] = None
) -> bool:
    """
    Returns True if cloud egress is blocked by enterprise air-gapped configuration.
    """
    if is_cloud_egress_blocked is not None:
        try:
            return is_cloud_egress_blocked(config_path)
        except Exception:
            pass
    if load_enterprise_config is not None:
        try:
            return load_enterprise_config(config_path).is_cloud_egress_blocked
        except Exception:
            pass
    return False


def check_cloud_egress_allowed(
    config_path: Optional[Union[str, Path]] = None,
    raise_on_blocked: bool = False
) -> bool:
    """
    Validates whether cloud egress is permitted.
    If egress is blocked and raise_on_blocked is True, raises CloudEgressBlockedError.
    Returns True if allowed, False if blocked.
    """
    if is_cloud_egress_killswitch_active(config_path):
        if raise_on_blocked:
            raise CloudEgressBlockedError(
                "Cloud egress blocked by Enterprise Air-Gapped Zero-Cloud policy."
            )
        return False
    return True


def get_api_key_for_provider(provider: str) -> Optional[str]:
    """Retrieves API key from environment variables."""
    prov = provider.lower().strip()
    if prov in ("anthropic", "claude"):
        return os.environ.get("ANTHROPIC_API_KEY")
    elif prov == "openai":
        return os.environ.get("OPENAI_API_KEY")
    elif prov == "gemini":
        return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    return None


def build_payload(
    provider: str,
    image_path: Union[str, Path],
    prompt: str,
    max_tokens: int = 2048
) -> Dict[str, Any]:
    """
    Constructs provider-specific API payload with embedded vision data.
    """
    prov = provider.lower().strip()
    data_uri = file_to_data_uri(image_path, max_dimension=1568)

    if prov in ("anthropic", "claude"):
        # Extract raw base64 and mime
        # data:image/png;base64,xxxx
        prefix, b64_data = data_uri.split(",", 1)
        media_type = prefix.split(";")[0].replace("data:", "")
        return {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64_data
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        }
    elif prov == "openai":
        return {
            "model": "gpt-4o",
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": data_uri,
                                "detail": "high"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        }
    elif prov == "gemini":
        prefix, b64_data = data_uri.split(",", 1)
        mime_type = prefix.split(";")[0].replace("data:", "")
        return {
            "contents": [
                {
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": b64_data
                            }
                        },
                        {
                            "text": prompt
                        }
                    ]
                }
            ]
        }
    else:
        raise ValueError(f"Unsupported provider: {provider}. Choose from: {SUPPORTED_PROVIDERS}")


def dispatch_to_llm(
    provider: str,
    image_path: Union[str, Path],
    prompt: str,
    api_key: Optional[str] = None,
    dry_run: bool = False,
    config_path: Optional[Union[str, Path]] = None,
    raise_on_blocked: bool = False,
) -> Dict[str, Any]:
    """
    Dispatches annotated image and prompt to target LLM provider API.
    Supports dry-run mode for offline verification without network calls.
    Enforces cloud egress killswitch when AirGappedMode / zero-cloud policy is active (ENT-004).
    """
    prov = provider.lower().strip()

    # Enforce Cloud Egress Killswitch when Air-Gapped / Zero-Cloud policy is active
    if is_cloud_egress_killswitch_active(config_path):
        if raise_on_blocked:
            raise CloudEgressBlockedError(
                "Cloud egress blocked by Enterprise Air-Gapped Zero-Cloud policy."
            )
        return {
            "status": "blocked",
            "provider": prov,
            "error": "Cloud egress blocked by Enterprise Air-Gapped Zero-Cloud policy.",
            "air_gapped_blocked": True,
        }
    payload = build_payload(prov, image_path, prompt)

    key = api_key or get_api_key_for_provider(prov)

    if dry_run or not key:
        return {
            "status": "simulated" if dry_run else "missing_key",
            "provider": prov,
            "payload_preview": {
                "model": payload.get("model", "gemini-vision"),
                "has_image": True,
                "prompt_length": len(prompt)
            },
            "response": f"[Simulated response from {prov}] Ready for analysis."
        }

    # Live network dispatch
    if prov in ("anthropic", "claude"):
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
    elif prov == "openai":
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {key}",
            "content-type": "application/json"
        }
    elif prov == "gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={key}"
        headers = {"content-type": "application/json"}
    else:
        raise ValueError(f"Unknown provider: {prov}")

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_body = resp.read().decode("utf-8")
            return {
                "status": "success",
                "provider": prov,
                "raw_response": json.loads(resp_body)
            }
    except Exception as e:
        return {
            "status": "error",
            "provider": prov,
            "error": str(e)
        }
