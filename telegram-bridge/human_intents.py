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
MOVE_STATUS = "move_status"
ISSUE_INVOICE = "issue_invoice"
GET_INVOICE = "get_invoice"
GET_ECONOMICS = "get_economics"


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


_DEAL_REF = r"(?:в|по)\s+(?:\d+\S*\s+)?сделк\w*(?:\s*(?:№|номер)?\s*\d+\S*)?"


def _strip_deal_ref(value):
    """«ООО Ромашка в сделке №900» / «в 900 на Ромашка» / «900 ромашка» -> «Ромашка»."""
    if not value:
        return value
    value = re.sub(r"(?i)\s+" + _DEAL_REF + r"\s*$", "", value)
    value = re.sub(r"(?i)^(?:(?:в|по)\s+)?(?:сделк\w*\s*)?(?:№|номер)?\s*\d{2,}\S*\s+(?:(?:на|теперь|будет)\s+)?", "", value)
    value = value.strip(" .,:;!?«»\"—-")
    return value or None


def _invoice_intent(folded, deal_id):
    # «счёт на оплату» names the document; any other «оплат…» asks about money received.
    folded = re.sub(r"сч[её]т\w*\s+на\s+оплату", "счет", folded)
    if not re.search(r"\bсч[её]т", folded) or re.search(r"поставщик|входящ|учт|учес|разнес|оплат", folded):
        return None
    missing = () if deal_id else ("deal",)
    if re.search(r"\b(?:выстав|сформир|подготов|сдела|созда|оформ|нуж[ен]\w*)\w*\b", folded):
        return Intent(ISSUE_INVOICE, deal_id, missing=missing)
    if re.search(r"\b(?:пришли|скинь\w*|отправ\w*|дай|покажи|получ\w*|скача\w*|достан\w*|найди|где)\b", folded):
        return Intent(GET_INVOICE, deal_id, missing=missing)
    return None


def _status_intent(original, folded, deal_id):
    asks = (re.search(r"\bстатус", folded) and re.search(r"\b(?:перевед|переведи|перевест|поменя|смени|измени|постав|сдела)\w*|\bсделк", folded)) \
        or (re.search(r"\b(?:перевед|переведи|перевест)\w*\b", folded) and re.search(r"\bсделк", folded))
    if not asks:
        return None
    target = _tail(original, (
        r"статус\w*\s+(?:у\s+)?сделк\w*\s*(?:№|номер)?\s*\d+\S*\s+(?:на|в)\s+[«\"]?(.+?)[»\"]?(?=[.;!?\n]|$)",
        r"статус\w*\s+(?:на|в)?\s*[«\"]?(.+?)[»\"]?(?=[.;!?\n]|$)",
        r"\bв\s+статус\s+[«\"]?(.+?)[»\"]?(?=[.;!?\n]|$)",
        r"\d+\S*\s+(?:в|на)\s+[«\"]?(.+?)[»\"]?(?=[.;!?\n]|$)",
        r"\bсделк\w*\s+(?:в|на)\s+[«\"]?(.+?)[»\"]?(?=[.;!?\n]|$)",
    ))
    if target and re.match(r"(?i)^(?:сделк|статус)", target):
        target = None
    target = _strip_deal_ref(target)
    missing = tuple(x for x, value in (("deal", deal_id), ("status", target)) if not value)
    return Intent(MOVE_STATUS, deal_id, target, missing=missing)


_NAME_ENDINGS = ("ого", "его", "ому", "ему", "ыми", "ими", "ой", "ей", "ым", "им", "ом", "ем",
                 "ую", "юю", "а", "я", "у", "ю", "ы", "и", "е")


def name_stems(query):
    """Stems of person names in any case: «Смирнова» -> «Смирнов», «Сергея» -> «Серге»."""
    stems = []
    for word in re.findall(r"[А-Яа-яЁёA-Za-z-]{4,}", str(query or "")):
        for ending in _NAME_ENDINGS:
            if word.casefold().endswith(ending) and len(word) - len(ending) >= 4:
                stem = word[:-len(ending)]
                if stem not in stems:
                    stems.append(stem)
                break
    return stems


def classify(text):
    original = _clean(text)
    folded = original.casefold()
    if not folded or folded.startswith("/"):
        return None
    if not (folded[0].isalnum() or folded[0] in "«\"("):
        # Telegram buttons start with an emoji; their meaning belongs to the screen.
        return None
    deal_id = _deal_id(original)

    # «Создай счёт по сделке 900» asks for an invoice, not a new deal.
    invoice_object = re.search(
        r"\b(?:созда|оформ|сформир|выстав|сдела)\w*\s+(?:нов\w*\s+|ещ[её]\s+|общ\w*\s+)?сч[её]т", folded)
    deal_object = re.search(r"\b(?:созда|заве(?:д|ст)|оформ|сдела)\w*\s+(?:\S+\s+){0,3}?сделку", folded)
    create_request = not (invoice_object and not deal_object) and bool(
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

    payer_word = "плательщик" in folded or re.search(r"\bплатить\s+будет\b", folded)
    if payer_word and re.search(r"\b(?:поменя|замени|смени|выбери|назнач|сдела|друг|теперь|будет)\w*\b", folded):
        target = _tail(original, (
            r"платить\s+будет\s+(.+?)(?=[.;\n]|$)",
            r"плательщик\w*\s+(?:по|в)\s+(?:сделк\w*\s*)?(?:№|номер)?\s*\d+\S*\s+(?:теперь|будет)\s+(.+?)(?=[.;\n]|$)",
            r"плательщик\w*\s+" + _DEAL_REF + r"\s+на\s+(.+?)(?=[.;\n]|$)",
            r"" + _DEAL_REF + r"\s+.*?плательщик\w*\s+на\s+(.+?)(?=[.;\n]|$)",
            r"плательщик\w*\s+на\s+(.+?)(?=[.;\n]|$)",
            r"плательщик\w*\s*[—:-]\s*(.+?)(?=[.;\n]|$)",
            r"плательщиком\s+(.+?)(?=[.;\n]|$)",
            r"на\s+плательщик\w*\s+(.+?)(?=[.;\n]|$)",
            r"плательщик\w*\s+(.+?)(?=[.;\n]|$)",
        ))
        if target and re.match(r"(?i)^(?:в|по)\s+(?:\d+\S*\s+)?сделк", target):
            target = None
        target = _strip_deal_ref(target)
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

    status = _status_intent(original, folded, deal_id)
    if status:
        return status

    invoice = _invoice_intent(folded, deal_id)
    if invoice:
        return invoice

    # Route an explicit economics question before the payment rule below:
    # «пришли расчёт» otherwise looks like «пришли деньги» by its word stem.
    if (re.search(r"\b(?:экономик|рентабельн|прибыл|марж)\w*", folded)
            and (re.search(r"\bсделк", folded) or deal_id)):
        return Intent(GET_ECONOMICS, deal_id=deal_id,
                      missing=(() if deal_id else ("deal",)))

    if (re.search(r"\b(?:оплачен|оплат|поступил|пришл|долг|остаток)\w*", folded)
            and (re.search(r"\bсделк", folded) or (deal_id and len(deal_id) >= 3 and not re.search(r"сч[её]т", folded)))):
        return Intent(CHECK_PAYMENT, deal_id=deal_id,
                      missing=(() if deal_id else ("deal",)))
    return None
