"""Voice requests (owner decision 23.10: OpenAI transcription), as a person uses them."""
import unittest

from human_qa_harness import HumanJourneyCase, press, send_voice
from test_human_journeys import DEAL, office
import voice_intake

KEY = {'OPENAI_API_KEY': 'sk-qa-not-a-real-key'}


class VoiceJourneys(HumanJourneyCase, unittest.TestCase):
    def test_dictated_payer_change_is_shown_then_confirmed_by_button(self):
        def journey(person):
            yield send_voice(5)
            person.sees('🎙 Распознано: «поменяй плательщика в сделке 990001 на альфа сервис»',
                        expected='Бот показал, как понял голосовое')
            person.sees('Новый плательщик: ООО «Альфа Сервис»', 'не записаны',
                        expected='Голосовое ведёт в тот же предпросмотр, что и текст')
            person.check('До кнопки ничего не записано', person.stand.crm.writes, not person.stand.crm.writes)
            yield press('✅ Сменить плательщика')
            person.sees('плательщик изменён')
        stand = self.play(journey, setup=office, env=KEY,
                          speech=['поменяй плательщика в сделке 990001 на альфа сервис'])
        self.assertEqual('7102', stand.crm.deals[DEAL]['payer_id'])
        self.assertEqual(0, len(stand.model.prompts))

    def test_dictated_invoice_request_opens_the_invoice_menu(self):
        def journey(person):
            yield send_voice(3)
            person.sees('Распознано', 'Какой счёт выставить по сделке №990001')
        stand = self.play(journey, setup=office, env=KEY, speech=['выстави счёт по сделке 990001'])
        self.assertEqual([], stand.crm.writes)

    def test_dictated_confirmation_is_not_a_button(self):
        def journey(person):
            yield send_voice(2)
            person.sees('Для подтверждения нажмите актуальную кнопку', expected='Голосом нельзя подтвердить запись')
        stand = self.play(journey, setup=office, env=KEY, speech=['✅ Сменить плательщика'])
        self.assertEqual([], stand.crm.writes)

    def test_service_failure_is_reported_and_nothing_else_happens(self):
        def journey(person):
            yield send_voice(4)
            person.sees('Голосовое не распознано', 'лимит распознавания исчерпан', 'напишите его текстом')
        stand = self.play(journey, setup=office, env=KEY,
                          speech=[voice_intake.VoiceError('лимит распознавания исчерпан')])
        self.assertEqual(([], 0), (stand.crm.writes, len(stand.model.prompts)))

    def test_long_voice_is_not_sent_to_the_service(self):
        def journey(person):
            yield send_voice(240)
            person.sees('длиннее 3 минут')
        stand = self.play(journey, setup=office, env=KEY, speech=['не должно понадобиться'])
        self.assertEqual(0, stand.speech_calls)

    def test_without_a_key_the_bot_asks_for_text(self):
        def journey(person):
            yield send_voice(4)
            person.sees('Голосовые сообщения бот пока не распознаёт')
        stand = self.play(journey, setup=office, speech=['поменяй плательщика'])
        self.assertEqual(0, stand.speech_calls)


if __name__ == '__main__':
    unittest.main()
