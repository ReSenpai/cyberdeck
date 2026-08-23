#!/usr/bin/env python3
"""portscan — masscan находит открытые порты, nmap опознаёт сервисы на них.

Двухэтапный скан по концепции пайпов кибердеки:
  1. masscan прочёсывает весь диапазон портов на скорости, которую задаёшь сам;
  2. найденные порты уходят в nmap -sV поштучно по хостам.

Логи и прогресс идут в stderr, машинный JSON (--json) — в stdout, поэтому
скрипт спокойно встаёт в середину цепочки:

    ./portscan.py 10.0.0.0/24 --json | ./httpprobe.py --json | ./report.py
    echo 10.0.0.1 | ./portscan.py --json > scan.json
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cyberdeck import Envelope, make_port, read_input  # noqa: E402
from cyberdeck import proc  # noqa: E402
from cyberdeck.ui import UI, force_utf8  # noqa: E402

force_utf8()

TOOL = "portscan"
VERSION = "0.1.0"

# masscan: "Discovered open port 22/tcp on 10.0.0.1"
RE_MASSCAN_PORT = re.compile(r"Discovered open port (\d+)/(tcp|udp) on ([0-9a-fA-F:.]+)")
# masscan: "rate: 12.34-kpps,  4.21% done,   0:03:12 remaining, found=7"
RE_PERCENT = re.compile(r"([\d.]+)%\s*done")
RE_RATE = re.compile(r"rate:\s*([\d.]+)-k?pps")
RE_FOUND = re.compile(r"found=(\d+)")
RE_REMAINING = re.compile(r"([\d:]+)\s*remaining")
# nmap --stats-every: "Service scan Timing: About 45.67% done; ETC: 20:15 (0:00:12 remaining)"
RE_NMAP_PERCENT = re.compile(r"About\s+([\d.]+)%\s+done")


# --------------------------------------------------------------------------
# аргументы
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="portscan",
        description="masscan (все порты) -> nmap -sV (сервисы). Цепочки через --json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "примеры:\n"
            "  sudo ./portscan.py 10.0.0.1\n"
            "  sudo ./portscan.py 10.0.0.0/24 -p 0-65535 --rate 5000 --json -o scan.json\n"
            "  cat hosts.txt | sudo ./portscan.py --sudo --json | ./next.py\n"
        ),
    )
    parser.add_argument("targets", nargs="*", help="IP, CIDR или диапазон (можно несколько)")

    scan = parser.add_argument_group("скан")
    scan.add_argument("-p", "--ports", default="0-65535", help="диапазон для masscan (по умолчанию все 0-65535)")
    scan.add_argument("--rate", type=int, default=1000, help="пакетов/сек для masscan (по умолчанию 1000)")
    scan.add_argument("--wait", type=int, default=3, help="сколько секунд ждать ответы после отправки (3)")
    scan.add_argument("-i", "--interface", help="сетевой интерфейс для masscan")
    scan.add_argument("--exclude", help="что исключить из скана (masscan --exclude)")
    scan.add_argument("--masscan-grace", type=float, default=None, metavar="SEC",
                      help="сколько ждать выхода masscan после 100%% (по умолчанию --wait + 10)")
    scan.add_argument("--masscan-extra", default="", help="доп. аргументы masscan одной строкой")

    svc = parser.add_argument_group("опознание сервисов")
    svc.add_argument("--nmap-args", default="-sV -Pn -T4", help="базовые аргументы nmap ('-sV -Pn -T4')")
    svc.add_argument("--nmap-extra", default="", help="доп. аргументы nmap одной строкой")
    svc.add_argument("-sC", "--scripts", action="store_true", help="добавить стандартные NSE-скрипты (-sC)")

    flow = parser.add_argument_group("этапы")
    flow.add_argument("--skip-discovery", action="store_true",
                      help="без masscan: берём порты из stdin или из --ports")
    flow.add_argument("--skip-nmap", action="store_true", help="только masscan, без опознания сервисов")
    flow.add_argument("--sudo", action="store_true", help="запускать masscan/nmap через sudo")

    out = parser.add_argument_group("вывод")
    out.add_argument("--json", action="store_true", help="выдать конверт cyberdeck.v1 в stdout")
    out.add_argument("-o", "--out", help="сохранить JSON в файл")
    out.add_argument("--raw-dir", help="сложить сырые выхлопы masscan/nmap в каталог")
    out.add_argument("-v", "--verbose", action="store_true", help="показывать сырые строки инструментов")
    out.add_argument("-q", "--quiet", action="store_true", help="без прогресса и логов")
    out.add_argument("--no-color", action="store_true", help="без цвета")
    return parser


# --------------------------------------------------------------------------
# этап 1: masscan
# --------------------------------------------------------------------------

def run_masscan(args, targets: list[str], ui: UI, env: Envelope, raw_path: Path | None) -> int:
    """Прогнать masscan, складывая находки прямо в конверт. Возвращает код возврата."""
    cmd = proc.sudo_prefix(args.sudo) + [
        "masscan", *targets,
        "-p", args.ports,
        "--rate", str(args.rate),
        "--wait", str(args.wait),
    ]
    if args.interface:
        cmd += ["-e", args.interface]
    if args.exclude:
        cmd += ["--exclude", args.exclude]
    if args.masscan_extra:
        cmd += shlex.split(args.masscan_extra)

    ui.stage("этап 1 — masscan: поиск открытых портов")
    ui.dim(" ".join(shlex.quote(c) for c in cmd))

    raw = raw_path.open("w", encoding="utf-8") if raw_path else None
    found = 0
    # masscan часто доходит до 100%, но не выходит (особенно под WSL): данные уже
    # собраны, а процесс висит. Досчитаем ему терпение сами.
    grace = args.masscan_grace if args.masscan_grace is not None else args.wait + 10
    done_at: float | None = None
    stalled = False
    stall_reason = ""
    interrupted = False

    silence_limit = grace + 30  # masscan сыплет статусом раз в секунду

    def watchdog(idle: float) -> bool:
        """Снять masscan, если он отработал, но не вышел, либо просто онемел."""
        nonlocal stalled, stall_reason
        if done_at is not None and time.monotonic() - done_at > grace:
            stalled, stall_reason = True, f"не завершился за {grace:.0f}с после 100%"
            return True
        if idle > silence_limit:
            stalled, stall_reason = True, f"молчит {idle:.0f}с"
            return True
        return False

    with ui.progress() as bar:
        task = bar.add("masscan", total=100.0)

        def on_stdout(line: str) -> None:
            nonlocal found
            if raw:
                raw.write(line + "\n")
            match = RE_MASSCAN_PORT.search(line)
            if match:
                port, protocol, ip = match.group(1), match.group(2), match.group(3)
                env.host(ip)["state"] = "up"
                env.add_port(ip, make_port(int(port), protocol, "open", source="masscan"))
                found += 1
                bar.log(f"[bold green]  +[/] {ip}[dim]:[/][bold]{port}[/]/{protocol}")
            else:
                ui.raw(line)

        def on_stderr(line: str) -> None:
            nonlocal done_at
            percent = RE_PERCENT.search(line)
            if percent:
                if done_at is None and (float(percent.group(1)) >= 100.0 or "waiting" in line):
                    done_at = time.monotonic()  # пошёл отсчёт терпения
                note = []
                rate = RE_RATE.search(line)
                if rate:
                    note.append(f"{rate.group(1)} kpps")
                remaining = RE_REMAINING.search(line)
                if remaining:
                    note.append(f"осталось {remaining.group(1)}")
                hits = RE_FOUND.search(line)
                note.append(f"найдено {hits.group(1) if hits else found}")
                bar.update(task, completed=float(percent.group(1)),
                           note="[dim]" + "  ".join(note) + "[/]")
            else:
                ui.raw(line)

        try:
            code = proc.stream(cmd, on_stdout, on_stderr, watchdog=watchdog)
        except KeyboardInterrupt:
            # первый Ctrl+C = «хватит искать, показывай сервисы по найденному»
            interrupted = True
            code = 0
        finally:
            if raw:
                raw.close()
        if not interrupted:  # прервали на середине — не рисуем ложные 100%
            bar.update(task, completed=100.0)

    if interrupted:
        env.status = "partial"
        env.warn("masscan прерван вручную")
        ui.warn(f"masscan прерван — иду на этап 2 с тем, что нашли ({found} портов)")
        return 0
    if stalled:
        env.warn(f"masscan снят принудительно: {stall_reason}")
        if done_at is None:
            # до 100% не дошли — часть диапазона осталась непроверенной
            env.status = "partial"
        ui.warn(f"masscan завис ({stall_reason}) — снял его, найдено портов: {found}")
        return 0
    if code == 0:
        ui.ok(f"masscan завершён: открытых портов {found} на {len(env.hosts)} хост(ах)")
    else:
        ui.err_msg(f"masscan вышел с кодом {code}")
    return code


# --------------------------------------------------------------------------
# этап 2: nmap
# --------------------------------------------------------------------------

def nmap_port_spec(ports: list[dict]) -> tuple[str, bool]:
    """Собрать '-p T:22,80,U:53' и сказать, нужен ли -sU."""
    tcp = sorted({p["port"] for p in ports if p["proto"] == "tcp"})
    udp = sorted({p["port"] for p in ports if p["proto"] == "udp"})
    chunks = []
    if tcp:
        chunks.append("T:" + ",".join(str(p) for p in tcp))
    if udp:
        chunks.append("U:" + ",".join(str(p) for p in udp))
    return ",".join(chunks), bool(udp)


def parse_nmap_xml(path: Path, env: Envelope) -> None:
    """Влить результаты nmap поверх находок masscan."""
    root = ET.parse(path).getroot()
    for host_el in root.findall("host"):
        addr_el = host_el.find("address[@addrtype='ipv4']")
        if addr_el is None:
            addr_el = host_el.find("address[@addrtype='ipv6']")
        if addr_el is None:
            continue
        ip = addr_el.get("addr")
        host = env.host(ip)

        status_el = host_el.find("status")
        if status_el is not None:
            host["state"] = status_el.get("state", host["state"])

        for hostname_el in host_el.findall("hostnames/hostname"):
            name = hostname_el.get("name")
            if name and name not in host["hostnames"]:
                host["hostnames"].append(name)

        for port_el in host_el.findall("ports/port"):
            state_el = port_el.find("state")
            service_el = port_el.find("service")
            fields: dict[str, object] = {}
            if service_el is not None:
                fields = {
                    "service": service_el.get("name", ""),
                    "product": service_el.get("product", ""),
                    "version": service_el.get("version", ""),
                    "extrainfo": service_el.get("extrainfo", ""),
                    "tunnel": service_el.get("tunnel", ""),
                    "cpe": [c.text for c in service_el.findall("cpe") if c.text],
                }
            scripts = {
                s.get("id"): s.get("output", "").strip()
                for s in port_el.findall("script")
                if s.get("id")
            }
            if scripts:
                fields["scripts"] = scripts

            env.add_port(ip, make_port(
                int(port_el.get("portid")),
                port_el.get("protocol", "tcp"),
                state_el.get("state", "unknown") if state_el is not None else "unknown",
                source="nmap",
                reason=state_el.get("reason", "") if state_el is not None else "",
                **fields,
            ))


def run_nmap(args, ui: UI, env: Envelope, workdir: Path, raw_dir: Path | None) -> None:
    hosts = [h for h in env.hosts if h["ports"]]
    if not hosts:
        ui.warn("открытых портов нет — nmap запускать не на чем")
        return

    total_ports = sum(len(h["ports"]) for h in hosts)
    ui.stage(f"этап 2 — nmap: опознание сервисов (портов: {total_ports}, хостов: {len(hosts)})")

    base = shlex.split(args.nmap_args)
    if args.scripts:
        base.append("-sC")
    if args.nmap_extra:
        base += shlex.split(args.nmap_extra)

    with ui.progress() as bar:
        task = bar.add("nmap", total=float(len(hosts)))
        for index, host in enumerate(hosts):
            ip = host["ip"]
            spec, needs_udp = nmap_port_spec(host["ports"])
            xml_path = (raw_dir or workdir) / f"nmap-{ip.replace(':', '_')}-{env.run_id}.xml"

            cmd = proc.sudo_prefix(args.sudo) + ["nmap", *base]
            if needs_udp and "-sU" not in cmd:
                cmd.append("-sU")
            cmd += ["-p", spec, "--stats-every", "2s", "-v", "-oX", str(xml_path), ip]

            bar.update(task, completed=float(index),
                       description=f"nmap {ip}", note=f"[dim]{len(host['ports'])} портов[/]")
            ui.raw(" ".join(shlex.quote(c) for c in cmd))

            def on_stdout(line: str, _ip: str = ip, _i: int = index) -> None:
                percent = RE_NMAP_PERCENT.search(line)
                if percent:
                    # доля внутри хоста добавляется к уже пройденным хостам
                    bar.update(task, completed=_i + float(percent.group(1)) / 100.0,
                               note=f"[dim]{_ip}: {percent.group(1)}%[/]")
                elif "Discovered open port" in line:
                    ui.raw(line)
                else:
                    ui.raw(line)

            code = proc.stream(cmd, on_stdout, ui.raw)
            bar.update(task, completed=float(index + 1), note="")

            if xml_path.exists():
                try:
                    parse_nmap_xml(xml_path, env)
                except ET.ParseError as exc:
                    env.warn(f"nmap {ip}: не разобрался XML ({exc})")
                    ui.err_msg(f"{ip}: битый XML от nmap")
            if code != 0:
                env.warn(f"nmap {ip}: код возврата {code}")

            named = ", ".join(sorted({
                p["service"] for p in env.host(ip)["ports"]
                if p.get("state") == "open" and p.get("service")
            }))
            bar.log(f"[bold cyan]  =[/] {ip} [dim]->[/] {named or 'открытых сервисов не опознано'}")

    ui.ok("nmap завершён")


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def collect_targets(args, ui: UI):
    """Цели из аргументов, иначе — со stdin.

    Читаем stdin только когда целей в аргументах нет: иначе скрипт, запущенный
    из обёртки с незакрытым stdin, встанет колом на read().
    """
    piped = None
    if not args.targets and not sys.stdin.isatty():
        piped = read_input(sys.stdin.read())

    targets = list(args.targets)
    if piped:
        targets += piped.targets
        if piped.hosts:
            ui.info(f"со stdin принято хостов: {len(piped.hosts)}")
    return list(dict.fromkeys(targets)), piped


def seed_from_input(piped, env: Envelope) -> int:
    """Перенести уже известные порты из входного конверта (режим --skip-discovery)."""
    count = 0
    for host in piped.hosts if piped else []:
        env.host(host["ip"])["state"] = host.get("state", "unknown")
        for name in host.get("hostnames", []):
            if name not in env.host(host["ip"])["hostnames"]:
                env.host(host["ip"])["hostnames"].append(name)
        for port in host.get("ports", []):
            if port.get("state", "open") == "open":
                env.add_port(host["ip"], make_port(
                    port["port"], port.get("proto", "tcp"), "open", source="input"))
                count += 1
    return count


def main() -> int:
    args = build_parser().parse_args()
    ui = UI(quiet=args.quiet, verbose=args.verbose, color=not args.no_color)

    env = Envelope(TOOL, VERSION, params={
        "ports": args.ports,
        "rate": args.rate,
        "nmap_args": args.nmap_args + (" -sC" if args.scripts else ""),
        "skip_discovery": args.skip_discovery,
        "skip_nmap": args.skip_nmap,
    })

    ui.banner("CYBERDECK :: portscan", f"run {env.run_id}")

    targets, piped = collect_targets(args, ui)
    env.targets = targets

    if not targets:
        ui.err_msg("не заданы цели: укажи IP/CIDR аргументом или подай их на stdin")
        return 2

    ui.info(f"цели: {', '.join(targets)}")

    # предполётные проверки
    needed = []
    if not args.skip_discovery:
        needed.append("masscan")
    if not args.skip_nmap:
        needed.append("nmap")
    missing = [b for b in needed if shutil.which(b) is None]
    if missing:
        ui.err_msg(f"не найдены в PATH: {', '.join(missing)}")
        ui.dim("Debian/Ubuntu/WSL:  sudo apt install masscan nmap")
        return 127

    if needed and not proc.is_root() and not args.sudo and os.name != "nt":
        ui.warn("не root: masscan и nmap -sV/-sU обычно требуют прав, добавь --sudo или запусти под sudo")
    if args.sudo and not proc.sudo_ready():
        ui.err_msg("sudo просит пароль, а stdin занят пайпом — выполни сначала 'sudo -v'")
        return 1

    raw_dir = None
    if args.raw_dir:
        raw_dir = Path(args.raw_dir)
        raw_dir.mkdir(parents=True, exist_ok=True)

    workdir = Path(tempfile.mkdtemp(prefix="cyberdeck-portscan-"))
    try:
        if args.skip_discovery:
            seeded = seed_from_input(piped, env)
            if seeded:
                ui.info(f"masscan пропущен, портов со входа: {seeded}")
            else:
                # портов на входе нет — берём то, что задано в --ports
                explicit = expand_ports(args.ports)
                if len(explicit) > 5000:
                    ui.err_msg(
                        f"--skip-discovery без входных портов: --ports={args.ports} "
                        f"разворачивается в {len(explicit)} портов, задай список поуже"
                    )
                    return 2
                for target in targets:
                    for port in explicit:
                        env.add_port(target, make_port(port, "tcp", "open", source="args"))
                ui.info(f"masscan пропущен, порты из --ports: {args.ports}")
        else:
            raw_path = (raw_dir / f"masscan-{env.run_id}.txt") if raw_dir else None
            if run_masscan(args, targets, ui, env, raw_path) != 0:
                env.status = "partial"

        if not args.skip_nmap:
            run_nmap(args, ui, env, workdir, raw_dir)

    except KeyboardInterrupt:
        env.status = "partial"
        env.warn("прервано пользователем")
        ui.err_msg("прервано — отдаю то, что успели собрать")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    payload = env.to_dict()

    if args.out:
        Path(args.out).write_text(env.to_json(), encoding="utf-8")
        ui.ok(f"JSON сохранён: {args.out}")

    if args.json:
        print(env.to_json(indent=None if args.quiet else 2))
    else:
        ui.report(payload)

    return 0 if env.status == "ok" else 1


def expand_ports(spec: str) -> list[int]:
    """'22,80,8000-8010' -> список портов (для --skip-discovery без входных данных)."""
    ports: list[int] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        chunk = chunk.split(":")[-1]  # отбрасываем префикс T:/U:
        if "-" in chunk:
            start, end = chunk.split("-", 1)
            ports.extend(range(int(start), int(end) + 1))
        else:
            ports.append(int(chunk))
    return ports


if __name__ == "__main__":
    sys.exit(main())