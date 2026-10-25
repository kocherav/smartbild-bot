# SmartBild Kids Internet (KidsBot)

Ограничение интернета детским устройствам по расписанию: Telegram-бот на VPS +
firewall на MikroTik hAP ac² (RouterOS 6.49.22). Полный handoff с инфраструктурой,
расписанием и командами проверки — архив `SmartBild_KidsBot_HANDOFF_2026-10-24.zip`
(в Git не хранится). Здесь лежит исходный код, который реально работает.

| Файл | Где живёт |
|---|---|
| `vps/app.py` | `/opt/smartbild-kidsbot/app.py` |
| `vps/config.template.json` | `/etc/smartbild-kidsbot/config.json` (с секретами, вне Git) |
| `vps/smartbild-kidsbot.service` | systemd unit |
| `vps/caddy-route.caddy` | блок внутри сайта `claude.smartbild.su` |
| `mikrotik/sbkb-scripts.rsc.in` | скрипты `sbkb-state-poll`, `sbkb-lease-sync` (шаблон без секрета) |
| `mikrotik/sbkb-schedulers.rsc`, `sbkb-firewall.rsc` | планировщики и 12 базовых правил |

Первый коммит каталога — версия 2.0.0 ровно как развёрнута; следующий — исправление 2.1.0.

## Почему блокировка работала криво (2.0.0)

1. **Спящее устройство выпадало из-под контроля.** Сервер отдавал в `KIDS` только
   устройства с DHCP `bound`. MacBook засыпает → lease `waiting` → IP удаляется из
   `kids_devices` → после пробуждения интернет есть, пока lease-sync (1 мин) и
   state-poll (15 с) не вернут его обратно. Плюс открытые соединения спящего
   устройства в это время вообще не фильтруются (в диагностике 14.10: 13 соединений
   с `.10`, при этом `.10` в списке нет, а drop-счётчики растут — правила рабочие).
2. **Одобренное продление пропадало**, если устройство уснуло (тот же фильтр `bound`),
   а предупреждение с кнопкой не приходило для спящего устройства.
3. **Блокировка по IP обходится.** Достаточно вручную прописать на ноутбуке другой IP
   из `192.168.10.0/24` — адреса нет в `kids_devices`, интернет без ограничений.
4. **Каждые 15 секунд списки удалялись целиком и создавались заново.** Между
   remove и add `kids_devices` пустой — короткое окно без блокировки на каждом опросе;
   у продлённого устройства в этот момент рвались пакеты. Кроме того,
   `kids_devices` — статические записи, то есть ~5 700 записей конфигурации во flash
   роутера в сутки.

## Что сделано в 2.1.0

**VPS (`vps/app.py`)**

- в `KIDS` и `EXT` попадают все назначенные устройства с IP, независимо от `bound/waiting`
  (это кандидат 2.0.1 из handoff);
- предупреждение с кнопкой «просить +30 мин» приходит и для спящих устройств;
- `/router/state` отдаёт четвёртую строку `MACS=<MAC назначенных устройств>`.
  Старый скрипт роутера читает только три строки, поэтому сервер можно обновлять первым;
- снятие устройства с ребёнка: «Дети и устройства → ребёнок → 🗑 Снять устройства»
  показывает только его устройства (имя • IP • MAC), нажатие на ❌ снимает устройство
  и его продление, роутер убирает блокировку за ~15 с. В 2.0.0 снять устройство было
  нельзя: экран назначения показывал первые 45 из 52 устройств, а назначенные
  сортировались в конец и обрезались. Теперь устройства ребёнка идут первыми.

**MikroTik (`mikrotik/sbkb-scripts.rsc.in`, `sbkb-state-poll`)**

- `kids_devices` и `kids_extension` **сверяются**, а не пересоздаются: удаляется только
  лишнее, добавляется только недостающее. Пустого окна нет, во flash пишется только
  при реальном изменении;
- запись продления создаётся один раз с остатком времени и истекает сама ровно
  в `end_ts`, даже если VPS недоступен;
- на каждый назначенный MAC создаётся правило
  `chain=forward src-mac-address=<MAC> out-interface-list=WAN action=jump jump-target=sbkb-out`
  с комментарием `SmartBild KidsBot 03 mac <MAC>`. Оно блокирует устройство по
  L2-адресу: ни `waiting`, ни пропавший lease, ни вручную прописанный IP больше не
  выводят его из-под расписания. Снятие устройства в боте удаляет правило.

Число правил после обновления: `12 + число назначенных MAC` (сейчас 15).
Проверки из handoff, которые ждут ровно `FIREWALL_RULES=12`, покажут 15 — это норма.

