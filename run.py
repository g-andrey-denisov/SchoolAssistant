"""
Сторожевой процесс: запускает main.py и перезапускает его при изменении
исходников (.py), конфига (.env) или учётных данных (credentials/*.json).

Запуск:
    python run.py

На Debian (systemd): ExecStart=%(venv)s/bin/python run.py
"""

import logging
import subprocess
import sys
from pathlib import Path

from watchfiles import Change, watch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("run")

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable

# Директории, изменения в которых не требуют перезапуска
_SKIP_DIRS = frozenset([
    ".venv", "venv", "__pycache__", ".git",
    "logs", ".mypy_cache", ".pytest_cache",
])


def _watch_filter(change: Change, path: str) -> bool:
    p = Path(path)
    if any(part in _SKIP_DIRS for part in p.parts):
        return False
    return p.suffix in (".py", ".json") or p.name == ".env"


def _start() -> subprocess.Popen:
    log.info("Запуск main.py")
    return subprocess.Popen([PYTHON, "main.py"], cwd=ROOT)


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    log.info("Остановка main.py (pid=%d)…", proc.pid)
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        log.warning("Таймаут — принудительное завершение")
        proc.kill()
        proc.wait()


def main() -> None:
    proc = _start()
    try:
        for changes in watch(ROOT, watch_filter=_watch_filter, raise_interrupt=True):
            names = ", ".join(
                str(Path(p).relative_to(ROOT)) for _, p in changes
            )
            log.info("Изменения: %s — перезапуск…", names)
            _stop(proc)
            proc = _start()
    except KeyboardInterrupt:
        log.info("Прерывание — завершаем бота…")
        _stop(proc)


if __name__ == "__main__":
    main()
