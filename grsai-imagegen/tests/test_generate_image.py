import base64
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_image.py"
SPEC = importlib.util.spec_from_file_location("grsai_generate_image", SCRIPT_PATH)
generate_image = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = generate_image
SPEC.loader.exec_module(generate_image)


class GenerateImageTests(unittest.TestCase):
    def test_normalize_base_url_removes_v1(self):
        self.assertEqual(generate_image.normalize_base_url("https://grsaiapi.com/"), "https://grsaiapi.com")
        self.assertEqual(generate_image.normalize_base_url("https://grsaiapi.com/v1"), "https://grsaiapi.com")

    def test_poll_payload_uses_documented_task_mode(self):
        payload = generate_image.build_payload(
            "gpt-image-2",
            "test prompt",
            "1024x1024",
            "high",
            ["https://example.com/reference.png"],
            "poll",
        )

        self.assertEqual(payload["webHook"], "-1")
        self.assertTrue(payload["shutProgress"])
        self.assertEqual(payload["aspectRatio"], "1024x1024")
        self.assertEqual(payload["urls"], ["https://example.com/reference.png"])

    def test_local_reference_is_encoded_as_data_uri(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "reference.png"
            path.write_bytes(b"image-bytes")

            value = generate_image.encode_reference(str(path))

            self.assertTrue(value.startswith("data:image/png;base64,"))
            encoded = value.split(",", 1)[1]
            self.assertEqual(base64.b64decode(encoded), b"image-bytes")

    def test_extracts_documented_results(self):
        response = {
            "code": 0,
            "data": {
                "status": "succeeded",
                "results": [{"url": "https://example.com/generated.png"}],
            },
        }

        results = generate_image.extract_image_results(response)

        self.assertEqual(results, [generate_image.ImageResult(url="https://example.com/generated.png")])

    def test_extracts_data_uri_result(self):
        image_bytes = b"generated-image"
        encoded = base64.b64encode(image_bytes).decode("ascii")

        results = generate_image.extract_image_results(
            {"results": [{"url": f"data:image/png;base64,{encoded}"}]}
        )

        self.assertEqual(results, [generate_image.ImageResult(data=image_bytes)])

    def test_stream_parser_accepts_sse_and_ndjson(self):
        lines = [
            b"event: progress\n",
            b'data: {"status":"running","progress":50}\n',
            b'{"status":"succeeded","results":[{"url":"https://example.com/a.png"}]}\n',
            b"data: [DONE]\n",
        ]

        events = list(generate_image.stream_json_objects(lines))

        self.assertEqual(events[0]["progress"], 50)
        self.assertEqual(events[1]["status"], "succeeded")

    def test_output_paths_are_numbered(self):
        base = Path("image.png")
        self.assertEqual(generate_image.output_path_for(base, 0), Path("image.png"))
        self.assertEqual(generate_image.output_path_for(base, 2), Path("image-3.png"))


if __name__ == "__main__":
    unittest.main()
