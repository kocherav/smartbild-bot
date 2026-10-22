"""Conservative routing of ordinary Russian business requests.

This module recognizes an operation class and explicit entities only. It never
authorizes a write and never fills missing business values from conversation
memory. Ambiguous language remains unresolved for the dialogue layer or model.
"""
from dataclasses import dataclass, field
import re


CREATE_DEAL = "create_deal"
CHANGE_PAYER = "change_payer"
CHANGE_INSTALLER = "change_installer"
ASSIGN_EXECUTOR = "assign_executor"
CHECK_PAYMENT = "check_payment"


@dataclass(frozen=True)
class Intent:
    name: str
    deal_id: str | None = None
    target: str | None = None
    fields: dict = field(default_factory=dict)
    missing: tuple[str, ...] = ()
    confidence: str = "high"


def _clean(value):
    return " ".join(str(value or "").replace("ё", "е").split())


def _deal_id(text):
    match = re.search(r"(?i)\b(?:сделк\w*\s*)?(?:№|номер\s*)?(\d{2,})\b", text)
    return match.group(1) if match else None


def _tail(text, patterns):
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            value = match.group(1).strip(" .,:;!?«»\"")
            if value:
                return value
    return None


def classify(text):
    original = _clean(text)
    folded = original.casefold()
    if not folded or folded.startswith("/"):
        return None
    deal_id = _deal_id(original)

    create_request = bool(
        re.search(r"\b(?:созда\w*|заве(?:д|ст)\w*|оформ\w*)\b", folded)
        or re.search(r"\bсдела\w*\b[^.\n]*\bсделку\b", folded)
        or re.search(r"\bнужн\w*\s+(?:нов\w*\s+)?сделк", folded)
    )
    if create_request and re.search(r"\bсделк", folded):
        client = _tail(original, (
            r"клиент(?:ом|а)?\s+(.+?)(?=\s+сделк|[,.;\n]|$)",
            r"сделк\w*\s+(?:для|с)\s+(?:клиент\w*\s+)?(.+?)(?=[,.;\n]|$)",
            r"сделк\w*\s+на\s+(.+?)(?=[,.;\n]|$)",
            r"для\s+(.+?)\s+сделк\w*(?=\s|[,.;\n]|$)",
        ))
        return Intent(CREATE_DEAL, target=client,
                      fields={"source_document_expected": bool(re.search(r"сч[её]т|файл|спецификац", text, re.I))},
                      missing=(() if client else ("client",)))

    if "плательщик" in folded and re.search(r"\b(?:поменя|замени|смени|выбери|назнач|сдела|друг)\w*\b", folded):
        target = _tail(original, (
            r"плательщик\w*\s+(?:на\s+)?(.+?)(?=[.;\n]|$)",
            r"на\s+плательщик\w*\s+(.+?)(?=[.;\n]|$)",
        ))
        if target and re.match(r"(?i)^(?:в|по)\s+сделк", target):
            target = None
        missing = tuple(x for x, value in (("deal", deal_id), ("payer", target)) if not value)
        return Intent(CHANGE_PAYER, deal_id, target, missing=missing)

    if re.search(r"\bмонтажник", folded) and re.search(r"\b(?:поменя|замени|смени|назнач|постав|друг|долж)\w*\b", folded):
        target = _tail(original, (
            r"монтажник\w*\s+(?:на\s+)?(.+?)(?=[.;\n]|$)",
            r"(?:назнач\w*|постав\w*)\s+(.+?)\s+монтажник\w*(?=[.;\n]|$)",
            r"монтажник\w*\s+долж\w*\s+быть\s+(.+?)(?=[.;\n]|$)",
        ))
        if target and re.match(r"(?i)^(?:в|по)\s+сделк", target):
            target = None
        missing = tuple(x for x, value in (("deal", deal_id), ("installer", target)) if not value)
        return Intent(CHANGE_INSTALLER, deal_id, target, missing=missing)

    if (re.search(r"\b(?:назнач|поменя|замени|смени|долж|сдела)\w*\b", folded)
            and re.search(r"\bисполнител", folded)):
        target = _tail(original, (
            r"исполнител\w*\s+сделк\w*\s*(?:№|номер\s*)?\d+[\s,—:-]+(.+?)(?=[.;\n]|$)",
            r"исполнител\w*\s+долж\w*\s+быть\s+(.+?)(?=[.;\n]|$)",
            r"исполнител\w*\s+(?:на\s+)?(.+?)(?=[.;\n]|$)",
            r"исполнител\w*\s+.+?\s+(.+?)(?=[.;\n]|$)",
        ))
        if target and re.match(r"(?i)^(?:в|по|сделк)", target):
            target = None
        missing = tuple(x for x, value in (("deal", deal_id), ("executor", target)) if not value)
        return Intent(ASSIGN_EXECUTOR, deal_id, target, missing=missing)

    if (re.search(r"\b(?:оплачен|оплат|поступил|пришл|долг|остаток)\w*", folded)
            and re.search(r"\bсделк", folded)):
        return Intent(CHECK_PAYMENT, deal_id=deal_id,
                      missing=(() if deal_id else ("deal",)))
    return None
