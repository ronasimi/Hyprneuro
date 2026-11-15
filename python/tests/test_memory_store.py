"""Owner identity and explicit migration: synthetic state only, no runtime DBs."""
from pathlib import Path
import sqlite3
import subprocess
import sys
from unittest.mock import patch

import pytest

from hyprneuro.application import TieredMemory
from hyprneuro.sidecar_store import SidecarStore, public_url


@pytest.fixture(params=["memory", "sqlite"])
def memory(request, tmp_path):
    store = SidecarStore(tmp_path / "memory.db") if request.param == "sqlite" else None
    yield TieredMemory(store)
    if store:
        store.close()


@pytest.mark.parametrize("scope", ["task", "app", "project"])
def test_same_key_distinct_owners(memory, scope):
    field = scope + "_id"
    for owner in ("a", "b"):
        memory.remember(scope, "same", {"owner": owner}, **{field: owner})
    memory.remember(scope, "same", {"owner": "updated-a"}, **{field: "a"})
    assert memory.get(scope, "same", **{field: "a"}) == {"owner": "updated-a"}
    assert memory.get(scope, "same", **{field: "b"}) == {"owner": "b"}
    assert memory.recall(scope, **{field: "absent"}) == []
    with pytest.raises(ValueError, match=field):
        memory.recall(scope, key="same")
    with pytest.raises(ValueError, match=field):
        memory.get(scope, "same")
    with pytest.raises(ValueError, match=field):
        memory.remember(scope, "same", "unscoped")


def test_global_and_each_scope_are_distinct(memory):
    memory.remember("global", "same", "global")
    for scope in ("task", "app", "project"):
        memory.remember(scope, "same", scope, **{scope + "_id": "owner"})
    assert memory.get("global", "same") == "global"
    memory.remember("global", "same", "updated")
    assert len(memory.recall("global")) == 1
    for scope in ("task", "app", "project"):
        assert memory.get(scope, "same", **{scope + "_id": "owner"}) == scope
        for method in (lambda: memory.recall("global", **{scope + "_id": "owner"}),
                       lambda: memory.remember("global", "same", "bad", **{scope + "_id": "owner"})):
            with pytest.raises(ValueError, match="global"):
                method()


@pytest.mark.parametrize("scope", ["task", "app", "project"])
@pytest.mark.parametrize("owner", ["", " ", 1, True, "x" * 129, "a\nb", "a\x00b", "a\x7fb"])
def test_invalid_owner_denied_on_read_and_write(memory, scope, owner):
    for method in (lambda: memory.remember(scope, "k", 1, **{scope + "_id": owner}),
                   lambda: memory.recall(scope, **{scope + "_id": owner})):
        with pytest.raises(ValueError):
            method()


@pytest.mark.parametrize("scope", ["task", "app", "project"])
def test_other_ids_are_restrictive_metadata_not_alternate_owners(memory, scope):
    ids = dict(task_id="task", app_id="app", project_id="project")
    memory.remember(scope, "k", 1, **ids)
    assert memory.get(scope, "k", **{scope + "_id": scope}) == 1
    assert len(memory.recall(scope, **ids)) == 1
    for field in ids:
        wrong = {**ids, field: "other"}
        assert memory.recall(scope, **wrong) == []
        with pytest.raises(ValueError):
            memory.recall(scope, **{**ids, field: ""})


def test_copy_isolation_and_json_parity(memory):
    original = {"nested": [{"key": "original"}]}
    memory.remember("app", "k", original, app_id="a")
    original["nested"][0]["key"] = "input-mutated"
    result = memory.recall("app", app_id="a")
    result[0]["value"]["nested"][0]["key"] = "output-mutated"
    result[0]["app_id"] = "b"
    assert memory.get("app", "k", app_id="a") == {"nested": [{"key": "original"}]}
    assert memory.recall("app", app_id="b") == []
    memory.remember("global", "tuple", (1, 2))
    assert memory.get("global", "tuple") == [1, 2]