Если сервер недоступен, скрипт падает до любых изменений и роутер продолжает работать
с последним известным состоянием (как и раньше).

## Установка

Сначала VPS, потом MikroTik. Перед этим — backup (`operations/backup_sensitive.command`
из handoff) и проверка, что у всех назначенных устройств статический lease, а на
iPhone/iPad «Частный адрес Wi‑Fi → Фиксированный»: блокировка по MAC держится, пока
MAC не меняется.

### 1. VPS

```bash
scp kids-internet/vps/app.py smartbild:/tmp/app_2.1.0.py
ssh smartbild 'sudo python3 -m py_compile /tmp/app_2.1.0.py && sudo python3 /tmp/app_2.1.0.py --self-test'
# ожидается SELF_TEST_OK
ssh smartbild 'sudo bash -s' <<'REMOTE'
set -Eeuo pipefail
STAMP=$(date +%Y%m%d-%H%M%S)
cp -a /opt/smartbild-kidsbot/app.py /root/smartbild-kidsbot-app-before-$STAMP.py
install -m 0755 -o root -g root /tmp/app_2.1.0.py /opt/smartbild-kidsbot/app.py
systemctl restart smartbild-kidsbot.service
sleep 2
systemctl is-active --quiet smartbild-kidsbot.service
curl -fsS http://127.0.0.1:8765/health
REMOTE
```

В `health` должно быть `"version":"2.1.0"`. Уже на этом шаге спящий `.10` возвращается в
`kids_devices` (старый скрипт роутера понимает новый ответ).

### 2. MikroTik

```bash
cd kids-internet/mikrotik
SECRET=$(ssh smartbild "sudo python3 -c 'import json;print(json.load(open(\"/etc/smartbild-kidsbot/config.json\"))[\"router_secret\"])'")
python3 render_templates.py --secret "$SECRET" --cert-check no --output /tmp/sbkb-scripts.rsc
unset SECRET
scp -O /tmp/sbkb-scripts.rsc admin@192.168.10.1:sbkb-scripts.rsc
ssh admin@192.168.10.1 '/import file-name=sbkb-scripts.rsc; /file remove [find where name="sbkb-scripts.rsc"]'
rm -f /tmp/sbkb-scripts.rsc
ssh admin@192.168.10.1 '/system script run sbkb-state-poll; /ip firewall filter print terse without-paging where comment~"SmartBild KidsBot 0"; /ip firewall address-list print without-paging where comment="SmartBild KidsBot managed"'
```

Ожидается: три правила `SmartBild KidsBot 03 mac …` в самом начале `forward`,
в `kids_devices` три IP (включая спящий `.10`). Файл с секретом в Git не коммитить.

Откат роутера: импортировать `sbkb-scripts.rsc.in` из коммита 2.0.0 тем же способом и
удалить MAC-правила: `/ip firewall filter remove [find where comment~"^SmartBild KidsBot 03 mac "]`.
Откат VPS — восстановить `/root/smartbild-kidsbot-app-before-*.py`.

## Приёмка

Скрипт `sbkb-state-poll` проверен только статически: RouterOS в этой среде нет.
Поэтому до приёмки считать его непроверенным.

1. После 23:00 (будний день) на Air-Dmitrij закрыть крышку на 15+ минут, чтобы lease стал
   `waiting`. Открыть — интернета нет; счётчик правила `03 mac 1C:57:DC:6E:43:80` растёт.
2. Прописать на ноутбуке вручную IP, например `192.168.10.200` — интернета всё равно нет.
3. Запросить продление, одобрить: интернет появляется только у выбранного устройства
   и пропадает в 23:30 / 00:30.
4. Снять одно устройство в боте → через ~15 с его MAC-правило и IP исчезают с роутера
   (это проверяет удаление; вернуть назначение после теста).
5. LAN (QNAP, камеры, принтер) доступен в любое время.

## Что осталось за рамками

- **Смена MAC обходит блокировку.** «Частный адрес: Ротация» на iOS/macOS или USB-Ethernet
  адаптер дают новый MAC, новое устройство в DHCP и полный интернет. Закрывается только
  политикой «в WAN выпускаются лишь известные MAC» — это затрагивает всю домашнюю сеть,
  поэтому без отдельного решения не делалось.
- **IPv6.** Сейчас на роутере нет IPv6 default route. Если провайдер его включит,
  правила `/ip firewall` IPv6 не покрывают.
- **FastTrack.** Сейчас выключен. Если его включить, уже установленные соединения
  будут обходить фильтр после отключения.
- Расписание по-прежнему зашито в двух местах (`app.py` и `sbkb-firewall.rsc`).
