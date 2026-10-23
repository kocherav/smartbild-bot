import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import voice_intake as vi

ENV = {'OPENAI_API_KEY': ' sk-test ', 'OPENAI_TRANSCRIBE_MODEL': 'gpt-transcribe'}


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class VoiceIntakeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.ogg = Path(self.folder.name) / 'voice.ogg'
        self.ogg.write_bytes(b'OggS')

    def test_request_carries_model_language_glossary_and_key(self):
        wav = Path(self.folder.name) / 'voice.wav'
        wav.write_bytes(b'RIFFdata')
        seen = {}
        def urlopen(request, timeout):
            seen.update(url=request.full_url, auth=request.headers['Authorization'], body=request.data)
            return Response(json.dumps({'text': 'выстави счёт'}).encode())
        with patch.object(vi.urllib.request, 'urlopen', side_effect=urlopen):
            self.assertEqual('выстави счёт', vi.request_transcription(wav, ENV))
        self.assertEqual(vi.API_URL, seen['url'])
        self.assertEqual('Bearer sk-test', seen['auth'])
        body = seen['body'].decode('utf-8', 'replace')
        for part in ('name="model"\r\n\r\ngpt-transcribe', 'name="language"\r\n\r\nru', 'Hogart', 'RIFFdata'):
            self.assertIn(part, body)

    def test_http_errors_become_plain_words(self):
        error = urllib.error.HTTPError(vi.API_URL, 401, 'Unauthorized', {}, None)
        with patch.object(vi.urllib.request, 'urlopen', side_effect=error):
            with self.assertRaisesRegex(vi.VoiceError, 'ключ OpenAI не принят'):
                vi.request_transcription(self.ogg, ENV)
        with patch.object(vi.urllib.request, 'urlopen', side_effect=urllib.error.URLError('down')):
            with self.assertRaisesRegex(vi.VoiceError, 'недоступен'):
                vi.request_transcription(self.ogg, ENV)

    def test_transcribe_cleans_up_in_every_outcome(self):
        convert = lambda source, target, runner=None: (Path(target).write_bytes(b'RIFF'), target)[1]
        with patch.object(vi, 'to_wav', side_effect=convert):
            self.assertEqual('смени плательщика', vi.transcribe(self.ogg, ENV, request=lambda p, e: '  смени   плательщика '))
            self.assertFalse(self.ogg.exists())
            self.ogg.write_bytes(b'OggS')
            with self.assertRaisesRegex(vi.VoiceError, 'не удалось разобрать'):
                vi.transcribe(self.ogg, ENV, request=lambda p, e: ' ')
        self.assertEqual([], list(Path(self.folder.name).iterdir()))

    def test_missing_key_is_refused_before_any_work(self):
        with self.assertRaisesRegex(vi.VoiceError, 'не настроено'):
            vi.transcribe(self.ogg, {'OPENAI_API_KEY': ''}, request=lambda p, e: self.fail('нет ключа — нет запроса'))

    def test_ffmpeg_conversion_and_missing_decoder(self):
        target = Path(self.folder.name) / 'out.wav'
        def runner(cmd, **_kwargs):
            self.assertIn('16000', cmd)
            target.write_bytes(b'RIFF')
            return subprocess.CompletedProcess(cmd, 0, '', '')
        with patch.object(vi.shutil, 'which', return_value='/usr/bin/ffmpeg'):
            self.assertEqual(target, vi.to_wav(self.ogg, target, runner))
        with patch.object(vi.shutil, 'which', return_value=None), patch.dict('sys.modules', {'av': None}):
            with self.assertRaisesRegex(vi.VoiceError, 'нет декодера'):
                vi.to_wav(self.ogg, target)


if __name__ == '__main__':
    unittest.main()
