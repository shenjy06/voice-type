# Repository Guidelines

## Project Structure & Module Organization

Voice Type is a Python 3.10+ Windows desktop dictation app. Application code lives in `voicetype/`, with the entry point in `voicetype/__main__.py`. Core modules include audio capture (`voicetype/audio.py`), ASR and polishing clients (`voicetype/asr.py`, `voicetype/polisher.py`, `voicetype/api_client.py`), glossary post-processing (`voicetype/glossary.py`), configuration/history storage (`voicetype/config.py`, `voicetype/history.py`), and text injection (`voicetype/typer.py`). Qt UI code is under `voicetype/ui/`. Tests live in `tests/`, with UI tests in `tests/ui/`. Packaging files are `VoiceType.spec`, `build.bat`, and the generated `build/` and `dist/` directories.

## Build, Test, and Development Commands

Install runtime dependencies:

```cmd
pip install -r requirements.txt
```

Install the project with test dependencies:

```cmd
pip install -e ".[dev]"
```

Run the app locally:

```cmd
python -m voicetype
```

Run tests:

```cmd
pytest tests/ -v
```

Build the Windows executable:

```cmd
build.bat
```

or:

```cmd
pyinstaller --clean --noconfirm VoiceType.spec
```

## Coding Style & Naming Conventions

Follow idiomatic Python with 4-space indentation, type hints where they clarify interfaces, and small modules that match existing boundaries. Use `snake_case` for functions, methods, variables, and module files; use `PascalCase` for classes. Keep UI-specific logic in `voicetype/ui/` and avoid mixing Qt widget code into service modules. No formatter or linter is currently configured, so keep edits consistent with surrounding files.

## Testing Guidelines

The test suite uses `pytest`, with `pytest-qt` for Qt widgets and `pytest-mock` for mocks. Name test files `test_*.py` and place them near the behavior they cover, for example `tests/test_config.py` for `voicetype/config.py` or `tests/ui/test_main_window.py` for `voicetype/ui/main_window.py`. Add focused tests for changed behavior, especially around API error handling, settings persistence, glossary replacements, history, and paste modes. Run `pytest tests/ -v` before packaging.

## Commit & Pull Request Guidelines

Recent commits use Conventional Commit-style subjects such as `fix: stabilize temp audio filenames`, `feat: add paste modes and history`, and scoped forms like `fix(typer): paste into terminal windows`. Prefer `feat:`, `fix:`, `build:`, `test:`, or `docs:` prefixes with concise imperative descriptions.

Pull requests should include a short summary, test results, linked issues when applicable, and screenshots or screen recordings for visible UI changes. For packaging changes, mention whether `build.bat` or `pyinstaller --clean --noconfirm VoiceType.spec` was tested.

## Security & Configuration Tips

Do not commit API keys, provider credentials, generated audio, local SQLite history, or packaged binaries. Keep provider configuration in the app settings and use placeholder values in documentation.
