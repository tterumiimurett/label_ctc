import json
import tempfile
import unittest
from pathlib import Path

from build_mturk_audio_mvp import (
    build_payload,
    generate,
    render_canvas_design_layout,
    render_design_layout,
    render_design_layout_probe,
    render_html_question,
)


class BuildMturkAudioMvpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.task = {
            "data": {"audio": "https://example.test/stereo.wav", "path_seg": "/tmp/stereo.wav"},
            "predictions": [
                {
                    "result": [
                        {
                            "id": "seg-1",
                            "from_name": "channel",
                            "value": {
                                "start": 0.123,
                                "end": 1.456,
                                "channel": 1,
                                "labels": ["Right"],
                            },
                        },
                        {
                            "id": "seg-1",
                            "from_name": "transcript",
                            "value": {"text": ["hello"]},
                        },
                    ]
                }
            ],
        }

    def test_build_payload_joins_region_transcript(self) -> None:
        payload = build_payload(self.task, "test", 0)
        self.assertEqual(payload["segments"][0]["transcript"], "hello")
        self.assertEqual(payload["segments"][0]["channel"], 1)
        self.assertIn("Buzz_in", payload["choices"]["ctc_status"])
        self.assertIn("is_assure", payload["choices"]["segment_flags"])

    def test_generate_writes_preview_and_html_question(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            source = root / "label_studio_tasks_test_predictions.json"
            source.write_text(json.dumps([self.task]), encoding="utf-8")
            preview, question, layout, probe = generate(source, root / "output", 0)
            html = preview.read_text(encoding="utf-8")
            xml = question.read_text(encoding="utf-8")
            design_layout = layout.read_text(encoding="utf-8")
            diagnostic_layout = probe.read_text(encoding="utf-8")
            self.assertIn("wavesurfer.js@7.10.1", html)
            self.assertIn("annotation_json", html)
            self.assertIn("https://example.test/stereo.wav", html)
            self.assertIn("Play selected segment", html)
            self.assertIn("Download JSON for local review", html)
            self.assertIn("turkSubmitTo", html)
            self.assertIn("Waveform library did not load", html)
            self.assertIn("Waveform status: waiting for custom JavaScript to run", html)
            self.assertIn('<source src="https://example.test/stereo.wav" type="audio/wav">', html)
            self.assertIn("<HTMLQuestion", xml)
            self.assertIn("<FrameHeight>1160</FrameHeight>", xml)
            self.assertIn('<crowd-form answer-format="flatten-objects">', design_layout)
            self.assertIn("assets.crowd.aws/crowd-html-elements.js", design_layout)
            self.assertIn("native canvas waveform", design_layout)
            self.assertNotIn("unpkg.com/wavesurfer", design_layout)
            self.assertNotIn("WaveSurfer is embedded", design_layout)
            self.assertIn("<canvas id=\"wave\"></canvas>", design_layout)
            self.assertLess(len(design_layout.encode("utf-8")), 65535)
            self.assertNotIn("<head>", design_layout)
            self.assertIn("INLINE JAVASCRIPT: not executed.", diagnostic_layout)
            self.assertIn("diagnostic_response", diagnostic_layout)

    def test_html_question_escapes_cdata_terminator(self) -> None:
        xml = render_html_question("<p>before ]]> after</p>")
        self.assertIn("]]]]><![CDATA[>", xml)

    def test_design_layout_moves_scripts_into_layout_fragment(self) -> None:
        html = """<!DOCTYPE html>
<html><head><script src="ignored.js"></script><style>.x { color: red; }</style></head>
<body>
  <form name="mturk_form" method="post" id="mturk_form"
        action="https://www.mturk.com/mturk/externalSubmit">
    <input type="hidden" name="assignmentId" id="assignmentId" value="">
    <input type="hidden" name="annotation_json" id="annotation_json" value="">
  </form>
</body></html>"""
        layout = render_design_layout(html)
        self.assertIn('<crowd-form id="mturk_form" answer-format="flatten-objects">', layout)
        self.assertIn("WaveSurfer is embedded", layout)
        self.assertNotIn("externalSubmit", layout)

    def test_probe_uses_static_audio_and_minimal_inline_script(self) -> None:
        payload = build_payload(self.task, "test", 0)
        probe = render_design_layout_probe(payload)
        self.assertIn("STATIC HTML: visible.", probe)
        self.assertIn("INLINE JAVASCRIPT: executed successfully.", probe)
        self.assertIn("https://example.test/stereo.wav", probe)

    def test_canvas_layout_renders_core_controls_statically(self) -> None:
        payload = build_payload(self.task, "test", 0)
        layout = render_canvas_design_layout(payload)
        self.assertIn("File-level flags", layout)
        self.assertIn("Selected segment annotation", layout)
        self.assertIn("hello", layout)
        self.assertIn("native canvas waveform", layout)


if __name__ == "__main__":
    unittest.main()
