#!/usr/bin/env python3
"""A tiny OpenAI-compatible provider used only for the SpendWarden demo.

It answers the first request with a ``wallet_send`` tool call for $5.00. After
Hermes returns the tool result (which SpendWarden should have blocked), it
answers with a short final message. No model, no network, no funds.
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = "spendwarden-mock"
PAY_TO = "0x1111111111111111111111111111111111111111"
TOOL_ARGS = json.dumps(
    {
        "command": (
            "cast send 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 "
            '\"transfer(address,uint256)\" '
            f"{PAY_TO} 5000000 --rpc-url http://127.0.0.1:8545"
        )
    },
    separators=(",", ":"),
)


def _chunk(delta: dict, finish: str | None = None) -> dict:
    return {
        "id": "chatcmpl-spendwarden",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": MODEL,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        print("mock:", fmt % args, flush=True)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/v1/models":
            self._json(200, {"object": "list", "data": [{"id": MODEL, "object": "model"}]})
        else:
            self._json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            request = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            request = {}
        messages = request.get("messages") or []
        has_tool_result = any(message.get("role") == "tool" for message in messages)
        stream = bool(request.get("stream"))

        if not request.get("tools") and not has_tool_result:
            # Auxiliary calls (titles, compression) must not receive a tool call.
            if stream:
                self._stream_text("ok")
            else:
                self._json(
                    200,
                    {
                        "id": "chatcmpl-spendwarden",
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": MODEL,
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": "ok"},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                    },
                )
            return

        if has_tool_result:
            tool_messages = [m for m in messages if m.get("role") == "tool"]
            detail = str(tool_messages[-1].get("content") or "").strip() if tool_messages else ""
            text = "SpendWarden blocked the transfer before the payment tool ran."
            if detail:
                text += f"\n\nTool result:\n{detail}"
            if stream:
                self._stream_text(text)
            else:
                self._json(
                    200,
                    {
                        "id": "chatcmpl-spendwarden",
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": MODEL,
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": text},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                    },
                )
            return

        tool_call = {
            "id": "call_spendwarden_1",
            "type": "function",
            "function": {"name": "terminal", "arguments": TOOL_ARGS},
        }
        if stream:
            self._stream_tool_call(tool_call)
        else:
            self._json(
                200,
                {
                    "id": "chatcmpl-spendwarden",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": MODEL,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [tool_call],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                },
            )

    def _start_stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

    def _send(self, payload: dict) -> None:
        self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
        self.wfile.flush()

    def _done(self) -> None:
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _stream_tool_call(self, tool_call: dict) -> None:
        self._start_stream()
        self._send(_chunk({"role": "assistant", "content": None}))
        self._send(
            _chunk(
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": tool_call["id"],
                            "type": "function",
                            "function": tool_call["function"],
                        }
                    ]
                }
            )
        )
        self._send(_chunk({}, "tool_calls"))
        self._done()

    def _stream_text(self, text: str) -> None:
        self._start_stream()
        self._send(_chunk({"role": "assistant", "content": ""}))
        self._send(_chunk({"content": text}))
        self._send(_chunk({}, "stop"))
        self._done()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"mock provider on http://127.0.0.1:{args.port}/v1", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
