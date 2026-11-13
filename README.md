# ping-monitor

A terminal network monitoring tool with a live dashboard and sparkline graphs.
Split into a server (pings hosts, exposes stats) and a client (displays the dashboard),
so the monitor can run on one machine and be watched from another.

## Configuration

On first run, a config file is created at `~/.config/ping-monitor/config.json` with all defaults:

```json
{
  "server": "http://localhost:8765",
  "port": 8765,
  "history": 60,
  "interval": 1.0,
  "threshold": 3,
  "latency_good_ms": 50,
  "latency_warn_ms": 150
}
```

| Key               | Used by               | Description                                     |
| ----------------- | --------------------- | ----------------------------------------------- |
| `server`          | client, wait_for_host | Default server URL to connect to                |
| `port`            | server                | Port the server listens on                      |
| `history`         | server                | Number of pings kept per host                   |
| `interval`        | server, client        | Seconds between pings / client refresh rate     |
| `threshold`       | server                | Consecutive failures before marking a host DOWN |
| `latency_good_ms` | client, wait_for_host | Latency below this is shown green               |
| `latency_warn_ms` | client, wait_for_host | Latency below this is yellow, above is red      |

Command-line flags always override config values.

---

## Requirements

- Python 3.7+
- [`rich`](https://github.com/Textualize/rich) for the terminal UI

```bash
pip install rich
# or
pip install -r requirements.txt
```

## Files

| File                | Purpose                                          |
| ------------------- | ------------------------------------------------ |
| `ping_server.py`    | Pings hosts, exposes rolling stats over HTTP     |
| `ping_client.py`    | Live terminal dashboard — connects to the server |
| `wait_for_host.py`  | Waits for a host to come back online             |
| `monitor_common.py` | Shared utilities (imported by client scripts)    |

---

## ping_server.py

Pings one or more hosts every second and serves the rolling stats as JSON on `/stats`.

```bash
python ping_server.py 8.8.8.8 1.1.1.1 192.168.1.1
python ping_server.py --port 9000 --history 120 8.8.8.8
```

| Option        | Default | Description                                     |
| ------------- | ------- | ----------------------------------------------- |
| `--port`      | `8765`  | HTTP port to listen on                          |
| `--history`   | `60`    | Number of pings to keep per host                |
| `--interval`  | `1.0`   | Seconds between pings                           |
| `--threshold` | `3`     | Consecutive failures before marking a host DOWN |

Hosts can also be added and removed at runtime via the API (see below).

Hosts given as a hostname (not an IP literal) are resolved to an IP once when
added, and that IP is pinged for the lifetime of the host — this pins the
target so round-robin/dynamic DNS can't shift it mid-history. The dashboard
and stats still report by the original hostname; the resolved IP is shown
alongside it. If resolution fails at add-time, the hostname is pinged
directly (letting the `ping` command resolve it itself each probe), same as
before this feature existed.

---

## ping_client.py

Connects to the server and displays a live updating dashboard.

```bash
python ping_client.py
python ping_client.py --server http://192.168.1.10:9000
python ping_client.py --interval 0.5
```

| Option       | Default                 | Description                 |
| ------------ | ----------------------- | --------------------------- |
| `--server`   | `http://localhost:8765` | Server base URL             |
| `--interval` | `1.0`                   | Refresh interval in seconds |

The dashboard shows for each host:

```
Host               Status   Last(ms)  Avg(ms)  Min(ms)  Max(ms)  Loss   Graph
192.168.1.1        ⬤ UP      4.2       4.1      3.8      5.1      0.0%  ▃▃▄▃▄▄▃▃
8.8.8.8            ⬤ DOWN    —         12.3     10.1     14.8     80.0% ▂▂✗✗✗✗✗✗
  ⚠  5 consecutive failure(s)!
```

- The graph shows the last 40 pings as a sparkline: `▁▂▃▄▅▆▇█`
- `✗` marks a dropped ping
- Colours: green &lt;50 ms · yellow &lt;150 ms · red ≥150 ms
- A host is marked **DOWN** after 3 consecutive missed pings (configurable)

---

## wait_for_host.py

Waits until a host comes back online; replaces simple bash ping loop.

```bash
python wait_for_host.py 192.168.1.1
python wait_for_host.py --server http://localhost:9000 192.168.1.1
```

**With ping_server running** — registers the host with the server, shows the full
live dashboard with the target host highlighted, and exits with a success message
(and a terminal bell) when it comes back up. Removes the host from the server on exit.

**Without ping_server** — falls back to a plain ping loop, printing one line per attempt,
same behaviour as the original bash script.

| Option        | Default                 | Description                                |
| ------------- | ----------------------- | ------------------------------------------ |
| `--server`    | `http://localhost:8765` | ping_server base URL                       |
| `--keep`      | off                     | Leave host in server after it comes back   |
| `--no-server` | off                     | Skip server detection, use standalone mode |

Exit code is `0` on success, `1` if interrupted.

---

## Running server and client on different machines

```bash
# On the monitoring machine
python ping_server.py --port 9000 8.8.8.8 1.1.1.1

# On any other machine on the network
python ping_client.py --server http://192.168.1.10:9000
python wait_for_host.py --server http://192.168.1.10:9000 192.168.1.254
```

---

## Server API

The server exposes a small HTTP API, useful for scripting or integration.

| Method   | Path            | Description                                 |
| -------- | --------------- | ------------------------------------------- |
| `GET`    | `/stats`        | JSON snapshot of all hosts                  |
| `GET`    | `/health`       | Returns `ok` — use to check if server is up |
| `POST`   | `/hosts`        | Add a host at runtime                       |
| `DELETE` | `/hosts/<host>` | Remove a host at runtime                    |

**Add a host:**

```bash
curl -X POST http://localhost:9000/hosts \
     -H 'Content-Type: application/json' \
     -d '{"host": "192.168.1.50"}'
```

**Remove a host:**

```bash
curl -X DELETE http://localhost:9000/hosts/192.168.1.50
```

**Stats response shape:**

```json
{
  "8.8.8.8": {
    "status": "up",
    "consecutive_failures": 0,
    "avg_latency": 12.3,
    "min_latency": 10.1,
    "max_latency": 14.8,
    "packet_loss_pct": 0.0,
    "total_sent": 60,
    "history": [12.1, 11.8, null, 13.0, "..."],
    "last_ping": "2026-05-21T14:30:00.123456",
    "resolved_ip": null
  }
}
```

`history` is an array of latency values in ms, with `null` for dropped pings,
newest last. Length is controlled by `--history` (default 60).
