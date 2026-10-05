"""Cap streamed request bodies before the multipart parser writes them to disk."""
from uuid import uuid4
from starlette.responses import JSONResponse


class RequestBodyLimit:
    def __init__(self, app, max_bytes=21 * 1024 * 1024):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('method') not in {'POST', 'PUT', 'PATCH'}:
            return await self.app(scope, receive, send)
        async def limit_response():
            request_id = scope.get('state', {}).get('request_id') or str(uuid4())
            response = JSONResponse({'error': {'code': 'REQUEST_TOO_LARGE', 'message': 'Yêu cầu vượt giới hạn upload PDF 20 MiB.', 'details': {}}, 'request_id': request_id}, status_code=413,
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
        # At most 21 MiB is retained, including multipart boundaries/metadata.
        messages = []
        size = 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            size += len(message.get('body', b''))
            if size > self.max_bytes:
                return await limit_response()
            messages.append(message)
            if not message.get('more_body', False):
                break
        index = 0

        async def buffered_receive():
            nonlocal index
            if index < len(messages):
                message = messages[index]
                index += 1
                return message
            return await receive()

        await self.app(scope, buffered_receive, send)
