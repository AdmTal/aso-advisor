"""State: the lifecycle of the suggestions and the history of the live data.

The database makes the advisor consistent. Every suggestion has a stable
fingerprint. Each run compares the new suggestions with the stored ones, so the
tool can tell you:

- which suggestions are NEW;
- which are STILL OPEN;
- which your last metadata push RESOLVED;
- which you DISMISSED, so that they stay quiet.

The file is SQLite. It holds no credentials. You can delete it. The next run
makes a new one, and all suggestions become new again.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             TEXT NOT NULL,
    version        TEXT NOT NULL,
    open_count     INTEGER DEFAULT 0,
    new_count      INTEGER DEFAULT 0,
    resolved_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS suggestions (
    fid          TEXT PRIMARY KEY,
    rule         TEXT NOT NULL,
    scope        TEXT NOT NULL,
    severity     TEXT NOT NULL,
    title        TEXT NOT NULL,
    detail       TEXT DEFAULT '',
    fix          TEXT DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'open',   -- open | dismissed | resolved
    note         TEXT DEFAULT '',
    first_seen   INTEGER NOT NULL,
    last_seen    INTEGER NOT NULL,
    resolved_run INTEGER
);
CREATE TABLE IF NOT EXISTS snapshots (
    run_id  INTEGER NOT NULL,
    version TEXT NOT NULL,
    locale  TEXT NOT NULL,
    field   TEXT NOT NULL,
    value   TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS api_cache (
    url  TEXT PRIMARY KEY,
    ts   TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rank_checks (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       TEXT NOT NULL,
    term     TEXT NOT NULL,
    country  TEXT NOT NULL,
    rank     INTEGER,            -- NULL means: not in the results that were read
    scanned  INTEGER NOT NULL,
    top_apps TEXT DEFAULT ''     -- json [[track_id, name], ...] of the first three
);
CREATE TABLE IF NOT EXISTS competitor_snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    track_id     INTEGER NOT NULL,
    country      TEXT NOT NULL,
    name         TEXT DEFAULT '',
    version      TEXT DEFAULT '',
    released     TEXT DEFAULT '',
    rating       REAL,
    rating_count INTEGER,
    price        REAL,
    desc_hash    TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_rank_term ON rank_checks (term, country, id);
CREATE INDEX IF NOT EXISTS idx_comp_track ON competitor_snapshots (track_id, country, id);
"""

TS_FORMAT = '%Y-%m-%d %H:%M:%SZ'


def _now():
    return datetime.now(timezone.utc).strftime(TS_FORMAT)


