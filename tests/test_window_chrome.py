import unittest

from undertow.window_chrome import NativeWindowChrome


class NativeWindowChromeTests(unittest.TestCase):
    def test_resize_hit_test_maps_all_edges_and_corners(self) -> None:
        chrome = NativeWindowChrome(None)
        size = (400, 300)

        self.assertEqual(chrome.resize_hit_test((0, 0), size), 13)
        self.assertEqual(chrome.resize_hit_test((399, 0), size), 14)
        self.assertEqual(chrome.resize_hit_test((0, 299), size), 16)
        self.assertEqual(chrome.resize_hit_test((399, 299), size), 17)
        self.assertEqual(chrome.resize_hit_test((0, 150), size), 10)
        self.assertEqual(chrome.resize_hit_test((399, 150), size), 11)
        self.assertEqual(chrome.resize_hit_test((200, 0), size), 12)
        self.assertEqual(chrome.resize_hit_test((200, 299), size), 15)
        self.assertIsNone(chrome.resize_hit_test((200, 150), size))
