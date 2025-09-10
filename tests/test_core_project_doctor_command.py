# tests/test_core_project_doctor_command.py
import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db


def test_project_doctor_runs_without_error(capsys):
    call_command("project_doctor")
    out = capsys.readouterr().out.lower()
    # Expect some known phrase printed by your command
    assert "doctor" in out or "ok" in out or "ready" in out
