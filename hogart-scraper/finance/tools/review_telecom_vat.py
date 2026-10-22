import json
from pathlib import Path
R=Path(__file__).resolve().parents[1];D=R/'evidence/remaining_oct6';r=json.loads((R/'reports/ledger.json').read_text());out=[]
for x in r:
 if x['id'][:10] not in ['bf4ac5aac1','23d4d91681','ced006e855','0520bb1207']:continue
 source='megafon_may.txt' if x['id'].startswith('bf4') else 'megafon_july.txt' if x['id'].startswith('23d') else 'd113ec83ca4c91cf4ec5551572e70cb7f9b7d2631b81e32549d4e07ebaef71c9.txt' if x['id'].startswith('ced') else '1af7d697f43a909f62797e9239d4e4dc82a66621449986b67adbadc21d2c8469.txt'
 t=(D/source).read_text();assert '22%' in t and 'ИНСИС' in t
 out.append(dict(id=x['id'],inn=x['inn'],date=x['date'],amount_cents=x['amount_cents'],source=str((D/source).resolve()),remove_flags=['Проверить указанную ставку НДС по первичному документу'],evidence='Ставка проверена по документам поставщика по тому же договору/лицевому счёту ИНСИС:22%. Банковское назначение с20% сохранено без изменения. Это пополнение лицевого счёта; сумма платежа не приравнена к месячному начислению и налоговый вычет автоматически не создаётся.'))
(D/'vat_review.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print('reviewed',len(out))
