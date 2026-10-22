"""New documents must be read, never substituted with historical pilot rows."""
import os
import tempfile
import unittest
import zipfile
from unittest.mock import patch
import installer_report_intake as intake

REPORT = '''Сделка 887 все по таблице выполненно-80.500
Доп работа(переделка всех воздуховодов,дренаж от внешних блоков,демонтаж/монтаж шкафа)-10.000
Сделка 894 все по таблице выполненно-69.200
Сделка 890 по таблице 53.400
Материал-10.000(Кфлекс,шпильки,траверсы,кронштейны и всякая мелочь)
Монтаж кондиционера в зоовете-20.000
Дитейлинг
Перекладка кабелей на потолке-10.000
Монтаж теплого пола в санузле-3.000
Монтаж автомата 160А-2.500
Монтаж конвекторов 6шт-30.000
Монтаж труб рехау 20-26мх350р=9.100
Монтаж труб рехау 16-12мх300р=3.600
Итого301.300
Зп виталик-63.000
Страховка нива-11.000
Итого:227.300'''

class IntakeTests(unittest.TestCase):
    def session(self,text=REPORT):
        with patch.object(intake,'pdf_text',return_value=text):
            return intake.build_session('/tmp/Зп_Артем_261012_065532.pdf')

    def test_new_report_not_restricted_to_pilot_markers(self):
        s=self.session()
        self.assertEqual(s['net_total'],227300)
        self.assertEqual(s['declared_total'],227300)
        self.assertEqual(s['required_tables'],3)
        self.assertEqual([x['deal_id'] for x in s['table_requests']],['887','894','890'])
        self.assertEqual(s['report_date'],'12.10.2026')
        self.assertEqual(len([r for r in s['report_lines'] if r['sign']]),14)
        material=next(r for r in s['report_lines'] if r['kind']=='Материал')
        self.assertEqual((material['amount'],material['deal_id']),(10000,'890'))
        zoo=next(r for r in s['report_lines'] if 'зоовете' in r['source'])
        self.assertIsNone(zoo['deal_id'])
        detail=next(o for o in s['objects'] if o['name']=='Дитейлинг')
        self.assertIsNone(detail['deal_id'])
        pipe=next(r for r in s['report_lines'] if '26м' in r['source'])
        self.assertEqual((pipe['qty'],pipe['unit'],pipe['rate'],pipe['amount']),(26,'м',350,9100))

    def test_changed_value_with_old_markers_reads_actual_input(self):
        s=self.session('Монтаж кондиционера Илья-17.000\nСлава по таблице-84.700\nИтого101.700')
        self.assertEqual(s['net_total'],101700)
        self.assertEqual(s['required_tables'],1)
        self.assertEqual(len(s['report_lines']),3)

    def test_docx_native_paragraphs(self):
        from xml.sax.saxutils import escape
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'Отчет_261012.docx')
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:drawing><offset>-2400300</offset></w:drawing></w:p>'+''.join('<w:p><w:r><w:t>'+escape(x)+'</w:t></w:r></w:p>' for x in REPORT.splitlines())+'</w:body></w:document>')
            s=intake.build_session(path)
        self.assertEqual(s['net_total'],227300)
        self.assertEqual(s['required_tables'],3)

    def test_wrapped_pdf_lines(self):
        s=self.session(REPORT.replace('выполненно','\nвыполненно').replace('всех воздуховодов,','всех\nвоздуховодов,').replace('траверсы','траверс\nы'))
        self.assertEqual(s['net_total'],227300)
        self.assertEqual(len([r for r in s['report_lines'] if r['sign']]),14)

    def test_unknown_row_is_retained_and_blocks_unreviewed_report(self):
        s=self.session('Сделка 887\nМонтаж-5.000\nЕщё непонятная работа без суммы\nИтого5.000')
        self.assertTrue(any('непонятная' in r['source'] for r in s['report_lines']))
        self.assertTrue(any(e['amount'] is None for e in s['exceptions']))

    def test_gross_discrepancy_not_hidden_by_matching_net(self):
        s=self.session(REPORT.replace('Итого301.300','Итого302.300'))
        self.assertTrue(any(e['type']=='recognition' for e in s['exceptions']))

    def test_source_amount_controls_not_model_or_template(self):
        s=self.session(REPORT.replace('53.400','54.400'))
        self.assertEqual(s['net_total'],228300)
        self.assertIsNone(s['payable_amount'])
        self.assertTrue(any(e['type']=='discrepancy' for e in s['exceptions']))

    def test_ocr_spaced_total_is_read_and_review_required(self):
        text=intake.ExtractedText(REPORT.replace('Итого:227.300','Итого:22 7.300'))
        text.ocr_pages=[1]
        s=self.session(text)
        self.assertEqual(s['declared_total'],227300)
        self.assertEqual(s['ocr_pages'],[1])
        self.assertTrue(any(e['type']=='recognition' for e in s['exceptions']))

    def test_formula_mismatch_requires_review(self):
        s=self.session(REPORT.replace('26мх350р=9.100','26мх350р=9.200'))
        self.assertTrue(any(e['type']=='recognition' and 'расценка' in e['reason'] for e in s['exceptions']))

    def test_all_three_tables_route_to_objects_with_actual_contents(self):
        import bridge
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory() as directory:
            paths=[]
            for deal,amount in [('887',80500),('894',69200),('890',53400)]:
                book=Workbook();sheet=book.active
                sheet.append(['№','Работа','Ед','План','Цена','Всего','Выполнено'])
                sheet.append([1,'Работа '+deal,'шт',1,amount,amount,amount])
                sheet.append(['Итого',None,None,None,None,None,amount])
                path=os.path.join(directory,deal+'.xlsx');book.save(path);book.close();paths.append(path)
            def run(path,table_paths=None):return {'ok':True,'session':intake.build_session(path,table_paths)}
            with patch.object(intake,'pdf_text',return_value=REPORT),patch.object(intake,'FACT_REGISTRY',os.path.join(directory,'facts.json')),patch.object(bridge,'run_installer_report_intake',side_effect=run),patch.object(bridge,'send_message') as send,patch.object(bridge,'update_deal_ui_state') as update,patch.object(bridge,'INSTALLER_CHAT_IDS',set()):
                bridge.process_installer_report('fake','test','/tmp/Отчет_261012.pdf')
                state=update.call_args.kwargs
                self.assertEqual(state['pending'],'installer_report_tables')
                session=state['installer_report'];session['table_paths']=paths
                bridge.finish_installer_report_files('fake','test',session)
                self.assertEqual(update.call_args.kwargs['pending'],'installer_report_objects')
                final=update.call_args.kwargs['installer_report']
                self.assertEqual(final['attached_tables'],3)
                self.assertEqual(final['net_total'],227300)
                tables=[e for e in final['exceptions'] if e['type']=='table']
                self.assertEqual([e['completion_sum'] for e in tables],[80500,69200,53400])
                self.assertTrue(all(e['completion_matches_report'] for e in tables))
                self.assertFalse(final['approved'])

    def test_failure_keeps_source_and_retry_uses_same_file(self):
        import bridge
        with tempfile.TemporaryDirectory() as directory:
            path=os.path.join(directory,'file.pdf');open(path,'w').close()
            with patch.object(bridge,'run_installer_report_intake',return_value={'ok':False,'error':'test failure'}),patch.object(bridge,'send_message') as send,patch.object(bridge,'update_deal_ui_state') as update:
                bridge.process_installer_report('fake','test',path)
                state=update.call_args.kwargs
                self.assertEqual(state['installer_report_failure']['source_path'],path)
                self.assertIn('🔄 Повторить разбор',str(send.call_args))
            with patch.object(bridge,'current_deal_ui_state',return_value=state),patch.object(bridge,'process_installer_report') as process:
                bridge.handle_installer_ui('fake','test','🔄 Повторить разбор')
                process.assert_called_once_with('fake','test',path)

    def test_pasted_report_is_saved_and_parsed_in_file_state(self):
        import bridge
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(bridge,'INCOMING_DIR',directory),patch.object(bridge,'current_deal_ui_state',return_value={'pending':'installer_report_file'}),patch.object(bridge,'process_installer_report') as process:
                bridge.handle_installer_ui('fake','test',REPORT)
                path=process.call_args.args[2]
                self.assertEqual(intake.build_session(path)['net_total'],227300)

    def test_scanned_page_does_not_hide_following_native_page(self):
        import installer_report_text as reader
        from types import SimpleNamespace
        fake=SimpleNamespace(pages=[{'/Contents':1},{'/Contents':1},{}])
        with patch('pypdf.PdfReader',return_value=fake),patch.object(reader.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='\fРабота-500\f\f')),patch.object(reader,'ocr_page',return_value='Сделка 887\nМонтаж-1000') as ocr:
            text,pages=reader.extract_pdf('fixture.pdf')
            self.assertIn('Монтаж-1000',text);self.assertIn('Работа-500',text)
            self.assertEqual(pages,[1]);ocr.assert_called_once_with('fixture.pdf',1)

    def test_work_without_amount_is_not_silently_a_heading(self):
        s=self.session('Сделка 887\nМонтаж-1000\nПеределка воды\nТакелаж\nИтого1000')
        for word in ('Переделка воды','Такелаж'):
            self.assertTrue(any(e['source']==word and e['amount'] is None for e in s['exceptions']))

    def test_word_is_allowed_at_both_document_entry_routes(self):
        import bridge,ast,inspect
        self.assertIn('.docx',bridge.INSTALLER_REPORT_EXTENSIONS)
        tree=ast.parse(inspect.getsource(bridge))
        # Both the home entry and explicit file state use the same supported formats.
        checks=[n for n in ast.walk(tree) if isinstance(n,ast.Compare) and isinstance(n.left,ast.Name) and n.left.id=='original_ext' and any(isinstance(c,ast.Name) and c.id=='INSTALLER_REPORT_EXTENSIONS' for c in n.comparators)]
        self.assertEqual(len(checks),2)

    def test_object_mapping_resolves_its_rows_together(self):
        import bridge
        s=self.session();s['fix_object']='Дитейлинг'
        with patch.object(bridge,'current_deal_ui_state',return_value={'pending':'installer_report_fix_deal','installer_report':s}),patch.object(bridge,'update_deal_ui_state') as update,patch.object(bridge,'send_message'):
            bridge.handle_deal_ui('fake','test','861',_background=True)
        saved=update.call_args.kwargs['installer_report']
        rows=[e for e in saved['exceptions'] if e['object']=='Дитейлинг']
        self.assertEqual(len(rows),6)
        self.assertTrue(all(e['deal_id']=='861' and e.get('resolution') for e in rows))
        self.assertTrue(any(e['object']=='зоовете' and not e.get('resolution') for e in saved['exceptions']))
