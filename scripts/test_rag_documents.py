"""Nginx + FastAPI + PostgreSQL + actual local encoder; synthetic PDF/provider.

Only newly created _test data and named disposable containers are modified.
The existing localhost website/database/PDF volume is never used for UI writes.
"""
from datetime import datetime
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request

from dotenv import dotenv_values
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject,DictionaryObject,NameObject
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url

sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_website import available_port

ROOT=Path(__file__).resolve().parents[1]

def pdf(path,texts,padding=0):
    writer=PdfWriter()
    for value in texts:
        page=writer.add_blank_page(width=500,height=500)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        stream=DecodedStreamObject();stream.set_data(('BT /F1 12 Tf 20 400 Td ('+value+') Tj ET').encode('ascii'))
        page[NameObject('/Contents')]=writer._add_object(stream)
    if padding:writer.add_attachment('synthetic-padding.bin',b'x'*padding)
    with path.open('wb') as target:writer.write(target)

def main():
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--skip-build',action='store_true');parser.add_argument('--keep-db',action='store_true');args=parser.parse_args()
    def docker(*command,**kwargs):return subprocess.run(['docker',*command],cwd=ROOT,check=True,**kwargs)
    if not args.skip_build:docker('compose','build','backend','frontend')
    db_container=docker('compose','ps','-q','postgres',capture_output=True,text=True).stdout.strip()
    network=next(iter(json.loads(docker('inspect','--format','{{json .NetworkSettings.Networks}}',db_container,capture_output=True,text=True).stdout)))
    config=dotenv_values(ROOT/'.env');source=make_url(config['DATABASE_URL']).set(host='127.0.0.1')
    stamp=datetime.now().strftime('%Y%m%d%H%M%S')+'_'+secrets.token_hex(3)
    database='studyhub_rag_'+stamp+'_test';assert database.endswith('_test') and database.replace('_','').isalnum()
    out=ROOT/'.local/pdf-rag-20261030/runs'/stamp;out.mkdir(parents=True)
    fixtures=out/'fixtures';fixtures.mkdir();(out/'pdfs').mkdir()
    normalization='Feature normalization scales numerical data before nearest neighbors distance comparisons so features share comparable units.'
    pdf(fixtures/'large-book.pdf',['Textbook cover']+[normalization]*11,padding=21*1024*1024)
    pdf(fixtures/'scan.pdf',['Scanned title',''])
    pdf(fixtures/'slide.pdf',['Slide cover','K nearest neighbors assigns the label using nearby training examples.'])
    assert (ROOT/'.local/embedding/manifest.json').is_file(),'Prepare the local embedding model first.'
    model=out/'model';model.mkdir()
    for name in ('model.onnx','tokenizer.json','manifest.json'):shutil.copyfile(ROOT/'.local/embedding'/name,model/name)
    engine=create_engine(source.set(database='postgres'),isolation_level='AUTOCOMMIT')
    with engine.connect() as db:db.execute(text('CREATE DATABASE '+database))
    port=available_port();origin=f'http://127.0.0.1:{port}'
    settings={'DATABASE_URL':source.set(database=database).render_as_string(hide_password=False),'JWT_SECRET':secrets.token_hex(32),'ALLOWED_ORIGINS':origin,'COOKIE_SECURE':'false',
        'AUTH_RATE_LIMIT':'1000','CHAT_PROVIDER':'disabled','RAG_WORKER_ENABLED':'true','RAG_POLL_SECONDS':'.2','RAG_PAGE_BATCH_SIZE':'2','RAG_EMBEDDING_BATCH_SIZE':'2',
        'BOOTSTRAP_TEACHER_EMAIL':'teacher.rag@example.com','BOOTSTRAP_TEACHER_PASSWORD':secrets.token_urlsafe(24),'BOOTSTRAP_TEACHER_DISPLAY_NAME':'Giảng viên RAG',
        'DEMO_STUDENT_EMAIL':'student.rag@example.com','DEMO_STUDENT_PASSWORD':secrets.token_urlsafe(24),'DEMO_STUDENT_DISPLAY_NAME':'Sinh viên RAG',
        'COURSE_RUN_CODE':'RAG_TEST','COURSE_RUN_START_DATE':'2026-10-30','PDF_STORAGE_PATH':str(out/'pdfs'),'PYTHONIOENCODING':'utf-8'}
    (out/'environment.json').write_text(json.dumps(settings),encoding='utf-8')
    env=os.environ.copy();env.update(settings)
    containers=[];passed=False
    try:
        for command in (['-m','alembic','upgrade','head'],['-m','app.seed']):subprocess.run([sys.executable,*command],cwd=ROOT/'backend',env=env,check=True)
        runtime=settings|{'DATABASE_URL':source.set(host='postgres',port=5432,database=database).render_as_string(hide_password=False),'PDF_STORAGE_PATH':'/data/pdfs','EMBEDDING_MODEL_PATH':'/embedding','TEST_API_BIND':'0.0.0.0'}
        (out/'container.env').write_text('\n'.join(k+'='+v for k,v in runtime.items()),encoding='utf-8')
        api_name='studyhub-rag-api-'+stamp;front_name='studyhub-rag-web-'+stamp
        containers.append(api_name)
        docker('run','-d','--name',api_name,'--network',network,'--env-file',str(out/'container.env'),
            '--mount',f'type=bind,src={out/"pdfs"},dst=/data/pdfs','--mount',f'type=bind,src={model},dst=/embedding,readonly',
            '--mount',f'type=bind,src={ROOT/"scripts/rag_test_api.py"},dst=/qa/rag_test_api.py,readonly','studyhub-backend','python','/qa/rag_test_api.py',stdout=subprocess.DEVNULL)
        # Use the repository's actual production proxy settings, only substitute
        # the disposable backend DNS name. Size/timeouts remain unchanged.
        nginx=(ROOT/'frontend/nginx.conf').read_text().replace('backend:8000',api_name+':8000')
        (out/'nginx.conf').write_text(nginx,encoding='utf-8')
        containers.append(front_name)
        docker('run','-d','--name',front_name,'--network',network,'-p',f'127.0.0.1:{port}:80',
            '--mount',f'type=bind,src={out/"nginx.conf"},dst=/etc/nginx/conf.d/default.conf,readonly','studyhub-frontend',stdout=subprocess.DEVNULL)
        for attempt in range(90):
            try:
                with urllib.request.urlopen(origin+'/api/v1/health',timeout=2) as response:
                    if response.status==200:break
            except Exception:time.sleep(.5)
        else:raise RuntimeError('Isolated Docker API did not become ready; inspect local logs.')
        env.update(FRONTEND_URL=origin,STUDYHUB_WEBSITE_TEST_ENV=str(out/'environment.json'),RAG_FIXTURE_DIR=str(fixtures),RAG_MODEL_FIXTURE_DIR=str(model),UI_SCREENSHOT_DIR=str(out/'screenshots'))
        if os.name=='nt':env.setdefault('PLAYWRIGHT_CHANNEL','msedge')
        result=subprocess.run(['node','--test','tests/rag-documents.e2e.cjs'],cwd=ROOT/'frontend',env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
        (out/'e2e.log').write_text(result.stdout,encoding='utf-8');print(result.stdout,flush=True);passed=result.returncode==0
        (out/'result.json').write_text(json.dumps({'passed':passed,'database':database,'origin':origin,'real_encoder':True,'provider':'synthetic loopback Gemini contract','proxy':'repository Nginx config','docker':True}),encoding='utf-8')
    finally:
        for name in containers:
            logs=subprocess.run(['docker','logs',name],cwd=ROOT,capture_output=True)
            (out/(name+'.log')).write_bytes(logs.stdout+logs.stderr)
        for name in reversed(containers):subprocess.run(['docker','rm','-f',name],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if passed and not args.keep_db:
            with engine.connect() as db:db.execute(text('DROP DATABASE '+database))
        engine.dispose()
    print('RAG evidence:',out,flush=True)
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
