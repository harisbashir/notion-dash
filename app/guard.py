from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse


class RequestGuard(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
            origin = request.headers.get("Origin")
            if origin is None:
                origin = request.headers.get("Referer", "")
            try:
                parsed = urlsplit(origin)
                same_host = (
                    parsed.scheme in {"http", "https"}
                    and parsed.netloc.lower() == request.headers.get("Host", "").lower()
                    and parsed.username is None
                )
            except ValueError:
                same_host = False
            if request.headers.get("HX-Request") != "true" or not same_host:
                return PlainTextResponse("Forbidden", status_code=403)
        return await call_next(request)
