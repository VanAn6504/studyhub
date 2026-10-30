"""Synthetic large files and exact byte boundaries; never modify real course data."""
import asyncio
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import text

from pypdf import PdfWriter

from test_learning import P, login, pdf_bytes, private_pdf_storage


def large_pdf():
    writer=PdfWriter()
    writer.add_blank_page(width=400,height=500)
    writer.add_attachment('synthetic-padding.txt',b'x'*(21*1024*1024))
    out=io.BytesIO();writer.write(out)
    return out.getvalue()


def test_large_pdf_create_version_replace_and_document_classification(client,seeded):
    h=login(client,seeded,'teacher')
    course=client.get(f'{P}/courses').json()['items'][0]
    data=large_pdf()
    response=client.post(f"{P}/courses/{course['id']}/documents",headers=h,data={'code':'BOOK','title':'Giáo trình','document_type':'textbook','show_in_learning':'false'},files={'file':('book.pdf',data,'application/pdf')})
    assert response.status_code==201,response.text
    doc=response.json();v=doc['versions'][0]
    assert doc['document_type']=='textbook' and not doc['show_in_learning']
    assert v['byte_size']==len(data) and v['sha256']==hashlib.sha256(data).hexdigest()
    version=client.post(f"{P}/documents/{doc['id']}/versions",headers=h,files={'file':('book-v2.pdf',data,'application/pdf')})
    assert version.status_code==201 and version.json()['version']==2
    assert client.get(f"{P}/document-versions/{v['id']}/content").status_code==200
    replacement=client.put(f"{P}/documents/{doc['id']}/file",headers=h,data={'code':'BOOK','title':'Giáo trình mới'},files={'file':('replacement.pdf',data,'application/pdf')})
    assert replacement.status_code==200 and len(replacement.json()['versions'])==1
    assert replacement.json()['document_type']=='textbook'
    assert client.get(f"{P}/document-versions/{v['id']}/content").status_code==404
    assert client.patch(f"{P}/documents/{doc['id']}",headers=h,json={'document_type':'supplement','show_in_learning':True}).json()['document_type']=='supplement'
    assert client.patch(f"{P}/documents/{doc['id']}",headers=h,json={'document_type':'invalid'}).status_code==422


def test_2000_pdf_pages_and_source_mapping_boundaries(client,seeded):
    h=login(client,seeded,'teacher');run=client.get(f'{P}/course-runs').json()['items'][0]
    r=client.post(f"{P}/courses/{run['course_id']}/documents",headers=h,data={'code':'LONG','title':'2000 pages'},files={'file':('long.pdf',pdf_bytes(2000),'application/pdf')})
    assert r.status_code==201,r.text
    d=r.json();v=d['versions'][0]['id']
    assert client.patch(f"{P}/documents/{d['id']}",headers=h,json={'status':'published'}).status_code==200
    topic=client.get(f"{P}/courses/{run['course_id']}/topics").json()['items'][0]
    assert client.put(f"{P}/topics/{topic['id']}/materials",headers=h,json={'items':[{'document_version_id':v,'page_start':1999,'page_end':2000,'order_index':1}]}).status_code==200
    question={'code':'Q2000','stem':'Trang cuối','options':dict(A='A',B='B',C='C',D='D'),'correct_option':'A','explanation':'Nguồn','sources':[{'document_version_id':v,'pdf_page':2000}]}
    assert client.post(f"{P}/topics/{topic['id']}/questions",headers=h,json=question).status_code==201
    question['code']='Q2001';question['sources'][0]['pdf_page']=2001
    assert client.post(f"{P}/topics/{topic['id']}/questions",headers=h,json=question).status_code==422


def test_streamed_request_lies_do_not_bypass_actual_byte_limit():
    from app.upload_limit import RequestBodyLimit
    async def scenario(length):
        called=[];messages=[]
        async def downstream(*_):called.append(True)
        parts=iter([{'type':'http.request','body':b'x'*60,'more_body':True},{'type':'http.request','body':b'y'*60,'more_body':False}])
        async def receive():return next(parts)
        async def send(message):messages.append(message)
        scope={'type':'http','method':'POST','headers':([] if length is None else [(b'content-length',length)])}
        await RequestBodyLimit(downstream,max_bytes=100)(scope,receive,send)
        assert not called and messages[0]['status']==413
    for length in (None,b'1',b'invalid'):
        asyncio.run(scenario(length))


def test_migration_roundtrip_preserves_old_rows_and_blocks_lossy_downgrade(client,seeded,database):
    h=login(client,seeded,'teacher');course=client.get(f'{P}/courses').json()['items'][0]
    doc=client.post(f"{P}/courses/{course['id']}/documents",headers=h,data={'code':'OLD','title':'Old metadata'},files={'file':('old.pdf',pdf_bytes(),'application/pdf')}).json()
    tables=('users','courses','course_runs','enrollments','topics','documents','document_versions')
    def snapshot():
        with database.connect() as db:
            return {t:db.execute(text('SELECT to_jsonb(r)'+(" - 'document_type' - 'show_in_learning'" if t=='documents' else '')+' FROM '+t+' r ORDER BY id')).scalars().all() for t in tables}
    before=snapshot()
    def migrate(*args):
        env=os.environ.copy();env['DATABASE_URL']=env['TEST_DATABASE_URL']
        return subprocess.run([sys.executable,'-m','alembic',*args],cwd=Path(__file__).resolve().parents[1],env=env,capture_output=True,text=True,encoding='utf-8')
    try:
        down=migrate('downgrade','0009_website_p0');assert down.returncode==0,down.stderr
        up=migrate('upgrade','head');assert up.returncode==0,up.stderr
        assert snapshot()==before
        with database.begin() as db:
            db.execute(text('UPDATE document_versions SET page_count=2000 WHERE document_id=:id'),{'id':doc['id']})
        down=migrate('downgrade','0009_website_p0')
        assert down.returncode!=0 and 'Downgrade blocked' in down.stderr
        with database.connect() as db:
            assert db.scalar(text('SELECT page_count FROM document_versions WHERE document_id=:id'),{'id':doc['id']})==2000
            assert db.scalar(text('SELECT version_num FROM alembic_version'))=='0010_large_pdf'
    finally:
        up=migrate('upgrade','head');assert up.returncode==0,up.stderr