@pytest.mark.parametrize("source", ["task", "app", "project", "global"])
@pytest.mark.parametrize("destination", ["task", "app", "project", "global"])
def test_promotion_exact_bindings_and_approval(memory, source, destination):
    source_ids = {} if source == "global" else {source + "_id": "source"}
    target_ids = {} if destination == "global" else {"to_" + destination + "_id": "target"}
    read_target = {k.removeprefix("to_"): v for k, v in target_ids.items()}
    memory.remember(source, "k", {"from": source}, **source_ids)
    if source == destination:
        with pytest.raises(ValueError, match="must differ"):
            memory.promote("k", source, destination, approved=True, **source_ids, **target_ids)
        return
    if destination != "global":
        memory.remember(destination, "k", "other", **{destination + "_id": "other"})
    for approval in (None, 1, "true"):
        with pytest.raises(ValueError, match="boolean"):
            memory.promote("k", source, destination, approved=approval, **source_ids, **target_ids)
    assert not memory.promote("k", source, destination, approved=False,
                              **source_ids, **target_ids)["promoted"]
    assert memory.get(destination, "k", **read_target) is None
    if source != "global":
        with pytest.raises(ValueError):
            memory.promote("k", source, destination, approved=True, **target_ids)
        with pytest.raises(LookupError):
            memory.promote("k", source, destination, approved=True,
                           **{source + "_id": "wrong"}, **target_ids)
    if destination != "global":
        with pytest.raises(ValueError):
            memory.promote("k", source, destination, approved=True, **source_ids)
    assert memory.promote("k", source, destination, approved=True,
                          **source_ids, **target_ids)["stored"]
    assert memory.get(destination, "k", **read_target) == {"from": source}
    assert memory.get(source, "k", **source_ids) == {"from": source}
    if destination != "global":
        assert memory.get(destination, "k", **{destination + "_id": "other"}) == "other"


def test_promotion_null_and_source_filters(memory):
    memory.remember("task", "null", None, task_id="t", app_id="a")
    with pytest.raises(LookupError):
        memory.promote("null", "task", "global", approved=True, task_id="t", app_id="b")
    memory.promote("null", "task", "global", approved=True, task_id="t", app_id="a")
    assert memory.recall("global", key="null")[0]["value"] is None
    memory.remember("global", "k", 1)
    with pytest.raises(ValueError):
        memory.promote("k", "global", "task", approved=True, task_id="t", to_task_id="t")


def test_direct_store_cannot_bypass_owner_validation(tmp_path):
    store = SidecarStore(tmp_path / "db")
    try:
        for scope in ("task", "app", "project"):
            with pytest.raises(ValueError):
                store.app_memory_remember(scope, "k", "{}")
            with pytest.raises(ValueError):
                store.app_memory_recall(scope)
            with pytest.raises(ValueError):
                store.app_memory_recall(scope, **{scope + "_id": "a"}, limit=True)
        with pytest.raises(ValueError):
            store.app_memory_remember("global", "k", "{}", app_id="a")
    finally:
        store.close()


ROWS = [
    ("app", "same", ' { "original" : [1,2] } ', "t", "app-a", "p", 10),
    ("task", "same", '"task"', "task-a", "app-a", "p", 11),
    ("project", "same", '"project"', "t", "app-a", "project-a", 12),
    ("global", "same", '"global"', None, None, None, 13),
    ("app", "missing-owner", "invalid json original", "unrelated-task", None, "p", 14),
    ("task", "blank-owner", '"keep"', "", "a", None, 15),
    ("project", "bad-owner", b"\xff\x00original", None, None, "a\nb", 16),
    ("global", "ambiguous", '"keep global metadata"', "t", "a", "p", 17),
    ("unknown-scope", "odd key", '"keep unknown"', None, None, None, 18),
    ("app", "bad-other-id", '"keep"', "", "valid-app", None, 19),
]


def historical(path, version):
    db = sqlite3.connect(path)
    db.create_function("public_url", 1, public_url, deterministic=True)
    db.executescript((Path(__file__).parent / "fixtures" / f"memory-schema-v{version}.sql").read_text())
    if version != "1":
        db.executemany("INSERT INTO app_memory VALUES(?,?,?,?,?,?,?)", ROWS)
        db.execute("INSERT INTO tasks(goal,created_ms,updated_ms,state_json) VALUES('original',1,1,?)",
                   (' {"original":true} ',))
        db.execute("INSERT INTO skill_manifests VALUES('a','original skill')")
    db.execute("INSERT INTO observations(time_ms,last_seen_ms,source,kind,title,url) "
               "VALUES(1,1,'manual','note','migrationneedle','https://example.test/path?secret=keep')")
    db.commit()
    return db


def snapshot(db):
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    return {t: sorted(db.execute('SELECT * FROM "' + t + '"').fetchall(), key=repr) for t in tables}


