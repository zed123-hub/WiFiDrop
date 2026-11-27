"""Real Chromium desktop/mobile browser tests; run with development tools only."""
import hashlib
import os
from pathlib import Path
import re
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / '.build-deps')]
from playwright.sync_api import sync_playwright, expect
import app


def open_view(page, view):
    page.locator(f'.nav-item[data-view="{view}"]').click()
    expect(page.locator(f'#{view}-view')).to_be_visible()


def select_recipient(page, name, selector='#target-select'):
    option = page.locator(f'{selector} option').filter(has_text=name)
    expect(option).to_have_count(1)
    page.locator(selector).select_option(option.get_attribute('value'))


def send_message(page, message):
    page.locator('#message-input').fill(message)
    page.locator('#send-message').click()


def exercise_peer_delivery(host, iphone, android, mac):
    private = '安卓发送给 iPhone 的私信 📱'
    reply = 'iPhone 已收到私信'
    shared = '四台设备集合'
    recipient_name = '我的 iPhone'
    open_view(iphone, 'messages')
    select_recipient(android, recipient_name)
    send_message(android, private)
    received = iphone.locator('#message-list .message-row').filter(has_text=private)
    expect(received).to_have_count(1, timeout=7000)
    received.locator('[data-reply]').click()
    send_message(iphone, reply)
    expect(android.locator('.message-text', has_text=reply)).to_have_count(1, timeout=7000)

    attachment = b'\x00PK\xff\x00device to device' * 1200
    filename = '设备安装包.apk'
    open_view(android, 'devices')
    android.get_by_role('button', name='给 我的 iPhone 发文件', exact=True).click()
    expect(android.locator('#files-view')).to_be_visible()
    expect(android.locator('#file-target-select option:checked')).to_have_text(recipient_name)
    android.locator('#file-input').set_input_files({'name':filename,'mimeType':'application/octet-stream','buffer':attachment})
    open_view(iphone, 'files')
    with iphone.expect_download() as event:
        iphone.get_by_role('button',name='下载 ' + filename,exact=True).click(timeout=10000)
    download = event.value
    assert download.suggested_filename == filename
    assert Path(download.path()).read_bytes() == attachment

    mac.locator('#target-select').select_option('all')
    send_message(mac, shared)
    for page in (host, iphone, android, mac):
        open_view(page, 'messages')
        expect(page.locator('.message-text', has_text=shared)).to_have_count(1, timeout=7000)
    for outsider in (host, mac):
        expect(outsider.locator('.message-text', has_text=private)).to_have_count(0)
        expect(outsider.locator('.message-text', has_text=reply)).to_have_count(0)
        expect(outsider.locator('.file-row', has_text=filename)).to_have_count(0)


