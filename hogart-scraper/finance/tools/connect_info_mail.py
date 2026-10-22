"""Interactively rotate the bot's mail app password after IMAP/SMTP verification."""
import fcntl
import getpass
import imaplib
import os
from pathlib import Path
import shutil
import smtplib
import ssl
import subprocess
import sys
import tempfile

ENV_FILE = Path('/home/kocher.av/telegram-bridge/.env')
USERNAME = 'info@innsis.ru'


def read_env(text):
    return {line.split('=', 1)[0].strip(): line.split('=', 1)[1].strip()
            for line in text.splitlines() if '=' in line and not line.lstrip().startswith('#')}


def replace_credentials(path, expected, password):
    # Preserve all unrelated settings, ownership and ACLs; publish atomically.
    updates = {'IMAP_HOST': 'imap.yandex.ru', 'IMAP_PORT': '993',
               'IMAP_USERNAME': USERNAME, 'IMAP_PASSWORD': password,
               'SMTP_PASSWORD': password}
    with path.open('r') as original:
        fcntl.flock(original, fcntl.LOCK_EX)
        if original.read() != expected:
            raise RuntimeError('configuration_changed')
        lines = []
        remaining = dict(updates)
        for line in expected.splitlines():
            key = line.split('=', 1)[0].strip() if '=' in line and not line.lstrip().startswith('#') else None
            if key in updates:
                if key in remaining:
                    lines.append(key + '=' + remaining.pop(key))
            else:
                lines.append(line)
        lines.extend(key + '=' + value for key, value in remaining.items())
        fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.mail-credentials-')
        try:
            with os.fdopen(fd, 'w') as target:
                target.write('\n'.join(lines) + '\n')
                target.flush()
                os.fsync(target.fileno())
            info = path.stat()
            if os.geteuid() == 0:
                os.chown(temp, info.st_uid, info.st_gid)
            shutil.copystat(path, temp)  # Includes POSIX ACL extended attributes on Linux.
            os.replace(temp, path)
            directory = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)


def main():
    if not sys.stdin.isatty():
        print('Запустите эту команду в обычном терминале: пароль вводится скрыто.')
        return 1
    # The shared configuration belongs to the service account. Preserve its ACL.
    if os.geteuid() != 0:
        result = subprocess.run(['sudo', '-n', '/usr/bin/python3', str(Path(__file__).resolve())])
        return result.returncode
    original = ENV_FILE.read_text()
    config = read_env(original)
    if config.get('SMTP_USERNAME') != USERNAME:
        print('Адрес отправителя в настройках отличается. Настройки не изменены.')
        return 1
    password = getpass.getpass('Новый пароль приложения для info@innsis.ru (ввод скрыт): ').strip()
    if not password or any(c.isspace() for c in password):
        print('Введите пароль приложения без пробелов и переносов. Настройки не изменены.')
        return 1
    stage = 'IMAP: чтение почты'
    try:
        with imaplib.IMAP4_SSL('imap.yandex.ru', 993, timeout=30) as box:
            box.login(USERNAME, password)
            if box.select('INBOX', readonly=True)[0] != 'OK':
                raise RuntimeError('inbox_unavailable')
        print('IMAP: вход успешен.')
        stage = 'SMTP: подключение для отправки'
        host = config.get('SMTP_HOST', 'smtp.yandex.ru')
        port = int(config.get('SMTP_PORT', '465'))
        context = ssl.create_default_context()
        if port == 587:
            connection = smtplib.SMTP(host, port, timeout=30)
        elif port == 465:
            connection = smtplib.SMTP_SSL(host, port, context=context, timeout=30)
        else:
            raise RuntimeError('unsupported_smtp_port')
        with connection as smtp:
            if port == 587:
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
            smtp.login(USERNAME, password)
        print('SMTP: вход успешен. Письма не отправлялись.')
        stage = 'сохранение настроек'
        replace_credentials(ENV_FILE, original, password)
    except Exception as exc:
        # Never print exception text: an upstream error could contain credentials.
        print('Не удалось завершить этап: ' + stage + '. Тип ошибки: ' + type(exc).__name__)
        print('Новый пароль не установлен либо сохранение не завершено; сообщите этот результат ассистенту.')
        return 1
    print('Пароль приложения обновлён для чтения и отправки почты info@innsis.ru.')
    print('Настройки перечитываются при следующем обращении к почте. Сообщите ассистенту: info подключена.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
