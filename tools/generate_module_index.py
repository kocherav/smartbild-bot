#!/usr/bin/env python3
"""Generate a static source index without importing project modules."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ("telegram-bridge", "megaplan-crm", "hogart-scraper", "daichi-scraper")

FALLBACK_SUMMARIES = {
    "telegram-bridge/bridge.py": "Главный Telegram polling-процесс, меню, обработчики сообщений и композиция бизнес-сценариев.",
    "telegram-bridge/build_installer_report_mockups.py": "Создание демонстрационных XLSX-макетов отчёта монтажника и сверки владельца.",
    "megaplan-crm/closing_documents.py": "Общие функции оформления закрывающих DOCX-документов.",
    "megaplan-crm/specification_unit_fixture.py": "Фикстура единиц измерения спецификации для совместимости документов.",
    "hogart-scraper/dashboard/matching_store.py": "SQLite-очередь кандидатов, решений и исполнения сопоставления товаров.",
    "hogart-scraper/dashboard/model.py": "Построение денежной модели и проекции данных для веб-пульта.",
    "hogart-scraper/dashboard/shipment_procurement.py": "Проверка покрытия отгрузки подтверждёнными закупками.",
    "hogart-scraper/dashboard/supplier_documents.py": "Поиск, разбор координат и рендеринг страниц документов поставщика.",
    "hogart-scraper/finance/mail_evidence.py": "Декодирование и нормализация почтовых доказательств финансовой сверки.",
    "hogart-scraper/finance/sent_evidence.py": "Декодирование доказательств ранее отправленных сообщений.",
}


def category(path: Path) -> str:
    value = path.as_posix()
    if "/docs/architecture/" in value and path.suffix == ".py":
        return "Архитектурный инструмент или исторический снимок"
    if "/finance/tools/" in value:
        return "Операторская/историческая финансовая утилита"
    if path.name.startswith("test_") or "/tests/" in value:
        return "Тест"
    if "/dashboard/static/" in value:
        return "Клиент веб-пульта"
    if "/dashboard/" in value:
        return "Сервер/модель веб-пульта"
    if "/finance/" in value:
        return "Финансовый контур"
    return "Рабочий модуль"


def python_info(path: Path) -> tuple[str, str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as exc:
        return f"Ошибка разбора: {exc.msg}", "—"
    docs = (ast.get_docstring(tree) or "").strip().splitlines()
    rel = path.relative_to(ROOT).as_posix()
    if docs:
        summary = docs[0].strip()
    elif rel in FALLBACK_SUMMARIES:
        summary = FALLBACK_SUMMARIES[rel]
    else:
        label = path.stem.replace("_", " ").replace("-", " ")
        summary = f"Узкоспециализированная утилита «{label}»; интерфейс перечислен справа."
    names = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            names.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            names.append(node.name)
    public = ", ".join(f"`{name}`" for name in names[:12]) or "—"
    if len(names) > 12:
        public += f" (+{len(names) - 12})"
    return summary.replace("|", "\\|"), public


def main() -> None:
    lines = [
        "# Полный индекс модулей", "",
        "Создан `tools/generate_module_index.py` статическим разбором исходников.",
        "Модули не импортируются, конфигурация и сеть не читаются.", "",
    ]
    totals = {"py": 0, "js": 0}
    for project in PROJECTS:
        lines += [f"## `{project}`", "", "| Файл | Тип | Назначение | Публичный интерфейс |", "|---|---|---|---|"]
        paths = sorted(p for p in (ROOT / project).rglob("*") if p.is_file() and p.suffix in {".py", ".js", ".mjs"})
        for path in paths:
            rel = path.relative_to(ROOT)
            if path.suffix == ".py":
                summary, public = python_info(path)
                totals["py"] += 1
            else:
                summary = f"JavaScript-модуль: {path.stem.replace('_', ' ').replace('-', ' ')}."
                public = "См. exports/обработчики в исходнике"
                totals["js"] += 1
            lines.append(f"| `{rel.as_posix()}` | {category(rel)} | {summary} | {public} |")
        lines.append("")
    lines += ["## Итого", "", f"- Python: {totals['py']}", f"- JavaScript/MJS: {totals['js']}", ""]
    (ROOT / "docs" / "MODULE_INDEX.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
