"""Общая библиотека кибердеки: единый формат ввода/вывода для всех скриптов."""

from .envelope import SCHEMA, Envelope, Input, read_input, make_port

__all__ = ["SCHEMA", "Envelope", "Input", "read_input", "make_port", "__version__"]

__version__ = "0.1.0"