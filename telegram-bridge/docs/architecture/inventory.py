"""Static inventory. Never imports the bot, reads configuration or calls APIs."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BRIDGE = ROOT.parents[1] / 'bridge.py'

def literals(node):
    return sorted({n.value for n in ast.walk(node)
                   if isinstance(n, ast.Constant) and isinstance(n.value, str)})

def scan(source):
    tree = ast.parse(source)
    functions = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    menus = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and 'KEYBOARD' in target.id:
                    labels = []
                    for d in ast.walk(node.value):
                        if isinstance(d, ast.Dict):
                            for k, v in zip(d.keys, d.values):
                                if isinstance(k, ast.Constant) and k.value == 'text' and isinstance(v, ast.Constant):
                                    labels.append(v.value)
                    menus.append({'name': target.id, 'line': node.lineno, 'buttons': labels})
    writes, branches, calls = [], [], []
    for name, fn in functions.items():
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                called = node.func.id
                if called in functions:
                    calls.append({'from': name, 'to': called, 'line': node.lineno})
                if called == 'update_deal_ui_state':
                    writes.append({'function': name, 'line': node.lineno,
                                   'fields': {kw.arg: ast.unparse(kw.value) for kw in node.keywords}})
            if isinstance(node, ast.If):
                expr = ast.unparse(node.test)
                if any(term in expr for term in ('pending', 'value', 'text', 'reply_to', 'document', 'is_installer', 'is_owner')):
                    branches.append({'function': name, 'line': node.lineno, 'condition': expr})
    return {'sha256': hashlib.sha256(source.encode()).hexdigest(),
            'functions': {k: {'start': v.lineno, 'end': v.end_lineno} for k,v in functions.items()},
            'menus': menus, 'state_writes': writes, 'branches': branches, 'calls': calls}

def render(data):
    out = ['# Статическая карта текущего bridge.py', '',
           'Сгенерировано inventory.py без импорта бота и без обращения к внешним системам.',
           'Это индекс для ручной трассировки, не доказательство полноты достижимых маршрутов.',
           'Динамические клавиатуры, условия в вызываемых модулях и семантика ИИ требуют отдельной проверки.',
           '', 'SHA-256 исходника: `' + data['sha256'] + '`', '', '## Меню']
    for menu in data['menus']:
        out += ['', f"### {menu['name']} — строка {menu['line']}", '']
        out += ['- ' + str(x) for x in menu['buttons']]
    out += ['', '## Изменения состояния диалога', '']
    for entry in data['state_writes']:
        fields = '; '.join(f'{k}={v}' for k,v in entry['fields'].items())
        out.append(f"- Строка {entry['line']}, `{entry['function']}`: `{fields}`")
    out += ['', '## Условия ветвления (синтаксический индекс)', '']
    for entry in data['branches']:
        out.append(f"- Строка {entry['line']}, `{entry['function']}`: `{entry['condition']}`")
    return '\n'.join(out) + '\n'

if __name__ == '__main__':
    data = scan(BRIDGE.read_text(encoding='utf-8'))
    (ROOT / 'INVENTORY.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT / 'CURRENT_CODE_MAP.md').write_text(render(data), encoding='utf-8')
    print(json.dumps({k: len(data[k]) for k in ('functions','menus','state_writes','branches','calls')}))
