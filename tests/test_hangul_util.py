import unittest
from rpg.hangul_util import eng_to_hangul, get_clipboard_text, set_clipboard_text


class HangulUtilTests(unittest.TestCase):
    def test_eng_to_hangul_conversion(self):
        cases = [
            ("rlwhs xkagjark", "기존 탐험가"),
            ("chlrkddml xkagjark", "최강의 탐험가"),
            ("wjddPeodnjs", "정예대원"),
            ("wjddP eodnjs", "정예 대원"),
            ("gksrmf", "한글"),
            ("skfk", "나라"),
            ("dlfma", "이름"),
            ("rk", "가"),
            ("rks", "간"),
            ("rkd", "강"),
            ("rka", "감"),
            ("Qkffl", "빨리"),
            ("Ekd", "땅"),
            ("Tmtl", "쓰시"),
            ("xptmxm 123", "테스트 123"),
            ("xpsxm", "텐트"),
            ("Alpha", "미ㅔㅗㅁ"),  # Direct mapping if QWERTY
            ("", ""),
        ]
        for inp, expected in cases:
            self.assertEqual(eng_to_hangul(inp), expected, f"Failed for input: {inp}")

    def test_clipboard_functions(self):
        # Test round-trip clipboard write and read on Windows
        import sys
        if sys.platform == "win32":
            sample = "탐험가_클립보드_테스트_123"
            success = set_clipboard_text(sample)
            if success:
                retrieved = get_clipboard_text()
                self.assertEqual(retrieved, sample)


if __name__ == "__main__":
    unittest.main()
