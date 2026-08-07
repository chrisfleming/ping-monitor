#!/usr/bin/env python3
"""Find the last RFC1918 hop before traffic exits to the public internet."""

import subprocess
import re
import ipaddress
import sys


def is_rfc1918(ip_str: str) -> bool:
    """Return True if the IP is in a private (RFC1918) range."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_private and not ip.is_loopback
    except ValueError:
        return False


def is_public(ip_str: str) -> bool:
    """Return True if the IP is a routable public address."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return not ip.is_private and not ip.is_loopback and not ip.is_link_local
    except ValueError:
        return False


def run_traceroute(target: str = "8.8.8.8", max_hops: int = 30) -> list[tuple[int, str]]:
    """
    Run traceroute and return a list of (hop_number, ip) tuples.
    Unresponsive hops are skipped.
    """
    # -n: no DNS resolution, -m: max hops, -w: wait seconds per probe
    cmd = ["traceroute", "-n", "-m", str(max_hops), "-w", "2", target]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        # Try traceroute on systems where it might be named differently
        cmd[0] = "traceroute6" if ":" in target else "traceroute"
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except FileNotFoundError:
            print("Error: traceroute not found. Install it with: sudo apt install traceroute / sudo dnf install traceroute")
            sys.exit(1)
    except subprocess.TimeoutExpired:
        print("Error: traceroute timed out.")
        sys.exit(1)

    hops = []
    # Match lines like: " 1  192.168.1.1  1.234 ms ..."
    hop_re = re.compile(r"^\s*(\d+)\s+([\d.]+)")

    for line in result.stdout.splitlines():
        m = hop_re.match(line)
        if m:
            hop_num = int(m.group(1))
            ip = m.group(2)
            hops.append((hop_num, ip))

    return hops


def find_last_rfc1918_hop(target: str = "8.8.8.8") -> dict | None:
    """
    Trace to target and return info about the last RFC1918 hop
    before the first public IP appears.
    """
    print(f"Running traceroute to {target}...\n")
    hops = run_traceroute(target)

    if not hops:
        print("No hops found — traceroute returned no results.")
        return None

    last_private = None
    first_public = None

    for hop_num, ip in hops:
        if is_rfc1918(ip):
            last_private = (hop_num, ip)
        elif is_public(ip) and first_public is None:
            first_public = (hop_num, ip)
            break  # No need to go further

    return {
        "hops": hops,
        "last_rfc1918": last_private,
        "first_public": first_public,
    }


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "8.8.8.8"

    result = find_last_rfc1918_hop(target)
    if not result:
        sys.exit(1)

    print("Hops found:")
    for hop_num, ip in result["hops"]:
        tag = ""
        if result["last_rfc1918"] and hop_num == result["last_rfc1918"][0]:
            tag = "  <-- last RFC1918"
        elif result["first_public"] and hop_num == result["first_public"][0]:
            tag = "  <-- first public"
        print(f"  {hop_num:>3}.  {ip:<18}{tag}")

    print()
    if result["last_rfc1918"]:
        hop_num, ip = result["last_rfc1918"]
        print(f"Last RFC1918 hop:  {ip}  (hop {hop_num})")
    else:
        print("No RFC1918 hops found — you may already be on a public IP.")

    if result["first_public"]:
        hop_num, ip = result["first_public"]
        print(f"First public hop:  {ip}  (hop {hop_num})")


if __name__ == "__main__":
    main()
