# 近传 WiFiDrop

在同一个局域网内，用 Windows、macOS、Android 或 iPhone 互发文字和文件。选一台电脑运行房间服务，其余设备用浏览器加入。任何成员都能向任意一台设备发送，也能发给整个房间。支持图片、视频、文档、压缩包、APK 等安装包，文件原样传输。

## 开一个房间

1. **Windows** 双击 `WiFiDrop.exe`。源码也可在安装 Python 3.10 或更新版本后用 `Start-Windows.bat` 启动。
2. **Mac** 安装 Python 3.10 或更新版本，在项目目录运行 `python3 app.py`，也可双击 `Start-Mac.command`。
3. 保持主机运行。其他设备连到同一路由器，通过浏览器打开主机二维码下方的局域网地址并输入六位连接码。手机也可直接用相机扫码。其他电脑加入同一个地址即可。
4. 在「收件人」选择一台设备或整个房间，然后发送文字或选择文件。接收设备点击文件旁的下载按钮。手机和另一台手机之间也可以互发。

## 在 Mac 上从 GitHub 更新

首次使用时，以有权访问私有仓库的 GitHub 账号克隆：

```bash
git clone https://github.com/zed123-hub/WiFiDrop.git
cd WiFiDrop
python3 app.py
```

以后先退出旧版近传，再进入原克隆目录更新并启动：

```bash
git pull --ff-only
python3 app.py
```

如果 GitHub HTTPS 验证未配置，可以用已绑定到同一账号的 SSH 密钥克隆 `git@github.com:zed123-hub/WiFiDrop.git`。GitHub 负责同步源码。文件和消息保存在你选择的房间主机上。

## 消息和文件

- 单发只出现在收发双方的应用页面。群发内容对房间成员可见，包括之后加入的成员。主机保留文件与聊天记录，可以从磁盘访问这些内容。界面显示最近 200 条可见消息。
- 同一浏览器、同一房间地址和同一个主机数据目录下，设备身份在服务重启后保留。清除浏览器数据、换浏览器或换主机后需要重新配对。
- 主机收到和中转的文件默认保存在 `~/Downloads/WiFiDrop`。点击「打开接收文件夹」可直接查看。接收设备从浏览器下载文件，iPhone 可在「文件」App 中找下载项。
- 可多选，支持桌面拖入、上传进度、暂停和续传。刷新后，在同一浏览器选择原收件人和同一原文件，可接着已确认的分块上传。实际可传输大小受主机磁盘、浏览器和文件系统限制。
- APK、IPA、EXE 等都按普通文件传输。系统是否能安装或运行取决于接收设备。视频保持源格式，能否播放取决于播放器。
- 同名文件在主机上自动加编号。页面中的「删除」删除主机保存的文件副本。已下载的副本和发送设备的原文件仍各自保留。

## 局域网连接

默认端口为 TCP 8765，端口被占用时会顺延。近传生成私有 IPv4 地址的邀请链接，接受主机所在网段的设备连接。运行近传时无需公网 IP、端口转发或互联网服务。Windows 或 Mac 主机可用网线接入同一路由器。

如果手机打不开页面，优先选主机实际接入的网卡地址，检查 Windows 防火墙或 Mac 的本地网络权限，并确认暂未开启访客网络隔离。IPv4 地址变化后重启近传并使用新地址。

近传使用局域网 HTTP，适合可信网络。请只把连接码分享给信任的设备。房间主机可暂停邀请、更新连接码或移除配对的设备。关闭网页不会退出服务，退出时请点「退出近传」或在运行终端按 Ctrl+C。

## 测试和打包

```bash
python3 -m unittest discover -s tests -v
```

运行源码无需安装第三方 Python 包。可用 `--port` 指定端口、用 `--data-dir` 指定主机数据目录。打包在对应系统上执行：

```bash
python3 -m pip install -r requirements-build.txt
python3 scripts/build.py
```

打包结果位于 `dist/`。Windows 生成独立 EXE。Mac 可用 `Build-Mac.command` 构建本机的 `WiFiDrop.app`。

二维码由 [Project Nayuki QR Code generator](https://www.nayuki.io/page/qr-code-generator-library) 在本机生成。许可见 `THIRD-PARTY-NOTICES.txt`。
