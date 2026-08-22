"""Client transport for the four-tool peer protocol."""

from __future__ import annotations

import asyncio
import contextlib
import queue
import time

from fastmcp import Client

from police_thief.services.mcp_server import PeerInboxes
from police_thief.services.wire_trace import trace_wire


class PeerClientError(RuntimeError):
    """Raised when the opponent cannot be reached within the deadline."""


async def send_move_async(
    opponent_url: str, signed_move: str, signature: str, timeout: float,
) -> dict:
    """Compatibility wrapper that transports an old envelope via receive_turn.

    New network matches use :class:`McpPeerTransport`; this remains only for
    the reliability-layer API while that layer is migrated independently.
    """
    try:
        async with Client(opponent_url, timeout=timeout) as client:
            result = await client.call_tool(
                "receive_turn",
                {"message": {"signed_move": signed_move, "signature": signature}},
            )
    except Exception as exc:
        raise PeerClientError(f"failed to reach opponent at {opponent_url}: {exc}") from exc
    data = result.data
    return {"accepted": bool(data.get("ok")), **data}


def send_move(
    opponent_url: str, signed_move: str, signature: str, timeout: float = 10.0,
) -> dict:
    return asyncio.run(send_move_async(opponent_url, signed_move, signature, timeout))


class McpPeerTransport:
    def __init__(
        self, opponent_url: str, inboxes: PeerInboxes,
        connect_timeout: float = 30.0, retry_interval: float = 1.0,
        boundary_retry_interval: float = 5.0,
        sender: str = "police-thief-peer",
    ) -> None:
        self.opponent_url = opponent_url
        self.inboxes = inboxes
        self.connect_timeout = connect_timeout
        self.retry_interval = retry_interval
        self.boundary_retry_interval = boundary_retry_interval
        self.sender = sender

    async def _call_async(self, tool: str, argument_name: str, payload: dict) -> dict:
        try:
            async with Client(
                self.opponent_url, name=self.sender, timeout=self.connect_timeout,
            ) as client:
                result = await client.call_tool(tool, {argument_name: payload})
        except Exception as exc:
            trace_wire(
                direction="out", tool=tool, peer=self.opponent_url,
                payload=payload, error=str(exc),
            )
            raise PeerClientError(
                f"failed to call {tool} at {self.opponent_url}: {exc}",
            ) from exc
        trace_wire(
            direction="out", tool=tool, peer=self.opponent_url,
            payload=payload, result="http-ok",
        )
        return result.data

    def _send(self, tool: str, argument_name: str, payload: dict, timeout: float) -> dict:
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                response = asyncio.run(self._call_async(tool, argument_name, payload))
            except PeerClientError as exc:
                last_error = exc
                time.sleep(self.retry_interval)
                continue
            if response.get("ok") is True or response.get("accepted") is True:
                trace_wire(
                    direction="out", tool=tool, peer=self.opponent_url,
                    payload=payload, result="accepted",
                )
                return response
            rejection = PeerClientError(f"{tool} rejected by opponent: {response}")
            trace_wire(
                direction="out", tool=tool, peer=self.opponent_url,
                payload=payload, result="rejected", error=str(response),
            )
            if self._is_boundary_retry(tool, response):
                last_error = rejection
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(self.boundary_retry_interval, remaining))
                continue
            raise rejection
        raise PeerClientError(f"{tool} timed out: {last_error}")

    @staticmethod
    def _is_boundary_retry(tool: str, response: dict) -> bool:
        """Retry only the peer's explicit temporary sub-game boundary refusal."""
        if tool != "negotiate":
            return False
        errors = response.get("errors", [])
        if isinstance(errors, str):
            errors = [errors]
        return isinstance(errors, list) and any(
            isinstance(error, str)
            and "mini-game is in progress" in error.casefold()
            and "boundary" in error.casefold()
            for error in errors
        )

    def exchange_agreement(self, message: dict, timeout: float) -> dict:
        deadline = time.monotonic() + timeout
        response = self._send("negotiate", "message", message, timeout)
        required = {"identity", "nonce", "signature", "terms"}
        for candidate in (
            response.get("agreement"), response.get("message"), response,
        ):
            if isinstance(candidate, dict) and required <= set(candidate):
                return candidate
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PeerClientError("opponent negotiation timed out")
        try:
            return self.inboxes.agreements.get(timeout=remaining)
        except queue.Empty as exc:
            raise PeerClientError("opponent negotiation timed out") from exc

    def send_turn(self, message: dict, timeout: float) -> None:
        self._send("receive_turn", "message", message, timeout)

    def receive_turn(self, timeout: float) -> dict:
        try:
            return self.inboxes.turns.get(timeout=timeout)
        except queue.Empty as exc:
            raise PeerClientError("opponent turn timed out") from exc

    def exchange_audit(self, payload: dict, timeout: float) -> dict:
        self._send("submit_audit", "payload", payload, timeout)
        try:
            return self.inboxes.audits.get(timeout=timeout)
        except queue.Empty as exc:
            raise PeerClientError("opponent audit timed out") from exc

    def send_audit(self, payload: dict, timeout: float) -> None:
        self._send("submit_audit", "payload", payload, timeout)

    def send_control(self, message: dict, timeout: float = 2.0) -> None:
        with contextlib.suppress(PeerClientError):
            self._send("receive_control", "message", message, timeout)

    def poll_control(self) -> dict | None:
        try:
            return self.inboxes.controls.get_nowait()
        except queue.Empty:
            return None