def assert_original(db, before, version):
    after = snapshot(db)
    assert after["sidecar_meta"] == [(k, "4" if k == "schema_version" else v)
                                      for k, v in before["sidecar_meta"]]
    for name, rows in before.items():
        if name not in {"app_memory", "sidecar_meta"}:
            assert after[name] == rows, name
    if version != "1":
        assert sorted(db.execute("SELECT scope,key,value_json,task_id,app_id,project_id,updated_ms "
                                 "FROM app_memory").fetchall(), key=repr) == before["app_memory"]
    assert db.execute("SELECT rowid FROM observations_fts WHERE observations_fts MATCH 'migrationneedle'").fetchall() == [(1,)]
    assert db.execute("SELECT rowid FROM search_fts WHERE search_fts MATCH 'migrationneedle'").fetchall() == [(1,)]


@pytest.mark.parametrize("version", ["1", "2", "3"])
def test_historic_migration_exact_preservation_backup_restart_and_fts(tmp_path, version):
    path, backup_path = tmp_path / "db", tmp_path / "before.db"
    db = historical(path, version)
    before = snapshot(db)
    db.close()
    with pytest.raises(RuntimeError, match="Explicit backed-up"):
        SidecarStore(path)
    SidecarStore.migrate_memory(path, backup_path=backup_path)
    backup = sqlite3.connect(backup_path)
    try:
        assert snapshot(backup) == before
    finally:
        backup.close()
    assert backup_path.stat().st_mode & 0o777 == 0o600
    store = SidecarStore(path)
    try:
        assert_original(store.db, before, version)
        store.record({"time_ms": 2, "source": "manual", "kind": "note", "message": "postmigrationneedle"})
        for fts in ("observations_fts", "search_fts"):
            assert store.db.execute(f"SELECT rowid FROM {fts} WHERE {fts} MATCH 'postmigrationneedle'").fetchall() == [(2,)]
        assert store.db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert [r[2] for r in store.db.execute("PRAGMA index_info(app_memory_scope_time)")] == [
            "scope", "legacy_unscoped", "owner_id", "updated_ms"]
        if version != "1":
            assert store.db.execute("SELECT count(*) FROM app_memory WHERE legacy_unscoped=1").fetchone()[0] == 6
            memory = TieredMemory(store)
            assert memory.get("app", "same", app_id="app-a") == {"original": [1, 2]}
            memory.remember("app", "same", "new-b", app_id="app-b")
            assert memory.get("app", "same", app_id="app-a") == {"original": [1, 2]}
            assert memory.get("app", "same", app_id="app-b") == "new-b"
            assert memory.recall("global", key="ambiguous") == []
            assert memory.recall("app", app_id="unrelated-task") == []
            memory.remember("app", "missing-owner", "new-owned", app_id="new")
            assert store.db.execute("SELECT value_json FROM app_memory WHERE legacy_unscoped=1 "
                                    "AND key='missing-owner'").fetchone()[0] == "invalid json original"
            # Idle trimming must not destroy retained ambiguous provenance.
            store.app_memory_trim(keep=8)
            assert store.db.execute("SELECT count(*) FROM app_memory WHERE legacy_unscoped=1").fetchone()[0] == 6
    finally:
        store.close()
    store = SidecarStore(path)
    store.close()
    with pytest.raises(RuntimeError, match="requires schema version"):
        SidecarStore.migrate_memory(path, backup_path=tmp_path / "again.db")
    assert not (tmp_path / "again.db").exists()


def test_backup_restore_is_an_exact_legacy_snapshot(tmp_path):
    path, backup_path, restored_path = (tmp_path / name for name in ("db", "backup", "restored"))
    db = historical(path, "3")
    before = snapshot(db)
    db.close()
    SidecarStore.migrate_memory(path, backup_path=backup_path)
    store = SidecarStore(path)
    try:
        store.app_memory_remember("app", "same", '"post migration write"', app_id="new-owner")
    finally:
        store.close()
    backup, restored = sqlite3.connect(backup_path), sqlite3.connect(restored_path)
    try:
        backup.backup(restored)
        assert snapshot(restored) == before
    finally:
        backup.close()
        restored.close()
    # Restore is to a separate disposable path. The v4 candidate stays intact;
    # a live rollback would require retaining it to preserve post-migration writes.
    store = SidecarStore(path)
    try:
        assert store.app_memory_recall("app", app_id="new-owner")[0]["value"] == "post migration write"
    finally:
        store.close()


