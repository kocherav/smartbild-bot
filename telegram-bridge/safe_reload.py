"""Reload only between polling batches and after all workers have exited."""
import hashlib
from pathlib import Path
import durable_json

def bundle_manifest(source):
    source=Path(source).resolve()
    roots=[source.parent]
    if source.parent.name=='telegram-bridge':
        roots.extend(source.parent.parent/name for name in ('megaplan-crm','hogart-scraper','daichi-scraper','hogart-scraper/finance','hogart-scraper/dashboard'))
    manifest={}
    for root in roots:
        for path in sorted(root.glob('*.py')):
            content=path.read_bytes(); compile(content,str(path),'exec')
            manifest[str(path)]=hashlib.sha256(content).hexdigest()
    return manifest

def request(path,source):
    code=Path(source).read_bytes()
    compile(code,source,'exec')
    durable_json.save(path,{'sha256':hashlib.sha256(code).hexdigest(),'manifest':bundle_manifest(source)})

def pending_reviewed(path,source):
    """Only a valid reviewed request may pause launching new background jobs."""
    if not Path(path).exists():return False
    try:
        expected=durable_json.read(path,dict)
        code=Path(source).read_bytes()
        return (hashlib.sha256(code).hexdigest()==expected.get('sha256')
                and expected.get('manifest')==bundle_manifest(source))
    except (OSError,SyntaxError,ValueError,TypeError):return False

def stale_request(path,source):
    """Files that differ from a pending reload request; [] when there is none or it is valid."""
    if not Path(path).exists():return []
    try:
        expected=durable_json.read(path,dict).get('manifest') or {}
        current=bundle_manifest(source)
    except (OSError,SyntaxError,ValueError,TypeError):
        return [str(source)]
    return sorted(p for p in set(expected)|set(current) if expected.get(p)!=current.get(p))

def apply_if_idle(path,source,active_children,restart):
    if active_children or not pending_reviewed(path,source): return False
    expected=durable_json.read(path,dict)
    code=Path(source).read_bytes()
    compile(code,source,'exec')
    Path(path).unlink()
    try: restart()
    except BaseException:
        durable_json.save(path,expected)
        raise
    return True
