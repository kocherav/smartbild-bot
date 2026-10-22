"""Create a replacement seller version without changing agreed payment terms."""
import json
import os
import subprocess
import tempfile
from pathlib import Path
from docx import Document
from contract_invoice import latest_contract, document_text
from generate_contract import LIBREOFFICE_APPIMAGE, LIBREOFFICE_DEPS, safe_filename_stem
from seller_documents import selected_seller, apply_ip_supplier
from megaplan_api import MegaplanAPI

def build(deal_id, source_path=None):
    api = MegaplanAPI()
    if source_path:
        selected, source = {'id': None}, str(source_path)
    else:
        selected, source = latest_contract(api, deal_id)
    if Path(source).suffix != '.docx':
        raise ValueError('Для сохранения условий требуется действующий договор DOCX')
    seller = selected_seller(deal_id)
    document = Document(source)
    original = document_text(source)
    apply_ip_supplier(document, seller)
    directory = Path(tempfile.mkdtemp(prefix=f'contract-{deal_id}-'))
    name = safe_filename_stem(f'Договор №1.{deal_id}-1709-2026 — ИП Кочержинский — БАРИОН', 170)
    signed = directory / (name + ' — подписанный.docx')
    unsigned = directory / (name + '.docx')
    document.save(signed)
    profile = tempfile.mkdtemp(prefix='libreoffice-profile-')
    env = dict(os.environ)
    env['LD_LIBRARY_PATH'] = str(LIBREOFFICE_DEPS)
    subprocess.run([str(LIBREOFFICE_APPIMAGE), '--headless', '--nologo', '--nodefault', '--nolockcheck',
                    f'-env:UserInstallation=file://{profile}', '--convert-to', 'pdf', '--outdir', str(directory),
                    str(signed)], env=env, check=True, capture_output=True, timeout=120)
    pdf = signed.with_suffix('.pdf')
    extracted = document_text(str(pdf))
    for expected in (seller['inn'], seller['ogrnip'], seller['accounts'][0]):
        assert expected in extracted, expected
    assert 'КЛИВЭЛ' not in extracted
    # Check every contractual payment against the original text.
    from contract_invoice import parse_contract
    for clause in ('6.4.1', '6.4.2', '6.4.3'):
        assert parse_contract(original, clause)['amount'] == parse_contract(extracted, clause)['amount']
    for node in document.element.xpath('.//w:drawing | .//w:pict'):
        node.getparent().remove(node)
    document.save(unsigned)
    return {'ok': True, 'docx_path': str(unsigned), 'pdf_path': str(pdf), 'source_file_id': selected['id']}

if __name__ == '__main__':
    print(json.dumps(build('888'), ensure_ascii=False))
