"""Telegram flow «📎 Цены из КП и счетов» for the open deal (owner 24.11).

States (deal_ui_state):
  pending 'deal_price_docs'      — collecting files; price_docs = [document, …]
  pending 'deal_price_kind'      — the last file's type is unclear: счёт or КП?
  pending 'deal_price_discount'  — our discount for the last КП (0…40 % step 5, or own figure)
  pending 'deal_price_review'    — proposals shown, waiting for «Применить»
The bridge passes its helpers in `io` so this module stays testable without Telegram or CRM.
"""
import json
import os
import re
import subprocess

BUTTON = "📎 Цены из КП и счетов"
DONE = "✅ Все файлы загружены"
CANCEL = "❌ Отмена"
IS_INVOICE = "📄 Это счёт (наша закупка)"
IS_KP = "🏷 Это КП (цена продажи)"
OWN_DISCOUNT = "✍️ Своя скидка"
APPLY = "✅ Применить"
READ_OK = "✅ Прочитано верно"
SWAP = "↔️ Кол-во и цена наоборот"
CURRENCY_BUTTONS = {"💱 RUB": "RUB", "💱 USD": "USD", "💱 EUR": "EUR"}
SIGN = {"RUB": "₽", "USD": "$", "EUR": "€"}
FITTINGS_250 = "🔁 Фасонка +250%"
DISCOUNTS = list(range(0, 45, 5))

COLLECT_KEYBOARD = {"keyboard": [[{"text": DONE}], [{"text": CANCEL}]], "resize_keyboard": True}
KIND_KEYBOARD = {"keyboard": [[{"text": IS_INVOICE}], [{"text": IS_KP}], [{"text": CANCEL}]], "resize_keyboard": True}
DISCOUNT_KEYBOARD = {"keyboard": [[{"text": f"Скидка {d}%"} for d in DISCOUNTS[i:i + 3]] for i in range(0, len(DISCOUNTS), 3)]
                     + [[{"text": OWN_DISCOUNT}], [{"text": CANCEL}]], "resize_keyboard": True}
CHECK_KEYBOARD = {"keyboard": [[{"text": READ_OK}], [{"text": b} for b in CURRENCY_BUTTONS], [{"text": SWAP}],
                                [{"text": IS_INVOICE}, {"text": IS_KP}], [{"text": CANCEL}]], "resize_keyboard": True}
REVIEW_KEYBOARD = {"keyboard": [[{"text": APPLY}], [{"text": FITTINGS_250}], [{"text": CANCEL}]], "resize_keyboard": True}

SOURCES = os.path.join(os.path.expanduser("~/megaplan-crm"), "deal_price_sources.py")


def run_sources(command, payload, python, timeout=300):
    try:
        out = subprocess.run([python, SOURCES, command], input=json.dumps(payload, ensure_ascii=False),
                             capture_output=True, text=True, timeout=timeout, cwd=os.path.dirname(SOURCES))
        return json.loads((out.stdout or "").strip().splitlines()[-1])
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def start(io, chat_id, deal_id):
    if not deal_id:
        io.send(chat_id, "Сначала откройте сделку, для которой нужны цены.")
        return
    io.update(chat_id, pending="deal_price_docs", price_docs=[], price_deal_id=str(deal_id), price_proposals=None)
    io.send(chat_id, f"📎 Сделка №{deal_id}: пришлите КП и счета поставщиков — PDF, Excel или фото, можно несколько, "
                     "по этому объекту или по другим с похожими позициями.\n"
                     "• Счёт → наша закупка.\n• КП → цена продажи; спрошу нашу скидку, закупку посчитаю.\n"
                     f"Когда всё — «{DONE}». Можно нажать и без файлов: подберу по прайсам Daichi/Hogart "
                     "и фасонку по площади.", COLLECT_KEYBOARD)


def read_document(io, path, python):
    """The document model first (TASK-20261124-15: OCR+regex failed on a scanned 16-page КП), checked
    row by row; the arithmetic parser only when the model gives nothing usable."""
    if hasattr(io, "read_model"):
        try:
            read = io.read_model(path)
        except Exception as exc:  # noqa: BLE001
            read = {"ok": False, "error": str(exc)}
        if read.get("ok"):
            return {**read, "file": os.path.basename(path), "reader": "модель"}
    read = run_sources("read", {"path": path}, python)
    return {**read, "reader": "разбор текста"} if read.get("ok") else read


