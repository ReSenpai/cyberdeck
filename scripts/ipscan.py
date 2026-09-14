#!/usr/bin/env python3
"""ipscan — лёгкий TCP-скан доступности + geo/ASN-обогащение, без root и masscan.

Чистый Python: соединяется с каждым ``host:port``, помечает открытые/закрытые,
по желанию (--geo) узнаёт владельца через ip-api.com и группирует по провайдеру
и подсети /16. В отличие от исходного чекера, проверяет НАСТОЯЩИЙ порт из
конверта (а не хардкод :80), понимает IPv6 и домены, работает пачкой потоков.

Встаёт в середину цепочки кибердеки:

    cat sub.txt | ./vlessparse.py --json | ./ipscan.py --geo --json > alive.json
    echo 1.1.1.1 | ./ipscan.py -p 80,443,8443
    ./vlessparse.py sub.txt --targets | ./ipscan.py --geo

Порты берутся из входного конверта; для голых адресов — из ``-p`` (по умолчанию
80,443). Логи и прогресс — в stderr, JSON (--json) или отчёт — в stdout.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib import request as urlrequest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cyberdeck import Envelope, make_port, read_input  # noqa: E402
from cyberdeck.ui import UI, force_utf8  # noqa: E402

force_utf8()

TOOL = "ipscan"
VERSION = "0.1.0"

GEO_URL = "http://ip-api.com/batch"
GEO_FIELDS = "status,message,query,country,countryCode,city,isp,org,as,asname"
GEO_KEYS = ("country", "countryCode", "city", "isp", "org", "as", "asname")
GEO_BATCH = 100  # лимит ip-api на один батч


# --------------------------------------------------------------------------
# порты и цели
# --------------------------------------------------------------------------

def expand_ports(spec: str) -> list[int]:
    """'80,443,8000-8010' -> список портов."""
    ports: list[int] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start, end = chunk.split("-", 1)
            ports.extend(range(int(start), int(end) + 1))
        else:
            ports.append(int(chunk))
    return list(dict.fromkeys(ports))


def split_addr_port(token: str) -> tuple[str, int | None]:
    """'1.2.3.4:443' / '[::1]:443' / 'host' -> (addr, port|None). IPv6-безопасно."""
    if token.startswith("["):  # [ipv6](:port)?
        host, sep, rest = token[1:].partition("]")
        if sep and rest.startswith(":") and rest[1:].isdigit():
            return host, int(rest[1:])
        return host, None
    if token.count(":") == 1:
        host, _, port = token.partition(":")
        if port.isdigit():
            return host, int(port)
    return token, None


def is_ipv4(addr: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(addr), ipaddress.IPv4Address)
    except ValueError:
        return False


def subnet16(ip: str) -> str | None:
    if not is_ipv4(ip):
        return None
    a, b, *_ = ip.split(".")
    return f"{a}.{b}.0.0/16"


# --------------------------------------------------------------------------
# проба и резолв
# --------------------------------------------------------------------------

def tcp_probe(addr: str, port: int, timeout: float) -> tuple[str, str, str]:
    """(state, resolved_ip, reason). state: open|closed|filtered."""
    try:
        with socket.create_connection((addr, port), timeout=timeout) as sock:
            ip = sock.getpeername()[0]
        return "open", ip, "connected"
    except socket.timeout:
        return "filtered", "", "timeout"
    except ConnectionRefusedError:
        return "closed", "", "refused"
    except OSError as exc:
        return "closed", "", (exc.strerror or type(exc).__name__)


def resolve(addr: str) -> str:
    """addr -> IP (или '' если не резолвится). IP отдаём как есть."""
    try:
        ipaddress.ip_address(addr)
        return addr
    except ValueError:
        pass
    try:
        return socket.getaddrinfo(addr, None)[0][4][0]
    except (socket.gaierror, OSError, IndexError):
        return ""


def geo_lookup(ips: list[str], ui: UI) -> dict[str, dict]:
    """ip-api.com батчами -> {ip: {country, isp, as, ...}}. Тихо переживает офлайн."""
    out: dict[str, dict] = {}
    for i in range(0, len(ips), GEO_BATCH):
        chunk = ips[i:i + GEO_BATCH]
        body = json.dumps([{"query": ip, "fields": GEO_FIELDS} for ip in chunk]).encode()
        req = urlrequest.Request(
            GEO_URL, data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlrequest.urlopen(req, timeout=15) as resp:
                entries = json.loads(resp.read().decode("utf-8", "replace"))
        except Exception as exc:  # noqa: BLE001 — сеть не должна валить скан
            ui.warn(f"geo: батч {i // GEO_BATCH + 1} не удался: {exc}")
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("status") == "success":
                query = entry.get("query")
                out[query] = {k: entry[k] for k in GEO_KEYS if entry.get(k)}
        if i + GEO_BATCH < len(ips):
            time.sleep(4)  # ip-api: 15 батчей/мин
    return out


# --------------------------------------------------------------------------
# сбор ввода
# --------------------------------------------------------------------------

def collect(args, ui: UI):
    """Хосты для проверки: из входного конверта (с портами и метаданными) и/или
    из голых адресов (аргументы/stdin), которым порты даёт -p.

    Возвращает (plan, seeded_hosts): plan = {addr: {"ports": set, "meta": host|None}}.
    """
    # stdin читаем, только когда целей нет в аргументах и это не терминал —
    # иначе скрипт из обёртки с незакрытым stdin встанет на read().
    piped = None
    if not args.targets and not sys.stdin.isatty():
        piped = read_input(sys.stdin.read())

    default_ports = expand_ports(args.ports)
    plan: dict[str, dict] = {}

    def want(addr: str) -> dict:
        return plan.setdefault(addr, {"ports": set(), "meta": None})

    piped_hosts = {h["ip"]: h for h in (piped.hosts if piped else [])}
    for addr, host in piped_hosts.items():
        entry = want(addr)
        entry["meta"] = host
        host_ports = [p["port"] for p in host.get("ports", [])]
        entry["ports"].update(host_ports or default_ports)

    bare = list(args.targets)
    if piped:
        bare += [t for t in piped.targets if t not in piped_hosts]
    for token in dict.fromkeys(bare):
        addr, port = split_addr_port(token)
        entry = want(addr)
        entry["ports"].update([port] if port is not None else default_ports)

    return plan


# --------------------------------------------------------------------------
# отчёт
# --------------------------------------------------------------------------

def human_report(payload: dict) -> None:
    stats = payload["stats"]
    hosts = payload["hosts"]

    print("\n== IP SCAN ==")
    print(f"  целей ......... {stats.get('targets', 0)}")
    print(f"  живых ......... {stats.get('alive', 0)}")
    print(f"  мёртвых ....... {stats.get('dead', 0)}")
    print(f"  открытых портов {stats.get('open_ports', 0)}")

    print("\n  хосты:")
    for host in hosts:
        rip = host.get("resolved_ip", "")
        rip_col = f" [{rip}]" if rip and rip != host["ip"] else ""
        geo = host.get("geo") or {}
        loc = " ".join(filter(None, [geo.get("countryCode", ""), geo.get("isp", "")]))
        mark = "up" if host["state"] == "up" else "down"
        print(f"    {host['ip']:<22}{rip_col:<18} {mark:<4} {loc}")
        opened = [str(p["port"]) for p in host["ports"] if p.get("state") == "open"]
        if opened:
            print(f"      open: {', '.join(opened)}")

    by_provider = stats.get("by_provider")
    if by_provider:
        print("\n  по провайдерам:")
        top = sorted(by_provider.items(), key=lambda kv: -kv[1])
        peak = top[0][1] if top else 1
        for name, count in top:
            bar = "█" * max(1, round(count / peak * 20))
            print(f"    {name[:28]:<28} {count:>3}  {bar}")

    by_subnet = stats.get("by_subnet")
    if by_subnet:
        print("\n  по подсетям /16:")
        for name, count in sorted(by_subnet.items(), key=lambda kv: -kv[1]):
            print(f"    {name:<18} {count}")
    print()


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ipscan",
        description="TCP-проверка доступности + geo/ASN (ip-api). Цепочки через --json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "примеры:\n"
            "  echo 1.1.1.1 | ./ipscan.py -p 80,443\n"
            "  cat sub.txt | ./vlessparse.py --json | ./ipscan.py --geo --json\n"
            "  ./ipscan.py 8.8.8.8 1.1.1.1 --geo --alive-only\n"
        ),
    )
    parser.add_argument("targets", nargs="*", help="IP/домен/host:port (иначе stdin)")

    scan = parser.add_argument_group("скан")
    scan.add_argument("-p", "--ports", default="80,443",
                      help="порты для голых адресов без порта (по умолчанию 80,443)")
    scan.add_argument("-t", "--timeout", type=float, default=3.0, help="таймаут коннекта, сек (3.0)")
    scan.add_argument("-c", "--concurrency", type=int, default=100, help="одновременных проб (100)")

    enrich = parser.add_argument_group("обогащение")
    enrich.add_argument("--geo", action="store_true", help="узнать владельца/страну через ip-api.com")

    out = parser.add_argument_group("вывод")
    out.add_argument("--json", action="store_true", help="конверт cyberdeck.v1 в stdout")
    out.add_argument("--alive-only", action="store_true", help="оставить в выводе только живые хосты")
    out.add_argument("-o", "--out", help="сохранить JSON в файл")
    out.add_argument("-q", "--quiet", action="store_true", help="без прогресса и логов")
    out.add_argument("-v", "--verbose", action="store_true", help="показывать каждую пробу")
    out.add_argument("--no-color", action="store_true", help="без цвета")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    ui = UI(quiet=args.quiet, verbose=args.verbose, color=not args.no_color)
    env = Envelope(TOOL, VERSION, params={
        "ports": args.ports,
        "timeout": args.timeout,
        "concurrency": args.concurrency,
        "geo": args.geo,
    })
    ui.banner("CYBERDECK :: ipscan", f"run {env.run_id}")

    plan = collect(args, ui)
    if not plan:
        ui.err_msg("нет целей: задай IP/домен аргументом или подай на stdin")
        return 2

    env.targets = list(plan.keys())
    # перенесём метаданные входного конверта (configs/hostnames), чтобы цепочка
    # не теряла разбор VLESS при проходе через сканер
    for addr, entry in plan.items():
        host = env.host(addr)
        meta = entry["meta"]
        if meta:
            for name in meta.get("hostnames", []):
                if name not in host["hostnames"]:
                    host["hostnames"].append(name)
            if meta.get("configs"):
                host["configs"] = meta["configs"]

    tasks = [(addr, port) for addr, entry in plan.items() for port in sorted(entry["ports"])]
    ui.info(f"хостов: {len(plan)}, проб: {len(tasks)}, потоки: {args.concurrency}, таймаут: {args.timeout}s")

    open_ip: dict[str, str] = {}  # addr -> resolved ip из первого открытого порта
    opened = 0

    with ui.progress() as bar:
        task_id = bar.add("scan", total=float(len(tasks)))
        done = 0
        with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
            futures = {
                pool.submit(tcp_probe, addr, port, args.timeout): (addr, port)
                for addr, port in tasks
            }
            for future in as_completed(futures):
                addr, port = futures[future]
                state, ip, reason = future.result()
                env.add_port(addr, make_port(port, "tcp", state, source="ipscan", reason=reason))
                if state == "open":
                    opened += 1
                    env.host(addr)["state"] = "up"
                    open_ip.setdefault(addr, ip)
                    bar.log(f"[bold green]  +[/] {addr}[dim]:[/][bold]{port}[/]")
                elif args.verbose:
                    ui.raw(f"{addr}:{port} {state} ({reason})")
                done += 1
                bar.update(task_id, completed=float(done), note=f"[dim]открыто {opened}[/]")

    # состояние хостов + резолв для подсетей/geo
    alive = dead = 0
    for host in env.hosts:
        addr = host["ip"]
        if host["state"] != "up":
            host["state"] = "down"
            dead += 1
        else:
            alive += 1
        rip = open_ip.get(addr) or resolve(addr)
        if rip:
            host["resolved_ip"] = rip

    ui.ok(f"живых {alive}, мёртвых {dead}, открытых портов {opened}")

    # geo-обогащение
    geo_map: dict[str, dict] = {}
    if args.geo:
        ips = list(dict.fromkeys(
            h["resolved_ip"] for h in env.hosts if h.get("resolved_ip")
        ))
        if ips:
            ui.stage(f"geo: запрашиваю владельцев {len(ips)} IP через ip-api.com")
            geo_map = geo_lookup(ips, ui)
            for host in env.hosts:
                info = geo_map.get(host.get("resolved_ip", ""))
                if info:
                    host["geo"] = info
            ui.ok(f"geo: опознано {len(geo_map)} из {len(ips)}")

    # группировки
    by_subnet: dict[str, int] = {}
    by_provider: dict[str, int] = {}
    for host in env.hosts:
        if host["state"] != "up":
            continue
        net = subnet16(host.get("resolved_ip", ""))
        if net:
            by_subnet[net] = by_subnet.get(net, 0) + 1
        if args.geo:
            geo = host.get("geo") or {}
            name = geo.get("isp") or geo.get("org") or geo.get("asname") or "unknown"
            by_provider[name] = by_provider.get(name, 0) + 1

    if args.alive_only:
        env.filter_hosts(lambda h: h["state"] == "up")

    env.add_stat("alive", alive)
    env.add_stat("dead", dead)
    env.add_stat("probes", len(tasks))
    env.add_stat("by_subnet", by_subnet)
    if args.geo:
        env.add_stat("by_provider", by_provider)

    payload = env.to_dict()

    if args.out:
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        ui.ok(f"JSON сохранён: {args.out}")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=None if args.quiet else 2))
    else:
        human_report(payload)

    return 0 if env.status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