def main():
    output = ROOT / 'test-results'
    output.mkdir(exist_ok=True)
    errors = []
    with tempfile.TemporaryDirectory() as temp:
        room = app.Room(Path(temp), addresses=['127.0.0.1'])
        server = app.Server(('127.0.0.1',0), room)
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        origin = f'http://127.0.0.1:{room.port}'
        try:
            with sync_playwright() as playwright:
                chrome = os.environ.get('WIFIDROP_CHROME')
                installed_chrome = Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
                if not chrome and installed_chrome.is_file():
                    chrome = str(installed_chrome)
                browser = playwright.chromium.launch(executable_path=chrome,headless=True)
                desktop_context = browser.new_context(viewport={'width':1440,'height':1100},device_scale_factor=1)
                desktop = desktop_context.new_page()
                desktop.on('pageerror',lambda error: errors.append(str(error)))
                desktop.goto(origin + '/#admin=' + room.admin_token)
                expect(desktop.locator('#transfer-view')).to_be_visible()
                expect(desktop.locator('#messages-view')).to_be_visible()
                expect(desktop.locator('#files-view')).to_be_hidden()
                desktop.screenshot(path=str(output/'desktop-chat-empty.png'),full_page=True)
                desktop.locator('#invite-shortcut').click()
                expect(desktop.locator('#devices-view')).to_be_visible()
                expect(desktop.locator('#qr-image')).to_be_visible()
                expect(desktop.locator('#pairing-code')).to_have_text(room.pair_code)
                assert desktop.evaluate('location.hash') == ''
                desktop.screenshot(path=str(output/'desktop-empty.png'),full_page=True)

                phone_context = browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,
                    user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1')
                phone = phone_context.new_page()
                phone.on('pageerror',lambda error: errors.append(str(error)))
                phone.goto(origin + '/#join=' + room.invite_token)
                expect(phone.locator('#transfer-view')).to_be_visible()
                assert phone.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                assert phone.locator('#qr-card').is_hidden()
                expect(desktop.locator('#device-count')).to_have_text('2',timeout=7000)
                desktop.screenshot(path=str(output/'desktop-devices.png'),full_page=True)
                open_view(desktop, 'files')
                open_view(phone, 'files')

                video = b'WiFiDrop-video\x00\xff' * 400000
                desktop.locator('#file-input').set_input_files({'name':'旅行原片.MKV','mimeType':'application/octet-stream','buffer':video})
                expect(desktop.locator('.upload-item').first).to_contain_text('已送达',timeout=30000)
                expect(phone.locator('.file-row')).to_have_count(1,timeout=7000)
                with phone.expect_download() as info:
                    phone.get_by_role('button',name='下载 旅行原片.MKV',exact=True).click()
                download = info.value
                downloaded = Path(download.path()).read_bytes()
                assert downloaded == video
                assert download.suggested_filename == '旅行原片.MKV'

                # Interrupt the second chunk once. The UI must resume from the
                # first confirmed chunk without duplicating or corrupting bytes.
                intercepted = {'count':0}
                def interrupt(route):
                    if route.request.method == 'PUT':
                        intercepted['count'] += 1
                        if intercepted['count'] == 2:
                            route.abort('failed'); return
                    route.continue_()
                phone.route('**/api/uploads/**',interrupt)
                payload = bytes(range(256)) * 35000
                phone.locator('#file-input').set_input_files({'name':'手机测试视频.MOV','mimeType':'application/octet-stream','buffer':payload})
                expect(phone.locator('.upload-item').first).to_contain_text('网络中断',timeout=30000)
                partial = [r for r in room.records.values() if not r.get('complete')][0]
                assert room.part_path(partial['id']).stat().st_size == app.CHUNK_SIZE
                phone.get_by_role('button',name='继续',exact=True).click()
                expect(phone.locator('.upload-item').first).to_contain_text('已送达',timeout=30000)
                result = next(r for r in room.records.values() if r['name']=='手机测试视频.MOV')
                assert (room.directory/result['saved_name']).read_bytes() == payload
                assert result['sha256'] == hashlib.sha256(payload).hexdigest()

                # Resume storage must also survive a page reload and original
                # file re-selection (which preserves its modification time).
                fixtures = Path(temp)/'fixtures'; fixtures.mkdir()
                original = fixtures/'刷新续传.bin'; original.write_bytes(payload)
                intercepted['count'] = 0
                phone.locator('#file-input').set_input_files(str(original))
                expect(phone.locator('.upload-item').last).to_contain_text('网络中断',timeout=30000)
                phone.reload()
                expect(phone.locator('#transfer-view')).to_be_visible()
                expect(phone.locator('#files-view')).to_be_visible()
                phone.locator('#file-input').set_input_files(str(original))
                expect(phone.locator('.upload-item').last).to_contain_text('已送达',timeout=30000)
                resumed = [r for r in room.records.values() if r['name']=='刷新续传.bin']
                assert len(resumed)==1
                assert (room.directory/resumed[0]['saved_name']).read_bytes()==payload
                assert original.read_bytes()==payload

                phone.locator('#file-input').set_input_files([
                    {'name':'会议记录.txt','mimeType':'text/plain','buffer':'手机传给电脑的中文文档。'.encode()},
                    {'name':'原始照片.HEIC','mimeType':'application/octet-stream','buffer':b'\x00\x00ftypheic\x01\xff'},
                    {'name':'empty.file','mimeType':'application/octet-stream','buffer':b''}])
                expect(phone.locator('.upload-item')).to_have_count(4)
                expect(phone.locator('.upload-item').last).to_contain_text('已送达',timeout=30000)
                expect(desktop.locator('.file-row')).to_have_count(6,timeout=7000)
                phone.locator('[data-filter="received"]').click()
                expect(phone.locator('.file-row')).to_have_count(1)
                phone.locator('[data-filter="all"]').click()
                phone.screenshot(path=str(output/'phone-files.png'),full_page=True)
                desktop.screenshot(path=str(output/'desktop-files.png'),full_page=True)
                for width in (320,390,768,1024,1440):
                    desktop.set_viewport_size({'width':width,'height':1000})
                    for view in ('messages', 'files', 'devices'):
                        open_view(desktop, view)
                        assert desktop.evaluate('document.documentElement.scrollWidth <= window.innerWidth'),f'{view} overflow at {width}'
                desktop.set_viewport_size({'width':1440,'height':1100})

                # Manual six-digit pairing in a fresh, untrusted browser context.
                other_context = browser.new_context(**playwright.devices['Pixel 7'])
                other = other_context.new_page(); other.goto(origin)
                other.on('pageerror',lambda error: errors.append(str(error)))
                expect(other.locator('#join-form')).to_be_visible()
                expect(other.locator('#connect-view')).to_have_class(re.compile(r'\bis-entered\b'))
                other.screenshot(path=str(output/'phone-join.png'),full_page=True)
                other.locator('#pair-code').fill(room.pair_code)
                other.locator('#device-name').fill('手动连接设备')
                other.locator('#join-button').click()
                expect(other.locator('#transfer-view')).to_be_visible()
                expect(other.locator('.file-row')).to_have_count(1)

                mac_context = browser.new_context(**playwright.devices['Desktop Safari'])
                mac = mac_context.new_page()
                mac.on('pageerror',lambda error: errors.append(str(error)))
                mac.goto(origin + '/#join=' + room.invite_token)
                expect(mac.locator('#transfer-view')).to_be_visible()
                exercise_peer_delivery(desktop, phone, other, mac)
                phone.screenshot(path=str(output/'phone-chat.png'),full_page=True)
                desktop.screenshot(path=str(output/'desktop-chat.png'),full_page=True)

                open_view(desktop, 'files')
                desktop.get_by_role('button',name='删除 会议记录.txt',exact=True).click()
                expect(desktop.locator('#confirm-dialog')).to_be_visible()
                desktop.locator('#confirm-dialog button[value="confirm"]').click()
                expect(desktop.locator('.file-row')).to_have_count(5,timeout=7000)
                desktop.locator('[data-view="help"]').click()
                expect(desktop.locator('#help-view')).to_be_visible()
                open_view(desktop, 'messages')
                assert not errors,errors
                browser.close()
            print('PASS: four isolated Chromium sessions, peer messaging and replies, broadcast, private APK download, binary integrity, upload resume, pairing, deletion and responsive layouts.')
            print('Screenshots: ' + str(output))
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    main()
