"""Command line for the encrypted GitHub Pages vault.

  python -m vault init                     create the master key (once)
  python -m vault user add <name>          allow a person (prompts for a password)
  python -m vault user passwd <name>       change a password
  python -m vault user remove <name>       revoke access (effective at the next seal/publish)
  python -m vault user list
  python -m vault seal                     encrypt data/*.json into encrypted/
  python -m vault unseal                   restore collector state from encrypted/ (CI)
  python -m vault verify <name>            test a login exactly like the browser does
  python -m vault build-site --out _site   assemble the static site for GitHub Pages
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

from . import (MIN_PASSWORD, VaultError, add_user, build_site, init_master, list_users, load_master,
               remove_user, seal, unseal, verify_login)


def _password(args, confirm: bool = True) -> str:
    if getattr(args, 'password_stdin', False):
        return sys.stdin.readline().rstrip('\n')
    first = getpass.getpass(f'Password (min {MIN_PASSWORD} chars): ')
    if confirm and getpass.getpass('Repeat password: ') != first:
        raise VaultError('Passwords do not match.')
    return first


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog='python -m vault', description='CyberCareers BD encrypted vault')
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('init')
    u = sub.add_parser('user')
    us = u.add_subparsers(dest='action', required=True)
    for action in ('add', 'passwd', 'remove'):
        a = us.add_parser(action)
        a.add_argument('username')
        if action != 'remove':
            a.add_argument('--password-stdin', action='store_true', help='read the password from stdin')
    us.add_parser('list')
    sub.add_parser('seal')
    un = sub.add_parser('unseal')
    un.add_argument('--keep-existing', action='store_true')
    v = sub.add_parser('verify')
    v.add_argument('username')
    v.add_argument('--password-stdin', action='store_true')
    b = sub.add_parser('build-site')
    b.add_argument('--out', default='_site')
    args = p.parse_args(argv)
    try:
        if args.cmd == 'init':
            value, created = init_master()
            if created:
                print('Master key created in .vault/master.key (git-ignored).\n')
            else:
                print('Master key already exists in .vault/master.key.\n')
            print('Add it to GitHub: Settings → Secrets and variables → Actions → New repository secret')
            print('  Name:  CC_MASTER_KEY')
            print(f'  Value: {value}\n')
            print('Keep a private backup. Without it the published data cannot be re-encrypted.')
        elif args.cmd == 'user':
            if args.action == 'list':
                rows = list_users(load_master())
                for r in rows:
                    print(f"{r['username']:<28} id {r['id']}  added {r['created_at'][:10]}  changed {r['updated_at'][:10]}")
                print(f'{len(rows)} user(s).')
            elif args.action == 'remove':
                print('Removed.' if remove_user(args.username) else 'No such user.')
                print('Commit config/users.json; access ends at the next publish (or run `python -m vault seal`).')
            else:
                master = load_master()
                add_user(args.username, _password(args), master, replace=args.action == 'passwd')
                print(f'{"Updated" if args.action == "passwd" else "Added"} {args.username}. '
                      'Commit config/users.json and push; the next publish includes this login.')
        elif args.cmd == 'seal':
            ring = seal(load_master())
            print(f"Sealed {len(ring['files'])} files for {len(ring['users'])} user(s) into encrypted/.")
            jobs_changed = 'jobs.json' in ring['changed']
            print('jobs.json changed since the previous seal.' if jobs_changed else 'jobs.json unchanged.')
            out = os.environ.get('GITHUB_OUTPUT')
            if out:
                with open(out, 'a', encoding='utf-8') as fh:
                    fh.write(f"jobs_changed={'true' if jobs_changed else 'false'}\n")
        elif args.cmd == 'unseal':
            restored = unseal(load_master(), overwrite=not args.keep_existing)
            print('Restored: ' + (', '.join(restored) if restored else 'nothing (no vault yet)'))
        elif args.cmd == 'verify':
            ok = verify_login(args.username, _password(args, confirm=False))
            print('Login OK. Decrypts: ' + ', '.join(ok))
        elif args.cmd == 'build-site':
            out = build_site(Path(args.out).resolve())
            print(f'Static site ready in {out}')
    except VaultError as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
