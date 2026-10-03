"""按当前生效的跨域白名单处理 CORS：白名单写进 runtime.json 后无需重启即生效。"""
from __future__ import annotations

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.runtime import runtime_store

ALL_METHODS = ("DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT")


class RuntimeCORSMiddleware:
    """语义与 Starlette CORSMiddleware 一致（credentials=true、方法和头不限），
    区别是白名单每次请求都读当前生效值，runtime.json 改了下一个请求就按新名单放行。"""

    def __init__(self, app: ASGIApp, max_age: int = 600) -> None:
        self.app = app
        self.max_age = max_age

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        origin = headers.get("origin")
        if origin is None:
            await self.app(scope, receive, send)
            return

        origins = runtime_store.get().allowed_origins
        allowed = "*" in origins or origin in origins

        if scope["method"] == "OPTIONS" and "access-control-request-method" in headers:
            if not allowed:
                await self.app(scope, receive, send)
                return
            response_headers = {
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": ", ".join(ALL_METHODS),
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Max-Age": str(self.max_age),
                "Vary": "Origin",
            }
            requested_headers = headers.get("access-control-request-headers")
            if requested_headers:
                response_headers["Access-Control-Allow-Headers"] = requested_headers
            response = PlainTextResponse("OK", status_code=200, headers=response_headers)
            await response(scope, receive, send)
            return

        if not allowed:
            await self.app(scope, receive, send)
            return

        async def send_with_cors(message: Message) -> None:
            if message["type"] == "http.response.start":
                out = MutableHeaders(scope=message)
                out["Access-Control-Allow-Credentials"] = "true"
                out["Access-Control-Allow-Origin"] = origin
                out.add_vary_header("Origin")
            await send(message)

        await self.app(scope, receive, send_with_cors)