def add_file(io, chat_id, state, path, python):
    read = read_document(io, path, python)
    if not read.get("ok"):
        io.send(chat_id, f"Файл не прочитан: {read.get('error')}. Пришлите другой или «{DONE}».", COLLECT_KEYBOARD)
        return
    # Files are read in parallel workers: take the list as it is now, not as it was on arrival.
    state = io.state(chat_id) if hasattr(io, "state") else state
    docs = list(state.get("price_docs") or [])
    doc = {"path": path, "file": read.get("file"), "kind": read.get("kind"), "supplier": read.get("supplier"),
           "rows": read.get("rows") or [], "discount": None, "currency": read.get("currency") or "RUB",
           "variants": read.get("variants") or [], "rejected": read.get("rejected") or [],
           "brand": read.get("brand") or ""}
    docs.append(doc)
    if not doc["rows"]:
        io.update(chat_id, pending="deal_price_docs", price_docs=docs)
        io.send(chat_id, f"⚠️ {doc['file']}: строк с ценами не нашёл (сумма = кол-во × цена ни в одной строке). "
                         "Если это скан — пришлите почётче.", COLLECT_KEYBOARD)
        return
    if len(doc["variants"]) > 1:
        io.update(chat_id, pending="deal_price_variant", price_docs=docs)
        io.send(chat_id, f"📄 {doc['file']}: в документе {len(doc['variants'])} варианта комплектации. Какой взять?",
                variant_keyboard(doc["variants"]))
        return
    io.update(chat_id, pending="deal_price_check", price_docs=docs)
    io.send(chat_id, check_text(doc), CHECK_KEYBOARD)


ALL_VARIANTS = "Все варианты"


def variant_keyboard(variants):
    return {"keyboard": [[{"text": f"Вариант: {v}"}] for v in variants] + [[{"text": ALL_VARIANTS}], [{"text": CANCEL}]],
            "resize_keyboard": True}


def _money(value, code):
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") + " " + SIGN.get(code, code)


def check_text(doc):
    """24.11: the owner sees what was read — type, currency, qty × price = sum — before anything is matched."""
    code = doc.get("currency") or "RUB"
    kind = {"kp": "КП (цена продажи)", "invoice": "счёт (наша закупка)"}.get(doc.get("kind"), "тип не понял")
    lines = [f"📄 {doc.get('file')}: {kind}, {doc.get('supplier') or 'поставщик не найден'}, валюта {code}.",
             f"Прочитано строк: {len(doc['rows'])}. Проверьте первые:"]
    for r in doc["rows"][:6]:
        lines.append(f"• {r['name']} — {r['qty']:g} × {_money(r['price'], code)} = {_money(r['amount'], code)}")
    if doc.get("rejected"):
        lines.append(f"Не взято строк: {len(doc['rejected'])} (кол-во × цена ≠ сумма или нет цены).")
    lines.append(f"Если валюта или колонки не те — кнопки ниже. Всё верно — «{READ_OK}».")
    return "\n".join(lines)


def after_check(io, chat_id, docs):
    doc = docs[-1]
    if doc["kind"] is None:
        io.update(chat_id, pending="deal_price_kind", price_docs=docs)
        io.send(chat_id, "Это счёт или КП?", KIND_KEYBOARD)
    elif doc["kind"] == "kp":
        io.update(chat_id, pending="deal_price_discount", price_docs=docs)
        io.send(chat_id, f"🏷 Какая наша скидка от этого КП ({doc['file']})?", DISCOUNT_KEYBOARD)
    else:
        io.update(chat_id, pending="deal_price_docs", price_docs=docs)
        io.send(chat_id, f"📄 Беру как закупку. Ещё файлы или «{DONE}».", COLLECT_KEYBOARD)


