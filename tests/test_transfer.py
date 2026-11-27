"""End-to-end tests against a real HTTP server and temporary filesystem."""
import hashlib
import http.client
from ipaddress import IPv4Network
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import Mock
from uuid import uuid4

import app


class TransferTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.room = app.Room(self.directory, addresses=[])
        self.server = app.Server(('127.0.0.1', 0), self.room)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.admin = self.room.admin_token
        self.phone = self.join('测试 iPhone')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def test_lan_connections_require_the_subnet_of_the_destination_interface(self):
        self.room.networks = {'192.168.1.2': IPv4Network('192.168.1.0/24')}
        connection = Mock()
        connection.getsockname.return_value = ('192.168.1.2', 8765)
        self.assertTrue(self.server.verify_request(connection, ('192.168.1.10', 40000)))
        self.assertFalse(self.server.verify_request(connection, ('192.168.2.10', 40000)))
        self.assertFalse(self.server.verify_request(connection, ('203.0.113.10', 40000)))
        connection.getsockname.return_value = ('127.0.0.1', 8765)
        self.assertTrue(self.server.verify_request(connection, ('127.0.0.1', 40000)))
        self.assertFalse(self.server.verify_request(connection, ('192.168.1.10', 40000)))

    def request(self, method, path, body=None, token=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.room.port, timeout=5)
        request_headers = dict(headers or {})
        if token:
            request_headers['Authorization'] = 'Bearer ' + token
        if isinstance(body, dict):
            body = json.dumps(body).encode()
            request_headers['Content-Type'] = 'application/json'
        conn.request(method, path, body=body, headers=request_headers)
        response = conn.getresponse()
        data = response.read()
        response_headers = dict(response.getheaders())
        status = response.status
        conn.close()
        if response_headers.get('Content-Type', '').startswith('application/json'):
            data = json.loads(data)
        return status, data, response_headers

    def join(self, name, kind='phone'):
        status, body, _ = self.request('POST', '/api/join', {'name':name,'kind':kind,'invite':self.room.invite_token})
        self.assertEqual(status, 200)
        return body['token']

    def state(self, token):
        status, body, _ = self.request('GET', '/api/state', token=token)
        self.assertEqual(status, 200, body)
        return body

    def restart(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.room = app.Room(self.directory, addresses=[])
        self.server = app.Server(('127.0.0.1', 0), self.room)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.admin = self.room.admin_token

    def post_message(self, token, target, text, client_id=None):
        body = {'target': target, 'text': text}
        if client_id is not None:
            body['clientId'] = client_id
        status, response, _ = self.request('POST', '/api/messages', body, token)
        self.assertIn(status, (200, 201), response)

    def create(self, name, data, token=None, **extra):
        status, body, _ = self.request('POST','/api/uploads',{'name':name,'size':len(data),'fingerprint':'sample',**extra},token=token or self.phone)
        self.assertIn(status,(200,201),body)
        return body

    def upload(self, name, data, token=None, **extra):
        token = token or self.phone
        rec = self.create(name,data,token,**extra)
        offset = 0
        while offset < len(data):
            chunk = data[offset:offset+app.CHUNK_SIZE]
            status, result, _ = self.request('PUT',f"/api/uploads/{rec['id']}",chunk,token,{'Upload-Offset':str(offset)})
            self.assertEqual(status,200,result)
            offset = result['offset']
        status, completed, _ = self.request('POST',f"/api/uploads/{rec['id']}/complete",{},token)
        self.assertEqual(status,200,completed)
        return completed

    def download(self, file_id, token=None, headers=None):
        status, body, _ = self.request('POST',f'/api/files/{file_id}/ticket',{},token or self.admin)
        self.assertEqual(status,200,body)
        return self.request('GET',body['url'],headers=headers)

    def test_binary_formats_roundtrip_and_sha256(self):
        for name in ('旅行原片.MOV','视频.mkv','照片.heic','资料.pdf','无扩展名'):
            with self.subTest(name=name):
                payload = bytes(range(256)) * 1100 + b'\x00\xff\r\n'
                rec = self.upload(name,payload)
                status, content, headers = self.download(rec['id'])
                self.assertEqual((status,content),(200,payload))
                self.assertEqual(rec['sha256'],hashlib.sha256(payload).hexdigest())
                self.assertEqual((self.directory/rec['saved_name']).read_bytes(),payload)
                self.assertEqual(headers['Content-Type'],'application/octet-stream')
                self.assertIn('attachment;',headers['Content-Disposition'])

    def test_host_to_phone_and_private_phone_uploads(self):
        other = self.join('另一个手机')
        inbound = self.upload('手机私有.bin',b'private')
        shared = self.upload('电脑分享.mp4',b'host-to-phone',self.admin)
        status, state, _ = self.request('GET','/api/state',token=other)
        self.assertEqual(status,200)
        self.assertEqual([f['id'] for f in state['files']],[shared['id']])
        self.assertEqual(self.download(shared['id'],other)[1],b'host-to-phone')
        self.assertEqual(self.request('POST',f"/api/files/{inbound['id']}/ticket",{},other)[0],404)
        self.assertEqual(self.request('DELETE',f"/api/files/{inbound['id']}",token=other)[0],403)

    def test_targeted_share(self):
        other = self.join('旁观设备')
        phone_id = self.room.authenticate(self.phone,False)['id']
        rec = self.upload('定向分享.zip',b'direct',self.admin,target=phone_id)
        self.assertEqual(self.download(rec['id'],self.phone)[1],b'direct')
        self.assertEqual(self.request('POST',f"/api/files/{rec['id']}/ticket",{},other)[0],404)

    def test_four_devices_discover_each_other_and_exchange_raw_files(self):
        mac = self.join('书房 Mac', 'computer')
        android = self.join('Android 平板', 'tablet')
        members = (self.admin, self.phone, android, mac)
        expected_peers = {'书房 Mac': 'computer', 'Android 平板': 'tablet', '测试 iPhone': 'phone'}
        for token in members:
            state = self.state(token)
            self.assertEqual({d['name']: d['kind'] for d in state['devices']}, expected_peers)
            for device in state['devices']:
                self.assertNotIn('token', device)
                self.assertNotIn('resumeSecret', device)
                self.assertIn('seen', device)
            if token != self.admin:
                self.assertNotIn('code', state)
                self.assertNotIn('urls', state)

        iphone_id = self.state(self.phone)['me']['id']
        payload = bytes(range(256)) * (app.CHUNK_SIZE // 256 + 3)
        direct = self.upload('安装包.apk', payload, android, target=iphone_id)
        for token in (self.phone, android):
            files = self.state(token)['files']
            self.assertEqual([item['id'] for item in files], [direct['id']])
            self.assertEqual(files[0]['sender'], 'Android 平板')
            self.assertEqual(files[0]['targetName'], '测试 iPhone')
        self.assertEqual(self.download(direct['id'], self.phone)[1], payload)
        for outsider in (mac, self.admin):
            self.assertEqual(self.state(outsider)['files'], [])
            status, _, _ = self.request('POST', f"/api/files/{direct['id']}/ticket", {}, outsider)
            self.assertIn(status, (403, 404))

        shared = self.upload('活动日程.pdf', b'PDF bytes from a paired device', mac, target='all')
        for token in members:
            ids = {item['id'] for item in self.state(token)['files']}
            self.assertIn(shared['id'], ids)
            self.assertEqual(self.download(shared['id'], token)[1], b'PDF bytes from a paired device')

    def test_peer_messages_host_replies_and_broadcast(self):
        android = self.join('安卓手机')
        mac = self.join('笔记本', 'computer')
        android_id = self.state(android)['me']['id']
        iphone_id = self.state(self.phone)['me']['id']
        private = '下班时带上耳机 🎧\n第二行'
        reply = '收到，稍后见'
        shared = '大家都可以收到的消息'
        to_host = '主机能看到这条私信'
        from_host = '主机回复'
        client_id = str(uuid4())
        self.post_message(self.phone, android_id, private, client_id)
        self.post_message(self.phone, android_id, private, client_id)
        self.post_message(android, iphone_id, reply)
        self.post_message(mac, 'all', shared)
        self.post_message(android, 'host', to_host)
        self.post_message(self.admin, android_id, from_host)

        expected = ((self.phone, [private, reply, shared]),
                    (android, [private, reply, shared, to_host, from_host]),
                    (mac, [shared]),
                    (self.admin, [shared, to_host, from_host]))
        for token, texts in expected:
            with self.subTest(messages=texts):
                messages = self.state(token)['messages']
                self.assertEqual([message['text'] for message in messages], texts)
                self.assertEqual(len({message['id'] for message in messages}), len(texts))
        first = self.state(android)['messages'][0]
        self.assertEqual(first['owner'], iphone_id)
        self.assertEqual(first['sender'], '测试 iPhone')
        self.assertEqual(first['targetName'], '安卓手机')
        self.assertEqual(first['target'], android_id)
        self.assertEqual(self.request('POST', '/api/messages', {'target':'all','text':'no auth'})[0],401)

    def test_invalid_and_removed_recipients_cannot_receive(self):
        target = self.join('待移除设备')
        target_id = self.state(target)['me']['id']
        self.assertEqual(self.request('DELETE', '/api/devices/' + target_id, token=self.admin)[0], 200)
        for destination in (target_id, 'unknown-device'):
            with self.subTest(destination=destination):
                result = self.request('POST', '/api/messages', {'target':destination,'text':'收件人失效'}, self.phone)
                self.assertIn(result[0], (400, 404, 409))
                result = self.request('POST', '/api/uploads', {'target':destination,'name':'bin','size':1}, self.phone)
                self.assertIn(result[0], (400, 404, 409))
        result = self.request('POST', '/api/messages', {'target':'all','text':'  \n'}, self.phone)
        self.assertEqual(result[0], 400)
        self.assertEqual(self.state(self.phone)['messages'], [])
        self.assertEqual(self.request('GET', '/api/state', token=target)[0], 401)

    def test_restart_preserves_direct_delivery_for_original_identities(self):
        recipient = self.join('同名手机')
        recipient_id = self.state(recipient)['me']['id']
        self.post_message(self.phone, recipient_id, '给原来那台手机')
        rec = self.upload('原文件.bin', b'original', self.phone, target=recipient_id)
        self.restart()
        self.assertEqual(self.state(recipient)['me']['id'], recipient_id)
        self.assertEqual([m['text'] for m in self.state(recipient)['messages']], ['给原来那台手机'])
        self.assertEqual(self.download(rec['id'], recipient)[1], b'original')
        lookalike = self.join('同名手机')
        self.assertNotEqual(self.state(lookalike)['me']['id'], recipient_id)
        self.assertEqual(self.state(lookalike)['files'], [])
        self.assertEqual(self.state(lookalike)['messages'], [])
        self.assertEqual(self.request('DELETE', '/api/devices/' + recipient_id, token=self.admin)[0], 200)
        self.restart()
        self.assertEqual(self.request('GET', '/api/state', token=recipient)[0], 401)

    def test_zero_byte_duplicate_names_and_path_safety(self):
        empty = self.upload('空文件.txt',b'')
        self.assertEqual(self.download(empty['id'])[1],b'')
        first = self.upload('同名.bin',b'one')
        second = self.upload('同名.bin',b'two')
        self.assertNotEqual(first['saved_name'],second['saved_name'])
        self.assertEqual((self.directory/first['saved_name']).read_bytes(),b'one')
        escaped = self.upload('../../CON.txt',b'contained')
        self.assertEqual(escaped['saved_name'],'_CON.txt')
        self.assertEqual((self.directory/escaped['saved_name']).parent,self.directory)
        self.assertEqual(self.request('GET','/.wifidrop/')[0],404)

    def test_resume_multiple_chunks_after_restart(self):
        payload = b'abc\x00' * (app.CHUNK_SIZE // 4 + 123)
        created = self.create('大视频.mkv',payload)
        path = '/api/uploads/' + created['id']
        self.assertEqual(self.request('PUT',path,payload[:app.CHUNK_SIZE],self.phone,{'Upload-Offset':'0'})[0],200)
        self.assertEqual(self.request('PUT',path,b'x',self.phone,{'Upload-Offset':'0'})[:2],(409,{'error':'传输位置已更新，请继续。','offset':app.CHUNK_SIZE}))
        # Reload all metadata exactly as a new application process does.
        self.restart()
        self.phone = self.join('重新连接的手机')
        bad = self.request('POST','/api/uploads',{'name':'大视频.mkv','size':len(payload),'fingerprint':'sample','resumeId':created['id'],'resumeSecret':'wrong'},self.phone)
        self.assertEqual(bad[0],403)
        resumed = self.create('大视频.mkv',payload,resumeId=created['id'],resumeSecret=created['resumeSecret'])
        self.assertEqual(resumed['offset'],app.CHUNK_SIZE)
        self.assertEqual(self.request('PUT',path,payload[app.CHUNK_SIZE:],self.phone,{'Upload-Offset':str(app.CHUNK_SIZE)})[0],200)
        self.assertEqual(self.request('POST',path+'/complete',{},self.phone)[0],200)
        self.assertEqual(self.download(created['id'])[1],payload)

    def test_interrupted_chunk_rolls_back(self):
        created = self.create('中断.dat',b'x' * 1000)
        with socket.create_connection(('127.0.0.1',self.room.port)) as conn:
            request = f"PUT /api/uploads/{created['id']} HTTP/1.1\r\nHost: 127.0.0.1:{self.room.port}\r\nAuthorization: Bearer {self.phone}\r\nUpload-Offset: 0\r\nContent-Length: 1000\r\n\r\n".encode()
            conn.sendall(request+b'x'*200)
            conn.shutdown(socket.SHUT_WR)
            conn.recv(4096)
        self.assertEqual(self.room.part_path(created['id']).stat().st_size,0)
        self.assertEqual(self.request('PUT','/api/uploads/'+created['id'],b'x'*1000,self.phone,{'Upload-Offset':'0'})[0],200)

    def test_ranges_and_invalid_offsets(self):
        rec = self.upload('范围.mp4',b'0123456789')
        status, data, headers = self.download(rec['id'],headers={'Range':'bytes=2-5'})
        self.assertEqual((status,data),(206,b'2345'))
        self.assertEqual(headers['Content-Range'],'bytes 2-5/10')
        self.assertEqual(self.download(rec['id'],headers={'Range':'bytes=-3'})[:2],(206,b'789'))
        self.assertEqual(self.download(rec['id'],headers={'Range':'bytes=5-'})[:2],(206,b'56789'))
        self.assertEqual(self.download(rec['id'],headers={'Range':'bytes=99-'})[0],416)
        self.assertEqual(self.download(rec['id'],headers={'Range':'bytes=-0'})[0],416)

    def test_auth_origin_rate_limit_and_revocation(self):
        self.assertEqual(self.request('GET','/api/state')[0],401)
        self.assertEqual(self.request('POST','/api/shutdown',{},self.phone)[0],403)
        self.assertEqual(self.request('GET','/api/state',token=self.admin,headers={'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('GET','/api/state',token=self.admin,headers={'Host':'evil.example'})[0],403)
        for _ in range(5):
            self.assertEqual(self.request('POST','/api/join',{'code':'invalid'})[0],403)
        self.assertEqual(self.request('POST','/api/join',{'code':'invalid'})[0],429)
        shared = self.upload('撤销.bin',b'abc',self.admin)
        _, ticket, _ = self.request('POST',f"/api/files/{shared['id']}/ticket",{},self.phone)
        phone_id = self.room.authenticate(self.phone,False)['id']
        self.assertEqual(self.request('DELETE','/api/devices/'+phone_id,token=self.admin)[0],200)
        self.assertEqual(self.request('GET','/api/state',token=self.phone)[0],401)
        self.assertEqual(self.request('GET',ticket['url'])[0],403)

    def test_invite_rotation_pause_and_delete(self):
        old = self.room.invite_token
        self.assertEqual(self.request('POST','/api/invites',{'rotate':True},self.admin)[0],200)
        self.assertEqual(self.request('POST','/api/join',{'invite':old})[0],403)
        self.assertEqual(self.request('POST','/api/invites',{'enabled':False},self.admin)[0],200)
        self.assertEqual(self.request('POST','/api/join',{'invite':self.room.invite_token})[0],403)
        rec = self.upload('待删.bin',b'to-delete')
        self.assertEqual(self.request('DELETE',f"/api/files/{rec['id']}",token=self.admin)[0],200)
        self.assertFalse((self.directory/rec['saved_name']).exists())
        self.assertNotIn(rec['id'],self.room.records)

    def test_reject_oversized_chunk_and_early_finalize(self):
        rec = self.create('数据.bin',b'abc')
        path = '/api/uploads/' + rec['id']
        self.assertEqual(self.request('PUT',path,b'abcdef',self.phone,{'Upload-Offset':'0'})[0],400)
        self.assertEqual(self.request('POST',path+'/complete',{},self.phone)[0],409)
        self.assertEqual(self.request('DELETE',path,token=self.phone)[0],200)
        self.assertFalse(self.room.part_path(rec['id']).exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
