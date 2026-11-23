"""24.11: «Клиент ID 1003030 — » (no name from search) could not be chosen at all."""
import unittest
from unittest.mock import patch

import bridge


class ClientChoiceById(unittest.TestCase):
    def test_nameless_card_gets_a_label_and_is_chosen_by_id(self):
        clients = [{'id': '1003031', 'name': 'Ларичев Сергей', 'kind': 'human'},
                   {'id': '1003030', 'name': '', 'kind': 'company'}]
        label = bridge.client_button_text(clients[1])
        self.assertEqual('Клиент ID 1003030 — организация (название не пришло из поиска)', label)
        state = {'pending': 'deal_create_client_select', 'deal_create_clients': clients,
                 'deal_create_spec': {'client_name': 'Архитектурное бюро Сергея Ларичева', 'items': [{'name': 'x', 'qty': 1}]}}
        saved = {}
        with patch.object(bridge, 'current_deal_ui_state', return_value=state), \
             patch.object(bridge, 'update_deal_ui_state', side_effect=lambda c, **k: saved.update(k)), \
             patch.object(bridge, 'send_message'), patch.object(bridge, 'prepare_deal_creation_review'):
            for text in (label, 'Клиент ID 1003030 —'):   # Telegram trims the trailing space
                saved.clear()
                bridge.handle_deal_ui('token', '1', text)
                self.assertEqual('1003030', saved['deal_create_spec']['client_id'])
                self.assertEqual('Архитектурное бюро Сергея Ларичева', saved['deal_create_spec']['client_name'])


if __name__ == '__main__':
    unittest.main()
