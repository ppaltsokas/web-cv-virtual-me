"""Check staged/tracked template files, including PDF text, before publication."""
from pathlib import Path
import argparse
import re
import subprocess
import sys
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
TOKEN_PATTERNS = [
    re.compile(rb'sk-(?:proj-)?[A-Za-z0-9_-]{30,}'),
    re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(rb'scrypt:[a-f0-9]{32}:[a-f0-9]{128}'),
]
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--working-tree', action='store_true', help='Also check non-ignored new files and unstaged edits')
    args = parser.parse_args()
    command = ['git', 'ls-files', '-z']
    if args.working_tree:
        command += ['--cached', '--others', '--exclude-standard']
    files = subprocess.check_output(command, cwd=ROOT).decode().split('\0')
    failures = []
    for name in filter(None, files):
        path = Path(name)
        if (path.name.startswith('.env') and name != '.env.example') or name.startswith(('content/private/', 'data/', 'models/')) or path.name.endswith(('.local.json', '.local.jsonl')):
            failures.append(f'Private/generated path is tracked: {name}')
        data = (ROOT / name).read_bytes() if args.working_tree else subprocess.check_output(['git', 'show', ':' + name], cwd=ROOT)
        if any(pattern.search(data) for pattern in TOKEN_PATTERNS):
            failures.append(f'Credential-like material in {name}')
        if path.suffix == '.pdf':
            from io import BytesIO
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(data))
            text = '\n'.join(page.extract_text() for page in reader.pages)
            if 'Fictional' not in text and 'FICTIONAL' not in text:
                failures.append(f'Template PDF must be clearly fictional: {name}')
    env = dotenv_values(ROOT / '.env.example', interpolate=False)
    for key in ['OPENAI_API_KEY', 'CV_ACCESS_PASSWORD_HASH', 'CV_API_PROXY_SECRET', 'DATABASE_URL', 'POSTGRES_PASSWORD', 'NEO4J_PASSWORD']:
        if env.get(key):
            failures.append(f'{key} must stay blank in the example')
    if env.get('PAID_AI_ENABLED') != 'false':
        failures.append('Paid AI must default to false in the template')
    for key in ['POSTGRES_ENABLED', 'PERSISTENT_CHAT_HISTORY_ENABLED', 'KNOWLEDGE_GRAPH_ENABLED',
                'GRAPH_RETRIEVAL_ENABLED', 'GNN_SHADOW_ENABLED', 'GNN_RERANKING_ENABLED']:
        if env.get(key) != 'false':
            failures.append(f'{key} must default to false in the template')
    if env.get('GNN_CANARY_PERCENT') != '0':
        failures.append('GNN canary must default to zero')
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        return 1
    scope = 'working-tree' if args.working_tree else 'staged/tracked'
    print(f'Release check passed for {len(list(filter(None, files)))} {scope} files; secret placeholders remain blank.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
