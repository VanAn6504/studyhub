"""Cap streamed request bodies before the multipart parser writes them to disk."""
from uuid import uuid4
from tempfile import SpooledTemporaryFile
from starlette.responses import JSONResponse
from app.pdf_limits import MAX_REQUEST_BYTES, IO_BLOCK_BYTES


class RequestBodyLimit:
    def __init__(self, app, max_bytes=MAX_REQUEST_BYTES):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('method') not in {'POST', 'PUT', 'PATCH'}:
            return await self.app(scope, receive, send)
        async def limit_response():
            request_id = scope.get('state', {}).get('request_id') or str(uuid4())
            response = JSONResponse({'error': {'code': 'REQUEST_TOO_LARGE', 'message': 'PDF tối đa 100 MiB; toàn yêu cầu multipart tối đa 102 MiB.', 'details': {}}, 'request_id': request_id}, status_code=413,
                                    headers={'X-Request-ID': request_id, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
            await response(scope, receive, send)

        # Content-Length is only a fast path; chunked requests are counted too.
        headers = dict(scope.get('headers', []))
        try:
            length = int(headers.get(b'content-length', b'0'))
        except ValueError:
            length = 0
        if length > self.max_bytes:
            return await limit_response()
        # Bound the complete body before invoking FastAPI's parser. Exceptions
        # from receive can otherwise be translated to 400 by body parsing.
        # Spill after1MiB; never retain a100MiB body as a list of ASGI messages.
        with SpooledTemporaryFile(max_size=1024*1024, mode='w+b') as body:
            size = 0
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                block = message.get('body', b'')
                size += len(block)
                if size > self.max_bytes:
                    return await limit_response()
                body.write(block)
                if not message.get('more_body', False):
                    break
            body.seek(0)
            remaining = size
            async def buffered_receive():
                nonlocal remaining
                if remaining:
                    block = body.read(IO_BLOCK_BYTES)
                    remaining -= len(block)
                    return {'type':'http.request','body':block,'more_body':remaining>0}
                if size == 0:
                    return {'type':'http.request','body':b'','more_body':False}
                return await receive()
            await self.app(scope, buffered_receive, send)
