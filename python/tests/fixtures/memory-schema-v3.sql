-- Schema captured from fc43267173d6c1386891c708c9ddcc77724ed3f7:python/src/hyprneuro/sidecar_store.py
CREATE TABLE observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time_ms INTEGER NOT NULL,
                last_seen_ms INTEGER NOT NULL,
                source TEXT NOT NULL,
                kind TEXT NOT NULL,
                workspace TEXT,
                app_id TEXT,
                title TEXT NOT NULL DEFAULT '',
                url TEXT,
                url_verified INTEGER NOT NULL DEFAULT 0,
                message TEXT NOT NULL DEFAULT '',
                ocr_text TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                repeat_count INTEGER NOT NULL DEFAULT 1,
                event_key TEXT,
                CHECK (last_seen_ms >= time_ms)
            );
CREATE INDEX observations_time ON observations(time_ms DESC);
CREATE INDEX observations_source_time ON observations(source, time_ms DESC);
CREATE INDEX observations_key_time ON observations(event_key, time_ms DESC);
CREATE VIRTUAL TABLE observations_fts USING fts5(
                title, message, ocr_text, description, content='observations', content_rowid='id'
            );
CREATE TRIGGER observations_ai AFTER INSERT ON observations BEGIN
                INSERT INTO observations_fts(rowid,title,message,ocr_text,description)
                VALUES (new.id,new.title,new.message,new.ocr_text,new.description);
            END;
CREATE TRIGGER observations_ad AFTER DELETE ON observations BEGIN
                INSERT INTO observations_fts(observations_fts,rowid,title,message,ocr_text,description)
                VALUES('delete',old.id,old.title,old.message,old.ocr_text,old.description);
            END;
CREATE TRIGGER observations_au AFTER UPDATE ON observations BEGIN
                INSERT INTO observations_fts(observations_fts,rowid,title,message,ocr_text,description)
                VALUES('delete',old.id,old.title,old.message,old.ocr_text,old.description);
                INSERT INTO observations_fts(rowid,title,message,ocr_text,description)
                VALUES (new.id,new.title,new.message,new.ocr_text,new.description);
            END;
CREATE TABLE alert_state (
                observation_id INTEGER PRIMARY KEY REFERENCES observations(id) ON DELETE CASCADE,
                state_json TEXT NOT NULL
            );
CREATE TABLE journal_events (
                cursor TEXT PRIMARY KEY,
                observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
                event_json TEXT NOT NULL,
                phase TEXT NOT NULL DEFAULT 'evidence'
            );
CREATE TABLE notification_attempts (time_ms INTEGER NOT NULL);
CREATE TABLE sidecar_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE VIRTUAL TABLE search_fts USING fts5(title,message,ocr_text,description,app_id,url_preview,explanation);
CREATE VIRTUAL TABLE search_vocab USING fts5vocab(search_fts,'row');
CREATE TRIGGER search_ai AFTER INSERT ON observations BEGIN
                INSERT INTO search_fts(rowid,title,message,ocr_text,description,app_id,url_preview)
                VALUES(new.id,new.title,new.message,new.ocr_text,new.description,new.app_id,public_url(new.url));
            END;
CREATE TRIGGER search_ad AFTER DELETE ON observations BEGIN
                DELETE FROM search_fts WHERE rowid=old.id;
            END;
CREATE TRIGGER search_au AFTER UPDATE ON observations BEGIN
                UPDATE search_fts SET title=new.title,message=new.message,ocr_text=new.ocr_text,
                    description=new.description,app_id=new.app_id,url_preview=public_url(new.url) WHERE rowid=new.id;
            END;
CREATE TABLE app_memory (
                scope TEXT NOT NULL,
                key TEXT NOT NULL,
                value_json TEXT NOT NULL,
                task_id TEXT,
                app_id TEXT,
                project_id TEXT,
                updated_ms INTEGER NOT NULL,
                PRIMARY KEY (scope, key)
            );
CREATE INDEX app_memory_scope_time ON app_memory(scope, updated_ms DESC);
CREATE TABLE skill_manifests (
                app_id TEXT PRIMARY KEY,
                manifest_json TEXT NOT NULL
            );
CREATE TABLE tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT 'task',
                status TEXT NOT NULL DEFAULT 'active',
                state_json TEXT NOT NULL DEFAULT '{}',
                created_ms INTEGER NOT NULL,
                updated_ms INTEGER NOT NULL
            );
CREATE INDEX tasks_status_time ON tasks(status, updated_ms DESC);
CREATE TABLE authorizations (
                task_id TEXT PRIMARY KEY,
                app_id TEXT,
                file_prefix TEXT,
                ops_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                approved INTEGER NOT NULL DEFAULT 0,
                created_ms INTEGER NOT NULL
            );
INSERT INTO sidecar_meta VALUES ('schema_version','3');
INSERT INTO sidecar_meta VALUES ('search_v2','1');
