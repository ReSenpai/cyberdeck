#!/usr/bin/env python3
"""adduser — завести пользователя на удалённом сервере по SSH (один вызов).

Подключается системным ``ssh`` (никаких зависимостей: работают ~/.ssh/config,
ключи, ssh-agent, known_hosts) и прогоняет на сервере сгенерированный
идемпотентный bash-скрипт. Скрипт уходит по зашифрованному stdin в ``bash -s`` —
не через argv, поэтому секреты не светятся в ``ps`` на сервере.

Умеет:
  * обычный пользователь или админ (--admin: в группу sudo/wheel);
  * sudo без пароля (--nopasswd-sudo, проверяется через visudo);
  * пароль: --random-password (сгенерит и покажет), --ask-password (скрытый
    ввод), --password (в аргументе); без флага — вход только по ключу;
  * SSH-ключ: --ssh-key '<строка>' или --ssh-key-file pub.key.

Цели берутся из аргументов (``root@host``) или со stdin (конверт cyberdeck.v1 —
можно пайпить живые хосты из ipscan). Результат — тот же конверт: каждый сервер
это host с полем ``user`` (что сделали) и журналом ``actions``.

    adduser.py root@1.2.3.4 -u deploy --ssh-key-file id.pub
    adduser.py 10.0.0.5 -u ops --admin --random-password
    ipscan.py hosts.txt --alive-only --json | adduser.py -u ci --nopasswd-sudo --ssh-key-file ci.pub --json

Логи/прогресс — в stderr, JSON (--json) или отчёт — в stdout. Перед боем удобно
прогнать с --dry-run: покажет удалённый скрипт (пароль скрыт), никуда не подключаясь.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import re
import secrets
import shlex
import string
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cyberdeck import Envelope, read_input  # noqa: E402
from cyberdeck.ui import UI, force_utf8  # noqa: E402

force_utf8()

TOOL = "adduser"
VERSION = "0.1.0"

# useradd допускает такие имена (Debian NAME_REGEX + типичный дефолт).
RE_USERNAME = re.compile(r"^[a-z_][a-z0-9_-]{0,31}\$?$")
PW_SENTINEL = "@@CYBERDECK_PW_B64@@"
KEY_SENTINEL = "@@CYBERDECK_KEY_B64@@"


# --------------------------------------------------------------------------
# вспомогательное
# --------------------------------------------------------------------------

def b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def gen_password(length: int) -> str:
    """Крепкий пароль без неоднозначных символов и без шелл-спецсимволов."""
    alphabet = (
        "ABCDEFGHJKLMNPQRSTUVWXYZ"
        "abcdefghijkmnopqrstuvwxyz"
        "23456789"
        "-_.=+@%"
    )
    return "".join(secrets.choice(alphabet) for _ in range(max(12, length)))


def split_addr_port(token: str) -> tuple[str, int | None]:
    """'host' / 'host:port' / '[ipv6]:port' -> (host, port|None)."""
    if token.startswith("["):
        host, sep, rest = token[1:].partition("]")
        if sep and rest.startswith(":") and rest[1:].isdigit():
            return host, int(rest[1:])
        return host, None
    if token.count(":") == 1:
        host, _, port = token.partition(":")
        if port.isdigit():
            return host, int(port)
    return token, None


def parse_target(token: str, default_user: str, default_port: int) -> tuple[str, str, int]:
    """'user@host:port' -> (ssh_user, host, port), подставляя дефолты."""
    user = default_user
    if "@" in token:
        user, token = token.split("@", 1)
    host, port = split_addr_port(token)
    return user, host, port or default_port


def read_public_key(args, ui: UI) -> str | None:
    """Публичный ключ из --ssh-key или --ssh-key-file (может быть несколько строк)."""
    if args.ssh_key:
        text = args.ssh_key.strip()
    elif args.ssh_key_file:
        path = Path(args.ssh_key_file)
        if not path.is_file():
            ui.err_msg(f"файл ключа не найден: {path}")
            return None
        text = path.read_text(encoding="utf-8").strip()
    else:
        return None

    valid = [l for l in text.splitlines() if l.strip()]
    for line in valid:
        if not re.match(r"^(ssh-(rsa|ed25519|dss)|ecdsa-|sk-)", line.strip()):
            ui.warn(f"строка не похожа на публичный ключ: {line[:40]}…")
    return "\n".join(valid) if valid else None


# --------------------------------------------------------------------------
# генерация удалённого скрипта
# --------------------------------------------------------------------------

def build_remote_script(opts: dict) -> str:
    """Собрать идемпотентный bash с плейсхолдерами под секреты (см. PW/KEY_SENTINEL)."""
    q = shlex.quote
    L: list[str] = []
    add = L.append

    add("set -eu")
    add("u=" + q(opts["user"]))
    add("shell=" + q(opts["shell"]))
    if opts.get("uid"):
        add("uid=" + q(str(opts["uid"])))
    if opts.get("gecos"):
        add("gecos=" + q(opts["gecos"]))
    if opts.get("home"):
        add("home_dir=" + q(opts["home"]))
    add("")
    add('if [ "$(id -u)" -ne 0 ]; then')
    add('  echo "adduser: на сервере нужен root (заходи под root или добавь --become)" >&2; exit 11')
    add("fi")
    add("")

    # 1. пользователь
    add('if id "$u" >/dev/null 2>&1; then')
    add('  echo "exists: $u"')
    add("else")
    useradd = '  useradd -m -s "$shell"'
    if opts.get("uid"):
        useradd += ' -u "$uid"'
    if opts.get("gecos"):
        useradd += ' -c "$gecos"'
    if opts.get("home"):
        useradd += ' -d "$home_dir"'
    useradd += ' "$u"'
    add(useradd)
    add('  echo "created: $u"')
    add("fi")
    add("")

    # 2. доп. группы
    if opts.get("groups"):
        grp = ",".join(opts["groups"])
        add(f'usermod -aG {q(grp)} "$u" && echo "groups: {grp}"')

    # 3. админ (sudo/wheel)
    if opts.get("admin"):
        add('adm=""')
        add('if getent group sudo >/dev/null 2>&1; then adm=sudo; '
            'elif getent group wheel >/dev/null 2>&1; then adm=wheel; fi')
        add('if [ -n "$adm" ]; then usermod -aG "$adm" "$u"; echo "admin: +$adm"; '
            'else echo "admin: нет группы sudo/wheel" >&2; fi')

    # 4. sudo без пароля
    if opts.get("nopasswd"):
        add('sf="/etc/sudoers.d/90-cyberdeck-$u"')
        add('printf "%s ALL=(ALL) NOPASSWD:ALL\\n" "$u" > "$sf"')
        add('chmod 440 "$sf"')
        add('if visudo -cf "$sf" >/dev/null 2>&1; then echo "sudoers: NOPASSWD"; '
            'else rm -f "$sf"; echo "sudoers: невалидно, откатил" >&2; exit 12; fi')

    # 5. пароль
    if opts.get("password_b64"):
        add(f"printf '%s' '{PW_SENTINEL}' | base64 -d | chpasswd && echo 'password: set'")
    elif opts.get("lock"):
        add('passwd -l "$u" >/dev/null 2>&1 || usermod -L "$u" || true')
        add('echo "password: locked"')

    # 6. SSH-ключ
    if opts.get("key_b64"):
        add('kh="$(getent passwd "$u" | cut -d: -f6)"')
        add('[ -n "$kh" ] || { echo "sshkey: не нашёл home пользователя" >&2; exit 13; }')
        add('ug="$(id -gn "$u")"')
        add('install -d -m 700 -o "$u" -g "$ug" "$kh/.ssh"')
        add('ak="$kh/.ssh/authorized_keys"')
        add('touch "$ak"')
        add(f"keydata=\"$(printf '%s' '{KEY_SENTINEL}' | base64 -d)\"")
        add('added=0')
        add('while IFS= read -r kl; do')
        add('  [ -z "$kl" ] && continue')
        add('  if ! grep -qxF "$kl" "$ak"; then printf "%s\\n" "$kl" >> "$ak"; added=$((added+1)); fi')
        add("done <<CDK_EOF")
        add("$keydata")
        add("CDK_EOF")
        add('chmod 600 "$ak"')
        add('chown "$u":"$ug" "$ak" "$kh/.ssh"')
        add('echo "sshkey: установлено ключей +$added"')

    add("")
    add('echo "DONE: $u"')
    return "\n".join(L) + "\n"


def fill_secrets(script: str, opts: dict) -> str:
    out = script
    if opts.get("password_b64"):
        out = out.replace(PW_SENTINEL, opts["password_b64"])
    if opts.get("key_b64"):
        out = out.replace(KEY_SENTINEL, opts["key_b64"])
    return out


def masked_script(script: str, opts: dict) -> str:
    out = script.replace(PW_SENTINEL, "<PASSWORD-REDACTED>")
    if opts.get("key_b64"):  # публичный ключ прятать незачем
        out = out.replace(KEY_SENTINEL, opts["key_b64"])
    return out


# --------------------------------------------------------------------------
# запуск по SSH
# --------------------------------------------------------------------------

def ssh_command(args, ssh_user: str, host: str, port: int) -> list[str]:
    cmd = ["ssh", "-o", f"ConnectTimeout={args.timeout}"]
    if args.batch:
        cmd += ["-o", "BatchMode=yes"]
    if port != 22:
        cmd += ["-p", str(port)]
    if args.identity:
        cmd += ["-i", args.identity]
    for opt in args.ssh_option or []:
        cmd += ["-o", opt]
    cmd.append(f"{ssh_user}@{host}")
    cmd.append("sudo -n bash -s" if args.become else "bash -s")
    return cmd


def run_target(args, token: str, script: str, ui: UI, env: Envelope) -> None:
    ssh_user, host, port = parse_target(token, args.ssh_user, args.ssh_port)
    dest = f"{ssh_user}@{host}" + (f":{port}" if port != 22 else "")
    rec = env.host(host)
    rec["destination"] = dest
    rec["actions"] = []

    ui.stage(f"{dest} — завожу {args.user}")
    cmd = ssh_command(args, ssh_user, host, port)
    ui.dim(" ".join(shlex.quote(c) for c in cmd))

    try:
        proc = subprocess.run(
            cmd, input=script.encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=args.timeout + 60,
        )
    except FileNotFoundError:
        ui.err_msg("не найден бинарь ssh в PATH")
        env.fail("ssh не установлен")
        rec["state"] = "error"
        return
    except subprocess.TimeoutExpired:
        ui.err_msg(f"{dest}: таймаут соединения/выполнения")
        env.warn(f"{host}: таймаут")
        rec["state"] = "error"
        return

    out = proc.stdout.decode("utf-8", "replace")
    errtext = proc.stderr.decode("utf-8", "replace")
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        rec["actions"].append(line)
        if not line.startswith("DONE"):
            ui.ok(f"{host}: {line}")

    if proc.returncode == 0:
        rec["state"] = "ok"
        created = any(a.startswith("created:") for a in rec["actions"])
        ui.ok(f"{dest}: готово ({'создан' if created else 'уже был'})")
    else:
        rec["state"] = "error"
        env.status = "partial" if env.status == "ok" else env.status
        detail = errtext.strip().splitlines()[-1] if errtext.strip() else f"код {proc.returncode}"
        env.warn(f"{host}: {detail}")
        ui.err_msg(f"{dest}: не удалось — {detail}")
    for line in errtext.splitlines():
        if line.strip():
            ui.raw(line.strip())


# --------------------------------------------------------------------------
# отчёт
# --------------------------------------------------------------------------

def human_report(payload: dict, generated: dict) -> None:
    stats = payload["stats"]
    print("\n== MKUSER ==")
    print(f"  серверов ...... {stats.get('targets', 0)}")
    print(f"  успешно ....... {stats.get('ok', 0)}")
    print(f"  с ошибкой ..... {stats.get('failed', 0)}")
    print(f"  пользователь .. {stats.get('user', '-')}")
    print("\n  серверы:")
    for host in payload["hosts"]:
        mark = "ok" if host.get("state") == "ok" else "ERR"
        print(f"    [{mark:>3}] {host.get('destination', host['ip'])}")
        for action in host.get("actions", []):
            print(f"          {action}")
    if generated:
        print("\n  сгенерированные пароли (сохрани, больше не покажутся):")
        for user, pw in generated.items():
            print(f"    {user}: {pw}")
    print()


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adduser",
        description="Завести пользователя на сервере(ах) по SSH. Цепочки через --json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "примеры:\n"
            "  ./adduser.py root@1.2.3.4 -u deploy --ssh-key-file id.pub\n"
            "  ./adduser.py 10.0.0.5 -u ops --admin --random-password\n"
            "  ./ipscan.py hosts.txt --alive-only --json | ./adduser.py -u ci --nopasswd-sudo --ssh-key-file ci.pub\n"
            "  ./adduser.py root@host -u test --dry-run   # показать скрипт, не подключаясь\n"
        ),
    )
    parser.add_argument("targets", nargs="*", help="user@host[:port] (иначе цели со stdin)")

    conn = parser.add_argument_group("подключение")
    conn.add_argument("--ssh-user", default="root", help="логин для SSH (по умолчанию root)")
    conn.add_argument("-p", "--ssh-port", type=int, default=22, help="порт SSH (22)")
    conn.add_argument("-i", "--identity", help="приватный ключ для SSH-аутентификации")
    conn.add_argument("--ssh-option", action="append", metavar="OPT", help="доп. -o для ssh (повторяемо)")
    conn.add_argument("--become", action="store_true", help="выполнять на сервере через sudo -n (если логин не root)")
    conn.add_argument("--batch", action="store_true", help="BatchMode: не спрашивать пароль SSH (только ключи)")
    conn.add_argument("--timeout", type=int, default=15, help="таймаут соединения, сек (15)")

    usr = parser.add_argument_group("пользователь")
    usr.add_argument("-u", "--user", help="имя создаваемого пользователя (обязательно)")
    usr.add_argument("--uid", type=int, help="явный UID")
    usr.add_argument("--shell", default="/bin/bash", help="login shell (/bin/bash)")
    usr.add_argument("--gecos", help="комментарий/полное имя")
    usr.add_argument("-G", "--groups", help="доп. группы через запятую")
    usr.add_argument("--home", help="путь домашнего каталога")

    priv = parser.add_argument_group("права")
    priv.add_argument("--admin", action="store_true", help="в группу sudo/wheel (root-права)")
    priv.add_argument("--nopasswd-sudo", action="store_true", help="sudo без пароля (подразумевает --admin)")

    pw = parser.add_argument_group("пароль")
    pw.add_argument("--password", metavar="PLAIN", help="задать этот пароль (виден в ps/history локально)")
    pw.add_argument("--ask-password", action="store_true", help="спросить пароль скрытым вводом")
    pw.add_argument("--random-password", action="store_true", help="сгенерировать пароль и показать")
    pw.add_argument("--length", type=int, default=20, help="длина случайного пароля (20)")
    pw.add_argument("--lock", action="store_true", help="явно заблокировать пароль (вход только по ключу)")

    key = parser.add_argument_group("SSH-ключ")
    key.add_argument("--ssh-key", metavar="STR", help="публичный ключ строкой")
    key.add_argument("--ssh-key-file", metavar="FILE", help="файл с публичным ключом (можно несколько строк)")

    out = parser.add_argument_group("вывод")
    out.add_argument("--dry-run", action="store_true", help="показать удалённый скрипт, не подключаясь")
    out.add_argument("--json", action="store_true", help="конверт cyberdeck.v1 в stdout")
    out.add_argument("--show-secrets", action="store_true", help="включить сгенерированные пароли в JSON")
    out.add_argument("-o", "--out", help="сохранить JSON в файл")
    out.add_argument("-q", "--quiet", action="store_true", help="без логов")
    out.add_argument("-v", "--verbose", action="store_true", help="показывать stderr сервера")
    out.add_argument("--no-color", action="store_true", help="без цвета")
    return parser


def resolve_password(args, ui: UI) -> tuple[str | None, bool]:
    """(plaintext|None, is_random). Разруливает конфликт режимов."""
    chosen = [n for n, v in (
        ("--password", args.password is not None),
        ("--ask-password", args.ask_password),
        ("--random-password", args.random_password),
    ) if v]
    if len(chosen) > 1:
        ui.err_msg(f"выбери один способ пароля, а не {', '.join(chosen)}")
        raise SystemExit(2)
    if args.password is not None:
        return args.password, False
    if args.ask_password:
        return getpass.getpass("Пароль нового пользователя: "), False
    if args.random_password:
        return gen_password(args.length), True
    return None, False


def main() -> int:
    args = build_parser().parse_args()
    ui = UI(quiet=args.quiet, verbose=args.verbose, color=not args.no_color)

    if not args.user:
        ui.err_msg("не задано имя пользователя: добавь -u/--user")
        return 2
    if not RE_USERNAME.match(args.user):
        ui.err_msg(f"недопустимое имя пользователя: {args.user!r} (ожидается [a-z_][a-z0-9_-]*)")
        return 2

    env = Envelope(TOOL, VERSION, params={
        "user": args.user,
        "admin": args.admin or args.nopasswd_sudo,
        "nopasswd_sudo": args.nopasswd_sudo,
        "ssh_user": args.ssh_user,
        "become": args.become,
    })
    ui.banner("CYBERDECK :: adduser", f"run {env.run_id}")

    plaintext, is_random = resolve_password(args, ui)
    key_text = read_public_key(args, ui)
    if args.ssh_key_file and key_text is None and not args.ssh_key:
        return 2  # файл ключа указан, но не прочитан
    if plaintext is None and key_text is None and not args.lock:
        ui.warn("ни пароля, ни ключа — пользователь не сможет войти (только консоль сервера)")

    opts = {
        "user": args.user,
        "shell": args.shell,
        "uid": args.uid,
        "gecos": args.gecos,
        "home": args.home,
        "groups": [g.strip() for g in args.groups.split(",")] if args.groups else [],
        "admin": args.admin or args.nopasswd_sudo,
        "nopasswd": args.nopasswd_sudo,
        "password_b64": b64(f"{args.user}:{plaintext}") if plaintext is not None else None,
        "lock": args.lock and plaintext is None,
        "key_b64": b64(key_text) if key_text else None,
    }

    template = build_remote_script(opts)

    if args.dry_run:
        ui.info("dry-run: удалённый скрипт (пароль скрыт), подключения нет")
        print(masked_script(template, opts))
        if is_random:
            ui.ok(f"сгенерированный пароль был бы: {plaintext}")
        return 0

    # цели: аргументы или stdin (конверт/список)
    targets = list(args.targets)
    if not targets and not sys.stdin.isatty():
        piped = read_input(sys.stdin.read())
        targets += [h["ip"] for h in piped.hosts] or piped.targets
    targets = list(dict.fromkeys(targets))
    if not targets:
        ui.err_msg("нет целей: укажи user@host аргументом или подай хосты на stdin")
        return 2
    env.targets = targets

    script = fill_secrets(template, opts)
    generated: dict[str, str] = {}
    if is_random:
        generated[args.user] = plaintext  # покажем в отчёте/логе
        ui.ok(f"пароль для {args.user}: {plaintext}  (сохрани — больше не покажу)")

    for token in targets:
        run_target(args, token, script, ui, env)

    ok = sum(1 for h in env.hosts if h.get("state") == "ok")
    failed = len(env.hosts) - ok
    if failed and ok:
        env.status = "partial"
    elif failed and not ok:
        env.status = "error"
    env.add_stat("user", args.user)
    env.add_stat("ok", ok)
    env.add_stat("failed", failed)

    payload = env.to_dict()
    if args.show_secrets and generated:
        for host in payload["hosts"]:
            if host.get("state") == "ok":
                host.setdefault("user", {})["generated_password"] = generated.get(args.user)

    if args.out:
        import json
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        ui.ok(f"JSON сохранён: {args.out}")

    if args.json:
        import json
        print(json.dumps(payload, ensure_ascii=False, indent=None if args.quiet else 2))
    else:
        human_report(payload, generated)

    return 0 if env.status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
