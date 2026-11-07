"""One open deal per chat: every deal action works only with the deal now being discussed.

Incidents: 06.11 (deal 905: the assistant answered about №865), 06–07.11 (project files of
№865 and №888 attached to each other: ``current_deal_id=865`` while a forgotten
``installation_deal_id=888`` won by ``installation_deal_id or current_deal_id``).

Rules, enforced in one place rather than per button:

1. ``current_deal_id`` is the only source of truth for «which deal».  Flow-specific ids
   (``contract_deal_id``, ``installation_deal_id``, ``payer_target_deal_id`` …) are only a
   bound copy of it for a step in progress.
2. When the open deal changes, everything that belonged to the previous deal — previews,
   bound ids, a waiting step, a chosen signatory, a pending file upload — is dropped in the
   same state transaction (:func:`switch_values`).  Nothing of deal A can be confirmed,
   uploaded or written once deal B is open.
3. Readers never prefer a stale bound id over the open deal (:func:`target`).
4. A button rendered for deal A and pressed while deal B is open does nothing
   (:func:`stale_button`); opening another deal and navigation stay allowed.

Explicit continuations that name their deal on the button itself (``proposal_draft``,
``suspended_payer_*``) and non-deal work (bank, supplier invoices across deals, the
installer's own cabinet, creating a new deal, developer tasks) are kept.
"""

DEAL_SCOPED_PREFIXES = (
    "contract_", "invoice_", "installation_", "proposal_", "payer_", "procurement_",
    "human_", "economics_", "transition", "document_order", "deal_sync",
)
DEAL_SCOPED_EXACT = {
    "generated_contract", "edo_offer", "find_then_act", "pending_transition", "transitions",
    "conversation_invoice", "work_price_preview", "bank_installer_deal_id",
    "bank_installer_transaction", "profitability_deal_id", "work_statement_deal_id",
    "resend_deal_id", "ledger_deal_id", "closing_deal_id",
}
KEEP = {
    "current_deal_id", "proposal_draft", "suspended_payer_deal_id", "suspended_payer_target",
    "supplier_invoice_queue", "supplier_invoice_preview", "supplier_invoice_deal_id",
}
# A waiting step that belongs to one deal.  Other steps (search, bank, creation, the
# developer prompt) survive a switch.
DEAL_SCOPED_PENDING = (
    "contract_", "invoice_", "installation_", "proposal_", "payer_", "procurement_", "human_",
    "economics_", "transition_invoice_", "deal_sync", "document_order_", "work_price",
    "edo_", "status_",
)


def is_deal_scoped(key):
    if key in KEEP or key.startswith("_"):
        return False
    return key in DEAL_SCOPED_EXACT or key.startswith(DEAL_SCOPED_PREFIXES) or key.endswith("_deal_id")


def switch_values(state, values):
    """Return ``values`` extended with the cleanup a change of the open deal requires."""
    if "current_deal_id" not in values:
        return values
    old = str(state.get("current_deal_id") or "")
    new = str(values.get("current_deal_id") or "")
    if old == new:
        return values
    result = dict(values)
    for key in list(state):
        if key in result or not is_deal_scoped(key):
            continue
        value = state.get(key)
        if key.endswith("_deal_id") and new and str(value) == new:
            continue  # already bound to the deal being opened
        result[key] = None
    pending = str(state.get("pending") or "")
    if "pending" not in result and pending.startswith(DEAL_SCOPED_PENDING):
        result["pending"] = None
    return result


def target(state, bound_key):
    """The deal a step acts on: the open deal; a bound id only when no deal is open
    (the installer's cabinet has its own object and no open card)."""
    current = str(state.get("current_deal_id") or "")
    if current:
        return current
    return str(state.get(bound_key) or "")


NAVIGATION_PREFIXES = ("№", "⬅️", "🤝", "❌", "🏠", "☰", "🔎", "⭐")


def stale_button(label, rendered_for, state):
    """Return the deal a button belonged to when it must not run now, else None."""
    rendered_for = str(rendered_for or "")
    current = str(state.get("current_deal_id") or "")
    if not rendered_for or not current or rendered_for == current:
        return None
    if str(label or "").startswith(NAVIGATION_PREFIXES):
        return None
    return rendered_for


def assistant_note(state):
    """One line for the assistant: which deal the person is talking about now."""
    current = str(state.get("current_deal_id") or "")
    if current:
        return (f"[КОНТЕКСТ БОТА: сейчас открыта сделка №{current}. Если в сообщении не назван другой "
                f"номер, речь только о сделке №{current}. Номера сделок из прошлых сообщений этого "
                "диалога не используй.]\n")
    return ("[КОНТЕКСТ БОТА: сделка не открыта. Если номер сделки не назван в этом сообщении, "
            "не бери его из прошлых сообщений — спроси номер.]\n")