@pytest.mark.parametrize("failure", [RuntimeError("interrupted"), KeyboardInterrupt()])
def test_migration_rolls_back_ddl_rows_and_version_on_interruption(tmp_path, failure):
    path, backup = tmp_path / "db", tmp_path / "backup"
    db = historical(path, "3")
    before = snapshot(db)
    schema = db.execute("SELECT * FROM sqlite_master ORDER BY name").fetchall()
    db.close()
    migrate = SidecarStore._migrate_memory_schema

    def interrupt(db):
        migrate(db)
        raise failure

    with patch.object(SidecarStore, "_migrate_memory_schema", side_effect=interrupt):
        with pytest.raises(type(failure)):
            SidecarStore.migrate_memory(path, backup_path=backup)
    db = sqlite3.connect(path)
    try:
        assert snapshot(db) == before
        assert db.execute("SELECT * FROM sqlite_master ORDER BY name").fetchall() == schema
    finally:
        db.close()
    SidecarStore.migrate_memory(path, backup_path=tmp_path / "retry-backup")


def test_abrupt_process_exit_rolls_back_incomplete_migration(tmp_path):
    path = tmp_path / "db"
    db = historical(path, "3")
    before = snapshot(db)
    db.close()
    script = """
import os, sys
from hyprneuro.sidecar_store import SidecarStore
original = SidecarStore._migrate_memory_schema
def interrupt(db):
    original(db)
    os._exit(17)
SidecarStore._migrate_memory_schema = staticmethod(interrupt)
SidecarStore.migrate_memory(sys.argv[1], backup_path=sys.argv[2])
"""
    result = subprocess.run([sys.executable, "-W", "error", "-c", script, str(path), str(tmp_path / "backup")],
                            check=False, capture_output=True, timeout=10)
    assert result.returncode == 17, result.stderr
    db = sqlite3.connect(path)
    try:
        assert snapshot(db) == before
        assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    finally:
        db.close()


@pytest.mark.parametrize("mutation", ["unknown-version", "missing-version", "extra-column", "missing-memory", "extra-index", "extra-trigger", "referencing-trigger", "referencing-view", "referencing-fk", "unknown-constraint"])
def test_unknown_or_changed_schema_denied_without_loss(tmp_path, mutation):
    path = tmp_path / "db"
    db = historical(path, "3")
    sql = {
        "unknown-version": "UPDATE sidecar_meta SET value='999' WHERE key='schema_version'",
        "missing-version": "DELETE FROM sidecar_meta WHERE key='schema_version'",
        "extra-column": "ALTER TABLE app_memory ADD COLUMN unexpected TEXT",
        "missing-memory": "DROP TABLE app_memory",
        "extra-index": "CREATE INDEX unexpected ON app_memory(key)",
        "extra-trigger": "CREATE TRIGGER unexpected AFTER INSERT ON app_memory BEGIN SELECT 1; END",
        "referencing-trigger": "CREATE TRIGGER unexpected AFTER INSERT ON tasks BEGIN SELECT key FROM app_memory; END",
        "referencing-view": "CREATE VIEW unexpected AS SELECT * FROM app_memory",
        "referencing-fk": "CREATE TABLE unexpected(scope TEXT,key TEXT,FOREIGN KEY(scope,key) REFERENCES app_memory(scope,key))",
        "unknown-constraint": "CREATE TABLE app_memory_changed(scope TEXT NOT NULL,key TEXT NOT NULL,value_json TEXT NOT NULL,"
                              "task_id TEXT,app_id TEXT,project_id TEXT,updated_ms INTEGER NOT NULL,PRIMARY KEY(scope,key),CHECK(length(key)>0))",
    }[mutation]
    db.execute(sql)
    if mutation == "unknown-constraint":
        db.execute("INSERT INTO app_memory_changed SELECT * FROM app_memory")
        db.execute("DROP TABLE app_memory")
        db.execute("ALTER TABLE app_memory_changed RENAME TO app_memory")
    db.commit()
    before = snapshot(db)
    schema = db.execute("SELECT * FROM sqlite_master ORDER BY name").fetchall()
    db.close()
    with pytest.raises(RuntimeError):
        SidecarStore.migrate_memory(path, backup_path=tmp_path / "backup")
    assert not (tmp_path / "backup").exists()
    with pytest.raises(RuntimeError):
        SidecarStore(path)
    db = sqlite3.connect(path)
    try:
        assert snapshot(db) == before
        assert db.execute("SELECT * FROM sqlite_master ORDER BY name").fetchall() == schema
    finally:
        db.close()


