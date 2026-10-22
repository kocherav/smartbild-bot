import sys
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();auth=wait_budget(v1_auth,a);D=ROOT/'evidence/finish_all';items=wait_budget(megaplan_operations,a,auth);atomic(D/'remote_salary_rejection_check.json',items)
with locked(REG):
 j=json.loads(JOURNAL.read_text());p=j['operations']['1b16d0237f2a93449c9d1637'];assert p['state']=='creating' and p['operation_type']=='35';assert not select_existing(items,p);atomic(D/'salary_rejected_attempt.json',p)
 p.update(state='rejected_no_remote_operation',operation_type='25',rejection_reason='Тип35 не корреспондирует с банковским счётом/карточкой. Выплата отражается как компания/денежный расход с нулевым начислением, категория зарплата сохранена.');atomic(JOURNAL,j)
print('Confirmed no salary operation created; safe corrected retry')
