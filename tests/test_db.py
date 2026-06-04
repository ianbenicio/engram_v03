from engram.core.db import connect, init_schema, VEC_DIM

def test_init_schema_creates_tables(tmp_path):
    conn = connect(tmp_path / "x.db")
    init_schema(conn)
    names = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','virtual')"
        )
    }
    assert "notes" in names
    assert "notes_fts" in names
    conn.close()

def test_notes_has_confidence_column(tmp_path):
    conn = connect(tmp_path / "x.db")
    init_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(notes)")}
    assert "confidence" in cols
    assert "content_hash" in cols
    assert "file_path" in cols
    conn.close()

def test_vec_extension_loads_and_knn_works(tmp_path):
    conn = connect(tmp_path / "x.db")
    init_schema(conn)
    from sqlite_vec import serialize_float32
    vec = [0.1] * VEC_DIM
    conn.execute(
        "INSERT INTO notes_vec(note_id, embedding) VALUES (?, ?)",
        ["n1", serialize_float32(vec)],
    )
    conn.commit()
    rows = conn.execute(
        "SELECT note_id, distance FROM notes_vec "
        "WHERE embedding MATCH ? AND k = 1 ORDER BY distance",
        [serialize_float32(vec)],
    ).fetchall()
    assert rows[0][0] == "n1"
    conn.close()