def handle_text(io, chat_id, state, value, ledger_of, python, run_job):
    """True when the text belonged to this flow."""
    pending = state.get("pending") or ""
    if value == BUTTON:
        start(io, chat_id, state.get("current_deal_id"))
        return True
    if not pending.startswith("deal_price_"):
        return False
    docs = list(state.get("price_docs") or [])
    if value == CANCEL:
        io.update(chat_id, pending=None, price_docs=None, price_proposals=None)
        io.send(chat_id, "Подбор цен по документам отменён. В сделке ничего не менялось.", io.deal_keyboard)
        return True
    if pending == "deal_price_variant" and docs:
        doc = docs[-1]
        if value == ALL_VARIANTS or value.startswith("Вариант: ") and value[9:] in doc.get("variants", []):
            if value != ALL_VARIANTS:
                import supplier_document_model
                docs[-1] = supplier_document_model.only_variant(doc, value[9:])
            io.update(chat_id, pending="deal_price_check", price_docs=docs)
            io.send(chat_id, check_text(docs[-1]), CHECK_KEYBOARD)
        else:
            io.send(chat_id, "Выберите вариант кнопкой.", variant_keyboard(doc.get("variants") or []))
        return True
    if pending == "deal_price_check" and docs:
        doc = dict(docs[-1])
        if value == READ_OK:
            after_check(io, chat_id, docs)
            return True
        if value in CURRENCY_BUTTONS:
            doc["currency"] = CURRENCY_BUTTONS[value]
        elif value == SWAP:
            doc["rows"] = [{**r, "qty": r["price"], "price": r["qty"]} for r in doc["rows"]]
        elif value in (IS_INVOICE, IS_KP):
            doc["kind"] = "invoice" if value == IS_INVOICE else "kp"
        else:
            io.send(chat_id, "Поправьте кнопками ниже или нажмите «✅ Прочитано верно».", CHECK_KEYBOARD)
            return True
        docs[-1] = doc
        io.update(chat_id, pending="deal_price_check", price_docs=docs)
        io.send(chat_id, check_text(doc), CHECK_KEYBOARD)
        return True
    if pending == "deal_price_kind" and value in (IS_INVOICE, IS_KP) and docs:
        docs[-1]["kind"] = "invoice" if value == IS_INVOICE else "kp"
        if docs[-1]["kind"] == "kp":
            io.update(chat_id, pending="deal_price_discount", price_docs=docs)
            io.send(chat_id, "Какая наша скидка от этого КП?", DISCOUNT_KEYBOARD)
        else:
            io.update(chat_id, pending="deal_price_docs", price_docs=docs)
            io.send(chat_id, f"Беру как закупку. Ещё файлы или «{DONE}».", COLLECT_KEYBOARD)
        return True
    if pending == "deal_price_discount" and docs:
        if value == OWN_DISCOUNT:
            io.send(chat_id, "Напишите скидку числом, например 12 или 17,5.", {"remove_keyboard": True})
            return True
        m = re.fullmatch(r"(?:скидка\s*)?(\d{1,2}(?:[.,]\d+)?)\s*%?", value.strip(), re.I)
        if not m or float(m.group(1).replace(",", ".")) > 90:
            io.send(chat_id, "Скидку — кнопкой или числом от 0 до 90.", DISCOUNT_KEYBOARD)
            return True
        docs[-1]["discount"] = float(m.group(1).replace(",", "."))
        io.update(chat_id, pending="deal_price_docs", price_docs=docs)
        io.send(chat_id, f"Скидка {docs[-1]['discount']:g}% записана. Ещё файлы или «{DONE}».", COLLECT_KEYBOARD)
        return True
    if value == DONE and pending == "deal_price_docs":
        if not any(d.get("rows") for d in docs):
            # Without documents the bot still tries supplier price lists (Daichi/Hogart) and fittings by area.
            io.send(chat_id, "Документов с ценами нет — подбираю по прайсам Daichi/Hogart и фасонку по площади.")
        run_job(lambda: build_proposals(io, chat_id, state, docs, ledger_of, python, 3.0))
        return True
    if pending == "deal_price_review" and value == FITTINGS_250:
        run_job(lambda: build_proposals(io, chat_id, state, docs, ledger_of, python, 3.5))
        return True
    if pending == "deal_price_review" and value == APPLY:
        run_job(lambda: apply(io, chat_id, state, python))
        return True
    # 24.11: free text inside this flow went to the model, which «порет чушь». Stay here.
    keyboards = {"deal_price_docs": COLLECT_KEYBOARD, "deal_price_kind": KIND_KEYBOARD,
                 "deal_price_discount": DISCOUNT_KEYBOARD, "deal_price_review": REVIEW_KEYBOARD}
    io.send(chat_id, "Сейчас идёт подбор цен по документам — ответьте кнопкой ниже. Если документ прочитан неверно, "
                     "нажмите «❌ Отмена» и пришлите его заново: после чтения я покажу строки, валюту и колонки для проверки.",
            keyboards.get(pending, COLLECT_KEYBOARD))
    return True


