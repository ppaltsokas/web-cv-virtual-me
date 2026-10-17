"""Owner setup, checks, local preview, explicit indexing and private build contexts."""
from __future__ import annotations
import argparse
import base64
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import dotenv_values, load_dotenv, set_key
from services.api.profile import load_profile, load_manifest, config_path
from services.api.knowledge import KnowledgeBase

def credentials(password=None):
    password = secrets.token_urlsafe(20) if password is None else password
    if not 12 <= len(password) <= 128:
        raise ValueError('Use an access password of 12-128 characters')
    salt = secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=salt.encode(), n=131072, r=8, p=1, maxmem=192 * 1024 * 1024, dklen=64)
    return password, f'scrypt:{salt}:{key.hex()}', secrets.token_urlsafe(32)

def initialize(root=ROOT):
    for kind in ['profile', 'content']:
        target = root / 'config' / f'{kind}.local.json'
        if target.exists():
            continue
        if kind == 'profile':
            shutil.copyfile(root / 'config/profile.example.json', target)
        else:
            data = json.loads((root / 'config/content.example.json').read_text())
            for spec in data['documents']:
                source = root / spec['path']
                destination = root / 'content/private' / source.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not destination.exists():
                    shutil.copyfile(source, destination)
                spec['path'] = destination.relative_to(root).as_posix()
            target.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    envfile = root / '.env.local'
    if not envfile.exists():
        password, hashed, proxy = credentials()
        example = (root / '.env.example').read_text(encoding='utf-8')
        example = example.replace('CV_ACCESS_PASSWORD_HASH=\n', f'CV_ACCESS_PASSWORD_HASH={hashed}\n')
        example = example.replace('CV_API_PROXY_SECRET=\n', f'CV_API_PROXY_SECRET={proxy}\n')
        example += '\n# Owner-only local sign-in password; not sent to visitors.\nCV_ACCESS_PASSWORD=' + password + '\n'
        with envfile.open('x', encoding='utf-8') as stream:
            stream.write(example)
        envfile.chmod(0o600)
    print('Local profile, content and credential files are ready. Existing files were preserved.')
    print('Edit config/profile.local.json and content/private/. Read your generated password privately in .env.local.')
    print('Chat stays disabled until you add OPENAI_API_KEY and set PAID_AI_ENABLED=true in .env.local.')

def check():
    profile = load_profile()
    from services.api.features import Features
    Features.from_env()  # Validate flags, without connecting to databases.
    knowledge = KnowledgeBase(profile, load_manifest(), ROOT, ROOT / os.getenv('INDEX_DIR', 'data/index'))
    ids = {spec.id for spec in knowledge.manifest.documents if spec.public and spec.path.lower().endswith('.pdf')}
    for project in profile.resume.projects + profile.resume.latestProjects:
        if project.pdfPath and project.pdfPath not in ids:
            raise ValueError(f'Project {project.id} refers to a PDF that is missing or not public')
    env = {**dotenv_values(ROOT / '.env.local', interpolate=False), **os.environ}
    if not re.fullmatch(r'scrypt:[a-f0-9]{32}:[a-f0-9]{128}', env.get('CV_ACCESS_PASSWORD_HASH', '') or ''):
        raise ValueError('Missing/invalid password hash. Run init or password; never put a plaintext password in the hash field.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', env.get('CV_API_PROXY_SECRET', '') or ''):
        raise ValueError('Missing/invalid proxy secret. Run init.')
    print(f'Configuration and {len(knowledge.manifest.documents)} documents are valid. No model request was made.')
    print('Chat enabled.' if env.get('OPENAI_API_KEY') and env.get('PAID_AI_ENABLED', '').lower() == 'true' else 'Demo mode: chat requires a backend key and PAID_AI_ENABLED=true.')

def free_port(port):
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', port))
        except OSError:
            raise ValueError(f'Port {port} is occupied. Stop the existing preview or choose different local origins.') from None

def serve(service):
    check()
    env = os.environ.copy()
    env['LOAD_DOTENV'] = 'false'
    env['NODE_ENV'] = 'development'
    url = urlparse(env.get('CV_API_ORIGIN' if service == 'backend' else 'CV_PUBLIC_ORIGIN',
                           'http://127.0.0.1:8000' if service == 'backend' else 'http://127.0.0.1:3000'))
    if url.scheme != 'http' or url.hostname not in {'localhost', '127.0.0.1'}:
        raise ValueError('Local preview origins must use http://127.0.0.1 with the desired port')
    port = url.port or (8000 if service == 'backend' else 3000)
    free_port(port)
    if service == 'backend':
        return subprocess.call([sys.executable, '-m', 'uvicorn', 'services.api.main:app', '--host', '127.0.0.1', '--port', str(port)], cwd=ROOT, env=env)
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    node = shutil.which('node')
    if not npm or not node:
        raise ValueError('Install Node.js 22+ and frontend dependencies first')
    for key in ['OPENAI_API_KEY', 'CV_ACCESS_PASSWORD']:
        env.pop(key, None)
    frontend = ROOT / 'services/frontend'
    code = subprocess.call([npm, 'run', 'build'], cwd=frontend, env={**env, 'NODE_ENV': 'production'})
    if code:
        return code
    env['PORT'] = str(port)
    return subprocess.call([node, 'server.js'], cwd=frontend, env=env)

