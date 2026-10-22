"""Track routing separately from completion of background business operations."""


def tracked(updates,store):
    for update in updates:
        message=update.get('message') or (update.get('callback_query') or {}).get('message') or {}
        actor=str((message.get('chat') or {}).get('id') or 'unknown')
        uid=update['update_id']
        store.receive(actor,uid,update)
        store.incoming_status(actor,uid,'routing')
        # On exception, process exit or generator close the state remains
        # routing. Startup recovery offers reconciliation, not a replay.
        yield update
        store.incoming_status(actor,uid,'routed')
