"""Simulate a room full of phones polling the live site.

At the party ~35 guests poll every 2s, which is ~18 requests/second sustained
for a couple of hours. This checks PythonAnywhere's workers can actually carry
that before the guests arrive rather than after.

    python scripts/load_test.py https://rethrow.dk --token <uuid> --clients 35

Deliberately pessimistic: it omits the `s=` state token that real phones send,
so every request re-renders the full fragment instead of short-circuiting to a
204. If the numbers hold here, the real party is comfortably lighter.

Read-only (GET on the poll endpoints only), so it writes nothing to the
database and is safe to run against production. Stdlib only.
"""

import argparse
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter


def poll(url, token):
    """One GET. Returns (status_or_None, elapsed_seconds)."""
    request = urllib.request.Request(url)
    request.add_header('User-Agent', 'load-test/1.0')
    if token:
        request.add_header('Cookie', f'player_token={token}')
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
            return response.status, time.perf_counter() - started
    except urllib.error.HTTPError as error:
        return error.code, time.perf_counter() - started
    except (urllib.error.URLError, OSError):
        return None, time.perf_counter() - started


def client(url, token, interval, deadline, results, lock):
    """One simulated phone: poll, wait out the rest of the interval, repeat."""
    while time.monotonic() < deadline:
        cycle_started = time.monotonic()
        status, elapsed = poll(url, token)
        with lock:
            results.append((status, elapsed))
        remaining = interval - (time.monotonic() - cycle_started)
        if remaining > 0:
            time.sleep(remaining)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', help='Site root, e.g. https://rethrow.dk')
    parser.add_argument('--token', help='A Player token (uuid), so the guest poll endpoint is reachable')
    parser.add_argument('--clients', type=int, default=35, help='Simulated phones (default: 35)')
    parser.add_argument('--interval', type=float, default=2.0, help='Seconds between polls (default: 2)')
    parser.add_argument('--duration', type=float, default=60.0, help='Seconds to run (default: 60)')
    args = parser.parse_args()

    base = args.base.rstrip('/')
    if args.token:
        url = f'{base}/quiz/status/'
        target = 'guest quiz poll'
    else:
        # No token means the guest endpoint would just bounce to /velkommen/,
        # which measures nothing. The projector poll is public and does the
        # heavier query, so it is a fair stand-in.
        url = f'{base}/quiz/projektor/status/'
        target = 'projector poll (no --token given)'

    print(f'{args.clients} clients -> {url}')
    print(f'{target}, every {args.interval}s for {args.duration}s')
    print(f'expected load: {args.clients / args.interval:.1f} req/s\n')

    results = []
    lock = threading.Lock()
    deadline = time.monotonic() + args.duration
    threads = []
    for index in range(args.clients):
        thread = threading.Thread(
            target=client, args=(url, args.token, args.interval, deadline, results, lock),
            daemon=True,
        )
        thread.start()
        threads.append(thread)
        # Spread the starts across one interval so all the phones don't hit the
        # server in the same millisecond, the way a real room doesn't.
        time.sleep(args.interval / max(args.clients, 1))

    started = time.monotonic()
    for thread in threads:
        thread.join()
    ran_for = time.monotonic() - started

    if not results:
        print('No requests completed.')
        return 1

    statuses = Counter(status for status, _ in results)
    latencies = sorted(elapsed for _, elapsed in results)

    def percentile(fraction):
        return latencies[min(int(len(latencies) * fraction), len(latencies) - 1)]

    print(f'requests:   {len(results)} in {ran_for:.0f}s ({len(results) / ran_for:.1f} req/s)')
    print('statuses:  ', ', '.join(
        f'{status if status else "ERROR"}: {count}' for status, count in statuses.most_common()
    ))
    print(f'latency:    median {percentile(0.5) * 1000:.0f}ms   '
          f'p90 {percentile(0.9) * 1000:.0f}ms   '
          f'p99 {percentile(0.99) * 1000:.0f}ms   '
          f'max {latencies[-1] * 1000:.0f}ms')
    print(f'            mean {statistics.mean(latencies) * 1000:.0f}ms')

    errors = statuses.get(None, 0) + sum(
        count for status, count in statuses.items() if status and status >= 500
    )
    print()
    if errors:
        print(f'PROBLEM: {errors} failed request(s). The server did not carry this load.')
        return 1
    if percentile(0.9) > 2.0:
        print('PROBLEM: p90 is slower than the 2s poll interval, so phones would '
              'fall behind. Reduce load or add workers.')
        return 1
    print('Healthy: no errors, and responses comfortably faster than the poll interval.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