def test_corrupt_database_denied_unchanged(tmp_path):
    path = tmp_path / "corrupt"
    original = b"not a sqlite database\x00" * 100
    path.write_bytes(original)
    with pytest.raises(sqlite3.DatabaseError):
        SidecarStore.migrate_memory(path, backup_path=tmp_path / "backup")
    assert path.read_bytes() == original
    assert not (tmp_path / "backup").exists()


def test_backup_failure_leaves_source_unchanged(tmp_path):
    path, backup = tmp_path / "db", tmp_path / "backup"
    db = historical(path, "3")
    before = snapshot(db)
    db.close()
    backup.write_bytes(b"existing backup must not be replaced")
    with pytest.raises(FileExistsError):
        SidecarStore.migrate_memory(path, backup_path=backup)
    assert backup.read_bytes() == b"existing backup must not be replaced"
    db = sqlite3.connect(path)
    try:
        assert snapshot(db) == before
    finally:
        db.close()


def test_wal_backup_and_writer_lock_version_check(tmp_path):
    path, backup = tmp_path / "db", tmp_path / "backup"
    writer = historical(path, "3")
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("UPDATE app_memory SET value_json='\"wal value\"' WHERE scope='app' AND key='same'")
        writer.commit()
        assert Path(str(path) + "-wal").exists()
        before = snapshot(writer)
        original = SidecarStore._migrate_memory_schema

        def locked_migration(db):
            competitor = sqlite3.connect(path, timeout=0)
            try:
                with pytest.raises(sqlite3.OperationalError, match="locked"):
                    competitor.execute("UPDATE sidecar_meta SET value='999' WHERE key='schema_version'")
            finally:
                competitor.close()
            # A stale caller cannot select a different migration version.
            assert db.execute("SELECT value FROM sidecar_meta WHERE key='schema_version'").fetchone() == ("3",)
            original(db)

        with patch.object(SidecarStore, "_migrate_memory_schema", side_effect=locked_migration):
            SidecarStore.migrate_memory(path, backup_path=backup)
        saved = sqlite3.connect(backup)
        try:
            assert snapshot(saved) == before
        finally:
            saved.close()
        assert_original(writer, before, "3")
    finally:
        writer.close()


@pytest.mark.parametrize("suffix", ["", "-journal", "-wal", "-shm"])
@pytest.mark.parametrize("alias", ["direct", "parent-symlink", "source-parent-symlink", "leaf-symlink", "case-variant"])
def test_backup_rejects_database_and_sidecar_names_before_open(tmp_path, suffix, alias):
    path = tmp_path / "source.db"
    db = historical(path, "3")
    before = snapshot(db)
    schema = db.execute("SELECT * FROM sqlite_master ORDER BY name").fetchall()
    db.close()
    original = path.read_bytes()
    destination = Path(str(path) + suffix)
    if alias == "parent-symlink":
        linked = tmp_path / "alias"
        linked.symlink_to(tmp_path, target_is_directory=True)
        destination = linked / destination.name
    elif alias == "source-parent-symlink":
        linked = tmp_path / "alias"
        linked.symlink_to(tmp_path, target_is_directory=True)
        path = linked / path.name
    elif alias == "leaf-symlink":
        linked = tmp_path / "backup-alias"
        linked.symlink_to(destination)
        destination = linked
    elif alias == "case-variant":
        destination = destination.with_name(destination.name.upper())
    destination_existed = destination.exists() or destination.is_symlink()
    # Preflight must reject without even opening the source (which could create
    # a journal) or reserving/creating the backup destination.
    with patch("hyprneuro.sidecar_store.sqlite3.connect") as connect, patch(
            "hyprneuro.sidecar_store.os.open") as open_file:
        with pytest.raises(ValueError, match="backup"):
            SidecarStore.migrate_memory(path, backup_path=destination)
        connect.assert_not_called()
        open_file.assert_not_called()
    assert path.read_bytes() == original
    assert (destination.exists() or destination.is_symlink()) == destination_existed
    for sidecar in ("-journal", "-wal", "-shm"):
        assert not Path(str(path) + sidecar).exists()
    db = sqlite3.connect(path)
    try:
        assert snapshot(db) == before
        assert db.execute("SELECT * FROM sqlite_master ORDER BY name").fetchall() == schema
    finally:
        db.close()


