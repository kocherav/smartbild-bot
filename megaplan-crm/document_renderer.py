"""Run the same LibreOffice build without requiring FUSE in the bot service."""
from pathlib import Path
BASE=Path('/home/kocher.av/.local/lib/libreoffice-appimage')

def office_command(env):
    executable=BASE/'extracted/squashfs-root/AppRun'
    if executable.is_file():return str(executable)
    # Portable fallback for installations without the pre-extracted copy.
    env['APPIMAGE_EXTRACT_AND_RUN']='1'
    return str(BASE/'LibreOffice.AppImage')
