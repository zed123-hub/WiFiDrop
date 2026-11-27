"""Smoke-test the real packaged executable, including bundled UI and QR code."""
import hashlib
import http.client
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def main(executable):
    with tempfile.TemporaryDirectory() as temp:
        process = subprocess.Popen([str(executable),'--no-browser','--port','0','--data-dir',temp],
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
        try:
            url = None
            for _ in range(6):
                line = process.stdout.readline()
                match = re.search(r'http://127\.0\.0\.1:\d+/#admin=\S+',line)
                if match:
                    url = urlsplit(match.group()); break
                if process.poll() is not None:
                    raise RuntimeError('Packaged application failed to start: '+line)
            assert url,'Missing local application URL'
            token = url.fragment.split('=',1)[1]
            def request(method,path,body=None,auth=token,headers=None,host=None):
                conn = http.client.HTTPConnection(host or url.hostname,url.port,timeout=10)
                headers = dict(headers or {})
                if auth: headers['Authorization'] = 'Bearer '+auth
                if isinstance(body,dict): body=json.dumps(body).encode();headers['Content-Type']='application/json'
                conn.request(method,path,body=body,headers=headers)
                response=conn.getresponse(); data=response.read(); status=response.status
                if response.getheader('Content-Type','').startswith('application/json'): data=json.loads(data)
                conn.close(); return status,data
            assert request('GET','/')[0]==200
            assert request('GET','/app.js')[0]==200
            assert request('GET','/style.css')[0]==200
            assert request('GET','/room.css')[0]==200
            status,state=request('GET','/api/state'); assert status==200
            if state['urls']:
                status,svg=request('GET','/api/qr'); assert status==200 and b'<svg' in svg and b'<path' in svg
                lan_address = urlsplit(state['urls'][0]).hostname
                status,info=request('GET','/api/info',auth=None,host=lan_address)
                assert status==200 and info['version']=='2.0.0'
                print(f'PASS: packaged server responds at LAN address {lan_address}.')
            status,joined=request('POST','/api/join',{'name':'Packaged smoke phone','code':state['code']},auth=None)
            assert status==200
            phone_token=joined['token']
            status,other=request('POST','/api/join',{'name':'Another phone','code':state['code']},auth=None)
            assert status==200
            other_token=other['token']
            target=other['me']['id']
            status,_=request('POST','/api/messages',{'target':target,'text':'Packaged peer smoke'},auth=phone_token)
            assert status==201
            status,inbox=request('GET','/api/state',auth=other_token)
            assert status==200 and [m['text'] for m in inbox['messages']]==['Packaged peer smoke']
            status,inbox=request('GET','/api/state')
            assert status==200 and inbox['messages']==[]
            payload=b'\x00\xffWiFiDrop packaged binary\r\n'*10000
            status,upload=request('POST','/api/uploads',{'name':'packaged-test.mkv','size':len(payload),'target':target},auth=phone_token); assert status==201
            path='/api/uploads/'+upload['id']
            assert request('PUT',path,payload,auth=phone_token,headers={'Upload-Offset':'0'})[0]==200
            status,completed=request('POST',path+'/complete',{},auth=phone_token); assert status==200
            assert completed['sha256']==hashlib.sha256(payload).hexdigest()
            status,ticket=request('POST','/api/files/'+upload['id']+'/ticket',{},auth=other_token); assert status==200
            assert request('GET',ticket['url'],auth=None)==(200,payload)
            assert request('POST','/api/shutdown',{})[0]==200
            assert process.wait(timeout=15)==0
            print('PASS: standalone executable, bundled UI, pairing, peer messages, private file upload, SHA-256, download and clean shutdown.')
        finally:
            if process.poll() is None:
                process.terminate();process.wait(timeout=10)


if __name__=='__main__': main(Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT/'dist'/'WiFiDrop.exe')
