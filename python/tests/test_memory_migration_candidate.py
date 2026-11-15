"""Only marked disposable Workspace/TMP fixtures; no service/runtime discovery."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from unittest.mock import patch

import pytest

from test_memory_store import historical
from hyprneuro.sidecar_store import SidecarStore

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/memory_migration_candidate.py"
spec = importlib.util.spec_from_file_location("memory_candidate", SCRIPT)
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)


def private_json(path, value):
    path.write_text(json.dumps(value))
    path.chmod(0o600)


@pytest.fixture
def fixture(tmp_path):
    root = tmp_path / "hn-memory-fixture-synthetic001"
    root.mkdir(mode=0o700)
    private_json(root / "fixture.json", {"schema": "hyprneuro.memory-disposable/1", "disposable": True})
    db = historical(root / "input.sqlite3", "3")
    db.close()
    (root / "input.sqlite3").chmod(0o600)
    private_json(root / "settings.json", {"fixture": "original settings"})
    return root


def request(root, phase):
    return {"schema": "hyprneuro.memory-fixture-request/1", "database": "input.sqlite3", "settings": "settings.json",
            "source": ops.source_identity(), "quiescence": {
                "schema": "hyprneuro.memory-fixture-quiescence/1", "phase": phase,
                "writers_closed": True, "old_owner_scopes": ["fixture-old"], "new_owner_scopes": ["fixture-new"],
                "database_family": ops.family(root / "input.sqlite3"),
                "settings_sha256": ops.digest(root / "settings.json")}}


def prepare(root):
    return ops.prepare(root, request(root, "prepare"))


def replaced(root):
    prepare(root)
    ops.replace_fixture(root, request(root, "replace"))


def activated(root):
    replaced(root)
    ops.mark_fixture_activation(root, request(root, "activation"))


@pytest.mark.parametrize("version", ["1", "2", "3"])
def test_prepare_verify_preserves_original_and_fts_typed_values(fixture, version):
    if version != "3":
        (fixture / "input.sqlite3").unlink()
        db = historical(fixture / "input.sqlite3", version)
        db.close()
        (fixture / "input.sqlite3").chmod(0o600)
    source = (fixture / "input.sqlite3").read_bytes()
    settings = (fixture / "settings.json").read_bytes()
    state = prepare(fixture)
    assert state["phase"] == "prepared"
    assert state["candidate"]["version"] == "4"
    assert state["baseline"]["version"] == version
    assert state["candidate"]["memory_original"] == state["baseline"]["memory_original"]
    assert state["candidate"]["fts"] == state["baseline"]["fts"]
    assert ops.verify(fixture, request(fixture, "verify")) == state
    assert (fixture / "input.sqlite3").read_bytes() == source
    assert (fixture / "settings.json").read_bytes() == settings
    with pytest.raises(FileExistsError):
        prepare(fixture)


@pytest.mark.parametrize("phase", ["verify", "replace", "recovery", "activation"])
def test_attestations_cannot_cross_phases(fixture, phase):
    with pytest.raises(ops.Refused, match="phase-specific"):
        ops.request_paths(fixture, request(fixture, "prepare"), phase)
    assert not (fixture / "operation").exists()


@pytest.mark.parametrize("mutation", ["schema", "absolute-db", "traversal", "source", "source-file", "writer", "old", "new", "extra", "alias-name"])
def test_invalid_explicit_inputs_fail_before_sqlite_open(fixture, mutation):
    req = request(fixture, "prepare")
    if mutation == "schema":
        req["schema"] = "production/1"
    elif mutation == "absolute-db":
        req["database"] = str(fixture / "input.sqlite3")
    elif mutation == "traversal":
        req["database"] = "../input.sqlite3"
    elif mutation == "source":
        req["source"]["commit"] = "0" * 40
    elif mutation == "source-file":
        req["source"]["files"]["python/src/hyprneuro/sidecar_store.py"] = "0" * 64
    elif mutation == "writer":
        req["quiescence"]["writers_closed"] = False
    elif mutation in ("old", "new"):
        req["quiescence"][mutation + "_owner_scopes"] = []
    elif mutation == "extra":
        req["production_mode"] = True
    else:
        req["settings"] = "INPUT.SQLITE3"
    with patch.object(ops.sqlite3, "connect") as connect:
        with pytest.raises(ops.Refused):
            ops.prepare(fixture, req)
        connect.assert_not_called()
    assert not (fixture / "operation").exists()


def test_unmarked_nonfixture_path_refused_before_any_db_access(tmp_path):
    with patch.object(ops.sqlite3, "connect") as connect:
        with pytest.raises(ops.Refused):
            ops.prepare(tmp_path / "not-a-disposable-root", {})
        connect.assert_not_called()


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "public-root", "false-marker"])
def test_disposable_root_does_not_adopt_unsafe_inputs(fixture, kind):
    req = request(fixture, "prepare")
    if kind == "symlink":
        (fixture / "alias").symlink_to(fixture / "input.sqlite3")
    elif kind == "hardlink":
        (fixture / "alias").hardlink_to(fixture / "input.sqlite3")
    elif kind == "public-root":
        fixture.chmod(0o755)
    else:
        private_json(fixture / "fixture.json", {"schema": "hyprneuro.memory-disposable/1", "disposable": False})
    with pytest.raises(ops.Refused):
        ops.prepare(fixture, req)
    assert not (fixture / "operation").exists()


def test_typed_hash_distinguishes_blob_text_null_numeric_and_multiplicity():
    values = [None, "", b"", 1, 1.0, "1", b"1"]
    assert len({ops.typed_rows([(v,)])["sha256"] for v in values}) == len(values)
    assert ops.typed_rows([(1,), (1,)]) != ops.typed_rows([(1,)])
    assert ops.typed_rows([(1,), (2,)]) == ops.typed_rows([(2,), (1,)])


@pytest.mark.parametrize("target", ["memory", "task", "fts", "schema"])
def test_candidate_drift_fails_even_with_updated_file_hash(fixture, target):
    prepare(fixture)
    candidate = fixture / "operation/candidate.sqlite3"
    db = sqlite3.connect(candidate)
    sql = {"memory": "UPDATE app_memory SET value_json='\"tampered\"' WHERE key='same'",
           "task": "UPDATE tasks SET state_json='\"tampered\"'",
           "fts": "UPDATE search_fts SET title='tampered' WHERE rowid=1",
           "schema": "CREATE TABLE unexpected(value TEXT)"}[target]
    db.execute(sql)
    db.commit()
    db.close()
    state = ops.load_state(fixture)
    state["artifacts"]["candidate.sqlite3"] = ops.digest(candidate)
    ops.state(fixture, state)
    with pytest.raises(ops.Refused, match="drift"):
        ops.verify(fixture, request(fixture, "verify"))


@pytest.mark.parametrize("what", ["database", "settings"])
def test_late_writes_refuse_stale_attestation_and_original_baseline(fixture, what):
    prepare(fixture)
    stale = request(fixture, "replace")
    if what == "database":
        db = sqlite3.connect(fixture / "input.sqlite3")
        db.execute("UPDATE tasks SET goal='late task write'")
        db.commit()
        db.close()
    else:
        private_json(fixture / "settings.json", {"fixture": "late settings"})
    with pytest.raises(ops.Refused, match="stale"):
        ops.replace_fixture(fixture, stale)
    with pytest.raises(ops.Refused, match="late writes"):
        ops.replace_fixture(fixture, request(fixture, "replace"))
    assert ops.load_state(fixture)["phase"] == "prepared"
    assert not (fixture / "replacement.sqlite3").exists()


def test_corrupt_input_refused_without_source_mutation(fixture):
    original = b"fixture corruption" * 100
    (fixture / "input.sqlite3").write_bytes(original)
    with pytest.raises(sqlite3.DatabaseError):
        prepare(fixture)
    assert (fixture / "input.sqlite3").read_bytes() == original
    assert not (fixture / "operation").exists()


@pytest.mark.parametrize("error", [RuntimeError("fixture interruption"), KeyboardInterrupt()])
def test_mid_transaction_interruption_keeps_source_and_blocks_replay(fixture, error):
    original = (fixture / "input.sqlite3").read_bytes()
    real = SidecarStore._migrate_memory_schema

    def worker(root, req, budget):
        def interrupted(db):
            real(db)
            raise error
        with patch.object(SidecarStore, "_migrate_memory_schema", side_effect=interrupted):
            SidecarStore.migrate_memory(root / "operation/candidate.sqlite3",
                                        backup_path=root / "operation/migration-backup.sqlite3")

    with patch.object(ops, "_run_migration", side_effect=worker):
        with pytest.raises(type(error)):
            prepare(fixture)
    assert (fixture / "input.sqlite3").read_bytes() == original
    assert ops.load_state(fixture)["phase"] == "prepare_intent"
    assert ops.inventory(fixture / "operation/candidate.sqlite3", ops.Budget())["version"] == "3"
    assert (fixture / "operation/migration-backup.sqlite3").exists()
    with pytest.raises(ops.Refused):
        ops.verify(fixture, request(fixture, "verify"))
    with pytest.raises(FileExistsError):
        prepare(fixture)


def test_abrupt_private_child_exit_rolls_back_and_has_no_source_effect(fixture):
    original = (fixture / "input.sqlite3").read_bytes()
    code = """
