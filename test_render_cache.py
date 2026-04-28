import unittest

import reposhow


class RenderCacheFingerprintTest(unittest.TestCase):
    def test_narration_query_stripped_for_cache(self) -> None:
        a = {"narration": "/narration/foo.mp3?t=111"}
        b = {"narration": "/narration/foo.mp3?t=222"}
        self.assertEqual(
            reposhow.render_props_fingerprint(a),
            reposhow.render_props_fingerprint(b),
        )

    def test_other_prop_changes_break_cache(self) -> None:
        a = {"repoDescription": "A", "narration": "/n/x.mp3"}
        b = {"repoDescription": "B", "narration": "/n/x.mp3"}
        self.assertNotEqual(
            reposhow.render_props_fingerprint(a),
            reposhow.render_props_fingerprint(b),
        )


if __name__ == "__main__":
    unittest.main()
