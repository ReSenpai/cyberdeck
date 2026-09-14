#!/usr/bin/env python3
"""build.py — самодостаточные версии скриптов в dist/.

Вклеивает пакет ``cyberdeck`` прямо в каждый скрипт, чтобы получившийся один
файл запускался где угодно, в том числе по пайпу:

    curl -sSL https://raw.../dist/ipscan.py | python3 - 1.1.1.1 --geo

Исходники не трогаем — правим ``scripts/`` и ``cyberdeck/``, потом гоняем build.

Как работает: модули cyberdeck кладём в base64, а бутстрап на старте разворачивает
их обратно в ``sys.modules`` (envelope/ui/proc + пакет), так что штатные
``from cyberdeck import ...`` в теле скрипта работают без изменений. Бутстрап
вставляется сразу ПОСЛЕ ``from __future__ import annotations`` (future-import
обязан быть первым стейтментом), а ``sys.path``-хак с ``__file__`` вырезается —
под ``python3 -`` файла нет и ``__file__`` не определён.
"""

from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):  # Windows-консоль в cp1252 не должна ронять принты
    _rc = getattr(_s, "reconfigure", None)
    if _rc:
        try:
            _rc(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

ROOT = Path(__file__).resolve().parent
LIB = ROOT / "cyberdeck"
SCRIPTS = ROOT / "scripts"
DIST = ROOT / "dist"

TARGETS = ("portscan.py", "vlessparse.py", "ipscan.py", "adduser.py")


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def bootstrap(need_proc: bool) -> str:
    envelope = _b64((LIB / "envelope.py").read_text(encoding="utf-8"))
    ui = _b64((LIB / "ui.py").read_text(encoding="utf-8"))
    proc = _b64((LIB / "proc.py").read_text(encoding="utf-8"))
    init = _b64((LIB / "__init__.py").read_text(encoding="utf-8"))

    lines = [
        "# ==== cyberdeck inlined by build.py — НЕ РЕДАКТИРОВАТЬ (правь cyberdeck/ и пересобери) ====",
        "import sys as _sys, types as _types, base64 as _b64",
        "def _cd(_n, _src):",
        "    _m = _types.ModuleType(_n); _m.__package__ = _n.rpartition('.')[0]",
        "    _sys.modules[_n] = _m",
        "    exec(compile(_b64.b64decode(_src).decode('utf-8'), '<' + _n + '>', 'exec'), _m.__dict__)",
        "    setattr(_sys.modules[_m.__package__], _n.rpartition('.')[2], _m)",
        "    return _m",
        "_cd_pkg = _types.ModuleType('cyberdeck'); _cd_pkg.__path__ = []; _cd_pkg.__package__ = 'cyberdeck'",
        "_sys.modules['cyberdeck'] = _cd_pkg",
        f"_cd('cyberdeck.envelope', '{envelope}')",
        f"_cd('cyberdeck.ui', '{ui}')",
    ]
    if need_proc:
        lines.append(f"_cd('cyberdeck.proc', '{proc}')")
    lines.append(
        f"exec(compile(_b64.b64decode('{init}').decode('utf-8'), '<cyberdeck>', 'exec'), _cd_pkg.__dict__)"
    )
    lines.append("# ==== end cyberdeck inlined ====")
    return "\n".join(lines)


def build_one(path: Path) -> Path:
    src = path.read_text(encoding="utf-8")
    need_proc = bool(re.search(r"cyberdeck import proc|cyberdeck\.proc", src))

    # sys.path-хак с __file__ под `python3 -` уронил бы скрипт — вырезаем
    src = re.sub(
        r"^sys\.path\.insert\(0, str\(Path\(__file__\).*?\)\)\n",
        "",
        src,
        flags=re.M,
    )

    marker = "from __future__ import annotations\n"
    if marker not in src:
        raise SystemExit(f"{path.name}: нет future-import, некуда встроить бутстрап")
    idx = src.index(marker) + len(marker)
    out = src[:idx] + "\n" + bootstrap(need_proc) + "\n" + src[idx:]

    DIST.mkdir(exist_ok=True)
    dest = DIST / path.name
    dest.write_text(out, encoding="utf-8")
    dest.chmod(0o755)
    return dest


def main() -> None:
    built = []
    for name in TARGETS:
        path = SCRIPTS / name
        if path.exists():
            dest = build_one(path)
            built.append(dest)
            print(f"built  dist/{dest.name}  ({dest.stat().st_size} bytes)")
    if not built:
        raise SystemExit("не нашёл скриптов в scripts/")
    print(f"\nготово: {len(built)} файл(ов) в dist/ — можно раздавать по одному и лить в `python3 -`")


if __name__ == "__main__":
    main()
