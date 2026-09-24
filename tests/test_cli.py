"""CLI error handling (workspace rule: plain-English errors, never raw stack traces)."""

from __future__ import annotations

from typer.testing import CliRunner

from pipeline.__main__ import app
from pipeline.stages import fetch


def test_stage_errors_print_a_plain_message_not_a_traceback(settings):
    # res 7 is built from res 6: without hexes_r6 the grid stage must say so in a sentence
    fetch.run(settings)
    result = CliRunner().invoke(app, ["--fixtures", "--res", "7", "--root", str(settings.root), "grid"])
    assert result.exit_code == 1
    assert "run grid for res 6 first" in result.output
    assert "Traceback" not in result.output
    assert isinstance(result.exception, SystemExit)  # handled, not an uncaught exception