def build_proposals(io, chat_id, state, docs, ledger_of, python, fitting_markup):
    deal_id = state.get("price_deal_id")
    ledger = ledger_of(deal_id)
    if ledger is None:
        io.send(chat_id, "Не удалось прочитать позиции сделки из Мегаплана. Повторите «✅ Все файлы загружены» чуть позже.",
                COLLECT_KEYBOARD)
        return
    result = run_sources("propose", {"ledger": ledger, "documents": docs, "fitting_markup": fitting_markup}, python)
    if not result.get("ok"):
        io.send(chat_id, f"Подбор не выполнен: {result.get('error')}", COLLECT_KEYBOARD)
        return
    proposals = result.get("proposals") or []
    io.update(chat_id, pending="deal_price_review", price_docs=docs, price_proposals=proposals,
              price_fitting_markup=fitting_markup)
    io.send(chat_id, summary(deal_id, proposals, result.get("skipped") or [], fitting_markup),
            REVIEW_KEYBOARD if proposals else COLLECT_KEYBOARD)
    if proposals:
        io.send_table(chat_id, deal_id, proposals, result.get("skipped") or [])


def summary(deal_id, proposals, skipped, fitting_markup):
    prices = sum(1 for p in proposals if "sell_price" in p)
    costs = sum(1 for p in proposals if "cost_material" in p)
    area = sum(1 for p in proposals if "по площади" in p.get("mark", ""))
    lines = [f"Сделка №{deal_id}: предлагаю цен продажи {prices}, закупок {costs}"
             + (f" (по площади — {area}, фасонка +{round((fitting_markup - 1) * 100):g}%)" if area else "") + "."]
    for p in proposals[:25]:
        parts = ([f"{p['sell_price']:,.2f} ₽".replace(",", " ")] if "sell_price" in p else []) + \
                ([f"закупка {p['cost_material']:,.2f} ₽".replace(",", " ")
                  + (f" (была {float(p.get('old_cost') or 0):,.2f})".replace(",", " ") if p.get("replace_cost") else "")]
                 if "cost_material" in p else [])
        lines.append(f"• {p['name']} — {', '.join(parts)}")
    if len(proposals) > 25:
        lines.append(f"… ещё {len(proposals) - 25} — в таблице.")
    if skipped:
        lines.append(f"Без предложения: {len(skipped)} (в таблице с причиной).")
    replaced = sum(1 for p in proposals if p.get("replace_cost"))
    if replaced:
        lines.append(f"Закупка по счёту поставщика заменит прежнюю (расчётную) в {replaced} строках.")
    lines.append(f"В сделку ничего не записано. «{APPLY}» — записать; уже стоящие цены продажи не трогаю.")
    return "\n".join(lines)


def apply(io, chat_id, state, python):
    proposals = state.get("price_proposals") or []
    deal_id = state.get("price_deal_id")
    result = io.apply_rows({"deal_id": deal_id, "rows": proposals})
    io.update(chat_id, pending=None, price_docs=None, price_proposals=None)
    if not result.get("ok"):
        io.send(chat_id, f"Запись не завершена: {result.get('error')}. Проверьте сделку №{deal_id} перед повтором.",
                io.deal_keyboard)
        return
    applied, kept = result.get("applied") or [], result.get("kept") or []
    io.send(chat_id, f"✅ Сделка №{deal_id}: записано позиций {len(applied)}; не тронуто {len(kept)} "
                     f"(цена уже стояла или позицию изменили). Источники — в комментарии сделки.", io.deal_keyboard)
