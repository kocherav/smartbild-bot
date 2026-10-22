"""Release receipt: fail on tests, isolation escapes, skips or changed source.

Run before requesting a bot reload. This never reloads or mutates business data.
"""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def verify(report):
    if not report.get('successful') or report.get('skipped') or report.get('blocked_events'):
        raise ValueError('Прогон не пройден полностью либо нарушена изоляция')
    if not report.get('tests') or not report.get('source_hashes'):
        raise ValueError('Нет тестов или контрольных сумм исходников')
    actual={str(p) for directory in report.get('source_dirs',[]) for p in Path(directory).glob('*.py')}
    for folder,patterns in report.get('asset_globs',{}).items():
        for pattern in patterns:actual.update(str(p) for p in Path(folder).glob(pattern))
    if actual and actual!=set(report['source_hashes']):raise ValueError('После проверки добавлены или удалены исходники; нужен новый прогон')
    changed=[p for p,digest in report['source_hashes'].items()
             if not Path(p).is_file() or hashlib.sha256(Path(p).read_bytes()).hexdigest()!=digest]
    if changed:raise ValueError('После проверки изменены исходники: '+', '.join(changed))
    return {'ok':True,'tests':report['tests'],'ran_at':report['ran_at'],'scope':'offline; external acceptance is separate'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true')
    parser.add_argument('--report',type=Path,default=ROOT/'audit-20261012/LAST_TEST_RUN.json');args=parser.parse_args()
    if args.run:
        result=subprocess.run([sys.executable,str(ROOT/'offline_tests.py'),'--output',str(args.report.parent)],stdout=subprocess.DEVNULL)
        if result.returncode:raise SystemExit('Проверки не пройдены: '+str(args.report.parent/'LAST_TEST_RUN.txt'))
    print(json.dumps(verify(json.loads(args.report.read_text())),ensure_ascii=False))
