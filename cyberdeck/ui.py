"""Консольный вывод деки.

Всё оформление уходит в stderr, чтобы stdout оставался чистым каналом данных
для пайпов. Красиво — если стоит rich; без него скрипт всё равно работает.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager

try:
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )
    from rich.table import Table

    HAS_RICH = True
except ImportError:  # голая система — работаем текстом
    HAS_RICH = False


def force_utf8() -> None:
    """UTF-8 на всех трёх потоках: кириллица/эмодзи не должны падать на cp1252/cp866.

    stdin тоже: конверты кибердеки ходят по пайпам в UTF-8 (remark'и VLESS — с
    эмодзи), а Windows по умолчанию читает stdin в cp1252 и корёжит их.
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


class _PlainProgress:
    """Заглушка прогресса: печатает вехи по 10%, не засоряя лог."""

    def __init__(self, ui: "UI"):
        self._ui = ui
        self._tasks: dict[int, tuple[str, float]] = {}
        self._next = 0

    def add(self, description: str, total: float | None = 100.0) -> int:
        task_id = self._next
        self._next += 1
        self._tasks[task_id] = (description, -1.0)
        self._ui.info(description)
        return task_id

    def update(self, task_id: int, completed: float | None = None, description: str | None = None, **_: object) -> None:
        desc, last = self._tasks.get(task_id, ("", -1.0))
        if description is not None:
            desc = description
        if completed is not None and completed - last >= 10:
            last = completed
            self._ui.dim(f"{desc} — {completed:.0f}%")
        self._tasks[task_id] = (desc, last)

    def log(self, message: str) -> None:
        self._ui.raw(message)


class _RichProgress:
    def __init__(self, progress: "Progress"):
        self._p = progress

    def add(self, description: str, total: float | None = 100.0) -> int:
        return self._p.add_task(description, total=total, note="")

    def update(self, task_id: int, **kwargs: object) -> None:
        self._p.update(task_id, **kwargs)

    def log(self, message: str) -> None:
        # печать через progress.console не ломает живой бар
        self._p.console.print(message, highlight=False)


class UI:
    def __init__(self, quiet: bool = False, verbose: bool = False, color: bool = True):
        self.quiet = quiet
        self.verbose = verbose
        if HAS_RICH:
            force = None if color else False
            self.err = Console(stderr=True, force_terminal=force, no_color=not color)
            self.out = Console(force_terminal=force, no_color=not color)
        else:
            self.err = self.out = None

    # -- примитивы ----------------------------------------------------------

    def _emit(self, plain: str, markup: str) -> None:
        if self.quiet:
            return
        if HAS_RICH:
            self.err.print(markup, highlight=False)
        else:
            print(plain, file=sys.stderr, flush=True)

    def info(self, message: str) -> None:
        self._emit(f"[*] {message}", f"[bold cyan]\\[*][/] {message}")

    def ok(self, message: str) -> None:
        self._emit(f"[+] {message}", f"[bold green]\\[+][/] {message}")

    def warn(self, message: str) -> None:
        self._emit(f"[!] {message}", f"[bold yellow]\\[!][/] {message}")

    def err_msg(self, message: str) -> None:
        # ошибки видно даже в quiet — молчать про них нельзя
        if HAS_RICH:
            self.err.print(f"[bold red]\\[x][/] {message}", highlight=False)
        else:
            print(f"[x] {message}", file=sys.stderr, flush=True)

    def dim(self, message: str) -> None:
        self._emit(f"    {message}", f"[dim]    {message}[/]")

    def raw(self, message: str) -> None:
        """Сырая строка внешнего инструмента (только при --verbose)."""
        if self.verbose:
            self._emit(f"  | {message}", f"[dim]  │ {message}[/]")

    def banner(self, title: str, subtitle: str = "") -> None:
        if self.quiet:
            return
        if HAS_RICH:
            self.err.print()
            self.err.rule(f"[bold magenta]{title}[/]" + (f" [dim]{subtitle}[/]" if subtitle else ""))
        else:
            print(f"\n=== {title} {subtitle} ===", file=sys.stderr, flush=True)

    def stage(self, title: str) -> None:
        if self.quiet:
            return
        if HAS_RICH:
            self.err.print(f"\n[bold blue]▐[/] [bold]{title}[/]", highlight=False)
        else:
            print(f"\n-- {title}", file=sys.stderr, flush=True)

    # -- прогресс -----------------------------------------------------------

    @contextmanager
    def progress(self):
        if not HAS_RICH or self.quiet:
            yield _PlainProgress(self)
            return
        progress = Progress(
            SpinnerColumn(style="magenta"),
            TextColumn("[bold]{task.description}"),
            BarColumn(bar_width=32, complete_style="green", finished_style="green"),
            TextColumn("[progress.percentage]{task.percentage:>5.1f}%"),
            TimeElapsedColumn(),
            TextColumn("{task.fields[note]}"),
            console=self.err,
            transient=False,
        )
        with progress:
            yield _RichProgress(progress)

    # -- итоговый отчёт (stdout) --------------------------------------------

    def report(self, envelope_dict: dict) -> None:
        hosts = envelope_dict["hosts"]
        stats = envelope_dict["stats"]

        if not HAS_RICH:
            for host in hosts:
                name = f" ({', '.join(host['hostnames'])})" if host["hostnames"] else ""
                print(f"\n{host['ip']}{name} — {host['state']}")
                for port in host["ports"]:
                    service = port.get("service", "?")
                    version = " ".join(
                        filter(None, [port.get("product", ""), port.get("version", ""), port.get("extrainfo", "")])
                    )
                    print(f"  {port['port']}/{port['proto']:<3} {port['state']:<8} {service:<16} {version}")
            print(
                f"\nхостов с портами: {stats['hosts_with_ports']}   "
                f"открытых портов: {stats['open_ports']}   "
                f"время: {envelope_dict['duration_sec']}s"
            )
            return

        for host in hosts:
            name = f"  [dim]{', '.join(host['hostnames'])}[/]" if host["hostnames"] else ""
            table = Table(
                title=f"[bold cyan]{host['ip']}[/]{name}",
                title_justify="left",
                header_style="bold magenta",
                box=None,
                pad_edge=False,
            )
            table.add_column("PORT", style="bold green", no_wrap=True)
            table.add_column("STATE", no_wrap=True)
            table.add_column("SERVICE", style="cyan", no_wrap=True)
            table.add_column("VERSION")
            for port in host["ports"]:
                version = " ".join(
                    filter(None, [port.get("product", ""), port.get("version", ""), port.get("extrainfo", "")])
                )
                state = port.get("state", "?")
                table.add_row(
                    f"{port['port']}/{port['proto']}",
                    f"[green]{state}[/]" if state == "open" else f"[yellow]{state}[/]",
                    port.get("service", "-"),
                    version or "[dim]-[/]",
                )
            self.out.print()
            self.out.print(table)

        self.out.print(
            f"\n[bold]итого:[/] хостов с портами [bold cyan]{stats['hosts_with_ports']}[/], "
            f"открытых портов [bold green]{stats['open_ports']}[/], "
            f"время [bold]{envelope_dict['duration_sec']}s[/]"
        )