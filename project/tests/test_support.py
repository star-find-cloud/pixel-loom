import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from pixel_workbench.welcome import support_options


class SupportTests(unittest.TestCase):
    def test_all_amounts_map_to_distinct_bundled_original_posters(self):
        options = support_options()
        self.assertEqual([option.amount_yuan for option in options], [5, 10, 15, 20])
        self.assertEqual([option.image.name for option in options],
                         ["wechat-05.jpg", "wechat-10.jpg", "wechat-15.jpg", "wechat-20.jpg"])
        self.assertEqual(len({option.image.read_bytes() for option in options}), 4)
        for option in options:
            with Image.open(option.image) as image:
                self.assertEqual(image.size, (1279, 1743))

    def test_invalid_amounts_or_external_image_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "options.json"
            for options in ([{"amount_yuan": 5, "image": "../other.jpg"}],
                            [{"amount_yuan": True, "image": "other.jpg"}],
                            [{"amount_yuan": 5, "image": "one.jpg"}, {"amount_yuan": 5, "image": "two.jpg"}]):
                path.write_text(json.dumps({"options": options}), encoding="utf-8")
                with self.assertRaises(ValueError):
                    support_options(folder)
