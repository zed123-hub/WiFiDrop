"""Durable device identities and room messages in the host's data directory."""
from contextlib import closing
import sqlite3


class RoomHistory:
    def __init__(self, path):
        self.path = path
        with closing(self.connect()) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS devices (
                    token_hash TEXT PRIMARY KEY, id TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL, kind TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    seq INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE,
                    owner TEXT NOT NULL, sender TEXT NOT NULL, target TEXT NOT NULL,
                    targetName TEXT NOT NULL, text TEXT NOT NULL, created REAL NOT NULL,
                    clientId TEXT, UNIQUE(owner, clientId)
                );
                CREATE INDEX IF NOT EXISTS messages_by_owner ON messages(owner, seq);
                CREATE INDEX IF NOT EXISTS messages_by_target ON messages(target, seq);
            """)

    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def devices(self):
        with closing(self.connect()) as db:
            return {
                row["token_hash"]: {"id": row["id"], "name": row["name"], "kind": row["kind"],
                                    "seen": 0.0, "admin": False}
                for row in db.execute("SELECT * FROM devices")
            }

    def add_device(self, token_hash, device):
        with closing(self.connect()) as db, db:
            db.execute("INSERT INTO devices(token_hash,id,name,kind) VALUES(?,?,?,?)",
                       (token_hash, device["id"], device["name"], device["kind"]))

    def remove_device(self, device_id):
        with closing(self.connect()) as db, db:
            db.execute("DELETE FROM devices WHERE id=?", (device_id,))

    def append(self, message, client_id):
        with closing(self.connect()) as db, db:
            cursor = db.execute("""
                INSERT INTO messages(id,owner,sender,target,targetName,text,created,clientId)
                VALUES(:id,:owner,:sender,:target,:targetName,:text,:created,:clientId)
                ON CONFLICT(owner,clientId) DO NOTHING
            """, {**message, "clientId": client_id})
            if cursor.rowcount == 1:
                return message, True
            row = db.execute("""
                SELECT id,owner,sender,target,targetName,text,created FROM messages
                WHERE owner=? AND clientId=?
            """, (message["owner"], client_id)).fetchone()
            return dict(row), False

    def recent_messages(self, device_id):
        with closing(self.connect()) as db:
            rows = db.execute("""
                SELECT id,owner,sender,target,targetName,text,created FROM messages
                WHERE owner=? OR target IN ('all', ?) ORDER BY seq DESC LIMIT 200
            """, (device_id, device_id)).fetchall()
            return [dict(row) for row in reversed(rows)]
