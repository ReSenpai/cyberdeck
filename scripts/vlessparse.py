#!/usr/bin/env python3
"""vlessparse — разбор ссылок VLESS (и соседних схем) в конверт cyberdeck.v1.

Сеть не трогает: только парсинг. Каждый конфиг — это эндпоинт ``host:port``,
поэтому сервер уходит в ``hosts`` конверта, а весь разбор (uuid, sni, security,
type, flow, pbk/sid, remark) складывается в ``host["configs"]`` без потери
дублей на одном адресе. Дальше цепочка сама решает, что с адресами делать:

    cat sub.txt | ./vlessparse.py --json | ./ipscan.py --geo --json
    cat sub.txt | ./vlessparse.py --targets | sudo ./portscan.py --json

Разбор через ``urllib.urlsplit`` (а не regex по ``@host:``): берётся настоящий
порт, IPv6 в скобках, домены и все query-параметры. Кроме ``vless://`` понимает
``trojan://``, ``vmess://`` (base64-JSON) и ``ss://`` (SIP002) — по возможности.

Логи и прогресс — в stderr, JSON (--json) или человекочитаемый отчёт — в stdout.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import sys
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cyberdeck import Envelope, make_port  # noqa: E402
from cyberdeck.ui import UI, force_utf8  # noqa: E402

force_utf8()

TOOL = "vlessparse"
VERSION = "0.1.0"

# Схемы с формой userinfo@host:port?query#remark — разбираются одинаково.
_USERINFO_SCHEMES = {"vless", "trojan"}
SUPPORTED = _USERINFO_SCHEMES | {"vmess", "ss"}

# Известные ключи прокси-конфига — их вытаскиваем в предсказуемом виде, остальные
# query-параметры тоже сохраняем как есть (universal: ничего не теряем).
_KNOWN_KEYS = (
    "security", "encryption", "type", "flow", "sni", "fp", "pbk", "sid", "spx",
    "host", "path", "serviceName", "mode", "alpn", "headerType", "extra",
)


def _b64decode(data: str) -> bytes:
    """Терпимый base64/base64url: чинит паддинг, пробует оба алфавита."""
    data = data.strip().replace("\n", "")
    pad = "=" * (-len(data) % 4)
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            return decoder(data + pad)
        except (binascii.Error, ValueError):
            continue
    raise ValueError("не base64")


def _clean(cfg: dict) -> dict:
    """Выбросить пустые поля — конверт должен читаться."""
    return {k: v for k, v in cfg.items() if v not in (None, "", [], {})}


def parse_userinfo(scheme: str, line: str) -> dict:
    """vless:// и trojan:// — общая форма userinfo@host:port?query#remark."""
    parts = urlsplit(line)
    if not parts.hostname:
        raise ValueError("нет адреса хоста")
    if parts.port is None:  # .port сам бросит ValueError на мусоре
        raise ValueError("нет порта")

    query = dict(parse_qsl(parts.query, keep_blank_values=False))
    cfg = {
        "scheme": scheme,
        "address": parts.hostname,
        "port": parts.port,
        "id": unquote(parts.username or ""),
        "remark": unquote(parts.fragment),
    }
    for key in _KNOWN_KEYS:
        if key in query:
            cfg[key] = query.pop(key)
    cfg.update(query)  # всё нераспознанное — тоже в конфиг, не теряем
    cfg["raw"] = line
    return _clean(cfg)


def parse_vmess(line: str) -> dict:
    """vmess:// — base64 от JSON {add, port, id, net, tls, sni, ps, ...}."""
    payload = json.loads(_b64decode(line[len("vmess://"):]))
    if not isinstance(payload, dict):
        raise ValueError("vmess: не JSON-объект")
    port = payload.get("port")
    if port in (None, ""):
        raise ValueError("нет порта")
    cfg = {
        "scheme": "vmess",
        "address": str(payload.get("add", "")).strip(),
        "port": int(port),
        "id": str(payload.get("id", "")),
        "type": payload.get("net", ""),
        "security": payload.get("tls", ""),
        "sni": payload.get("sni") or payload.get("host", ""),
        "path": payload.get("path", ""),
        "host": payload.get("host", ""),
        "alpn": payload.get("alpn", ""),
        "aid": payload.get("aid", ""),
        "remark": payload.get("ps", ""),
        "raw": line,
    }
    if not cfg["address"]:
        raise ValueError("нет адреса хоста")
    return _clean(cfg)


