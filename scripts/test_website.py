"""Run website E2E and workspace UI regressions on isolated local servers."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import urllib.request

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


def available_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def wait_ready(url, process, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('Test server exited; inspect the local server log.')
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(.25)
    raise RuntimeError('Test server did not become ready; inspect the local server log.')


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keep-db', action='store_true', help='Keep successful test data for local inspection.')
    args = parser.parse_args()
    env_file = dotenv_values(ROOT / '.env')
    source = make_url(os.environ.get('DATABASE_URL') or env_file['DATABASE_URL'])
    if source.host in ('postgres', 'localhost'):
        source = source.set(host='127.0.0.1')
    stamp = datetime.now().strftime('%Y%m%d%H%M%S') + '_' + secrets.token_hex(3)
    database = 'studyhub_website_' + stamp + '_test'
    assert database.endswith('_test') and database.replace('_', '').isalnum()
    output = ROOT / '.local' / 'website-p0' / 'runs' / stamp
    output.mkdir(parents=True, exist_ok=False)
    engine = create_engine(source.set(database='postgres'), isolation_level='AUTOCOMMIT')
    with engine.connect() as db:
        db.execute(text('CREATE DATABASE ' + database))
    backend_port, frontend_port = available_port(), available_port()
    while frontend_port == backend_port:
        frontend_port = available_port()
    origin = f'http://127.0.0.1:{frontend_port}'
    backend_url = f'http://127.0.0.1:{backend_port}'
    settings = {
        'DATABASE_URL': source.set(database=database).render_as_string(hide_password=False),
        'JWT_SECRET': secrets.token_hex(32), 'ALLOWED_ORIGINS': origin, 'COOKIE_SECURE': 'false',
        'AUTH_RATE_LIMIT': '1000', 'CHAT_PROVIDER': 'disabled',
        'COURSE_MANIFEST_PATH': str(ROOT / 'content/mobile_multiplatform/course_manifest.json'),
        'PDF_STORAGE_PATH': str(output / 'pdfs'), 'COURSE_RUN_CODE': 'WEB_SEED',
        'COURSE_RUN_START_DATE': '2026-10-26', 'PYTHONIOENCODING': 'utf-8',
        'BOOTSTRAP_TEACHER_EMAIL': 'teacher.web@example.com',
        'BOOTSTRAP_TEACHER_PASSWORD': secrets.token_urlsafe(24),
        'BOOTSTRAP_TEACHER_DISPLAY_NAME': 'Giảng viên website',
        'DEMO_STUDENT_EMAIL': 'student.web@example.com',
        'DEMO_STUDENT_PASSWORD': secrets.token_urlsafe(24),
        'DEMO_STUDENT_DISPLAY_NAME': 'Sinh viên website',
    }
    config = output / 'environment.json'
    config.write_text(json.dumps(settings), encoding='utf-8')
    child = os.environ.copy()
    child.update(settings)
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    servers, logs, exit_code = [], [], 1
    try:
        for module in ('alembic', 'app.seed'):
            command = [sys.executable, '-m', module] + (['upgrade', 'head'] if module == 'alembic' else [])
            subprocess.run(command, cwd=ROOT / 'backend', env=child, check=True, creationflags=flags)
        backend_log = (output / 'backend.log').open('w', encoding='utf-8')
        logs.append(backend_log)
        backend = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(backend_port)], cwd=ROOT / 'backend', env=child, stdout=backend_log, stderr=subprocess.STDOUT, creationflags=flags)
        servers.append(backend)
        wait_ready(backend_url + '/api/v1/health', backend)
        frontend_log = (output / 'frontend.log').open('w', encoding='utf-8')
        logs.append(frontend_log)
        child['API_PROXY_TARGET'] = backend_url
        frontend = subprocess.Popen(['node', str(ROOT / 'frontend/node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', str(frontend_port), '--strictPort'], cwd=ROOT / 'frontend', env=child, stdout=frontend_log, stderr=subprocess.STDOUT, creationflags=flags)
        servers.append(frontend)
        wait_ready(origin, frontend)
        child.update(FRONTEND_URL=origin, STUDYHUB_WEBSITE_TEST_ENV=str(config), UI_SCREENSHOT_DIR=str(output / 'screenshots'))
        if os.name == 'nt':
            child.setdefault('PLAYWRIGHT_CHANNEL', 'msedge')
        print('Running website E2E against an isolated _test database and local temporary servers.', flush=True)
        result = subprocess.run(['node', '--test', 'tests/pdf-workspace.test.cjs', 'tests/website-p0.e2e.cjs'], cwd=ROOT / 'frontend', env=child, creationflags=flags, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
        exit_code = result.returncode
        (output / 'e2e.log').write_text(result.stdout, encoding='utf-8')
        print(result.stdout, flush=True)
        (output / 'result.json').write_text(json.dumps({'passed': exit_code == 0, 'database': database, 'origin': origin, 'screenshots': str(output / 'screenshots')}), encoding='utf-8')
    finally:
        for server in reversed(servers):
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
        for log in logs:
            log.close()
        if exit_code == 0 and not args.keep_db:
            with engine.connect() as db:
                db.execute(text('DROP DATABASE ' + database))
        engine.dispose()
    print('Website test evidence:', output, flush=True)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
