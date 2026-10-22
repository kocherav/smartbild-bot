"""Protected local rollback evidence; never restores business registries automatically."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile


def main():
    root = Path('/home/kocher.av')
    target = Path(tempfile.mkdtemp(prefix='architecture-state-', dir=root / 'telegram-bridge'))
    entries = []
    selected = {
        'telegram-bridge': ['deal_ui_state.json', 'document_jobs.json', 'installer_fact_registry.json',
                            'installer_approved_reports.json', 'installer_settlements.json', 'edo_dispatch_registry.json',
                            'procurement_status_watch.json', 'workflow_runtime.sqlite3','watcher_schedule.json','installer_accounts.sqlite3'],
        'megaplan-crm': ['megaplan_transport.sqlite3', 'installations.sqlite3', 'procurement_registry.json', 'financial_amount_overrides.json',
                         'megaplan_finance_registry.json', 'bank_statement_registry.json', 'email_payment_registry.json',
                         'archive_outbox/jobs.sqlite3', 'financial_archive.json','hogart_order_journal.json','economics_attachments.json'],
    }
    for project, names in selected.items():
        directory = target / project; directory.mkdir(mode=0o700)
        for name in names:
            source, dest = root / project / name, directory / name
            if not source.exists(): continue
            dest.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            if source.suffix == '.sqlite3':
                with sqlite3.connect(f'file:{source}?mode=ro', uri=True) as original, sqlite3.connect(dest) as backup:
                    original.backup(backup)
            else:
                shutil.copy2(source, dest)
            os.chmod(dest, 0o600)
            entries.append({'path': f'{project}/{name}', 'sha256': hashlib.sha256(dest.read_bytes()).hexdigest()})
    manifest = target / 'manifest.json'
    manifest.write_text(json.dumps(entries, indent=2)); os.chmod(manifest, 0o600)
    print(json.dumps({'snapshot': str(target), 'files': len(entries)}))


if __name__ == '__main__': main()
