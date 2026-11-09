"""Image preprocessing checks: python -m unittest tests.test_imaging -v."""
import os
import tempfile
import unittest
from types import SimpleNamespace

import numpy as np
from PIL import Image

from core import imaging
from core.api import Api
from core.settings import DEFAULTS


def faint_page():
    """Nền xám nhạt 235 với một khối chữ xám 170."""
    arr = np.full((200, 200, 3), 235, dtype=np.uint8)
    arr[60:140, 60:140] = 170
    return Image.fromarray(arr)


def ink_and_paper(image):
    arr = np.array(image.convert("L"))
    return int(arr[100, 100]), int(arr[10, 10])


class BoostInkTests(unittest.TestCase):
    def test_off_by_default_and_leaves_image_untouched(self):
        self.assertEqual(DEFAULTS["ink_boost"], "off")
        page = faint_page()
        self.assertIs(imaging.boost_ink(page, "off"), page)

    def test_levels_darken_ink_progressively(self):
        ink, _ = ink_and_paper(faint_page())
        light, _ = ink_and_paper(imaging.boost_ink(faint_page(), "light"))
        strong, _ = ink_and_paper(imaging.boost_ink(faint_page(), "strong"))
        self.assertLessEqual(strong, light)
        self.assertLess(light, ink)

    def test_paper_stays_white(self):
        for level in ("light", "strong"):
            self.assertGreaterEqual(ink_and_paper(imaging.boost_ink(faint_page(), level))[1], 250, level)

    def test_strong_darkens_midtones_more_than_light(self):
        arr = np.tile(np.linspace(0, 255, 256, dtype=np.uint8), (64, 1))
        gradient = Image.fromarray(np.dstack([arr] * 3))
        light = np.array(imaging.boost_ink(gradient, "light").convert("L"))[0, 128]
        strong = np.array(imaging.boost_ink(gradient, "strong").convert("L"))[0, 128]
        self.assertLess(strong, light)

    def test_grayscale_input_is_supported(self):
        result = imaging.boost_ink(faint_page().convert("L"), "strong")
        self.assertEqual(result.mode, "RGB")


def red_page():
    """Nền trắng với một khối đỏ nhạt như con dấu."""
    arr = np.full((200, 200, 3), 255, dtype=np.uint8)
    arr[60:140, 60:140] = (200, 120, 120)
    return Image.fromarray(arr)


class ColorModeTests(unittest.TestCase):
    def test_keep_by_default_and_leaves_image_untouched(self):
        self.assertEqual(DEFAULTS["color_mode"], "keep")
        page = red_page()
        self.assertIs(imaging.apply_color_mode(page, "keep"), page)

    def test_gray_removes_color(self):
        r, g, b = np.array(imaging.apply_color_mode(red_page(), "gray"))[100, 100]
        self.assertEqual(r, g)
        self.assertEqual(g, b)

    def test_vivid_increases_saturation(self):
        r, g, _ = np.array(imaging.apply_color_mode(red_page(), "vivid"))[100, 100].astype(int)
        self.assertGreater(r - g, 80)

    def test_bw_leaves_only_black_and_white(self):
        arr = np.full((200, 200, 3), 235, dtype=np.uint8)
        arr[98:102, 40:160] = 90
        result = np.array(imaging.apply_color_mode(Image.fromarray(arr), "bw"))
        self.assertEqual(set(np.unique(result)), {0, 255})
        self.assertEqual(int(result[100, 100, 0]), 0)
        self.assertEqual(int(result[10, 10, 0]), 255)

    def test_grayscale_input_is_supported(self):
        for mode in ("gray", "vivid", "bw"):
            self.assertEqual(imaging.apply_color_mode(faint_page().convert("L"), mode).mode, "RGB", mode)


class PageImageTests(unittest.TestCase):
    """Khung đọc trang Tách & ghép phải hiện ảnh sẽ xuất, không phải ảnh đã xử lý cho OCR."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ocr_path = os.path.join(tmp.name, "ocr.png")
        Image.new("RGB", (40, 40), "black").save(ocr_path)
        doc = SimpleNamespace(page=lambda uid: uid, ocr_images={"p1": ocr_path},
                              render=lambda page, dpi: (Image.new("RGB", (60, 80), "white"), ""))
        self.api = SimpleNamespace(_doc=lambda doc_id: doc, _settings=SimpleNamespace(get=lambda key: 200))

    def test_default_returns_ocr_image(self):
        self.assertEqual(Api.page_image(self.api, "d", "p1")["width"], 40)

    def test_original_skips_ocr_image(self):
        self.assertEqual(Api.page_image(self.api, "d", "p1", 1600, True)["width"], 60)


if __name__ == "__main__":
    unittest.main()