def parse_ss(line: str) -> dict:
    """ss:// — SIP002 (base64(method:pass)@host:port) и цельно-base64 форма."""
    body, _, fragment = line[len("ss://"):].partition("#")
    remark = unquote(fragment)

    if "@" not in body:  # ss://base64(method:pass@host:port)
        body = _b64decode(body.split("?", 1)[0]).decode("utf-8", "replace")

    userinfo, _, hostport = body.partition("@")
    if not hostport:
        raise ValueError("ss: не разобрал host:port")

    if ":" not in userinfo:  # userinfo мог быть base64(method:pass)
        try:
            userinfo = _b64decode(userinfo).decode("utf-8", "replace")
        except ValueError:
            pass
    method, _, password = userinfo.partition(":")

    hostport = hostport.split("?", 1)[0].split("/", 1)[0]
    parts = urlsplit(f"//{hostport}")
    if not parts.hostname or parts.port is None:
        raise ValueError("ss: нет host:port")

    return _clean({
        "scheme": "ss",
        "address": parts.hostname,
        "port": parts.port,
        "method": method,
        "id": password,
        "remark": remark,
        "raw": line,
    })


def parse_line(line: str) -> dict:
    scheme = line.split("://", 1)[0].lower()
    if scheme in _USERINFO_SCHEMES:
        return parse_userinfo(scheme, line)
    if scheme == "vmess":
        return parse_vmess(line)
    if scheme == "ss":
        return parse_ss(line)
    raise ValueError(f"схема не поддержана: {scheme}")


def iter_links(text: str):
    """Строки-ссылки из текста. Пустое, комментарии (# / //) — мимо."""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//") or line.startswith("#"):
            continue
        yield line


# --------------------------------------------------------------------------
# сбор ввода
# --------------------------------------------------------------------------

def gather_text(args, ui: UI) -> str:
    """Ввод из файлов-аргументов, прямых ссылок в аргументах или из stdin."""
    chunks: list[str] = []
    literal = 0
    for token in args.inputs:
        path = Path(token)
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
        elif "://" in token:
            chunks.append(token)
            literal += 1
        else:
            ui.warn(f"пропущено (не файл и не ссылка): {token}")
    if literal:
        ui.info(f"ссылок из аргументов: {literal}")

    if not chunks and not sys.stdin.isatty():
        chunks.append(sys.stdin.read())

    return "\n".join(chunks)


# --------------------------------------------------------------------------
# отчёт
# --------------------------------------------------------------------------

