"""Telegram voice messages → text through the OpenAI transcription API.

Owner decision (23.10): cloud recognition with OpenAI.  Telegram sends voice as
OGG/Opus, which the current OpenAI audio docs do not list, so the file is first
converted to 16 kHz mono WAV (``ffmpeg`` binary, else the PyAV package).

The recognised text is only *input*: the bridge shows it to the person and
routes it like a typed message, so every write still needs its preview and
button.  Audio and transcripts are never written to logs; temporary files are
removed in every outcome.
"""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.error
import urllib.request
import uuid


API_URL = 'https://api.openai.com/v1/audio/transcriptions'
DEFAULT_MODEL = 'gpt-4o-transcribe'
MAX_SECONDS = 180
# Context for names the model cannot guess (prompt is supported by the API).
GLOSSARY = ('SmartBild, КЛИВЭЛ, Мегаплан, Hogart (Хогарт), Daichi (Дайчи), Haier, Kentatsu, '
            'сплит-система, сделка, плательщик, исполнитель, монтаж, монтажник, КП, счёт, договор, '
            'спецификация, ЭДО, НДС, ИНН, номер сделки.')


class VoiceError(Exception):
    """A failure the person is told about in plain words."""


def configured(env):
    return bool(str(env.get('OPENAI_API_KEY') or '').strip())


def to_wav(source, target, runner=None):
    """OGG/Opus → 16 kHz mono WAV.  Raises VoiceError when no decoder is available."""
    runner = runner or subprocess.run
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg:
        done = runner([ffmpeg, '-nostdin', '-loglevel', 'error', '-y', '-i', str(source),
                       '-ac', '1', '-ar', '16000', '-t', str(MAX_SECONDS), str(target)],
                      capture_output=True, text=True, timeout=60)
        if done.returncode or not Path(target).exists():
            raise VoiceError('не удалось преобразовать голосовое')
        return target
    try:
        import av  # PyAV bundles its own FFmpeg libraries
    except ImportError:
        raise VoiceError('на сервере нет декодера звука (ffmpeg или PyAV)') from None
    import wave
    with av.open(str(source)) as container, wave.open(str(target), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
        for frame in container.decode(audio=0):
            for chunk in resampler.resample(frame):
                out.writeframes(chunk.to_ndarray().tobytes())
    return target


def _multipart(fields, file_field, filename, payload):
    boundary = 'smartbild-' + uuid.uuid4().hex
    body = io.BytesIO()
    for name, value in fields.items():
        body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
               'Content-Type: audio/wav\r\n\r\n'.encode())
    body.write(payload)
    body.write(f'\r\n--{boundary}--\r\n'.encode())
    return body.getvalue(), 'multipart/form-data; boundary=' + boundary


def request_transcription(wav_path, env, timeout=60):
    """One HTTPS call; returns the text.  The only network boundary of this module."""
    fields = {'model': env.get('OPENAI_TRANSCRIBE_MODEL') or DEFAULT_MODEL, 'language': 'ru',
              'response_format': 'json', 'prompt': GLOSSARY}
    data, content_type = _multipart(fields, 'file', 'voice.wav', Path(wav_path).read_bytes())
    request = urllib.request.Request(API_URL, data=data, method='POST', headers={
        'Authorization': 'Bearer ' + env['OPENAI_API_KEY'].strip(), 'Content-Type': content_type})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return str(json.loads(response.read().decode()).get('text') or '')
    except urllib.error.HTTPError as exc:
        kinds = {401: 'ключ OpenAI не принят', 403: 'доступ к распознаванию запрещён',
                 429: 'лимит распознавания исчерпан', 413: 'голосовое слишком длинное'}
        raise VoiceError(kinds.get(exc.code, f'сервис распознавания ответил ошибкой {exc.code}')) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise VoiceError('сервис распознавания недоступен') from None


def transcribe(source, env, runner=None, request=None):
    """Telegram voice file → stripped text.  Temporary WAV is always removed."""
    if not configured(env):
        raise VoiceError('распознавание голоса не настроено')
    target = Path(str(source) + '.wav')
    try:
        to_wav(source, target, runner)
        text = ' '.join((request or request_transcription)(target, env).split())
    finally:
        for path in (target, Path(source)):
            try:
                path.unlink()
            except OSError:
                pass
    if not text:
        raise VoiceError('в голосовом не удалось разобрать слова')
    return text