def private_bundle():
    """Create a deliberate deployment context without importing dotenv secrets."""
    check()
    destination = ROOT / 'data/deploy-context'
    if destination.exists():
        raise ValueError('data/deploy-context already exists. Choose a fresh copy or remove the reviewed old context yourself.')
    allowed_dirs = ['services', 'config', 'examples', 'scripts', 'docs', 'infra']
    def ignore(directory, names):
        return [name for name in names if name in {'node_modules', 'dist', '__pycache__', '.pytest_cache', 'secrets'}
                or name.endswith(('.local.json', '.local.jsonl', '.key', '.pem', '.sqlite', '.db', '.log')) or name.startswith('.env')]
    destination.mkdir(parents=True)
    for name in allowed_dirs:
        if (ROOT / name).is_dir():
            shutil.copytree(ROOT / name, destination / name, ignore=ignore)
    for name in ['Dockerfile', 'README.md', 'LICENSE', 'railway.json']:
        if (ROOT / name).is_file():
            shutil.copyfile(ROOT / name, destination / name)
    profile = load_profile()
    (destination / 'config/profile.local.json').write_text(profile.model_dump_json(indent=2), encoding='utf-8')
    manifest = load_manifest()
    knowledge = KnowledgeBase(profile, manifest, ROOT)
    for spec, path in knowledge.documents.values():
        output = destination / 'content/private' / (spec.id + path.suffix.lower())
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, output)
        spec.path = output.relative_to(destination).as_posix()
    (destination / 'config/content.local.json').write_text(manifest.model_dump_json(indent=2), encoding='utf-8')
    # Reuse a valid local embedding index only after rebinding it to the same
    # documents at their bundled paths. No embedding/model call occurs here.
    local_index = ROOT / os.getenv('INDEX_DIR', 'data/index')
    original = KnowledgeBase(profile, load_manifest(), ROOT, local_index)
    if original.index is not None:
        bundled = KnowledgeBase(profile, manifest, destination)
        output_index = destination / 'data/index'
        output_index.mkdir(parents=True)
        shutil.copyfile(local_index / 'index.faiss', output_index / 'index.faiss')
        store = json.loads((local_index / 'store.json').read_text())
        store['fingerprint'] = bundled.fingerprint
        (output_index / 'store.json').write_text(json.dumps(store, ensure_ascii=False), encoding='utf-8')
    # Graph/model artifacts are deliberately not rebound: their versions include
    # profile, manifest paths and source bytes. Rebuild in the private context.
    from services.api.features import Features
    features = Features.from_env()
    if features.graph or features.gnn_shadow or features.gnn_active:
        print('Optional graph/GNN artifacts are excluded. Build and evaluate them inside the private context before deployment.')
    # This deliberate private bundle includes owner inputs but always excludes keys.
    (destination / '.dockerignore').write_text('.git\n.env\n.env.*\nnode_modules\n**/node_modules\n**/dist\n**/__pycache__\n*.log\nconfig/*.local.jsonl\n', encoding='utf-8')
    print('Private deployment context created at data/deploy-context. It contains owner content, no dotenv credentials.')
    print('Keep this directory private. Build/deploy from it; inject runtime secrets on your hosting platform.')

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'check', 'password', 'backend', 'frontend', 'index', 'bundle'])
    args = parser.parse_args(argv)
    load_dotenv(ROOT / '.env.local', override=False)
    try:
        if args.command == 'init':
            initialize()
        elif args.command == 'check':
            check()
        elif args.command == 'password':
            if not (ROOT / '.env.local').is_file():
                raise ValueError('Run init first')
            password = getpass.getpass('New access password (12-128 characters): ')
            if password != getpass.getpass('Confirm password: '):
                raise ValueError('Passwords do not match')
            password, hashed, _ = credentials(password)
            set_key(ROOT / '.env.local', 'CV_ACCESS_PASSWORD_HASH', hashed)
            set_key(ROOT / '.env.local', 'CV_ACCESS_PASSWORD', password)
            print('Local password updated. Restart the frontend. Update its hosted hash separately if deployed.')
        elif args.command in {'backend', 'frontend'}:
            return serve(args.command)
        elif args.command == 'index':
            check()
            from openai import OpenAI
            from services.api.cost_controls import require_paid_ai
            require_paid_ai()
            if not os.getenv('OPENAI_API_KEY'):
                raise ValueError('Configure the backend key before indexing')
            knowledge = KnowledgeBase(load_profile(), load_manifest(), ROOT)
            count = knowledge.build_index(ROOT / os.getenv('INDEX_DIR', 'data/index'), OpenAI(max_retries=0))
            print(f'Indexed {count} owner-specific chunks. API embedding usage was incurred.')
        elif args.command == 'bundle':
            private_bundle()
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        # Pydantic and provider exceptions can contain owner input or request data.
        if isinstance(exc, ValueError) and type(exc) is ValueError:
            print(str(exc), file=sys.stderr)
        else:
            print(f'Setup failed ({type(exc).__name__}). Check the selected profile, manifest, paths and private environment settings.', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
