"""Retain installer evidence locally before acknowledging it or queuing upload."""
import hashlib
import os
from pathlib import Path
import shutil
import tempfile

MAX_SIZE=20*1024*1024
def digest(path):
    value=hashlib.sha256()
    with open(path,'rb') as file:
        for part in iter(lambda:file.read(1024*1024),b''):value.update(part)
    return value.hexdigest()

def retain(path,root):
    source=Path(path)
    if source.stat().st_size>MAX_SIZE:raise ValueError('Размер файла превышает 20 МБ')
    sha=digest(source); root=Path(root); root.mkdir(parents=True,exist_ok=True,mode=0o700)
    suffix=source.suffix.lower()[:12]; target=root/(sha+suffix)
    if not target.exists():
        fd,tmp=tempfile.mkstemp(prefix='.media-',dir=root); os.close(fd)
        try:
            shutil.copyfile(source,tmp); os.chmod(tmp,0o600)
            if os.path.getsize(tmp)>MAX_SIZE or digest(tmp)!=sha:raise ValueError('Исходный файл изменился во время сохранения')
            with open(tmp,'rb') as file:os.fsync(file.fileno())
            os.replace(tmp,target)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
    elif digest(target)!=sha:raise ValueError('Повреждена сохранённая копия исходного файла')
    return str(target),sha,target.stat().st_size
