import io
from types import SimpleNamespace

from raspberry_phone.cli import run_interactive


class FakeState:
    def __init__(self) -> None:
        self.statuses: list[str] = []

    def publish(self, status: str, **_kwargs: object) -> None:
        self.statuses.append(status)


class FakeAssistant:
    def __init__(self) -> None:
        self.state = FakeState()
        self.turns = 0

    def run_turn(self):
        self.turns += 1
        return SimpleNamespace(
            transcript="Olá",
            answer="Oi!",
            timings_seconds={"turn_total": 1.25},
        )


def test_interactive_cli_runs_a_turn_then_quits() -> None:
    answers = iter(["", "q"])
    assistant = FakeAssistant()
    output = io.StringIO()

    exit_code = run_interactive(
        assistant,
        input_fn=lambda _prompt: next(answers),
        output=output,
    )

    assert exit_code == 0
    assert assistant.turns == 1
    assert assistant.state.statuses == ["ready", "stopped"]
    assert "Você: Olá" in output.getvalue()
    assert "Telefone: Oi!" in output.getvalue()