def connect(path):
    """Open the database and make the schema if it is missing."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def connect_memory():
    """An in-memory database, for a run that must not write state."""
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


# -- suggestions --------------------------------------------------------------

def start_run(conn, version):
    cur = conn.execute('INSERT INTO runs (ts, version) VALUES (?, ?)', (_now(), version))
    conn.commit()
    return cur.lastrowid


def reconcile(conn, run_id, suggestions):
    """Store the suggestions of this run and resolve the ones that are gone.

    The function sets `.is_new`, `.regressed`, and `.status` on each
    suggestion.
    """
    emitted = {s.fid for s in suggestions}
    new = regressed = 0

    for s in suggestions:
        row = conn.execute('SELECT * FROM suggestions WHERE fid = ?', (s.fid,)).fetchone()
        if row is None:
            conn.execute(
                'INSERT INTO suggestions (fid, rule, scope, severity, title, detail, fix, '
                'status, first_seen, last_seen) VALUES (?,?,?,?,?,?,?,?,?,?)',
                (s.fid, s.rule, s.scope, s.severity, s.title, s.detail, s.fix,
                 'open', run_id, run_id))
            s.is_new, s.status = True, 'open'
            new += 1
        else:
            status = row['status']
            if status == 'resolved':          # The problem came back.
                status = 'open'
                s.regressed = True
                regressed += 1
            conn.execute(
                'UPDATE suggestions SET title=?, detail=?, fix=?, severity=?, '
                'last_seen=?, status=?, resolved_run=NULL WHERE fid=?',
                (s.title, s.detail, s.fix, s.severity, run_id, status, s.fid))
            s.status = status

    rows = conn.execute(
        "SELECT fid, title FROM suggestions WHERE status = 'open' AND last_seen < ?",
        (run_id,)).fetchall()
    resolved = [r for r in rows if r['fid'] not in emitted]
    for r in resolved:
        conn.execute("UPDATE suggestions SET status='resolved', resolved_run=? WHERE fid=?",
                     (run_id, r['fid']))

    open_count = sum(1 for s in suggestions if s.status == 'open')
    conn.execute('UPDATE runs SET open_count=?, new_count=?, resolved_count=? WHERE id=?',
                 (open_count, new, len(resolved), run_id))
    conn.commit()
    return {'new': new, 'regressed': regressed,
            'resolved': [dict(r) for r in resolved], 'open': open_count}


def save_snapshots(conn, run_id, version, locales):
    rows = []
    for meta in locales.values():
        for fld in ('name', 'subtitle', 'keywords'):
            rows.append((run_id, version, meta.code, fld, getattr(meta, fld)))
    conn.executemany('INSERT INTO snapshots (run_id, version, locale, field, value) '
                     'VALUES (?,?,?,?,?)', rows)
    conn.commit()


def set_status(conn, fid, status, note=''):
    cur = conn.execute('UPDATE suggestions SET status=?, note=? WHERE fid=?',
                       (status, note, fid))
    conn.commit()
    return cur.rowcount > 0


def get_suggestion(conn, fid):
    return conn.execute('SELECT * FROM suggestions WHERE fid=?', (fid,)).fetchone()


def list_suggestions(conn, status='open'):
    order = ("CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 "
             "WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 3 ELSE 4 END, scope")
    if status == 'all':
        return conn.execute(f'SELECT * FROM suggestions ORDER BY status, {order}').fetchall()
    return conn.execute(
        f'SELECT * FROM suggestions WHERE status=? ORDER BY {order}', (status,)).fetchall()


def run_history(conn, limit=20):
    return conn.execute('SELECT * FROM runs ORDER BY id DESC LIMIT ?', (limit,)).fetchall()


# -- live data ----------------------------------------------------------------

def cache_get(conn, url, ttl_hours):
    row = conn.execute('SELECT ts, body FROM api_cache WHERE url=?', (url,)).fetchone()
    if row is None:
        return None
    age = datetime.now(timezone.utc) - datetime.strptime(
        row['ts'], TS_FORMAT).replace(tzinfo=timezone.utc)
    if age.total_seconds() > ttl_hours * 3600:
        return None
    return row['body']


def cache_put(conn, url, body):
    conn.execute('INSERT OR REPLACE INTO api_cache (url, ts, body) VALUES (?,?,?)',
                 (url, _now(), body))
    conn.commit()


def cache_clear(conn):
    cur = conn.execute('DELETE FROM api_cache')
    conn.commit()
    return cur.rowcount


def record_rank(conn, term, country, rank, scanned, top_apps):
    conn.execute(
        'INSERT INTO rank_checks (ts, term, country, rank, scanned, top_apps) '
        'VALUES (?,?,?,?,?,?)',
        (_now(), term, country, rank, scanned, json.dumps(top_apps)))
    conn.commit()


def previous_rank(conn, term, country, before_id=None):
    """The rank recorded before `before_id` for (term, country).

    The comparison uses the row identifier, not the timestamp. Two checks in
    the same second are common, and a timestamp cannot separate them.
    """
    query = 'SELECT rank, ts FROM rank_checks WHERE term=? AND country=?'
    args = [term, country]
    if before_id is not None:
        query += ' AND id < ?'
        args.append(before_id)
    row = conn.execute(query + ' ORDER BY id DESC LIMIT 1', args).fetchone()
    return (row['rank'], row['ts']) if row else (None, None)


def rank_summary(conn, limit_terms=40):
    """The last rank per (term, country), with the rank before it."""
    rows = conn.execute("""
        SELECT id, term, country, rank, ts FROM rank_checks
        WHERE id IN (SELECT MAX(id) FROM rank_checks GROUP BY term, country)
        ORDER BY country, CASE WHEN rank IS NULL THEN 999 ELSE rank END
        LIMIT ?""", (limit_terms,)).fetchall()
    out = []
    for r in rows:
        prev, prev_ts = previous_rank(conn, r['term'], r['country'], r['id'])
        out.append({'term': r['term'], 'country': r['country'], 'rank': r['rank'],
                    'ts': r['ts'], 'prev': prev, 'prev_ts': prev_ts})
    return out


def record_competitor(conn, snap):
    conn.execute(
        'INSERT INTO competitor_snapshots '
        '(ts, track_id, country, name, version, released, rating, rating_count, price, '
        'desc_hash) VALUES (?,?,?,?,?,?,?,?,?,?)',
        (_now(), snap['track_id'], snap['country'], snap['name'], snap['version'],
         snap['released'], snap['rating'], snap['rating_count'], snap['price'],
         snap['desc_hash']))
    conn.commit()


def previous_competitor(conn, track_id, country, before_id):
    return conn.execute(
        'SELECT * FROM competitor_snapshots WHERE track_id=? AND country=? AND id < ? '
        'ORDER BY id DESC LIMIT 1', (track_id, country, before_id)).fetchone()


def last_competitor_id(conn):
    row = conn.execute('SELECT MAX(id) AS m FROM competitor_snapshots').fetchone()
    return row['m'] or 0
