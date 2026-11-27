"""近传 / WiFiDrop: a dependency-free, local-network file transfer application."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlsplit
import uuid
import webbrowser

from vendor.qrcodegen import QrCode
from room_history import RoomHistory
from lan_network import is_lan, local_networks

VERSION = "2.0.0"
CHUNK_SIZE = 4 * 1024 * 1024
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
STATIC_FILES = {"/": ("index.html", "text/html; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/style.css": ("style.css", "text/css; charset=utf-8"),
                "/motion.css": ("motion.css", "text/css; charset=utf-8"),
                "/motion.js": ("motion.js", "text/javascript; charset=utf-8"),
                "/moments/moments.js": ("moments/moments.js", "text/javascript; charset=utf-8"),
                "/moments/lib.js": ("moments/lib.js", "text/javascript; charset=utf-8"),
                "/moments/liquid-type/moment.js": ("moments/liquid-type/moment.js", "text/javascript; charset=utf-8"),
                "/moments/liquid-type/moment.css": ("moments/liquid-type/moment.css", "text/css; charset=utf-8"),
                "/icon.svg": ("icon.svg", "image/svg+xml")}


def safe_filename(name: str) -> str:
    name = str(name).replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", name).strip(" .")
    if not name or name in (".", ".."):
        name = "未命名文件"
    if name.split(".")[0].rstrip(" .").upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        name = "_" + name
    # Leave space for collision suffixes on both Windows and macOS filesystems.
    while len(name.encode("utf-8")) > 180:
        stem, ext = os.path.splitext(name)
        if len(ext.encode("utf-8")) > 30:
            name = name[:-1]
        else:
            name = stem[:-1] + ext
    return name


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


class Room:
    def __init__(self, directory: Path, addresses=None, networks=None):
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.meta_dir = self.directory / ".wifidrop"
        self.meta_dir.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.records: dict[str, dict] = {}
        self.upload_locks: dict[str, threading.Lock] = {}
        self.admin_token = secrets.token_urlsafe(32)
        self.invite_token = secrets.token_urlsafe(24)
        self.pair_code = f"{secrets.randbelow(1000000):06d}"
        self.invites_enabled = True
        self.started = time.time()
        self.instance = secrets.token_hex(8)
        self.networks = local_networks() if networks is None and addresses is None else networks or {}
        self.addresses = list(self.networks if addresses is None else addresses)
        self.port = 0
        self.history = RoomHistory(self.meta_dir / "room.sqlite3")
        self.devices = self.history.devices()
        self.failures: dict[str, list[float]] = {}
        self.tickets: dict[str, tuple[str, str, float]] = {}
        self.admin = {"id": "host", "name": socket.gethostname(), "kind": "computer", "admin": True}
        self._load()

    def _load(self):
        for path in self.meta_dir.glob("*.json"):
            try:
                rec = json.loads(path.read_text(encoding="utf-8"))
                if not re.fullmatch(r"[a-f0-9]{32}", rec["id"]) or path.stem != rec["id"]:
                    continue
                if not isinstance(rec["size"], int) or rec["size"] < 0:
                    continue
                if rec.get("complete"):
                    saved = self.directory / rec["saved_name"]
                    if saved.parent.resolve() != self.directory or saved.is_symlink() or not saved.is_file():
                        continue
                elif not self.part_path(rec["id"]).exists():
                    continue
                self.records[rec["id"]] = rec
            except (OSError, ValueError, KeyError, TypeError):
                continue

    def part_path(self, file_id):
        return self.meta_dir / (file_id + ".part")

    def save(self, rec):
        temp = self.meta_dir / (rec["id"] + ".tmp")
        temp.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, temp.with_suffix(".json"))

    def invite_urls(self):
        return [f"http://{address}:{self.port}/#join={self.invite_token}" for address in self.addresses]

    def visible(self, rec, device):
        return rec["owner"] == device["id"] or (rec.get("complete") and rec["target"] in ("all", device["id"]))

    def target_name(self, target):
        if target == "host":
            return self.admin["name"]
        if target == "all":
            return "整个房间"
        return next((d["name"] for d in self.devices.values() if d["id"] == target), None)

    def recipient(self, target, sender):
        if not isinstance(target, str) or target == sender["id"]:
            raise ApiError(400, "请选择其他设备或整个房间。")
        name = self.target_name(target)
        if name is None:
            raise ApiError(400, "设备已被移除，请重新选择接收方。")
        return name

    def public_record(self, rec):
        result = {k: rec.get(k) for k in ("id", "name", "size", "owner", "sender", "target", "created", "complete", "sha256", "saved_name")}
        result["targetName"] = rec.get("targetName") or self.target_name(rec["target"]) or "已移除的设备"
        if not rec.get("complete"):
            result["offset"] = self.part_path(rec["id"]).stat().st_size
        return result

    def authenticate(self, token, is_local):
        if not token.isascii():
            raise ApiError(401, "连接凭证无效，请重新配对。")
        if is_local and hmac.compare_digest(token, self.admin_token):
            return self.admin
        with self.lock:
            device = self.devices.get(hashlib.sha256(token.encode()).hexdigest())
            if device:
                device["seen"] = time.time()
                return device.copy()
        raise ApiError(401, "连接已失效，请重新扫码连接。")

    def snapshot(self, device):
        with self.lock:
            files = [self.public_record(r) for r in self.records.values() if self.visible(r, device) and r.get("complete")]
            result = {"version": VERSION, "instance": self.instance, "me": device,
                      "host": self.admin["name"], "files": sorted(files, key=lambda r: r["created"], reverse=True),
                      "devices": [{k: d[k] for k in ("id", "name", "kind", "seen")} for d in self.devices.values()],
                      "messages": self.history.recent_messages(device["id"]),
                      "chunkSize": CHUNK_SIZE, "invitesEnabled": self.invites_enabled}
            if device["admin"]:
                result.update(urls=self.invite_urls(), code=self.pair_code, directory=str(self.directory),
                              freeBytes=shutil.disk_usage(self.directory).free)
            return result


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64

    def __init__(self, address, room):
        self.room = room
        # Prevent an unbounded number of threads from an accidental connection storm.
        self.slots = threading.BoundedSemaphore(48)
        super().__init__(address, Handler)
        room.port = self.server_port

    def verify_request(self, request, client_address):
        source = ipaddress.IPv4Address(client_address[0])
        destination = request.getsockname()[0]
        if ipaddress.IPv4Address(destination).is_loopback:
            return source.is_loopback
        subnet = self.room.networks.get(destination)
        return subnet is not None and is_lan(source) and source in subnet

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "WiFiDrop"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    @property
    def room(self):
        return self.server.room

    @property
    def is_local(self):
        return ipaddress.ip_address(self.client_address[0]).is_loopback

    def setup(self):
        super().setup()
        self.connection.settimeout(90)

    def log_message(self, *args):
        # URLs can contain one-use download credentials. Never log them.
        pass

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        super().end_headers()

    def reply(self, status, body=b"", content_type="application/json; charset=utf-8", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        super_close = self.command not in ("GET", "HEAD")
        if super_close:
            # Never leave unread request bytes on a reusable connection after errors.
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def validate_request(self):
        host = self.headers.get("Host", "")
        allowed = {f"{a}:{self.room.port}" for a in self.room.addresses}
        allowed.update({f"127.0.0.1:{self.room.port}", f"localhost:{self.room.port}"})
        if host not in allowed:
            raise ApiError(403, "请使用应用显示的局域网地址。")
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{host}":
            raise ApiError(403, "不允许跨站访问。")
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise ApiError(403, "不允许跨站访问。")

    def json_body(self, limit=16 * 1024):
        length = self.body_length(limit)
        try:
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError()
            return body
        except (ValueError, UnicodeError):
            raise ApiError(400, "请求内容不正确。")

    def body_length(self, limit):
        if self.headers.get("Transfer-Encoding"):
            raise ApiError(400, "请提供明确的文件长度。")
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        if length < 0 or length > limit:
            raise ApiError(413, "本次传输块过大或长度不正确。")
        return length

    def device(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise ApiError(401, "请先连接这台电脑。")
        return self.room.authenticate(auth[7:], self.is_local)

    def admin(self):
        device = self.device()
        if not device["admin"]:
            raise ApiError(403, "此操作只能在电脑端进行。")
        return device

    def dispatch(self):
        try:
            self.validate_request()
            self.route()
        except ApiError as error:
            self.reply(error.status, {"error": error.message})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        except OSError as error:
            if error.errno == 28 or getattr(error, "winerror", None) == 112:
                self.reply(507, {"error": "电脑磁盘空间不足，请清理后继续。"})
            else:
                self.reply(500, {"error": "文件读写失败，请检查文件是否被移动或占用。"})
        except Exception:
            self.reply(500, {"error": "操作失败，请重试。"})

    do_GET = do_HEAD = do_POST = do_PUT = do_DELETE = dispatch

    def route(self):
        parsed = urlsplit(self.path)
        path = parsed.path
        method = self.command
        if method in ("GET", "HEAD") and path in STATIC_FILES:
            name, mime = STATIC_FILES[path]
            return self.reply(200, (RESOURCE_DIR / "web" / name).read_bytes(), mime)
        if method == "GET" and path == "/api/info":
            return self.reply(200, {"name": "近传", "host": self.room.admin["name"], "version": VERSION, "invitesEnabled": self.room.invites_enabled})
        if method == "POST" and path == "/api/join":
            return self.join()
        if method == "GET" and path == "/api/state":
            return self.reply(200, self.room.snapshot(self.device()))
        if method == "POST" and path == "/api/messages":
            return self.send_message()
        if method == "GET" and path == "/api/qr":
            self.admin()
            try:
                index = int(parse_qs(parsed.query).get("index", ["0"])[0])
                url = self.room.invite_urls()[index]
                if index < 0:
                    raise IndexError()
            except (ValueError, IndexError):
                raise ApiError(404, "没有可用的局域网地址，请先连接 Wi-Fi。")
            qr = QrCode.encode_text(url, QrCode.Ecc.MEDIUM)
            border = 4
            size = qr.get_size()
            squares = " ".join(f"M{x+border},{y+border}h1v1h-1z" for y in range(size) for x in range(size) if qr.get_module(x, y))
            svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size+8} {size+8}" shape-rendering="crispEdges"><rect width="100%" height="100%" fill="white"/><path d="{squares}" fill="#123b34"/></svg>'
            return self.reply(200, svg, "image/svg+xml")
        if method == "POST" and path == "/api/uploads":
            return self.create_upload()
        match = re.fullmatch(r"/api/uploads/([a-f0-9]{32})(/complete)?", path)
        if match:
            file_id, complete = match.groups()
            if method == "PUT" and not complete:
                return self.upload_chunk(file_id)
            if method == "POST" and complete:
                return self.complete_upload(file_id)
            if method == "DELETE" and not complete:
                return self.delete_file(file_id, partial_only=True)
        match = re.fullmatch(r"/api/files/([a-f0-9]{32})(/ticket)?", path)
        if match:
            file_id, ticket = match.groups()
            if method == "DELETE" and not ticket:
                return self.delete_file(file_id)
            if method == "POST" and ticket:
                return self.download_ticket(file_id)
        match = re.fullmatch(r"/download/([a-f0-9]{32})", path)
        if match and method in ("GET", "HEAD"):
            return self.download(match[1], parse_qs(parsed.query).get("ticket", [""])[0])
        match = re.fullmatch(r"/api/devices/([a-f0-9]{16})", path)
        if match and method == "DELETE":
            self.admin()
            with self.room.lock:
                self.room.history.remove_device(match[1])
                for token, device in list(self.room.devices.items()):
                    if device["id"] == match[1]:
                        del self.room.devices[token]
            return self.reply(200, {"ok": True})
        if method == "POST" and path == "/api/invites":
            self.admin()
            body = self.json_body()
            with self.room.lock:
                self.room.invites_enabled = bool(body.get("enabled", True))
                if body.get("rotate"):
                    self.room.invite_token = secrets.token_urlsafe(24)
                    self.room.pair_code = f"{secrets.randbelow(1000000):06d}"
            return self.reply(200, {"ok": True})
        if method == "POST" and path == "/api/open-folder":
            self.admin()
            if sys.platform == "win32":
                os.startfile(str(self.room.directory))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self.room.directory)])
            else:
                subprocess.Popen(["xdg-open", str(self.room.directory)])
            return self.reply(200, {"ok": True})
        if method == "POST" and path == "/api/shutdown":
            self.admin()
            self.reply(200, {"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        raise ApiError(404, "内容不存在。")

    def join(self):
        body = self.json_body()
        now = time.time()
        with self.room.lock:
            if not self.room.invites_enabled:
                raise ApiError(403, "电脑已暂停新设备连接。")
            # Bound both per-client guesses and aggregate memory use.
            self.room.failures = {ip: [t for t in times if now - t < 60] for ip, times in self.room.failures.items() if any(now - t < 60 for t in times)}
            attempts = self.room.failures.setdefault(self.client_address[0], [])
            if len(attempts) >= 5 or sum(map(len, self.room.failures.values())) >= 100:
                raise ApiError(429, "尝试次数过多，请一分钟后再试。")
            invite, code = str(body.get("invite", "")), str(body.get("code", ""))
            if not (hmac.compare_digest(invite.encode(), self.room.invite_token.encode()) or hmac.compare_digest(code.encode(), self.room.pair_code.encode())):
                attempts.append(now)
                raise ApiError(403, "连接码不正确，请查看电脑上的六位连接码。")
            if len(self.room.devices) >= 32:
                raise ApiError(429, "已连接设备过多，请在电脑端移除不用的设备。")
            name = re.sub(r"[\x00-\x1f]", "", str(body.get("name", "新设备")))[:40].strip() or "新设备"
            kind = body.get("kind", "phone")
            if kind not in ("phone", "computer", "tablet"):
                kind = "phone"
            token = secrets.token_urlsafe(32)
            device = {"id": secrets.token_hex(8), "name": name, "kind": kind, "seen": now, "admin": False}
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            self.room.history.add_device(token_hash, device)
            self.room.devices[token_hash] = device
        self.reply(200, {"token": token, "me": device})

    def send_message(self):
        body = self.json_body(64 * 1024)
        text, target, client_id = body.get("text"), body.get("target"), body.get("clientId")
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ApiError(400, "请输入 1 到 4000 个字符的消息。")
        if client_id is not None and (not isinstance(client_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,96}", client_id)):
            raise ApiError(400, "消息标识无效，请重新发送。")
        with self.room.lock:
            device = self.device()
            target_name = self.room.recipient(target, device)
            message = {"id": uuid.uuid4().hex, "owner": device["id"], "sender": device["name"],
                       "target": target, "targetName": target_name, "text": text, "created": time.time()}
            saved, created = self.room.history.append(message, client_id)
            if saved["text"] != text or saved["target"] != target:
                raise ApiError(409, "该标识已用于另一条消息。")
        return self.reply(201 if created else 200, saved)

    def create_upload(self):
        device = self.device()
        body = self.json_body()
        name, size = body.get("name"), body.get("size")
        if not isinstance(name, str) or not name or len(name) > 1024 or type(size) is not int or size < 0 or size > 2**53 - 1:
            raise ApiError(400, "文件名或文件大小不正确。")
        target = body.get("target", "all" if device["admin"] else "host")
        with self.room.lock:
            target_name = self.room.recipient(target, device)
            resume_id = str(body.get("resumeId", ""))
            rec = self.room.records.get(resume_id)
            if rec:
                secret = hashlib.sha256(str(body.get("resumeSecret", "")).encode()).hexdigest()
                if not hmac.compare_digest(secret, rec["secret_hash"]):
                    raise ApiError(403, "无法继续这个传输，请重新发送文件。")
                if rec["name"] != name or rec["size"] != size or rec.get("fingerprint") != str(body.get("fingerprint", "")):
                    raise ApiError(409, "文件已经改变，请重新选择原文件。")
                if rec["target"] != target:
                    raise ApiError(409, "续传时请选择原来的接收方。")
                if rec.get("complete"):
                    return self.reply(200, {"id": rec["id"], "offset": size, "complete": True})
                # A new pairing after restart may reclaim only with the resume secret.
                rec.update(owner=device["id"], sender=device["name"], targetName=target_name)
                self.room.save(rec)
                return self.reply(200, {"id": rec["id"], "offset": self.room.part_path(rec["id"]).stat().st_size, "complete": False})
            if size > shutil.disk_usage(self.room.directory).free - 16 * 1024 * 1024:
                raise ApiError(507, "电脑磁盘空间不足，无法接收这个文件。")
            if len([r for r in self.room.records.values() if not r.get("complete")]) >= 128:
                raise ApiError(429, "未完成的传输过多，请先清理或完成已有传输。")
            file_id, secret = uuid.uuid4().hex, secrets.token_urlsafe(32)
            rec = {"id": file_id, "name": name, "size": size, "owner": device["id"], "sender": device["name"],
                   "target": target, "targetName": target_name, "created": time.time(), "complete": False,
                   "fingerprint": str(body.get("fingerprint", ""))[:256],
                   "secret_hash": hashlib.sha256(secret.encode()).hexdigest()}
            self.room.part_path(file_id).touch(exist_ok=False)
            self.room.save(rec)
            self.room.records[file_id] = rec
        self.reply(201, {"id": file_id, "offset": 0, "complete": False, "resumeSecret": secret})

    def owned_record(self, file_id, device, partial_only=False):
        with self.room.lock:
            rec = self.room.records.get(file_id)
            if rec is None:
                raise ApiError(404, "传输记录不存在，请重新发送。")
            if rec["owner"] != device["id"] and not (device["admin"] and self.room.visible(rec, device)):
                raise ApiError(403, "不能修改其他设备的文件。")
            if partial_only and rec.get("complete"):
                raise ApiError(409, "文件已完成传输。")
            lock = self.room.upload_locks.setdefault(file_id, threading.Lock())
            return rec, lock

    def upload_chunk(self, file_id):
        device = self.device()
        rec, lock = self.owned_record(file_id, device, partial_only=True)
        length = self.body_length(CHUNK_SIZE)
        try:
            offset = int(self.headers.get("Upload-Offset", "-1"))
        except ValueError:
            raise ApiError(400, "传输位置不正确。")
        with lock:
            if rec.get("complete") or file_id not in self.room.records:
                raise ApiError(409, "传输状态已改变。")
            part = self.room.part_path(file_id)
            actual = part.stat().st_size
            if actual != offset:
                return self.reply(409, {"error": "传输位置已更新，请继续。", "offset": actual})
            if length == 0 or offset + length > rec["size"]:
                raise ApiError(400, "文件数据长度不正确。")
            try:
                with part.open("r+b") as stream:
                    stream.seek(offset)
                    remaining = length
                    while remaining:
                        block = self.rfile.read(min(256 * 1024, remaining))
                        if not block:
                            raise ApiError(400, "传输中断，可继续发送。")
                        stream.write(block)
                        remaining -= len(block)
            except BaseException:
                with part.open("r+b") as stream:
                    stream.truncate(offset)
                raise
        self.reply(200, {"offset": offset + length})

    def complete_upload(self, file_id):
        device = self.device()
        rec, lock = self.owned_record(file_id, device)
        with lock:
            if rec.get("complete"):
                return self.reply(200, self.room.public_record(rec))
            part = self.room.part_path(file_id)
            if part.stat().st_size != rec["size"]:
                raise ApiError(409, "文件还未传完，请继续发送。")
            sha = hashlib.sha256()
            with part.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    sha.update(block)
            with self.room.lock:
                name = safe_filename(rec["name"])
                stem, ext = os.path.splitext(name)
                candidate = self.room.directory / name
                number = 1
                while candidate.exists() or candidate.is_symlink():
                    candidate = self.room.directory / f"{stem} ({number}){ext}"
                    number += 1
                os.replace(part, candidate)
                rec.update(complete=True, saved_name=candidate.name, sha256=sha.hexdigest())
                self.room.save(rec)
        self.reply(200, self.room.public_record(rec))

    def delete_file(self, file_id, partial_only=False):
        device = self.device()
        rec, lock = self.owned_record(file_id, device, partial_only=partial_only)
        with lock, self.room.lock:
            if file_id not in self.room.records:
                raise ApiError(404, "文件已经移除。")
            path = self.room.directory / rec["saved_name"] if rec.get("complete") else self.room.part_path(file_id)
            path.unlink(missing_ok=True)
            (self.room.meta_dir / (file_id + ".json")).unlink(missing_ok=True)
            del self.room.records[file_id]
        self.reply(200, {"ok": True})

    def download_ticket(self, file_id):
        device = self.device()
        with self.room.lock:
            rec = self.room.records.get(file_id)
            if not rec or not rec.get("complete") or not self.room.visible(rec, device):
                raise ApiError(404, "文件不存在或不可访问。")
            now = time.time()
            self.room.tickets = {t: v for t, v in self.room.tickets.items() if v[2] > now}
            if len(self.room.tickets) >= 2048:
                raise ApiError(429, "下载请求过多，请稍后再试。")
            ticket = secrets.token_urlsafe(32)
            self.room.tickets[ticket] = (file_id, device["id"], now + 6 * 60 * 60)
        self.reply(200, {"url": f"/download/{file_id}?ticket={ticket}"})

    def download(self, file_id, ticket):
        with self.room.lock:
            permission = self.room.tickets.get(ticket)
            rec = self.room.records.get(file_id)
            if not permission or permission[0] != file_id or permission[2] < time.time():
                raise ApiError(403, "下载链接已失效，请重新点击下载。")
            if permission[1] != "host" and not any(d["id"] == permission[1] for d in self.room.devices.values()):
                raise ApiError(403, "设备连接已移除。")
            if not rec or not rec.get("complete"):
                raise ApiError(404, "文件已经移除。")
            path = self.room.directory / rec["saved_name"]
        if path.parent.resolve() != self.room.directory or path.is_symlink():
            raise ApiError(403, "文件路径不可访问。")
        # Open before sending headers, so moved or locked files produce a proper error.
        with path.open("rb") as stream:
            size = os.fstat(stream.fileno()).st_size
            start, end, status = 0, size - 1, 200
            range_header = self.headers.get("Range")
            if range_header:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
                if not match or not any(match.groups()) or size == 0:
                    return self.reply(416, {"error": "下载范围超出文件大小。"}, headers={"Content-Range": f"bytes */{size}"})
                a, b = match.groups()
                if a:
                    start = int(a)
                    end = min(int(b), size - 1) if b else size - 1
                else:
                    start, end = max(0, size - int(b)), size - 1
                if start > end or start >= size:
                    return self.reply(416, {"error": "下载范围超出文件大小。"}, headers={"Content-Range": f"bytes */{size}"})
                status = 206
            self.send_response(status)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", f"attachment; filename=\"download\"; filename*=UTF-8''{quote(rec['name'], safe='')}")
            self.send_header("Content-Length", str(max(0, end - start + 1)))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("ETag", '"' + rec["sha256"] + '"')
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if self.command == "HEAD":
                return
            stream.seek(start)
            remaining = max(0, end - start + 1)
            while remaining:
                block = stream.read(min(1024 * 1024, remaining))
                if not block:
                    break
                self.wfile.write(block)
                remaining -= len(block)


def main(argv=None):
    parser = argparse.ArgumentParser(description="近传 WiFiDrop — 局域网消息与文件互传")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--data-dir", type=Path, default=Path.home() / "Downloads" / "WiFiDrop")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port 必须在 0 到 65535 之间。")
    try:
        bind = ipaddress.IPv4Address(args.bind)
    except ValueError:
        parser.error("--bind 必须是 IPv4 地址。")
    networks = local_networks()
    if bind.is_loopback:
        if str(bind) != "127.0.0.1":
            parser.error("本机调试请使用 127.0.0.1。")
        networks = {}
    elif not bind.is_unspecified:
        parser.error("应用需要本机管理入口。请使用默认绑定，或指定 127.0.0.1 进行本机调试。")
    room = Room(args.data_dir, networks=networks)
    server = None
    for port in ([0] if args.port == 0 else range(args.port, min(args.port + 20, 65536))):
        try:
            server = Server((str(bind) if networks else "127.0.0.1", port), room)
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit("无法启动本地服务。请关闭占用端口的程序，或使用 --port 指定其他端口。")
    local_url = f"http://127.0.0.1:{room.port}/#admin={room.admin_token}"
    # Console-free executables can have stdout=None.
    if sys.stdout:
        print(f"近传 WiFiDrop {VERSION}\n电脑入口: {local_url}\n接收目录: {room.directory}\n关闭此窗口或在页面中点击「退出近传」以结束服务。", flush=True)
    if not args.no_browser:
        webbrowser.open(local_url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
