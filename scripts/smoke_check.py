"""Fetch every page of the live site and verify each referenced asset returns 200.

Run this from a machine with network access (not on the server) after any deploy:

    python scripts/smoke_check.py https://rethrow.dk

The point is to catch the failures that only exist in production and that a
browser hides: a missing /static/ mapping (htmx 404s, so pages silently stop
polling and freeze on the old question) or a missing /media/ mapping (interlude
images render blank on the projector, mid-speech).

Guest pages are gated by the player cookie, so they redirect to /velkommen/
unless you pass a real token:

    python scripts/smoke_check.py https://rethrow.dk --token <uuid from admin>

Stdlib only, so it runs anywhere with no install step. Exits 1 if anything is
broken, 0 if the site is clean.
"""

import argparse
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

# Every page a guest, the host, or the projector laptop can land on. The poll
# endpoints are included because a 500 there is invisible in a browser but
# breaks every live update in the room.
PAGES = [
    ('/', 'home (guest)'),
    ('/velkommen/', 'registration'),
    ('/profil/', 'demographics'),
    ('/quiz/', 'quiz (guest)'),
    ('/quiz/status/', 'quiz poll endpoint'),
    ('/quiz/projektor/', 'quiz projector'),
    ('/quiz/projektor/status/', 'projector poll endpoint'),
    ('/drinky/', 'drinky (guest)'),
    ('/drinky/status/', 'drinky poll endpoint'),
    ('/drinky/projektor/', 'drinky results'),
    ('/accounts/login/', 'host login'),
    ('/admin/login/', 'admin login'),
]


class AssetFinder(HTMLParser):
    """Collects local /static/ and /media/ URLs referenced by a page."""

    def __init__(self):
        super().__init__()
        self.assets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for attr in ('src', 'href'):
            url = attrs.get(attr) or ''
            if url.startswith(('/static/', '/media/')):
                self.assets.append(url)


def fetch(url, token=None, method='GET'):
    """Return (status, body_bytes, redirect_target). Redirects are reported,
    not followed: a 302 to /velkommen/ is the correct answer for a gated page,
    and following it would hide which page we actually measured."""

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(url, method=method)
    request.add_header('User-Agent', 'smoke-check/1.0')
    if token:
        request.add_header('Cookie', f'player_token={token}')
    try:
        with opener.open(request, timeout=20) as response:
            return response.status, response.read(), None
    except urllib.error.HTTPError as error:
        target = error.headers.get('Location') if error.code in (301, 302, 303, 307, 308) else None
        return error.code, b'', target
    except (urllib.error.URLError, OSError) as error:
        return None, str(error).encode(), None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', help='Site root, e.g. https://rethrow.dk')
    parser.add_argument('--token', help='A Player token (uuid) so guest pages are reachable')
    args = parser.parse_args()

    base = args.base.rstrip('/')
    failures = []
    checked_assets = {}
    saw_media = False

    print(f'Checking {base}\n')

    for path, label in PAGES:
        url = base + path
        status, body, redirect = fetch(url, args.token)

        if status is None:
            print(f'  UNREACHABLE  {path:28} {label}  ({body.decode(errors="replace")})')
            failures.append(f'{path} unreachable')
            continue

        note = ''
        if redirect:
            note = f'-> {redirect}'
        # 204 is the correct, cheap answer from a poll endpoint whose state is
        # unchanged; 302 on a guest page means the cookie gate did its job.
        ok = status in (200, 204, 302)
        if not ok:
            failures.append(f'{path} returned {status}')
        print(f'  {"ok " if ok else "FAIL"}  {status}  {path:28} {label} {note}')

        finder = AssetFinder()
        finder.feed(body.decode('utf-8', errors='replace'))
        for asset in finder.assets:
            if asset.startswith('/media/'):
                saw_media = True
            checked_assets.setdefault(asset, []).append(path)

    print(f'\nAssets referenced by those pages ({len(checked_assets)}):\n')
    for asset, seen_on in sorted(checked_assets.items()):
        status, _, _ = fetch(urljoin(base, asset), args.token)
        ok = status == 200
        if not ok:
            failures.append(f'{asset} returned {status} (referenced by {", ".join(seen_on)})')
        print(f'  {"ok " if ok else "FAIL"}  {status}  {asset}')

    print()
    if not saw_media:
        print('NOTE: no /media/ URL appeared on any page, so the interlude image\n'
              '      path was NOT tested. Put the quiz in the interlude state on a\n'
              '      question that has an image, then run this again.\n')

    if failures:
        print(f'{len(failures)} problem(s):')
        for failure in failures:
            print(f'  - {failure}')
        return 1

    print('All pages and assets OK.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
