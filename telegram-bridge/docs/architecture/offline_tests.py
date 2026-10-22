"""Run existing tests in source-only temporary copies with side effects blocked.

Usage: report-venv/bin/python offline_tests.py [test_module ...]
No production config/registries are copied. All network/subprocess calls fail.
Only the dedicated temporary directory is writable (including SQLite).
"""
import argparse
import hashlib
import importlib.abc
import importlib.util
import datetime as dt
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent
PROJECTS = [Path('/home/kocher.av/telegram-bridge'), Path('/home/kocher.av/megaplan-crm'),
            Path('/home/kocher.av/hogart-scraper'), Path('/home/kocher.av/daichi-scraper')]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('modules', nargs='*')
    parser.add_argument('--output',type=Path,default=ROOT)
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    sys.dont_write_bytecode = True
    with tempfile.TemporaryDirectory(prefix='smartbild-offline-') as temporary:
        sandbox = Path(temporary).resolve()
        paths, names, source_hashes = [], [], {}
        for project in PROJECTS:
            target = sandbox / project.name
            target.mkdir()
            if project.name=='megaplan-crm' and (project/'templates').exists():
                shutil.copytree(project/'templates',target/'templates')
            for source in project.glob('*.py'):
                compile(source.read_bytes(),str(source),'exec')
                shutil.copy2(source, target / source.name)
                source_hashes[str(source)]=hashlib.sha256(source.read_bytes()).hexdigest()
                if source.name.startswith('test_'):
                    names.append(source.stem)
            paths.append(str(target))
        for relative in ('hogart-scraper/finance','hogart-scraper/dashboard','hogart-scraper/dashboard/tests','telegram-bridge/docs/architecture'):
            project=Path('/home/kocher.av')/relative;target=sandbox/relative
            target.mkdir(parents=True,exist_ok=True)
            for source in project.glob('*.py'):
                compile(source.read_bytes(),str(source),'exec')
                shutil.copy2(source,target/source.name)
                source_hashes[str(source)]=hashlib.sha256(source.read_bytes()).hexdigest()
                if source.name.startswith('test_'):names.append(source.stem)
            paths.append(str(target))
        asset_globs={
            '/home/kocher.av/megaplan-crm':['tax_policies.json'],
            '/home/kocher.av/megaplan-crm/templates/closing':['*.png'],
            '/home/kocher.av/megaplan-crm/templates/closing/kocherzhinsky_ip-smartbild-v1':['*.png','*.pdf','*.docx'],
            '/home/kocher.av/hogart-scraper/dashboard/static':['*.js','*.html','*.css'],
            '/home/kocher.av/hogart-scraper/dashboard/tests':['*.cjs'],
            '/home/kocher.av/hogart-scraper/dashboard/deploy':['*.service','*.timer'],
            '/home/kocher.av/hogart-scraper/finance/deploy':['*.service','*.timer']}
        for folder,patterns in asset_globs.items():
            for pattern in patterns:
                for source in Path(folder).glob(pattern):source_hashes[str(source)]=hashlib.sha256(source.read_bytes()).hexdigest()
        (sandbox/'hogart-scraper/finance/user_rules.json').write_text('{}')
        os.environ['XDG_CACHE_HOME']=str(sandbox/'cache')
        # Warm up renderer library discovery before banning subprocesses; no
        # application code, tokens or external API calls execute here.
        import weasyprint
        # Hard-coded sys.path insertions in application modules must not escape
        # the source sandbox or mix live/sandbox exception classes.
        sources={}
        for folder in paths:
            for file in Path(folder).glob('*.py'):sources.setdefault(file.stem,file)
        class SandboxFinder(importlib.abc.MetaPathFinder):
            def find_spec(self,fullname,path=None,target=None):
                if fullname in sources:return importlib.util.spec_from_file_location(fullname,sources[fullname])
        sys.meta_path.insert(0,SandboxFinder())
        sys.path[:0] = paths
        original_expanduser = os.path.expanduser
        def test_expanduser(path):
            for project, replacement in zip(PROJECTS, paths):
                prefix = '~/' + project.name
                if isinstance(path, str) and (path == prefix or path.startswith(prefix + '/')):
                    return replacement + path[len(prefix):]
            return original_expanduser(path)
        os.path.expanduser = test_expanduser
        tempfile.tempdir = temporary
        original_cwd = Path.cwd()
        os.chdir(sandbox)
        blocks = []
        enabled = True

        def local(path):
            if isinstance(path, int):
                return True
            try:
                return Path(os.fsdecode(path)).resolve().is_relative_to(sandbox)
            except (TypeError, ValueError):
                return False

        def guard(event, argv):
            if not enabled:
                return
            deny = event in ('socket.connect', 'socket.bind', 'subprocess.Popen', 'os.system', 'os.fork', 'os.exec', 'os.posix_spawn')
            if event == 'open':
                path, mode, flags = argv
                write = bool((flags or 0) & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
                sensitive = isinstance(path, (str, bytes)) and Path(os.fsdecode(path)).name in ('.env', 'token.json', 'session_id.txt', 'developer_session_id.txt')
                deny = (write and not local(path)) or (sensitive and not local(path))
            elif event in ('os.remove', 'os.rmdir', 'os.mkdir', 'os.chmod'):
                deny = not local(argv[0])
            elif event in ('os.rename', 'os.link', 'os.symlink'):
                deny = not local(argv[0]) or not local(argv[1])
            elif event == 'sqlite3.connect':
                deny = argv[0] != ':memory:' and not local(argv[0])
            if deny:
                frames = []
                frame = sys._getframe(1)
                while frame and len(frames) < 5:
                    filename = frame.f_code.co_filename
                    if any(part in filename for part in ('telegram-bridge', 'megaplan-crm', 'hogart-scraper')):
                        frames.append(Path(filename).name + ':' + str(frame.f_lineno))
                    frame = frame.f_back
                blocks.append({'event': event, 'source': frames})
                raise PermissionError('Offline test guard blocked: ' + event)

        sys.addaudithook(guard)
        stream = io.StringIO()
        start = time.monotonic()
        try:
            suite = unittest.defaultTestLoader.loadTestsFromNames(args.modules or sorted(set(names)))
            def flatten(node):
                for item in node:
                    if isinstance(item,unittest.TestSuite):yield from flatten(item)
                    else:yield item
            suite=unittest.TestSuite({test.id():test for test in flatten(suite)}.values())
            class CaseResult(unittest.TextTestResult):
                def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.cases=[]
                def startTest(self,test):self.started=time.monotonic();super().startTest(test)
                def record(self,test,status):
                    item={'id':test.id(),'status':status,'seconds':round(time.monotonic()-self.started,4)}
                    if getattr(test,'qa_transcript',None):item['transcript']=test.qa_transcript
                    if getattr(test,'qa_observations',None):item['observations']=test.qa_observations
                    self.cases.append(item)
                def addSuccess(self,test):super().addSuccess(test);self.record(test,'passed')
                def addFailure(self,test,err):super().addFailure(test,err);self.record(test,'failed')
                def addError(self,test,err):super().addError(test,err);self.record(test,'error')
                def addSkip(self,test,reason):super().addSkip(test,reason);self.record(test,'skipped')
            result = unittest.TextTestRunner(stream=stream, verbosity=2,resultclass=CaseResult).run(suite)
        finally:
            enabled = False
            os.path.expanduser = original_expanduser
            os.chdir(original_cwd)
        output = stream.getvalue()
        print(output)
        report = {'ran_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source_hashes':source_hashes,'source_dirs':sorted({str(Path(p).parent) for p in source_hashes if p.endswith('.py')}),'asset_globs':asset_globs,'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
                  'skipped': len(result.skipped), 'seconds': round(time.monotonic()-start, 3),
                  'blocked_events': blocks, 'successful': result.wasSuccessful() and not blocks,'cases':result.cases,
                  'modules': args.modules or sorted(set(names))}
        (args.output / 'LAST_TEST_RUN.txt').write_text(output, encoding='utf-8')
        (args.output / 'LAST_TEST_RUN.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in ('source_hashes','blocked_events','modules','cases','source_dirs','asset_globs')}, ensure_ascii=False))
        return 0 if report['successful'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
