"""Create small, reproducible delivery archives without build dependencies."""
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT/'dist'
DIST.mkdir(exist_ok=True)

for name in ('README.md','THIRD-PARTY-NOTICES.txt'):
    shutil.copy2(ROOT/name,DIST/name)

source_files = ['app.py','lan_network.py','room_history.py','README.md','THIRD-PARTY-NOTICES.txt','requirements-build.txt',
                'Start-Windows.bat','Start-Mac.command','Build-Mac.command']
for directory in ('web','vendor','scripts','tests','assets'):
    source_files += [str(path.relative_to(ROOT)) for path in (ROOT/directory).rglob('*')
                     if path.is_file() and '__pycache__' not in path.parts]

with zipfile.ZipFile(DIST/'WiFiDrop-Source.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for name in sorted(source_files):
        path = ROOT/name
        info = zipfile.ZipInfo.from_file(path,'WiFiDrop/'+str(Path(name)).replace('\\','/'))
        if path.suffix == '.command':
            info.create_system=3;info.external_attr=(0o100755 << 16)
        archive.writestr(info,path.read_bytes(),compress_type=zipfile.ZIP_DEFLATED)
if (DIST/'WiFiDrop.exe').exists():
    with zipfile.ZipFile(DIST/'WiFiDrop-Windows.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for name in ('WiFiDrop.exe','README.md','THIRD-PARTY-NOTICES.txt'):
            archive.write(DIST/name,'WiFiDrop/'+name)
print('Delivery archives: ' + str(DIST))
