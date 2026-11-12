status: done
commits: e160fb6a9abbfcd4e079adcc643e5a2c258da07f
branch: handoff/QA-C8CCAA837ABE53AF7555

Исправлен общий класс причины: source-only QA-контур больше не меняет discovery
тестов из-за установленного на рабочем хосте непубликуемого Node runtime и не
пытается выполнить запрещённый `subprocess.Popen`. Граница CRM-строки → JSON/CSV →
PDF и Word → read-back точной суммы проверяется через внедряемые runner и reader;
реальный Node/Playwright-тест сохранён для интеграционного окружения.

Проверки:

- воспроизведение по receipt `20261111T210000Z-full-783ba4e1`: 1 error,
  `isolation:subprocess.Popen`, источник `smartbild_kp.py:151`;
- затронутые тесты: 17/17, failures 0, errors 0, skipped 0, blocked events 0;
- регрессия при искусственно присутствующем `node_modules/playwright`: 10/10,
  failures 0, errors 0, skipped 0, blocked events 0;
- полный `quality_gate.py --run`: 1900 тестов, `ok: true`, failures 0,
  errors 0, skipped 0, blocked events 0; 2026-11-11T21:05:58.407359+00:00.
- browser runner: N/A, пульт не изменялся.

Стадии:

- реализовано: да, в указанном коммите ветки handoff;
- проверено изолированно: да;
- выпущено: нет, задание `kind: code`, merge/reload запрещены;
- подтверждено в работающей системе: нет; живые записи и рассылки не выполнялись.

Не сделано: ветка не сливалась в main, служба не перезапускалась. Следующий шаг —
QA-проверка опубликованной ветки и отдельное подтверждённое владельцем задание release.
