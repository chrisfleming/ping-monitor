#!/usr/bin/env python3
"""
Ping Monitor Client
Connects to ping_server.py and displays a live terminal dashboard.

Usage: python ping_client.py
       python ping_client.py --server http://192.168.1.10:8765
       python ping_client.py --interval 0.5

Requires: pip install rich
"""

import argparse
import sys
import time
from datetime import datetime

from monitor_common import (
    HAS_RICH, LEGEND, config as _cfg,
    fetch_stats, build_stats_table, build_error_panel, ms_str,
)

if HAS_RICH:
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.text import Text
    from rich.align import Align


def build_dashboard(stats):
    now = datetime.now().strftime("%H:%M:%S")
    table = build_stats_table(
        stats,
        title=f"[bold white]Ping Monitor[/bold white]   [dim]{now}[/dim]",
    )
    return Panel(
        Align.center(table),
        subtitle=LEGEND,
        border_style="bright_blue",
        padding=(0, 1),
    )


def simple_display(base_url, interval):
    """Fallback display when rich is not installed."""
    print("Tip: install 'rich' for a better display:  pip install rich\n")
    while True:
        stats, err = fetch_stats(base_url)
        ts = datetime.now().strftime("%H:%M:%S")
        if err:
            print(f"[{ts}] ERROR: {err}")
        else:
            print(f"\n{'='*60}  {ts}")
            for host, d in stats.items():
                status = d["status"].upper()
                avg = f"{d['avg_latency']:.1f}ms" if d["avg_latency"] is not None else "N/A"
                loss = f"{d['packet_loss_pct']:.1f}%"
                cf = d["consecutive_failures"]
                flag = "  *** DOWN ***" if status == "DOWN" else ""
                print(f"  {host:<25}  {status:<6}  avg={avg:<10}  loss={loss:<7}  fail={cf}{flag}")
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="Ping monitor client — live terminal dashboard")
    parser.add_argument("--server",   default=_cfg["server"],
                        help=f"Server base URL (default: {_cfg['server']})")
    parser.add_argument("--interval", type=float, default=_cfg["interval"],
                        help=f"Refresh interval in seconds (default: {_cfg['interval']})")
    args = parser.parse_args()

    if not HAS_RICH:
        simple_display(args.server, args.interval)
        return

    console = Console()

    console.print(f"[dim]Connecting to {args.server} ...[/dim]")
    _, err = fetch_stats(args.server)
    if err:
        console.print(f"[bold red]Cannot reach server:[/bold red] {err}")
        console.print("[yellow]Make sure ping_server.py is running. Will keep retrying.[/yellow]")

    with Live(console=console, refresh_per_second=4, screen=False) as live:
        while True:
            try:
                stats, err = fetch_stats(args.server)
                if err:
                    live.update(build_error_panel(args.server, err))
                else:
                    live.update(build_dashboard(stats))
            except Exception as exc:
                live.update(Panel(Text(f"Render error: {exc}", style="bold red"), border_style="red"))

            time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
