import threading
import time
from pathlib import Path

from raspberry_phone.controller import TurnController
from raspberry_phone.conversation import ConversationHistory, ConversationStore
from raspberry_phone.state import StateStore


class BlockingAssistant:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def run_turn(self) -> None:
        self.entered.set()
        assert self.release.wait(timeout=2)


def test_controller_serializes_turns_and_clears_only_while_idle(
    tmp_path: Path,
) -> None:
    assistant = BlockingAssistant()
    history = ConversationHistory()
    history.add_turn("pergunta", "resposta")
    conversation = ConversationStore(tmp_path / "conversation.json")
    turn_id = conversation.begin_turn("pergunta")
    conversation.complete_turn(turn_id, "resposta")
    state = StateStore(
        tmp_path / "state.json", turns_provider=conversation.turns
    )
    controller = TurnController(
        assistant,
        history=history,
        conversation=conversation,
        state=state,
    )

    assert controller.reset_conversation()
    assert conversation.turns() == []
    assert history.messages() == []
    assert controller.start_turn()
    assert assistant.entered.wait(timeout=2)
    assert not controller.start_turn()
    assert not controller.reset_conversation()

    assistant.release.set()
    deadline = time.monotonic() + 2
    while controller.busy and time.monotonic() < deadline:
        time.sleep(0.01)

    controller.run_turn()
    controller.shutdown()
    assert not controller.start_turn()


def test_enter_turn_blocks_web_turn_through_the_same_controller(
    tmp_path: Path,
) -> None:
    assistant = BlockingAssistant()
    history = ConversationHistory()
    conversation = ConversationStore(tmp_path / "conversation.json")
    state = StateStore(
        tmp_path / "state.json", turns_provider=conversation.turns
    )
    controller = TurnController(
        assistant,
        history=history,
        conversation=conversation,
        state=state,
    )
    enter_thread = threading.Thread(target=controller.run_turn)

    enter_thread.start()
    assert assistant.entered.wait(timeout=2)
    assert not controller.start_turn()
    assert not controller.reset_conversation()

    assistant.release.set()
    enter_thread.join(timeout=2)
    assert not enter_thread.is_alive()
    controller.shutdown()
