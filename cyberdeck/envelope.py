"""Единый JSON-контракт кибердеки (schema: cyberdeck.v1).

Правила пайпов:
  * машинный JSON  -> stdout  (только он, ничего больше)
  * логи и прогресс -> stderr
  * любой скрипт умеет читать со stdin такой же конверт и достать оттуда цели

Форма конверта::

    {
      "schema": "cyberdeck.v1",
      "tool": "portscan",
      "run_id": "a1b2c3d4e5f6",
      "status": "ok" | "partial" | "error",
      "started_at": "...", "finished_at": "...", "duration_sec": 12.3,
      "params": {...},                 # чем именно запускали
      "targets": ["10.0.0.1"],         # что просили просканировать
      "hosts": [                       # главный носитель данных цепочки
        {"ip": "10.0.0.1", "hostnames": [...], "state": "up",
         "ports": [{"port": 22, "proto": "tcp", "state": "open",
                    "service": "ssh", "product": "OpenSSH", "version": "9.6p1",
                    "cpe": [...], "scripts": {...}, "source": "nmap"}]}
      ],
      "stats": {...},
      "warnings": [], "errors": []
    }

Ключ ``hosts`` — общий для всего набора скриптов, поэтому следующий инструмент
в цепочке (http-проба, брутфорс баннеров и т.д.) читает его, дополняет своими
полями и отдаёт дальше в том же виде.
"""

from __future__ import annotations

import datetime as dt
import json
import time
import uuid
from typing import Any, Iterable

SCHEMA = "cyberdeck.v1"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def make_port(
    port: int,
    proto: str = "tcp",
    state: str = "open",
    source: str = "",
    **extra: Any,
) -> dict:
    """Порт в каноничном виде. Пустые поля не тащим — конверт должен быть читаемым."""
    rec: dict[str, Any] = {"port": int(port), "proto": proto, "state": state}
    if source:
        rec["source"] = source
    for key, value in extra.items():
        if value not in (None, "", [], {}):
            rec[key] = value
    return rec


class Envelope:
    """Накопитель результата одного запуска."""

    def __init__(self, tool: str, tool_version: str, params: dict | None = None):
        self.tool = tool
        self.tool_version = tool_version
        self.run_id = uuid.uuid4().hex[:12]
        self.started_at = _now()
        self._t0 = time.monotonic()
        self.params = params or {}
        self.targets: list[str] = []
        self.status = "ok"
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self._hosts: dict[str, dict] = {}

    # -- наполнение ---------------------------------------------------------

    def host(self, ip: str) -> dict:
        """Достать или завести запись хоста."""
        rec = self._hosts.get(ip)
        if rec is None:
            rec = {"ip": ip, "hostnames": [], "state": "unknown", "ports": []}
            self._hosts[ip] = rec
        return rec

    def add_port(self, ip: str, port: dict) -> dict:
        """Добавить порт хосту либо обогатить уже известный (nmap поверх masscan)."""
        host = self.host(ip)
        key = (port["proto"], port["port"])
        for existing in host["ports"]:
            if (existing["proto"], existing["port"]) == key:
                existing.update(port)
                return existing
        host["ports"].append(port)
        return port

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def fail(self, message: str) -> None:
        self.errors.append(message)
        self.status = "error"

    # -- выгрузка -----------------------------------------------------------

    @property
    def hosts(self) -> list[dict]:
        return [self._hosts[ip] for ip in sorted(self._hosts)]

    def to_dict(self) -> dict:
        hosts = self.hosts
        for host in hosts:
            host["ports"].sort(key=lambda p: (p["proto"], p["port"]))
        open_ports = sum(
            1 for h in hosts for p in h["ports"] if p.get("state") == "open"
        )
        return {
            "schema": SCHEMA,
            "tool": self.tool,
            "tool_version": self.tool_version,
            "run_id": self.run_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": _now(),
            "duration_sec": round(time.monotonic() - self._t0, 2),
            "params": self.params,
            "targets": self.targets,
            "hosts": hosts,
            "stats": {
                "targets": len(self.targets),
                "hosts_with_ports": sum(1 for h in hosts if h["ports"]),
                "open_ports": open_ports,
            },
            "warnings": self.warnings,
            "errors": self.errors,
        }

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


class Input:
    """То, что пришло на вход: цели и (опционально) уже известные порты."""

    def __init__(self, targets: Iterable[str] = (), hosts: Iterable[dict] = ()):
        self.targets = list(dict.fromkeys(targets))
        self.hosts = list(hosts)

    def __bool__(self) -> bool:
        return bool(self.targets or self.hosts)


def read_input(text: str) -> Input:
    """Разобрать stdin.

    Понимает: конверт cyberdeck.v1, голый список строк/объектов в JSON и
    просто построчный список адресов — чтобы дека дружила с обычным текстом.
    """
    text = text.strip()
    if not text:
        return Input()

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        targets = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        return Input(targets=targets)

    if isinstance(payload, list):
        targets, hosts = [], []
        for item in payload:
            if isinstance(item, str):
                targets.append(item)
            elif isinstance(item, dict) and item.get("ip"):
                hosts.append(item)
                targets.append(item["ip"])
        return Input(targets=targets, hosts=hosts)

    if isinstance(payload, dict):
        hosts = [h for h in payload.get("hosts", []) if isinstance(h, dict) and h.get("ip")]
        targets = list(payload.get("targets") or [])
        targets += [h["ip"] for h in hosts]
        return Input(targets=targets, hosts=hosts)

    return Input()