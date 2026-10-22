"""Local operator tool. Never calls a remote write or automatically replays input."""
import argparse
import json
from pathlib import Path
from workflow_runtime import Store


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',default=str(Path(__file__).with_name('workflow_runtime.sqlite3')))
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('list')
    show=sub.add_parser('show'); show.add_argument('operation')
    resolve=sub.add_parser('resolve')
    resolve.add_argument('operation'); resolve.add_argument('--revision',type=int,required=True)
    resolve.add_argument('--actor',required=True); resolve.add_argument('--evidence',required=True)
    resolve.add_argument('--outcome',choices=['succeeded','failed'],required=True)
    resolve.add_argument('--receipt',help='Path to verified receipt JSON; never credentials')
    args=parser.parse_args(); store=Store(args.db)
    if args.command=='list':
        result=[{k:item[k] for k in ('id','scenario','status','target','revision','created_at')} for item in store.unresolved()]
    elif args.command=='show':
        result=store.get(args.operation)
    else:
        receipt=json.loads(Path(args.receipt).read_text()) if args.receipt else None
        result=store.reconcile(args.operation,args.revision,args.actor,args.outcome,args.evidence,receipt)
        result={k:result[k] for k in ('id','status','revision')}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
