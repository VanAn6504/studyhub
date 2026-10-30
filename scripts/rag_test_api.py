"""TEST ONLY: real API/worker/encoder with a loopback Gemini contract fixture."""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


def main():
    assert urlparse(os.environ['DATABASE_URL']).path.endswith('_test'),'Only isolated test databases are permitted'
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
    # The image runs from/app; the local runner runs from the repository.
    sys.path.insert(0,'/app' if Path('/app/app').is_dir() else str(Path.cwd()))
    from pydantic import SecretStr
    from app import chat_provider
    from app.config import get_settings
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_POST(self):
            try:
                assert self.headers.get('x-goog-api-key')=='synthetic-contract-key'
                length=int(self.headers['Content-Length']);assert length<100000
                request=json.loads(self.rfile.read(length))
                data=json.loads(request['contents'][0]['parts'][0]['text'])
                assert 1<=len(data['SOURCES'])<=4
                source=data['SOURCES'][0]
                quote=source['text'].strip()[:300]
                result={'status':'answered','answer':'Theo nguồn kiểm thử, chuẩn hóa giúp các đặc trưng có đơn vị so sánh phù hợp khi tính khoảng cách. Hãy mở trang trích dẫn để đối chiếu.','evidence':[{'chunk_id':source['chunk_id'],'quote':quote}]}
                body=json.dumps({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(result)}]}}]}).encode()
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            except Exception:
                self.send_error(500,'Invalid synthetic contract')
    provider=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=provider.serve_forever,daemon=True).start()
    chat_provider.GEMINI_ORIGIN=f'http://127.0.0.1:{provider.server_port}'
    settings=get_settings();settings.chat_provider='gemini';settings.gemini_api_key=SecretStr('synthetic-contract-key');settings.gemini_model='contract-only'
    import uvicorn
    try:uvicorn.run('app.main:app',host=os.environ.get('TEST_API_BIND','127.0.0.1'),port=int(os.environ.get('TEST_API_PORT','8000')))
    finally:provider.shutdown();provider.server_close()

if __name__=='__main__':main()
