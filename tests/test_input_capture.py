import queue
import unittest

import pygame

from undertow.events import EventHandler
from undertow.input_capture.client import InputClient
from undertow.input_capture.events import KeyEvent


class InputClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def test_poll_preserves_the_capture_sequence(self) -> None:
        events: queue.SimpleQueue[KeyEvent] = queue.SimpleQueue()
        events.put(KeyEvent("down", "a", sequence=1))
        events.put(KeyEvent("text", "a", "a", sequence=2))
        events.put(KeyEvent("down", "b", sequence=3))
        client = InputClient(events)

        self.assertEqual(client.poll(), [
            KeyEvent("down", "a", sequence=1),
            KeyEvent("text", "a", "a", sequence=2),
            KeyEvent("down", "b", sequence=3),
        ])
        self.assertFalse(client.order_error)

    def test_poll_rejects_reordered_or_duplicate_events(self) -> None:
        events: queue.SimpleQueue[KeyEvent] = queue.SimpleQueue()
        events.put(KeyEvent("text", "a", "a", sequence=2))
        events.put(KeyEvent("text", "b", "b", sequence=1))
        client = InputClient(events)

        self.assertEqual([event.text for event in client.poll()], ["a", "b"])
        self.assertTrue(client.order_error)

    def test_canonical_event_maps_modifiers_and_navigation_to_editor_input(self) -> None:
        event = EventHandler._pygame_key_event(KeyEvent("down", "right", modifiers=("ctrl", "shift"), sequence=1))

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.key, pygame.K_RIGHT)
        self.assertTrue(event.mod & pygame.KMOD_CTRL)
        self.assertTrue(event.mod & pygame.KMOD_SHIFT)


if __name__ == "__main__":
    unittest.main()