@pytest.mark.parametrize("target", ["APP_MEMORY", "App_Memory"])
def test_case_insensitive_populated_foreign_key_rejected_before_backup(tmp_path, target):
    path, backup = tmp_path / "db", tmp_path / "backup"
    db = historical(path, "3")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute(f"CREATE TABLE dependent(scope TEXT,key TEXT,FOREIGN KEY(scope,key) REFERENCES {target}(scope,key))")
    db.execute("INSERT INTO dependent VALUES('app','same')")
    db.commit()
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    before = snapshot(db)
    schema = db.execute("SELECT * FROM sqlite_master ORDER BY name").fetchall()
    db.close()
    original = path.read_bytes()
    with pytest.raises(RuntimeError, match="foreign key"):
        SidecarStore.migrate_memory(path, backup_path=backup)
    assert not backup.exists()
    assert path.read_bytes() == original
    db = sqlite3.connect(path)
    try:
        assert snapshot(db) == before
        assert db.execute("SELECT * FROM sqlite_master ORDER BY name").fetchall() == schema
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        db.close()


def test_backup_hardlink_to_source_rejected_before_open(tmp_path):
    path, backup = tmp_path / "db", tmp_path / "backup"
    db = historical(path, "3")
    db.close()
    backup.hardlink_to(path)
    original = path.read_bytes()
    with patch("hyprneuro.sidecar_store.sqlite3.connect") as connect, patch(
            "hyprneuro.sidecar_store.os.open") as open_file:
        with pytest.raises(ValueError, match="backup"):
            SidecarStore.migrate_memory(path, backup_path=backup)
        connect.assert_not_called()
        open_file.assert_not_called()
    assert path.read_bytes() == backup.read_bytes() == original


@pytest.mark.parametrize("untrusted", ["source", "backup"])
def test_migration_requires_trusted_resolved_parent_before_open(tmp_path, untrusted):
    source_dir, backup_dir = tmp_path / "source", tmp_path / "backups"
    source_dir.mkdir(mode=0o700)
    backup_dir.mkdir(mode=0o700)
    path, backup = source_dir / "db", backup_dir / "backup"
    db = historical(path, "3")
    db.close()
    original = path.read_bytes()
    parent = source_dir if untrusted == "source" else backup_dir
    parent.chmod(0o777)
    try:
        with patch("hyprneuro.sidecar_store.sqlite3.connect") as connect, patch(
                "hyprneuro.sidecar_store.os.open") as open_file:
            with pytest.raises(ValueError, match="trusted"):
                SidecarStore.migrate_memory(path, backup_path=backup)
            connect.assert_not_called()
            open_file.assert_not_called()
        assert path.read_bytes() == original
        assert not backup.exists()
    finally:
        parent.chmod(0o700)


@pytest.mark.parametrize("table_name", ["APP_MEMORY", "App_Memory"])
def test_sqlite_master_memory_identifiers_are_case_insensitive(tmp_path, table_name):
    path = tmp_path / "db"
    sql = (Path(__file__).parent / "fixtures" / "memory-schema-v3.sql").read_text()
    sql = sql.replace("CREATE TABLE app_memory (", f"CREATE TABLE {table_name} (")
    sql = sql.replace("sidecar_meta", "SIDECAR_META")
    db = sqlite3.connect(path)
    try:
        db.executescript(sql)
        db.execute("INSERT INTO app_memory VALUES('app','key','1',NULL,'owner',NULL,1)")
        db.commit()
    finally:
        db.close()
    SidecarStore.migrate_memory(path, backup_path=tmp_path / "backup")
    store = SidecarStore(path)
    try:
        assert store.app_memory_recall("app", app_id="owner")[0]["value"] == 1
        assert store.db.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        store.close()


def test_writable_parent_ancestor_denied_without_artifacts(tmp_path):
    shared, private = tmp_path / "shared", tmp_path / "shared" / "private"
    private.mkdir(parents=True, mode=0o700)
    path, backup = private / "db", private / "backup"
    db = historical(path, "3")
    db.close()
    original = path.read_bytes()
    shared.chmod(0o777)
    try:
        with patch("hyprneuro.sidecar_store.sqlite3.connect") as connect, patch(
                "hyprneuro.sidecar_store.os.open") as open_file:
            with pytest.raises(ValueError, match="trusted parent ancestry"):
                SidecarStore.migrate_memory(path, backup_path=backup)
            connect.assert_not_called()
            open_file.assert_not_called()
        assert path.read_bytes() == original
        assert not backup.exists()
    finally:
        shared.chmod(0o700)
