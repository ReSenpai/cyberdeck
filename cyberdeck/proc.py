"""Запуск внешних инструментов с построчным чтением вывода в реальном времени."""

from __future__ import annotations

import os
import re
import select
import shutil
import subprocess
import threading
import time
from typing import Callable

# masscan рисует статус через '\r' без перевода строки — режем по обоим символам.
_LINE_SPLIT = re.compile(r"[\r\n]")

# select по пайпам есть только на POSIX; Windows обходится блокирующим чтением.
_CAN_SELECT = os.name != "nt"


def which(binary: str) -> str | None:
    return shutil.which(binary)


def _pump(fd: int, on_line: Callable[[str], None], idle_flush: float = 0.4) -> None:
    """Читать поток и отдавать строки, разрезая по '\\r' и '\\n'.

    Отдельная беда — статус masscan: он начинается с '\\r', поэтому строка
    «дозревает» только когда придёт следующая. Если тул замирает (masscan любит
    зависнуть после 100%), последняя строка так и осталась бы в буфере, а вместе
    с ней — и весь прогресс. Поэтому недописанный хвост выдаём по тишине.
    """
    buf = ""
    last_data = time.monotonic()
    while True:
        if _CAN_SELECT:
            ready, _, _ = select.select([fd], [], [], 0.2)
            if not ready:
                if buf.strip() and time.monotonic() - last_data > idle_flush:
                    on_line(buf.rstrip())
                    buf = ""
                continue
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            break
        if not chunk:
            break
        last_data = time.monotonic()
        buf += chunk.decode("utf-8", "replace")
        parts = _LINE_SPLIT.split(buf)
        buf = parts.pop()
        for part in parts:
            if part.strip():
                on_line(part.rstrip())
    if buf.strip():
        on_line(buf.rstrip())


def _signal(process: subprocess.Popen, hard: bool) -> None:
    """Послать сигнал, а если процесс под sudo и мы не root — то через sudo."""
    try:
        process.kill() if hard else process.terminate()
    except ProcessLookupError:
        pass
    except PermissionError:
        # запускали через sudo: своим правом дочерний root-процесс не снять
        try:
            subprocess.run(
                ["sudo", "-n", "kill", "-KILL" if hard else "-TERM", str(process.pid)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass


def terminate(process: subprocess.Popen) -> None:
    """Мягко прибить процесс, при упрямстве — жёстко."""
    if process.poll() is not None:
        return
    _signal(process, hard=False)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _signal(process, hard=True)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def stream(
    cmd: list[str],
    on_stdout: Callable[[str], None],
    on_stderr: Callable[[str], None],
    watchdog: Callable[[float], bool] | None = None,
    poll_interval: float = 0.25,
) -> int:
    """Выполнить команду, отдавая строки вывода в колбэки по мере поступления.

    stdin закрыт: интерактивные подсказки (пароль sudo) не должны съесть
    данные, пришедшие в скрипт по пайпу.

    ``watchdog`` получает число секунд с последней строки вывода и, вернув True,
    просит снять процесс. Нужен для тулов вроде masscan, которые умеют закончить
    работу, но не умеют завершиться.
    """
    last_line_at = [time.monotonic()]

    def watched(callback: Callable[[str], None]) -> Callable[[str], None]:
        def inner(line: str) -> None:
            last_line_at[0] = time.monotonic()
            callback(line)
        return inner

    on_stdout, on_stderr = watched(on_stdout), watched(on_stderr)
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    threads = [
        threading.Thread(target=_pump, args=(proc.stdout.fileno(), on_stdout), daemon=True),
        threading.Thread(target=_pump, args=(proc.stderr.fileno(), on_stderr), daemon=True),
    ]
    for thread in threads:
        thread.start()
    try:
        if watchdog is None:
            proc.wait()
        else:
            while True:
                try:
                    proc.wait(timeout=poll_interval)
                    break
                except subprocess.TimeoutExpired:
                    if watchdog(time.monotonic() - last_line_at[0]):
                        terminate(proc)
                        break
    except KeyboardInterrupt:
        terminate(proc)
        raise
    finally:
        for thread in threads:
            thread.join(timeout=2)
        for pipe in (proc.stdout, proc.stderr):
            try:
                pipe.close()
            except OSError:
                pass
    return proc.returncode


def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def sudo_prefix(enabled: bool) -> list[str]:
    """['sudo'] если он нужен и мы не root."""
    if not enabled or is_root() or os.name == "nt":
        return []
    return ["sudo"]


def sudo_ready() -> bool:
    """Проверить закешированный тикет sudo, не показывая запрос пароля."""
    try:
        return subprocess.run(
            ["sudo", "-n", "true"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0
    except OSError:
        return False