"""Reference-compatible FastMCP mailbox exposed by every independent peer."""

from __future__ import annotations

import hashlib
import json
import queue
import threading
from collections import OrderedDict

import anyio
import uvicorn
from fastmcp import FastMCP

from police_thief.services.wire_trace import trace_wire

TOOL_SCHEMA_VERSION = "3.0.0"


class PeerInboxes:
    """Thread-safe inbound channels consumed by the local match runtime."""

    def __init__(self) -> None:
        self.agreements: queue.Queue[dict] = queue.Queue()
        self.turns: queue.Queue[dict] = queue.Queue()
        self.audits: queue.Queue[dict] = queue.Queue()
        self.controls: queue.Queue[dict] = queue.Queue()
        self._delivery_lock = threading.Lock()
        self._agreement_lock = threading.Lock()
        self._local_agreement: dict | None = None
        self._delivered: dict[str, OrderedDict[str, None]] = {
            "agreements": OrderedDict(),
            "turns": OrderedDict(),
            "audits": OrderedDict(),
        }

    def set_local_agreement(self, agreement: dict) -> None:
        with self._agreement_lock:
            self._local_agreement = dict(agreement)

    def local_agreement(self) -> dict | None:
        with self._agreement_lock:
            return dict(self._local_agreement) if self._local_agreement is not None else None

    def enqueue_once(self, inbox_name: str, payload: dict) -> bool:
        """Queue a retriable payload once and acknowledge safe redelivery.

        A turn's immutable commitment is its delivery identifier.  Transport
        metadata such as the timestamp may change when a peer retries the
        envelope, but that must not execute the sealed turn twice.
        """
        commit = payload.get("commit") if inbox_name == "turns" else None
        if isinstance(commit, str) and commit:
            fingerprint = f"commit:{commit}"
        else:
            canonical = json.dumps(
                payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
            ).encode()
            fingerprint = f"payload:{hashlib.sha256(canonical).hexdigest()}"
        with self._delivery_lock:
            delivered = self._delivered[inbox_name]
            if fingerprint in delivered:
                delivered.move_to_end(fingerprint)
                return False
            delivered[fingerprint] = None
            if len(delivered) > 2048:
                delivered.popitem(last=False)
            getattr(self, inbox_name).put(payload)
        return True


def build_peer_server(role: str, inboxes: PeerInboxes) -> FastMCP:
    """Expose the four tools used by the lecturer's v3 peer protocol."""
    mcp = FastMCP(name=f"police-thief-{role}")

    @mcp.tool(version=TOOL_SCHEMA_VERSION)
    def negotiate(message: dict) -> dict:
        """Receive signed terms and the opponent's public identity."""
        queued = inboxes.enqueue_once("agreements", message)
        trace_wire(
            direction="in", tool="negotiate", payload=message,
            result="accepted", queued=queued,
        )
        response = {"ok": True, "accepted": True, "kind": "negotiate", "errors": []}
        agreement = inboxes.local_agreement()
        if agreement is not None:
            response["agreement"] = agreement
        return response

    @mcp.tool(version=TOOL_SCHEMA_VERSION)
    def receive_turn(message: dict) -> dict:
        """Receive one public sealed turn; private truth remains committed."""
        queued = inboxes.enqueue_once("turns", message)
        trace_wire(
            direction="in", tool="receive_turn", payload=message,
            result="accepted", queued=queued,
        )
        return {"ok": True, "accepted": True, "kind": "turn", "errors": []}

    @mcp.tool(version=TOOL_SCHEMA_VERSION)
    def submit_audit(payload: dict) -> dict:
        """Receive end-of-game records and nonce reveals for verification."""
        queued = inboxes.enqueue_once("audits", payload)
        trace_wire(
            direction="in", tool="submit_audit", payload=payload,
            result="accepted", queued=queued,
        )
        return {"ok": True, "accepted": True, "kind": "audit", "errors": []}

    @mcp.tool(version=TOOL_SCHEMA_VERSION)
    def receive_control(message: dict) -> dict:
        """Receive enable, status, restart, or quit lifecycle messages."""
        inboxes.controls.put(message)
        trace_wire(
            direction="in", tool="receive_control", payload=message,
            result="accepted", queued=True,
        )
        return {"ok": True, "accepted": True, "kind": "control", "errors": []}

    return mcp


def run_peer_server(
    mcp: FastMCP, host: str, port: int, stop_event: threading.Event | None = None,
) -> None:
    """Run a peer server, optionally allowing a GUI session to stop it.

    FastMCP's synchronous ``run`` call owns Uvicorn until the process exits.
    GUI users can return to the game selector without exiting the process, so
    those sessions need an explicit shutdown path to release the listening
    port before the next network game starts.
    """
    if stop_event is None:
        mcp.run(transport="http", host=host, port=port, show_banner=False)
        return

    async def serve_until_stopped() -> None:
        app = mcp.http_app(path="/mcp", transport="http")
        config = uvicorn.Config(
            app, host=host, port=port, lifespan="on", ws="websockets-sansio",
            timeout_graceful_shutdown=2,
        )
        server = uvicorn.Server(config)

        def request_shutdown() -> None:
            stop_event.wait()
            server.should_exit = True

        watcher = threading.Thread(
            target=request_shutdown, daemon=True, name="mcp-peer-shutdown",
        )
        watcher.start()
        async with mcp._lifespan_manager():
            await server.serve()

    anyio.run(serve_until_stopped)
