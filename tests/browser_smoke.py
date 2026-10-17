"""Optional browser smoke test: pip install playwright; playwright install chromium.

Builds two fictional profiles, starts only loopback test servers and mocks the
provider. Does not read real dotenv files or make paid API requests.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['LOAD_DOTENV'] = 'false'
from test_portfolio import FakeClient
from services.api.main import create_app
from scripts.manage import credentials
import uvicorn
from playwright.sync_api import sync_playwright

def unused_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]

def wait_for(url, process=None):
    end = time.monotonic() + 15
    while time.monotonic() < end:
        if process and process.poll() is not None:
            raise RuntimeError('Test frontend exited unexpectedly')
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError('Loopback test server did not become healthy')

def run():
    evidence = ROOT / 'output/browser'
    evidence.mkdir(parents=True, exist_ok=True)
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    node = shutil.which('node')
    with tempfile.TemporaryDirectory(prefix='smoke-', dir=evidence) as folder, sync_playwright() as playwright:
        work = Path(folder).resolve()
        assert work.is_relative_to(evidence.resolve())
        browser = playwright.chromium.launch(headless=True)
        try:
            for owner in ['Alex', 'Sam']:
                data = json.loads((ROOT / 'config/profile.example.json').read_text())
                if owner == 'Sam':
                    data['resume']['personalInfo'].update(name='Sam Rivera', title='Product Designer', bio='A fictional designer building accessible tools.', email='', location='', socials={})
                    for key in ['experience', 'education', 'certifications', 'latestProjects', 'skills']:
                        data['resume'][key] = []
                    data['resume']['projects'] = [{'id': 'garden', 'title': 'Garden Planner', 'description': 'A fictional accessible planning prototype.', 'technologies': ['Design']}]
                    data['chat'].update(name='Virtual Sam', greeting="Hello! I'm Sam's virtual persona.")
                    data['timezone'] = 'America/Los_Angeles'
                    data['birthMonthYear'] = 'January 1990'
                profile = work / f'{owner}.json'
                manifest = work / f'{owner}-content.json'
                profile.write_text(json.dumps(data), encoding='utf-8')
                manifest.write_text((ROOT / 'config/content.example.json').read_text() if owner == 'Alex' else '{"documents": []}', encoding='utf-8')
                api_port, web_port = unused_port(), unused_port()
                base = f'http://127.0.0.1:{web_port}'
                api = f'http://127.0.0.1:{api_port}'
                password, hashed, proxy = credentials('browser-test-password-only')
                env = {**os.environ, 'PORTFOLIO_PROFILE': str(profile), 'CONTENT_MANIFEST': str(manifest),
                       'PRIVATE_CV_ENABLED': 'true', 'CV_PUBLIC_ORIGIN': base, 'CV_API_ORIGIN': api,
                       'CV_ACCESS_PASSWORD_HASH': hashed, 'CV_API_PROXY_SECRET': proxy,
                       'OPENAI_API_KEY': 'synthetic-browser-key', 'PAID_AI_ENABLED': 'true', 'NODE_ENV': 'development'}
                os.environ.update(env)
                dist = work / f'{owner}-dist'
                subprocess.run([npm, 'run', 'build', '--', '--outDir', str(dist)], cwd=ROOT / 'services/frontend', env={**env, 'NODE_ENV': 'production'}, check=True, stdout=subprocess.DEVNULL)
                for path in dist.rglob('*'):
                    if path.is_file() and path.suffix in {'.js', '.html', '.css'}:
                        text = path.read_text(encoding='utf-8')
                        assert 'synthetic-browser-key' not in text and hashed not in text and proxy not in text
                        assert 'birthMonthYear' not in text and 'January 1990' not in text
                fake = FakeClient('social', [f'Hello! I am {owner}\'s virtual persona.', 'Your first message was "hi".'])
                app = create_app(profile_path=profile, manifest_path=manifest, client_factory=lambda: fake)
                server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=api_port, log_level='error', access_log=False))
                thread = threading.Thread(target=server.run, daemon=True)
                thread.start()
                code = "import {createStaticServer} from './server.js';createStaticServer({distDir:process.env.TEST_DIST}).listen(Number(process.env.PORT),'127.0.0.1');"
                front_env = {**env, 'TEST_DIST': str(dist), 'PORT': str(web_port)}
                front_env.pop('OPENAI_API_KEY', None)
                front_env.pop('CV_ACCESS_PASSWORD', None)
                logs = (work / f'{owner}.log').open('w', encoding='utf-8')
                process = subprocess.Popen([node, '--input-type=module', '-e', code], cwd=ROOT / 'services/frontend', env=front_env, stdout=logs, stderr=logs)
                try:
                    wait_for(api + '/health')
                    wait_for(base + '/health', process)
                    context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
                    page = context.new_page()
                    failures = []
                    page.on('pageerror', lambda error: failures.append(str(error)))
                    page.goto(base + '/access')
                    page.get_by_role('heading', level=1).wait_for()
                    assert data['resume']['personalInfo']['name'] in page.title()
                    page.screenshot(path=str(evidence / f'{owner.lower()}-entrance.png'))
                    page.get_by_label('Access password').fill('wrong-password')
                    page.get_by_role('button', name='Enter', exact=True).click()
                    page.get_by_role('status').filter(has_text='Incorrect password').wait_for()
                    page.get_by_label('Access password').fill(password)
                    page.get_by_role('button', name='Enter', exact=True).click()
                    page.wait_for_url(base + '/')
                    page.get_by_role('heading', name=data['resume']['personalInfo']['name'], exact=True).wait_for()
                    assert page.locator('a a').count() == 0
                    page.get_by_role('heading', name=data['chat']['name'], exact=True).wait_for()
                    message = page.get_by_role('textbox', name='Your message')
                    message.wait_for(state='visible')
                    page.wait_for_function("!document.querySelector('input[aria-label=\"Your message\"]').disabled")
                    message.fill('hi')
                    page.get_by_role('button', name='Send message').click()
                    page.get_by_text(f'Hello! I am {owner}\'s virtual persona.', exact=True).wait_for()
                    fake.kind = 'conversation'
                    message.fill('What was my first message?')
                    page.get_by_role('button', name='Send message').click()
                    page.get_by_text('Your first message was "hi".', exact=True).wait_for()
                    page.get_by_role('tab', name='Work Projects', exact=True).click()
                    if owner == 'Sam':
                        page.get_by_text('No items have been added to this topic yet.').wait_for()
                        assert page.get_by_role('link', name='Download Resume').count() == 0
                        assert page.get_by_role('heading', name='Experience', exact=True).count() == 0
                        assert 'Alex Morgan' not in page.locator('body').inner_text()
                    else:
                        page.get_by_text('Customer Insights Dashboard', exact=True).first.wait_for()
                        download = context.request.get(base + '/api/me/cv')
                        assert download.status == 200 and download.body().startswith(b'%PDF')
                    page.screenshot(path=str(evidence / f'{owner.lower()}-portfolio.png'))
                    assert not failures, failures
                    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                    mobile = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=1, reduced_motion='reduce')
                    phone = mobile.new_page()
                    phone.goto(base + '/access')
                    phone.screenshot(path=str(evidence / f'{owner.lower()}-mobile-entrance.png'))
                    phone.get_by_label('Access password').fill(password)
                    phone.get_by_role('button', name='Enter', exact=True).click()
                    phone.wait_for_url(base + '/')
                    phone.get_by_role('heading', name=data['resume']['personalInfo']['name'], exact=True).wait_for()
                    phone.get_by_role('heading', name='Personal Projects', exact=True).wait_for()
                    phone.get_by_role('button', name='Open Chat', exact=True).wait_for(state='visible')
                    bounds = phone.get_by_role('button', name='Open Chat', exact=True).bounding_box()
                    assert bounds and bounds['x'] > 195 and bounds['x'] + bounds['width'] <= 390
                    assert phone.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                    phone.screenshot(path=str(evidence / f'{owner.lower()}-mobile-portfolio.png'), full_page=True)
                    mobile.close()
                    os.environ['PAID_AI_ENABLED'] = 'false'
                    page.get_by_role('button', name='Minimize chat').click()
                    page.get_by_role('button', name='Open Chat', exact=True).click()
                    page.get_by_text('Demo - chat setup needed', exact=True).wait_for()
                    assert message.is_disabled()
                    context.close()
                    assert len(fake.calls) == 4
                finally:
                    process.terminate()
                    process.wait(timeout=10)
                    logs.close()
                    server.should_exit = True
                    thread.join(timeout=10)
                print(f'{owner} browser flow passed: login, profile, LLM-backed mock chat, recall, mobile, demo state and secret-free bundle.')
        finally:
            browser.close()
    print('Browser smoke checks passed for two fictional owners; no paid model calls were made.')

if __name__ == '__main__':
    run()