def human_report(payload: dict) -> None:
    """Человекочитаемая сводка в stdout (когда без --json)."""
    stats = payload["stats"]
    hosts = payload["hosts"]

    print("\n== VLESS PARSE ==")
    print(f"  строк на входе .... {stats.get('lines_in', 0)}")
    print(f"  конфигов .......... {stats.get('configs', 0)}")
    print(f"  не разобрано ...... {stats.get('failed', 0)}")
    print(f"  уникальных хостов . {len(hosts)}")
    print(f"  эндпоинтов host:port {stats.get('endpoints', 0)}")

    by_scheme = stats.get("by_scheme", {})
    if by_scheme:
        print("\n  по схемам:")
        for name, count in sorted(by_scheme.items(), key=lambda kv: -kv[1]):
            print(f"    {name:<8} {count}")

    by_security = stats.get("by_security", {})
    if by_security:
        print("\n  по security:")
        for name, count in sorted(by_security.items(), key=lambda kv: -kv[1]):
            print(f"    {name or '(нет)':<12} {count}")

    print("\n  хосты:")
    for host in hosts:
        ports = ",".join(str(p["port"]) for p in host["ports"])
        remarks = [c.get("remark", "") for c in host.get("configs", []) if c.get("remark")]
        tag = f"  {remarks[0]}" if remarks else ""
        extra = f" (+{len(remarks) - 1})" if len(remarks) > 1 else ""
        print(f"    {host['ip']:<22} :{ports:<16} [{len(host.get('configs', []))} cfg]{tag}{extra}")
    print()


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vlessparse",
        description="Разбор VLESS/trojan/vmess/ss в конверт cyberdeck.v1. Цепочки через --json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "примеры:\n"
            "  cat sub.txt | ./vlessparse.py\n"
            "  ./vlessparse.py sub.txt --json | ./ipscan.py --geo --json\n"
            "  cat sub.txt | ./vlessparse.py --targets | sudo ./portscan.py --json\n"
        ),
    )
    parser.add_argument("inputs", nargs="*", help="файлы с ссылками или сами ссылки (иначе stdin)")

    flt = parser.add_argument_group("фильтры")
    flt.add_argument("--scheme", action="append", metavar="NAME",
                     help="оставить только эти схемы (можно повторять): vless/trojan/vmess/ss")
    flt.add_argument("--unique", action="store_true",
                     help="схлопнуть эндпоинты host:port до уникальных (по одному конфигу)")

    out = parser.add_argument_group("вывод")
    out.add_argument("--json", action="store_true", help="конверт cyberdeck.v1 в stdout")
    out.add_argument("--targets", action="store_true",
                     help="печатать только уникальные адреса host:port построчно (для пайпа)")
    out.add_argument("-o", "--out", help="сохранить JSON в файл")
    out.add_argument("-q", "--quiet", action="store_true", help="без логов")
    out.add_argument("-v", "--verbose", action="store_true", help="показывать причины отбраковки")
    out.add_argument("--no-color", action="store_true", help="без цвета")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    ui = UI(quiet=args.quiet, verbose=args.verbose, color=not args.no_color)

    scheme_filter = {s.lower() for s in args.scheme} if args.scheme else None
    env = Envelope(TOOL, VERSION, params={
        "schemes": sorted(scheme_filter) if scheme_filter else "all",
        "unique": args.unique,
    })
    ui.banner("CYBERDECK :: vlessparse", f"run {env.run_id}")

    text = gather_text(args, ui)
    if not text.strip():
        ui.err_msg("нет ввода: подай ссылки на stdin, файлом или аргументом")
        return 2

    lines_in = 0
    configs = 0
    failed = 0
    by_scheme: dict[str, int] = {}
    by_security: dict[str, int] = {}
    seen_endpoints: set[tuple[str, int]] = set()

    for line in iter_links(text):
        lines_in += 1
        try:
            cfg = parse_line(line)
        except ValueError as exc:
            failed += 1
            ui.raw(f"skip: {exc} :: {line[:60]}")
            continue
        except Exception as exc:  # noqa: BLE001 — не роняем разбор из-за одной битой строки
            failed += 1
            ui.raw(f"skip: {type(exc).__name__}: {exc} :: {line[:60]}")
            continue

        if scheme_filter and cfg["scheme"] not in scheme_filter:
            continue

        addr, port = cfg["address"], cfg["port"]
        endpoint = (addr, port)
        if args.unique and endpoint in seen_endpoints:
            continue
        seen_endpoints.add(endpoint)

        env.host(addr)["state"] = "unknown"
        env.add_port(addr, make_port(port, "tcp", "unknown", source=cfg["scheme"], service=cfg["scheme"]))
        env.host(addr).setdefault("configs", []).append(cfg)

        configs += 1
        by_scheme[cfg["scheme"]] = by_scheme.get(cfg["scheme"], 0) + 1
        sec = cfg.get("security", "")
        by_security[sec] = by_security.get(sec, 0) + 1

    env.targets = [h["ip"] for h in env.hosts]
    if failed:
        env.warn(f"не разобрано строк: {failed}")
        if configs == 0:
            env.status = "error"

    env.add_stat("lines_in", lines_in)
    env.add_stat("configs", configs)
    env.add_stat("failed", failed)
    env.add_stat("endpoints", len(seen_endpoints))
    env.add_stat("by_scheme", by_scheme)
    env.add_stat("by_security", by_security)

    payload = env.to_dict()
    ui.ok(f"разобрано конфигов: {configs}, хостов: {len(payload['hosts'])}, отбраковано: {failed}")

    if args.out:
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        ui.ok(f"JSON сохранён: {args.out}")

    if args.targets:
        for addr, port in sorted(seen_endpoints):
            print(f"{addr}:{port}")
    elif args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=None if args.quiet else 2))
    else:
        human_report(payload)

    return 0 if env.status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