import os,sys
from hyprneuro.sidecar_store import SidecarStore
original=SidecarStore._migrate_memory_schema
def interrupt(db):
    original(db)
    os._exit(19)
SidecarStore._migrate_memory_schema=staticmethod(interrupt)
SidecarStore.migrate_memory(sys.argv[1],backup_path=sys.argv[2])
"""
    def worker(root, req, budget):
        subprocess.run([sys.executable, "-W", "error", "-c", code,
                        str(root / "operation/candidate.sqlite3"), str(root / "operation/migration-backup.sqlite3")],
                       check=True, timeout=budget.remaining(), env={"PYTHONPATH": str(ops.CODE / "python/src"),
                                                                  "PYTHONDONTWRITEBYTECODE": "1"})
    with patch.object(ops, "_run_migration", side_effect=worker):
        with pytest.raises(subprocess.CalledProcessError) as error:
            prepare(fixture)
        assert error.value.returncode == 19
    assert (fixture / "input.sqlite3").read_bytes() == original
    assert ops.inventory(fixture / "operation/candidate.sqlite3", ops.Budget())["version"] == "3"
    assert ops.load_state(fixture)["phase"] == "prepare_intent"


def test_deadline_failure_retains_partial_artifacts(fixture):
    def timeout(root, req, budget):
        raise subprocess.TimeoutExpired("owned-fixture-child", 0.01)
    with patch.object(ops, "_run_migration", side_effect=timeout):
        with pytest.raises(subprocess.TimeoutExpired):
            prepare(fixture)
    assert ops.load_state(fixture)["phase"] == "prepare_intent"
    assert (fixture / "operation/baseline.sqlite3").exists()
    with pytest.raises(ops.Refused):
        ops.verify(fixture, request(fixture, "verify"))


@pytest.mark.parametrize("suffix", ["-journal", "-wal", "-shm"])
def test_replacement_refuses_source_sidecars_without_removal(fixture, suffix):
    prepare(fixture)
    sidecar = Path(str(fixture / "input.sqlite3") + suffix)
    sidecar.write_bytes(b"fixture artifact")
    sidecar.chmod(0o600)
    original = (fixture / "input.sqlite3").read_bytes()
    with pytest.raises((ops.Refused, sqlite3.DatabaseError)):
        ops.replace_fixture(fixture, request(fixture, "replace"))
    assert sidecar.read_bytes() == b"fixture artifact"
    assert (fixture / "input.sqlite3").read_bytes() == original
    assert ops.load_state(fixture)["phase"] == "prepared"


def test_atomic_fixture_replacement_and_pre_activation_failure_plan(fixture):
    original_settings = (fixture / "settings.json").read_bytes()
    replaced(fixture)
    assert ops.load_state(fixture)["phase"] == "replaced_unstarted"
    assert ops.inventory(fixture / "input.sqlite3", ops.Budget())["version"] == "4"
    with pytest.raises(ops.Refused):
        ops.replace_fixture(fixture, request(fixture, "replace"))
    result = ops.recovery_plan(fixture, request(fixture, "recovery"))
    assert result["action"] == "pre_activation_recovery_review_required"
    assert not result["automatic_restore"]
    assert (fixture / "settings.json").read_bytes() == original_settings
    with pytest.raises(FileExistsError):
        ops.recovery_plan(fixture, request(fixture, "recovery"))


@pytest.mark.parametrize("when", ["before-rename", "after-rename"])
def test_replacement_failure_never_claims_activation_or_replays(fixture, when):
    prepare(fixture)
    real_replace = os.replace
    def fail(source, target):
        if Path(target) == fixture / "input.sqlite3":
            if when == "after-rename":
                real_replace(source, target)
            raise OSError("fixture replacement failure")
        return real_replace(source, target)
    with patch.object(ops.os, "replace", side_effect=fail):
        with pytest.raises(OSError):
            ops.replace_fixture(fixture, request(fixture, "replace"))
    assert ops.load_state(fixture)["phase"] == "replacement_intent"
    assert ops.inventory(fixture / "input.sqlite3", ops.Budget())["version"] == ("3" if when == "before-rename" else "4")
    with pytest.raises(ops.Refused):
        ops.replace_fixture(fixture, request(fixture, "replace"))
    result = ops.recovery_plan(fixture, request(fixture, "recovery"))
    assert not result["automatic_restore"]
    assert result["action"] == ("retain_legacy_manual_review" if when == "before-rename" else "retain_current_forward_repair")


def test_possible_activation_write_even_without_changed_data_is_forward_only(fixture):
    activated(fixture)
    result = ops.recovery_plan(fixture, request(fixture, "recovery"))
    assert result["action"] == "retain_current_forward_repair"
    assert not result["downgrade_permitted"]


def test_post_write_preserves_all_v4_wal_state_and_current_settings_refuses_downgrade(fixture):
    activated(fixture)
    writer = sqlite3.connect(fixture / "input.sqlite3")
    writer.create_function("public_url", 1, ops.store_module().public_url, deterministic=True)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.setconfig(sqlite3.SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE, True)
    try:
        for owner in ("new-a", "new-b"):
            writer.execute("INSERT INTO app_memory VALUES('app','collision',?,NULL,?,NULL,100,?,0)",
                           ('"value-' + owner + '"', owner, owner))
        writer.execute("INSERT INTO app_memory VALUES('global','new-global','42',NULL,NULL,NULL,100,'',0)")
        writer.execute("UPDATE tasks SET state_json=' {\"new\":true} '")
        writer.execute("INSERT INTO observations(time_ms,last_seen_ms,source,kind,title) VALUES(2,2,'manual','note','newwalneedle')")
        writer.execute("INSERT INTO authorizations VALUES('new-task','a',NULL,'[]','active',0,100)")
        writer.commit()
    finally:
        writer.close()
    assert Path(str(fixture / "input.sqlite3") + "-wal").exists()
    private_json(fixture / "settings.json", {"fixture": "latest settings", "preserve": True})
    before = ops.inventory(fixture / "input.sqlite3", ops.Budget())
    result = ops.recovery_plan(fixture, request(fixture, "recovery"))
    assert result["action"] == "retain_current_forward_repair"
    assert result["compatibility"] == "blocked_duplicate_keys"
    assert result["v3_duplicate_keys"] >= 1
    assert not result["automatic_restore"] and not result["downgrade_permitted"]
    assert result["authoritative"] == before
    assert ops.inventory(fixture / "input.sqlite3", ops.Budget()) == before
    assert ops.inventory(fixture / "operation/recovery/authoritative.sqlite3", ops.Budget()) == before
    assert "current.sqlite3-wal" in result["raw_sha256"]
    assert (fixture / "operation/recovery/settings-current.json").read_bytes() == (fixture / "settings.json").read_bytes()
    assert not (fixture / "operation/lossless-v3.sqlite3").exists()


def test_corrupt_recovery_retains_raw_evidence_never_restores_baseline(fixture):
    activated(fixture)
    original = b"broken activated fixture" * 100
    (fixture / "input.sqlite3").write_bytes(original)
    with pytest.raises(sqlite3.DatabaseError):
        ops.recovery_plan(fixture, request(fixture, "recovery"))
    assert (fixture / "input.sqlite3").read_bytes() == original
    assert (fixture / "operation/recovery/raw/current.sqlite3").read_bytes() == original
    assert not (fixture / "operation/recovery/plan.json").exists()


def test_cli_requires_explicit_fixture_and_has_no_production_option(fixture):
    private_json(fixture / "request.json", request(fixture, "prepare"))
    run = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "prepare", str(fixture)],
                         env={"PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, text=True, timeout=20)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["fixture_only"] is True
    run = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "production", str(fixture)],
                         env={"PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, text=True, timeout=5)
    assert run.returncode != 0


@pytest.mark.parametrize("name", ["baseline.sqlite3", "migration-backup.sqlite3"])
def test_verify_rechecks_backup_inventory_not_only_hash(fixture, name):
    prepare(fixture)
    db = sqlite3.connect(fixture / "operation" / name)
    db.execute("UPDATE tasks SET goal='backup tamper'")
    db.commit()
    db.close()
    record = ops.load_state(fixture)
    record["artifacts"][name] = ops.digest(fixture / "operation" / name)
    ops.state(fixture, record)
    with pytest.raises(ops.Refused, match="inventory drift"):
        ops.verify(fixture, request(fixture, "verify"))


def test_state_cannot_inject_external_artifact_paths(fixture, tmp_path):
    prepare(fixture)
    unrelated = tmp_path / "must-not-open"
    unrelated.write_bytes(b"not a fixture artifact")
    unrelated.chmod(0o600)
    record = ops.load_state(fixture)
    record["artifacts"] = {str(unrelated): "0" * 64}
    ops.state(fixture, record)
    with patch.object(ops, "digest", wraps=ops.digest) as digest:
        with pytest.raises(ops.Refused, match="artifact map"):
            ops.verify(fixture, request(fixture, "verify"))
        assert all(call.args[0] != unrelated for call in digest.call_args_list)
    assert unrelated.read_bytes() == b"not a fixture artifact"


@pytest.mark.parametrize("suffix", ["-journal", "-wal", "-shm"])
def test_prepared_artifact_sidecars_are_refused(fixture, suffix):
    prepare(fixture)
    sidecar = fixture / ("operation/candidate.sqlite3" + suffix)
    sidecar.write_bytes(b"fixture sidecar")
    sidecar.chmod(0o600)
    with pytest.raises(ops.Refused, match="sidecars"):
        ops.verify(fixture, request(fixture, "verify"))
    assert sidecar.read_bytes() == b"fixture sidecar"


def test_legacy_late_write_recovery_preserves_latest_not_preparation_baseline(fixture):
    prepare(fixture)
    db = sqlite3.connect(fixture / "input.sqlite3")
    db.execute("UPDATE tasks SET goal='keep late legacy task'")
    db.commit()
    db.close()
    before = ops.inventory(fixture / "input.sqlite3", ops.Budget())
    result = ops.recovery_plan(fixture, request(fixture, "recovery"))
    assert result["action"] == "retain_legacy_manual_review"
    assert not result["automatic_restore"]
    assert result["authoritative"] == before
    assert before != ops.load_state(fixture)["baseline"]


def test_readonly_setup_failure_closes_sqlite_connection(fixture):
    real_connect = sqlite3.connect
    opened = []
    def connect(*args, **kwargs):
        db = real_connect(*args, **kwargs)
        opened.append(db)
        return db
    with patch.object(ops.sqlite3, "connect", side_effect=connect), patch.object(
            ops, "store_module", side_effect=ops.Refused("fixture origin failure")):
        with pytest.raises(ops.Refused):
            ops.readonly(fixture / "input.sqlite3", ops.Budget())
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")


def test_recovery_detects_fixture_changes_during_preservation(fixture):
    activated(fixture)
    snapshot = ops.snapshot
    def late_change(source, destination, budget):
        snapshot(source, destination, budget)
        if destination.name == "authoritative.sqlite3":
            db = sqlite3.connect(source)
            db.execute("UPDATE tasks SET goal='changed during preservation'")
            db.commit()
            db.close()
    with patch.object(ops, "snapshot", side_effect=late_change):
        with pytest.raises(ops.Refused, match="changed during preservation"):
            ops.recovery_plan(fixture, request(fixture, "recovery"))
    assert not (fixture / "operation/recovery/plan.json").exists()
    assert (fixture / "operation/recovery/raw/current.sqlite3").exists()
    db = sqlite3.connect(fixture / "input.sqlite3")
    try:
        assert db.execute("SELECT goal FROM tasks").fetchone()[0] == "changed during preservation"
    finally:
        db.close()


def test_prepare_consumes_committed_wal_and_late_wal_write_fences_replacement(fixture):
    path = fixture / "input.sqlite3"
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.setconfig(sqlite3.SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE, True)
    db.execute("UPDATE tasks SET goal='committed baseline WAL'")
    db.commit()
    db.close()
    record = prepare(fixture)
    assert record["baseline_family"]["-wal"] is not None
    assert record["baseline"]["tables"]["tasks"] == record["candidate"]["tables"]["tasks"]
    stale = request(fixture, "replace")
    before_main = ops.digest(path)
    db = sqlite3.connect(path)
    db.setconfig(sqlite3.SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE, True)
    db.execute("UPDATE tasks SET goal='late WAL-only change'")
    db.commit()
    db.close()
    assert ops.digest(path) == before_main
    with pytest.raises(ops.Refused, match="stale"):
        ops.replace_fixture(fixture, stale)
    with pytest.raises(ops.Refused, match="late writes"):
        ops.replace_fixture(fixture, request(fixture, "replace"))
    assert ops.load_state(fixture)["phase"] == "prepared"


def test_fsync_failure_after_atomic_rename_preserves_unknown_replacement(fixture):
    prepare(fixture)
    real_sync, real_replace = ops.fsync_directory, ops.os.replace
    renamed = False
    def replace(source, destination):
        nonlocal renamed
        real_replace(source, destination)
        if Path(destination) == fixture / "input.sqlite3":
            renamed = True
    def sync(path):
        if renamed and Path(path) == fixture:
            raise OSError("fixture directory fsync failure")
        return real_sync(path)
    with patch.object(ops.os, "replace", side_effect=replace), patch.object(ops, "fsync_directory", side_effect=sync):
        with pytest.raises(OSError, match="fsync"):
            ops.replace_fixture(fixture, request(fixture, "replace"))
    assert ops.load_state(fixture)["phase"] == "replacement_intent"
    assert ops.inventory(fixture / "input.sqlite3", ops.Budget())["version"] == "4"
    result = ops.recovery_plan(fixture, request(fixture, "recovery"))
    assert result["action"] == "retain_current_forward_repair"
    assert not result["automatic_restore"]


def test_expired_verification_budget_is_not_a_success(fixture):
    budget = ops.Budget()
    budget.end = 0
    with pytest.raises(ops.Refused, match="deadline"):
        ops.inventory(fixture / "input.sqlite3", budget)
    assert not (fixture / "operation").exists()


def test_owned_fixture_child_timeout_kills_and_waits(fixture):
    real_run = subprocess.run
    pidfile = fixture / "owned-child.pid"
    code = "import os,pathlib,time; p=pathlib.Path(__import__('sys').argv[1]); p.write_text(str(os.getpid())); p.chmod(0o600); time.sleep(60)"
    def run(command, *args, **kwargs):
        if "_migrate-child" in command:
            command = [sys.executable, "-c", code, str(pidfile)]
            kwargs["timeout"] = 0.3
        return real_run(command, *args, **kwargs)
    with patch.object(ops.subprocess, "run", side_effect=run):
        with pytest.raises(subprocess.TimeoutExpired):
            prepare(fixture)
    assert pidfile.exists()
    assert not Path("/proc", pidfile.read_text()).exists()
    assert ops.load_state(fixture)["phase"] == "prepare_intent"
