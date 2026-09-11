from io import BytesIO
import unittest

from PIL import Image

from gptsnip.core import Window, choose_target, image_dib, selection_box


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.a = Window(10, 1, "msedge.exe", "ChatGPT - Edge")
        self.b = Window(20, 2, "firefox.exe", "ChatGPT - Firefox")

    def test_remembered_target_wins_over_enum_order(self):
        self.assertEqual(choose_target([self.a, self.b], self.b), self.b)

    def test_discovery_requires_one_unambiguous_candidate(self):
        self.assertIsNone(choose_target([self.b, self.a]))
        self.assertEqual(choose_target([self.a]), self.a)
        self.assertIsNone(choose_target([]))

    def test_arbitrary_app_and_browser_rejected(self):
        windows = [Window(1, 1, "notepad.exe", "ChatGPT"),
                   Window(2, 2, "chrome.exe", "Documentation"),
                   Window(3, 3, "chrome.exe", "FakeChatGPTClone")]
        self.assertIsNone(choose_target(windows))

    def test_browser_process_and_case_insensitive_brand(self):
        self.assertTrue(Window(1, 1, "MSEDGE.EXE", "chatgpt").recognized)

    def test_automatic_eligibility_requires_allowlisted_browser_and_chatgpt_title(self):
        for process in ("msedge.exe", "firefox.exe", "brave.exe",
                        "vivaldi.exe", "opera.exe"):
            with self.subTest(process=process):
                window = Window(1, 1, process, "ChatGPT - Conversation")
                self.assertTrue(window.recognized)
                self.assertEqual(choose_target([window]), window)
                for title in ("OpenAI", "GPT", "Documentation", "FakeChatGPTClone",
                              "Easier Screenshot Sharing - Google Chrome", ""):
                    self.assertFalse(Window(1, 1, process, title).recognized)

    def test_codex_and_chatgpt_desktop_are_never_automatic_targets(self):
        # Real Codex package on this machine also uses the name ChatGPT.exe.
        for process in ("codex.exe", "ChatGPT.exe", "CHATGPT.EXE"):
            for title in ("Codex", "ChatGPT", "OpenAI", "GPT", "Conversation", ""):
                with self.subTest(process=process, title=title):
                    window = Window(30, 3, process, title)
                    self.assertFalse(window.recognized)
                    self.assertIsNone(choose_target([window]))
                    self.assertIsNone(choose_target([window, self.a], window))

    def test_non_browser_brand_titles_are_never_automatic_targets(self):
        for process in ("notepad.exe", "Code.exe", "powershell.exe", "OpenAI.exe",
                        "GPT.exe", "mychrome.exe"):
            for title in ("ChatGPT", "OpenAI", "GPT"):
                with self.subTest(process=process, title=title):
                    window = Window(30, 3, process, title)
                    self.assertFalse(window.recognized)
                    self.assertIsNone(choose_target([window]))

    def test_desktop_does_not_compete_with_browser_discovery(self):
        desktop = Window(30, 3, "ChatGPT.exe", "ChatGPT")
        self.assertEqual(choose_target([desktop, self.a]), self.a)
        self.assertEqual(choose_target([self.a, desktop]), self.a)

    def test_explicit_binding_supports_custom_title(self):
        bound = Window(30, 3, "chrome.exe", "Design discussion")
        self.assertEqual(choose_target([self.a, bound], self.a, bound), bound)

    def test_changed_bound_target_never_falls_through(self):
        for changed in (Window(10, 1, self.a.process, "Other tab"),
                        Window(10, 99, self.a.process, self.a.title)):
            self.assertIsNone(choose_target([changed, self.b], self.b, self.a))
        self.assertIsNone(choose_target([self.b], self.b, self.a))

    def test_invalid_memory_never_falls_through_to_other_chatgpt(self):
        for changed in (None,
                        Window(10, 1, self.a.process, "Other tab"),
                        Window(10, 1, self.a.process, "Another ChatGPT conversation"),
                        Window(10, 99, self.a.process, self.a.title),
                        Window(10, 1, "firefox.exe", self.a.title)):
            with self.subTest(changed=changed):
                windows = [self.b] if changed is None else [changed, self.b]
                self.assertIsNone(choose_target(windows, self.a))

    def test_unrecognized_memory_is_not_a_target(self):
        window = Window(30, 3, "chrome.exe", "Documentation")
        self.assertIsNone(choose_target([window], window))

    def test_negative_origins_and_reverse_drag(self):
        self.assertEqual(selection_box((300, 100), (-1700, -900),
                                       (-1920, -1080, 3840, 2160)),
                         (-1700, -900, 300, 100))

    def test_clamp_and_zero_area(self):
        self.assertEqual(selection_box((-100, -20), (200, 300), (0, 0, 100, 100)),
                         (0, 0, 100, 100))
        self.assertIsNone(selection_box((2, 2), (2, 10), (0, 0, 100, 100)))
        self.assertIsNone(selection_box((2, 2), (2, 2), (0, 0, 100, 100)))

    def test_dib_round_trip_preserves_pixels_dimensions_and_row_padding(self):
        image = Image.new("RGB", (3, 2))
        colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255),
                  (1, 2, 3), (4, 5, 6), (255, 255, 255)]
        image.putdata(colors)
        dib = image_dib(image)
        with Image.open(BytesIO(dib)) as restored:
            self.assertEqual(restored.size, image.size)
            self.assertEqual(restored.tobytes(), image.tobytes())


if __name__ == "__main__":
    unittest.main()
