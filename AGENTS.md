# Repository Guidelines

## Project Structure & Module Organization

This repository has two delivery paths plus shared Label Studio tooling. `prolific/` contains the Prolific-compatible annotation server, worker UI, runtime data directories, and planning docs. `mturk/` contains the MTurk HTMLQuestion/layout generator, vendored WaveSurfer assets, and generated preview outputs. `label_studio/` contains the Label Studio config, input task JSON/CSV files, exports, and summary utilities. Tests live in `tests/` and are split by delivery path.

## Build, Test, and Development Commands

- `python -m unittest discover -s tests -v`: run the full test suite.
- `python -m py_compile prolific/conversation_annotation_app/app.py`: syntax-check the pilot server.
- `COMPLETION_URL='https://app.prolific.com/submissions/complete?cc=YOUR_CODE' prolific/run_annotation_app.sh`: start the Prolific app on `0.0.0.0:8000`.
- `python prolific/conversation_annotation_app/app.py --tasks label_studio/data/tasks_test_predictions.json --bundle-size 1`: run the server directly.
- `python mturk/build_mturk_audio_mvp.py label_studio/data/tasks_test_predictions.json`: regenerate MTurk preview/layout assets.

Use `uv sync` if you need the declared `label-studio` dependency from `pyproject.toml` and `uv.lock`.

## Coding Style & Naming Conventions

Use Python 3.10+ syntax, four-space indentation, and type hints for public helpers or non-obvious data shapes. Keep the Prolific app standard-library-first unless a workflow truly requires a framework. Use `Path`, UTF-8 reads/writes, and deterministic JSON formatting. Use snake_case for Python names and descriptive task/data names such as `tasks_test_predictions.json`, `SESSION_ID.json`, and `ctc_status_summary_example.csv`.

## Testing Guidelines

Tests use `unittest` and temporary directories. Update `tests/test_prolific_annotation_app.py` when changing assignment, submission, or saved schema behavior. Update `tests/test_mturk_audio_mvp.py` when changing payload normalization or generated HTML/XML output. Prefer stable string, JSON-field, and file-existence assertions over full snapshots.

## Commit & Pull Request Guidelines

Recent commits use concise, imperative summaries such as `Add Prolific annotation pilot app` and `Document Prolific annotation workflow`. Keep commits focused on one workflow or artifact group. Pull requests should include purpose, commands run, affected path (`prolific`, `mturk`, or `label_studio`), and any generated files intentionally changed.

## Security & Configuration Tips

Do not commit real Prolific completion codes, participant data, or production submissions. Runtime data belongs under `prolific/conversation_annotation_app/data/`; treat `assignments.json` and `submissions/*.json` as operational artifacts unless adding sanitized fixtures.
