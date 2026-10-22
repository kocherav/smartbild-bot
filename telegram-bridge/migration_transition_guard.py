"""Suppress procurement side effects during an explicitly recorded migration.

An interrupted migration stays guarded until reconciled, never expires into a
supplier order. Missing database/table means no migration; damaged data fails
closed by propagating the read error to the background worker.
"""
import os
import sqlite3


def blocked(path,deal_id):
    if not os.path.exists(path):return False
    db=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)
    try:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='audit_log'").fetchone():return False
        row=db.execute("SELECT action FROM audit_log WHERE deal_id=? AND action IN ('historical_stage_migration_started','historical_stage_migration_finished') ORDER BY id DESC LIMIT 1",(str(deal_id),)).fetchone()
        return bool(row and row[0]=='historical_stage_migration_started')
    finally:db.close()
