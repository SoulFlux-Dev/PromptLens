"""
Generic Local IPC Socket and Webhook Interface (ROB-007, ENT-005).
Provides a lightweight localhost HTTP/JSON API server allowing third-party
integrations (Stream Deck, OBS, scripts, automation harnesses) to trigger captures.
Includes security policy enforcement and disable toggles for high-security environments (ENT-005).
"""

from __future__ import annotations
import json
import socket
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

try:
    from enterprise_config import is_local_ipc_allowed
except ImportError:
    try:
        from .enterprise_config import is_local_ipc_allowed
    except Exception:
        is_local_ipc_allowed = None


DEFAULT_IPC_PORT = 15710


class LocalIpcDisabledError(PermissionError):
    """Raised when local IPC webhook server is prohibited by enterprise security policy (ENT-005)."""
    pass


def is_ipc_server_permitted(config_path: Optional[Union[str, Path]] = None) -> bool:
    """
    Checks enterprise configuration to determine if local IPC webhook server is permitted.
    Returns False if DisableLocalIPC=True or AllowLocalNetwork=False.
    """
    if is_local_ipc_allowed is not None:
        try:
            return bool(is_local_ipc_allowed(config_path))
        except Exception:
            pass
    try:
        from enterprise_config import load_enterprise_config
        return bool(load_enterprise_config(config_path).is_local_ipc_allowed)
    except Exception:
        return True


class IpcRequestHandler(BaseHTTPRequestHandler):
    """Handles incoming localhost webhook triggers."""
    def log_message(self, format: str, *args: Any) -> None:
        pass  # Suppress standard console access logs

    def _send_json(self, status_code: int, data: Dict[str, Any]) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        server: IpcServer = self.server  # type: ignore
        if getattr(server, "enforce_security_policy", True) and not is_ipc_server_permitted(getattr(server, "config_path", None)):
            self._send_json(403, {
                "error": "Forbidden",
                "message": "Local IPC webhook interface is disabled by enterprise security policy.",
                "blocked": True,
            })
            return

        if self.path in ("/api/status", "/status"):
            status_data = server.get_status()
            self._send_json(200, status_data)
        else:
            self._send_json(404, {"error": "Not Found"})

    def do_POST(self) -> None:
        server: IpcServer = self.server  # type: ignore
        if getattr(server, "enforce_security_policy", True) and not is_ipc_server_permitted(getattr(server, "config_path", None)):
            self._send_json(403, {
                "error": "Forbidden",
                "message": "Local IPC webhook interface is disabled by enterprise security policy.",
                "blocked": True,
            })
            return

        content_len = int(self.headers.get("Content-Length", 0))
        post_data = {}
        if content_len > 0:
            try:
                raw = self.rfile.read(content_len).decode("utf-8")
                post_data = json.loads(raw)
            except Exception:
                pass

        action = self.path.lstrip("/").replace("api/", "")
        result = server.dispatch_action(action, post_data)
        self._send_json(200, result)


class IpcServer(HTTPServer):
    """Specialized localhost HTTPServer with action routing and enterprise policy gating."""
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = DEFAULT_IPC_PORT,
        config_path: Optional[Union[str, Path]] = None,
        enforce_security_policy: bool = True,
    ):
        self.config_path = config_path
        self.enforce_security_policy = enforce_security_policy
        if self.enforce_security_policy and not is_ipc_server_permitted(self.config_path):
            raise LocalIpcDisabledError(
                "Local IPC webhook server is disabled by high-security enterprise policy (ENT-005)."
            )
        super().__init__((host, port), IpcRequestHandler)
        self.action_handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self.status_provider: Optional[Callable[[], Dict[str, Any]]] = None

    def register_action(self, action: str, handler: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
        self.action_handlers[action.lower()] = handler

    def dispatch_action(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        act = action.lower()
        if act in self.action_handlers:
            return self.action_handlers[act](params)
        return {"status": "dispatched", "action": action, "params": params}

    def get_status(self) -> Dict[str, Any]:
        if self.status_provider:
            return self.status_provider()
        return {
            "status": "online",
            "service": "PromptLens IPC",
            "version": "1.0.0",
            "ipc_enabled": True,
        }


class IpcServerThread:
    """Manages background thread lifecycle for IpcServer with enterprise policy gating."""
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = DEFAULT_IPC_PORT,
        config_path: Optional[Union[str, Path]] = None,
        enforce_security_policy: bool = True,
    ):
        self.host = host
        self.port = port
        self.config_path = config_path
        self.enforce_security_policy = enforce_security_policy
        self.server: Optional[IpcServer] = None
        self.thread: Optional[threading.Thread] = None
        self.is_disabled: bool = False
        self.error: Optional[str] = None

    def start(self) -> bool:
        if self.enforce_security_policy and not is_ipc_server_permitted(self.config_path):
            self.is_disabled = True
            self.error = "Local IPC webhook server is disabled by high-security enterprise policy (ENT-005)."
            return False
        try:
            self.server = IpcServer(
                self.host,
                self.port,
                config_path=self.config_path,
                enforce_security_policy=self.enforce_security_policy,
            )
            if self.port == 0:
                self.port = self.server.server_address[1]
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            return True
        except Exception as e:
            self.error = str(e)
            return False

    def stop(self) -> None:
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
            self.server = None


def create_ipc_server_thread(
    host: str = "127.0.0.1",
    port: int = DEFAULT_IPC_PORT,
    config_path: Optional[Union[str, Path]] = None,
    enforce_security_policy: bool = True,
) -> Optional[IpcServerThread]:
    """
    Factory helper to create and start an IpcServerThread only if permitted by security policy.
    Returns running IpcServerThread or None if disabled by enterprise policy or failed.
    """
    thread = IpcServerThread(
        host=host,
        port=port,
        config_path=config_path,
        enforce_security_policy=enforce_security_policy,
    )
    if thread.start():
        return thread
    return None


def send_ipc_trigger(
    action: str,
    port: int = DEFAULT_IPC_PORT,
    payload: Optional[Dict[str, Any]] = None,
    config_path: Optional[Union[str, Path]] = None,
    enforce_security_policy: bool = True,
    timeout: float = 2.0,
) -> Dict[str, Any]:
    """Client utility sending a webhook command to the local recorder."""
    if enforce_security_policy and not is_ipc_server_permitted(config_path):
        return {
            "error": "Local IPC webhook interface is disabled by enterprise security policy.",
            "blocked": True,
            "status": "disabled",
        }

    url = f"http://127.0.0.1:{port}/api/{action}"
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"error": f"HTTP {e.code}", "status_code": e.code}
    except Exception as e:
        return {"error": str(e), "status": "failed"}
