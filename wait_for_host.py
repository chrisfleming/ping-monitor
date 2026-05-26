#!/usr/bin/env python3
"""
wait_for_host — wait until a host comes back online.

If ping_server is running, registers the host with it and shows a live
dashboard until the host is UP, then cleans up.

If ping_server is not running, falls back to a plain ping loop (like the
original bash script).

Usage:
  python wait_for_host.py 192.168.1.1
  python wait_for_host.py --server http://192.168.1.10:8765 myhost.local
  python wait_for_host.py --keep 8.8.8.8      # don't remove from server on exit
  python wait_for_host.py --no-server 10.0.0.1  # force standalone mode
"""

import argparse
import platform
import subprocess
import sys
import time
from datetime import datetime

from monitor_common import (
    HAS_RICH, config as _cfg,
    server_alive, fetch_stats, add_host, remove_host,
    build_stats_table, build_error_panel, elapsed_str,
)

if HAS_RICH:
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.text import Text
    from rich.align import Align



def build_waiting_panel(target, stats, elapsed):
    header = Text()
    header.append("Waiting for ", style="white")
    header.append(target, style="bold yellow")
    header.append(f"  —  {elapsed_str(elapsed)}  —  {datetime.now().strftime('%H:%M:%S')}", style="dim")

    table = build_stats_table(
        stats,
        highlight=target,
    )
    return Panel(
        Align.center(table),
        title=header,
        subtitle=" ▁▂▃▄▅▆▇█ = latency   ✗ = dropped   ▶ = target host",
        border_style="yellow",
        padding=(0, 1),
    )


def build_success_panel(target, elapsed):
    msg = Text()
    msg.append(f"\n  ✓  {target}  is back online!\n\n", style="bold green")
    msg.append(f"  Waited {elapsed_str(elapsed)}\n", style="dim")
    return Panel(msg, title="[bold green]Host reachable[/bold green]", border_style="green", padding=(1, 4))


# Server mode

def wait_with_server(target, base_url, keep, console):
    console.print(f"[dim]Registering [bold]{target}[/bold] with server {base_url} ...[/dim]")
    result, err = add_host(base_url, target)
    if err:
        console.print(f"[red]Failed to add host: {err}[/red]")
        return False

    console.print(f"[dim]{'Host added.' if result.get('added') else 'Already monitored.'}[/dim]")

    start = time.monotonic()
    success = False

    try:
        with Live(console=console, refresh_per_second=4, screen=False) as live:
            while True:
                try:
                    stats, err = fetch_stats(base_url)
                    elapsed = time.monotonic() - start
                    if err:
                        live.update(Panel(
                            Text(f"Lost connection to server: {err}", style="bold red"),
                            border_style="red",
                        ))
                    elif stats.get(target, {}).get("status") == "up":
                        live.update(build_success_panel(target, elapsed))
                        sys.stdout.write("\a")
                        sys.stdout.flush()
                        success = True
                        time.sleep(2)
                        break
                    else:
                        live.update(build_waiting_panel(target, stats, elapsed))
                except Exception as exc:
                    live.update(Panel(Text(f"Error: {exc}", style="red"), border_style="red"))
                time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")

    if not keep:
        _, err = remove_host(base_url, target)
        if not err:
            console.print(f"[dim]Removed {target} from server.[/dim]")

    return success


# Standalone

def ping_once(host):
    is_windows = platform.system() == "Windows"
    cmd = ["ping", "-n", "1", "-w", "1000", host] if is_windows else ["ping", "-c", "1", "-W", "1", host]
    try:
        return subprocess.run(cmd, capture_output=True, timeout=3).returncode == 0
    except Exception:
        return False


def wait_standalone(target, console):
    """Plain ping loop — mirrors the original bash script behaviour."""
    msg = "ping_server not found — running standalone ping loop"
    console.print(f"[yellow]{msg}[/yellow]") if HAS_RICH else print(msg)

    start = time.monotonic()
    attempt = 0

    while True:
        attempt += 1
        reachable = ping_once(target)
        elapsed = time.monotonic() - start
        ts = datetime.now().strftime("%H:%M:%S")

        if HAS_RICH:
            mark = Text("UP", style="bold green") if reachable else Text("unreachable", style="red")
            console.print(f"[dim]{ts}[/dim]  {target}  ", mark, f"  (attempt {attempt}, {int(elapsed)}s)")
        else:
            print(f"[{ts}] {target}  {'OK' if reachable else '...'}  (attempt {attempt}, {int(elapsed)}s)")

        if reachable:
            summary = f"✓  {target} is back online!  (waited {elapsed_str(elapsed)})"
            console.print(f"\n[bold green]{summary}[/bold green]\n") if HAS_RICH else print(f"\n{summary}\n")
            sys.stdout.write("\a")
            sys.stdout.flush()
            return True

        time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description="Wait for a host to come back online.")
    parser.add_argument("host", help="Hostname or IP to wait for")
    parser.add_argument("--server", default=_cfg["server"],
                        help=f"ping_server base URL (default: {_cfg['server']})")
    parser.add_argument("--keep", action="store_true",
                        help="Don't remove host from server after it comes back")
    parser.add_argument("--no-server", action="store_true",
                        help="Skip server check and use standalone ping loop")
    args = parser.parse_args()

    console = Console() if HAS_RICH else None

    if not args.no_server and server_alive(args.server):
        ok = wait_with_server(args.host, args.server, args.keep, console)
    else:
        if not args.no_server:
            msg = f"ping_server not reachable at {args.server}, falling back to standalone mode."
            console.print(f"[dim]{msg}[/dim]") if HAS_RICH else print(msg)
        ok = wait_standalone(args.host, console)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(1)
