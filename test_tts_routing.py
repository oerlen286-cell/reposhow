import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import reposhow


class GenerateTtsRoutingTest(unittest.TestCase):
    def test_english_falls_back_to_openai_without_dashscope(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "narration.mp3"

            with (
                patch.object(reposhow, "_resolve_gemini_api_key", return_value="gemini-key"),
                patch.object(reposhow, "_generate_tts_gemini", return_value=False),
                patch.object(reposhow, "_generate_tts_openai", return_value=True) as openai_tts,
                patch.object(reposhow, "_generate_tts_dashscope", return_value=False) as dashscope_tts,
            ):
                result = reposhow.generate_tts(
                    "English narration",
                    "English narration",
                    output_path,
                    lang="en",
                )

        self.assertTrue(result)
        openai_tts.assert_called_once_with("English narration", output_path)
        dashscope_tts.assert_not_called()


if __name__ == "__main__":
    unittest.main()
