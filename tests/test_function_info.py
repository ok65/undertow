import unittest

from undertow.function_info import function_at


class FunctionInfoTests(unittest.TestCase):
    def test_function_hover_shows_typed_signature_and_docstring(self) -> None:
        lines = [
            "async def surf(board: Board, waves: int = 3, *, safe: bool = True) -> list[str]:",
            '    """Ride the best available waves."""',
            "    return []",
            "",
            "surf(board)",
        ]

        info = function_at(lines, 4, 1)

        self.assertIsNotNone(info)
        self.assertEqual(info.prototype, "async def surf(board: Board, waves: int = 3, *, safe: bool = True) -> list[str]")
        self.assertEqual(info.docstring, "Ride the best available waves.")

    def test_function_hover_returns_nothing_for_non_function_symbols(self) -> None:
        self.assertIsNone(function_at(["tide = 3"], 0, 1))

    def test_class_hover_shows_class_docstring(self) -> None:
        lines = ["class Wave:", '    """A surfable wave."""', "    pass"]

        info = function_at(lines, 0, 7)

        self.assertEqual(info.prototype, "class Wave")
        self.assertEqual(info.docstring, "A surfable wave.")


if __name__ == "__main__":
    unittest.main()
