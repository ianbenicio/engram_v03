from __future__ import annotations

import json
from pathlib import Path

import typer

from engram.config import load_config
from engram.core.db import connect, init_schema

app = typer.Typer(help="Engram — persistent dev memory")


def _load():
    config = load_config()
    conn = connect(config.db_path)
    init_schema(conn)
    return config, conn


@app.command()
def status():
    """Show vault stats and hub notes."""
    from engram.core import hubs
    config, conn = _load()
    st = hubs.vault_status(conn, config.activity_log)
    st["hubs"] = hubs.hub_notes(conn, config.vault_root, top=5)
    typer.echo(json.dumps(st, indent=2, ensure_ascii=False))


@app.command()
def reindex():
    """Rebuild SQLite index (incremental, hash-skipped)."""
    from engram.core.reindex import reindex_all
    config, conn = _load()
    stats = reindex_all(conn, config)
    typer.echo(f"Reindex complete: {stats['indexed']} indexed, "
               f"{stats['skipped']} skipped (unchanged).")


@app.command()
def watch():
    """Watch vault for external edits and reindex incrementally."""
    from engram.core.watcher import watch as run_watch
    config, conn = _load()
    typer.echo(f"Watching {config.vault_root} ... (Ctrl-C to stop)")
    run_watch(conn, config)


@app.command("import-graph")
def import_graph_cmd(graph_path: str, project: str):
    """Import a Graphify graph.json into the vault."""
    from engram.importers.graphify import import_graph
    config, conn = _load()
    res = import_graph(Path(graph_path), project, config, conn)
    typer.echo(f"Imported {res['created']} nodes, {res['edges']} edges.")


@app.command()
def cluster(project: str, threshold: float = 0.75):
    """Cluster notes by embedding similarity → _clusters.md."""
    from engram.core.clustering import cluster_notes
    config, conn = _load()
    res = cluster_notes(conn, config, project, threshold)
    typer.echo(f"{res['num_clusters']} clusters → {res['path']}")


@app.command()
def mine(source: str, project: str, mode: str = "files"):
    """Mine source files (mode=files: *.md/*.txt) or transcripts
    (mode=convos: *.jsonl) into DRAFT notes under _mined/ for review."""
    from engram.core import mining
    config, conn = _load()
    if mode == "convos":
        res = mining.mine_convos(Path(source), project, config, conn)
    else:
        res = mining.mine_files(Path(source), project, config, conn)
    typer.echo(f"Mined {res['created']} draft notes → {res['path']} "
               f"(review, then promote via vault.update status→active).")


if __name__ == "__main__":
    app()
