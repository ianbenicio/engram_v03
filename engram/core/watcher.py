from __future__ import annotations

import sqlite3
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from engram.config import Config
from engram.core.reindex import reindex_file


class VaultEventHandler(FileSystemEventHandler):
    def __init__(self, conn: sqlite3.Connection, config: Config):
        self.conn = conn
        self.config = config

    def handle_path(self, path_str: str) -> None:
        path = Path(path_str)
        if path.suffix != ".md" or path.name.endswith(".tmp"):
            return
        if not path.exists():
            return
        try:
            reindex_file(self.conn, path, self.config)
        except Exception:
            pass

    def on_modified(self, event):
        if not event.is_directory:
            self.handle_path(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self.handle_path(event.src_path)


def watch(conn: sqlite3.Connection, config: Config) -> None:
    handler = VaultEventHandler(conn, config)
    observer = Observer()
    observer.schedule(handler, str(config.vault_root), recursive=True)
    observer.start()
    try:
        while True:
            observer.join(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
