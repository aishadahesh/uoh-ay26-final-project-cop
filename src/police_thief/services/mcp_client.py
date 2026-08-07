"""Client transport for the four-tool peer protocol."""

from __future__ import annotations

import asyncio
import contextlib
import queue
import time

from fastmcp import Client

from police_thief.services.mcp_server import PeerInboxes


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
        sender: str = "police-thief-peer",
    ) -> None:
        self.opponent_url = opponent_url
        self.inboxes = inboxes
        self.connect_timeout = connect_timeout
        self.retry_interval = retry_interval
        self.sender = sender

    async def _call_async(self, tool: str, argument_name: str, payload: dict) -> dict:
        try:
            async with Client(
                self.opponent_url, name=self.sender, timeout=self.connect_timeout,
            ) as client:
                result = await client.call_tool(tool, {argument_name: payload})
        except Exception as exc:
            raise PeerClientError(
                f"failed to call {tool} at {self.opponent_url}: {exc}",
            ) from exc
        return result.data

    def _send(self, tool: str, argument_name: str, payload: dict, timeout: float) -> dict:
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                response = asyncio.run(self._call_async(tool, argument_name, payload))
                if response.get("ok") is True or response.get("accepted") is True:
                    return response
                raise PeerClientError(f"{tool} rejected by opponent: {response}")
            except PeerClientError as exc:
                last_error = exc
                time.sleep(self.retry_interval)
        raise PeerClientError(f"{tool} timed out: {last_error}")

    def exchange_agreement(self, message: dict, timeout: float) -> dict:
        response = self._send("negotiate", "message", message, timeout)
        required = {"identity", "nonce", "signature", "terms"}
        for candidate in (
            response.get("agreement"), response.get("message"), response,
        ):
            if isinstance(candidate, dict) and required <= set(candidate):
                return candidate
        try:
            return self.inboxes.agreements.get(timeout=timeout)
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

    def send_control(self, message: dict, timeout: float = 2.0) -> None:
        with contextlib.suppress(PeerClientError):
            self._send("receive_control", "message", message, timeout)

    def poll_control(self) -> dict | None:
        try:
            return self.inboxes.controls.get_nowait()
        except queue.Empty:
            return None
