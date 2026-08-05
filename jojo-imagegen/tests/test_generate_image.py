import base64
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_image.py"
SPEC = importlib.util.spec_from_file_location("jojo_generate_image", SCRIPT_PATH)
generate_image = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = generate_image
SPEC.loader.exec_module(generate_image)


class GenerateImageTests(unittest.TestCase):
    def test_normalize_base_url_adds_v1_once(self):
        self.assertEqual(generate_image.normalize_base_url("https://jojocode.com"), "https://jojocode.com/v1/")
        self.assertEqual(generate_image.normalize_base_url("https://jojocode.com/v1/"), "https://jojocode.com/v1/")

    def test_extracts_markdown_image_from_chat_response(self):
        response = {
            "choices": [
                {
                    "message": {
                        "content": "Generated: ![image](https://cdn.example.com/generated.png)"
                    }
                }
            ]
        }

        results = generate_image.extract_image_results(response)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].url, "https://cdn.example.com/generated.png")

    def test_images_payload_maps_legacy_standard_quality(self):
        args = generate_image.build_parser().parse_args(
            ["--prompt", "test", "--out", "test.png", "--quality", "standard"]
        )

        payload = generate_image.images_payload(args, "test")

        self.assertEqual(payload["quality"], "medium")

    def test_extracts_base64_image_from_images_response(self):
        image_bytes = b"test-image-bytes"
        response = {"data": [{"b64_json": base64.b64encode(image_bytes).decode("ascii")}]} 

        results = generate_image.extract_image_results(response)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].data, image_bytes)

    def test_save_results_uses_numbered_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir) / "image.png"
            results = [
                generate_image.ImageResult(data=b"one"),
                generate_image.ImageResult(data=b"two"),
            ]

            saved = generate_image.save_results(results, out_path, 2, 1)

            self.assertEqual(saved, [out_path.resolve(), (Path(temp_dir) / "image-2.png").resolve()])
            self.assertEqual(out_path.read_bytes(), b"one")
            self.assertEqual((Path(temp_dir) / "image-2.png").read_bytes(), b"two")


if __name__ == "__main__":
    unittest.main()
