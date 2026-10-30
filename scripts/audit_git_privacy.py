"""Compare tracked/staged files and optional Git history to local secrets in memory.

Never prints credential bytes; local configuration files are not modified.
"""
import argparse
import json
import subprocess
from pathlib import Path

from verify_release import known_credentials

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', action='store_true')
    args = parser.parse_args()
    secrets = known_credentials()
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    hits = []
    forbidden = []
    for name in filter(None, names):
        path = ROOT / name
        if name.startswith(('data/', 'output/', 'dist/')) or path.name in ('.env', '.env.production', 'ai_settings.json', 'xhs_cookies.json'):
            forbidden.append(name)
        if path.is_file() and any(value in path.read_bytes() for value in secrets):
            hits.append(name)
    historical = []
    scanned = 0
    if args.history:
        objects = subprocess.check_output(['git', 'rev-list', '--objects', '--all'], cwd=ROOT).splitlines()
        proc = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        for entry in objects:
            oid = entry.split(b' ', 1)[0]
            proc.stdin.write(oid+b'\n'); proc.stdin.flush()
            header = proc.stdout.readline().split()
            if len(header) != 3:
                raise RuntimeError('Invalid Git object response')
            data = proc.stdout.read(int(header[2])); proc.stdout.read(1)
            if header[1] == b'blob':
                scanned += 1
                if any(value in data for value in secrets):
                    historical.append(oid.decode())
        proc.stdin.close(); proc.wait(timeout=20)
        assert proc.returncode == 0
    report = {'tracked_files_checked': len([n for n in names if n]),
        'known_credentials_checked': len(secrets), 'credential_findings': hits,
        'forbidden_private_paths': forbidden, 'historical_blobs_checked': scanned,
        'historical_credential_findings': historical}
    print(json.dumps(report, ensure_ascii=False))
    assert not hits and not forbidden and not historical, 'Privacy audit failed; values withheld'


if __name__ == '__main__':
    main()
