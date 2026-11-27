"""Build on the destination OS: Windows .exe or macOS .app."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
# Local-only build dependencies installed by the development environment.
if (ROOT / '.build-deps').exists():
    sys.path.insert(0,str(ROOT / '.build-deps'))
import PyInstaller.__main__

arguments = [str(ROOT/'app.py'),'--noconfirm','--clean','--name','WiFiDrop',
             '--distpath',str(ROOT/'dist'),'--workpath',str(ROOT/'build'),
             '--specpath',str(ROOT/'build'),'--add-data',f'{ROOT / "web"}:web',
             '--add-data',f'{ROOT / "THIRD-PARTY-NOTICES.txt"}:.',
             '--paths',str(ROOT),'--collect-submodules','vendor']
if sys.platform == 'darwin':
    arguments += ['--windowed','--osx-bundle-identifier','local.wifidrop.app']
else:
    arguments += ['--onefile']
    if sys.platform == 'win32':
        arguments += ['--console']
        if (ROOT/'assets'/'icon.ico').exists():
            arguments += ['--icon',str(ROOT/'assets'/'icon.ico')]
PyInstaller.__main__.run(arguments)

