import threading
import time
from types import SimpleNamespace

from raspberry_phone.controller import TurnController
from raspberry_phone.conversation import ConversationHistory, ConversationStore
from raspberry_phone.state import StateStore
from raspberry_phone.response import respond, INTERRUPTED_CONTEXT
from raspberry_phone.cancellation import Cancellation


def eventually(condition):
    deadline = time.monotonic() + 3
    while not condition():
        assert time.monotonic() < deadline
        time.sleep(.005)


class Input:
    def __init__(self):
        self.ready = threading.Event()
        self.calls = None

    def listen_session(self, **callbacks):
        self.calls = callbacks
        callbacks['on_ready']()
        self.ready.set()
        while not callbacks['stop'].wait(.01):
            if callbacks['release'].is_set():
                callbacks['on_utterance']('manual')
                return


class LLM:
    def stream(self, messages, *, cancel):
        yield 'Uma resposta.'


class Speaker:
    def __init__(self):
        self.started = threading.Event()
        self.allow = threading.Event()
        self.calls = 0

    def speak(self, phrases, *, on_first_audio, cancel):
        for phrase in phrases:
            cancel.check()
            self.calls += 1
            on_first_audio()
            self.started.set()
            while not self.allow.wait(.005):
                cancel.check()


def setup(tmp_path):
    conversation = ConversationStore(tmp_path / 'conversation.json')
    assistant = SimpleNamespace(speech_input=Input(), history=ConversationHistory(),
        conversation=conversation, state=StateStore(tmp_path / 'state.json', turns_provider=conversation.turns),
        llm=LLM(), speaker=Speaker(), phrase_max_chars=180)
    controller = TurnController(assistant, history=assistant.history, conversation=conversation, state=assistant.state)
    return assistant, controller


def test_continuous_silence_multiple_turns_and_barge_in(tmp_path):
    a, c = setup(tmp_path)
    assert a.state.snapshot()['mode'] == 'continuous'
    assert not a.state.snapshot()['session_active']
    assert c.start_session('continuous')
    assert a.speech_input.ready.wait(1)
    assert a.conversation.turns() == []
    assert not c.start_turn()
    assert not c.reset_conversation()
    assert not c.set_mode('push-to-talk')
    cb = a.speech_input.calls
    cb['on_utterance']('primeira')
    assert a.speaker.started.wait(1)
    assert a.state.snapshot()['listening']
    cb['on_speech']()
    cb['on_partial']('segunda desde o início')
    cb['on_utterance']('segunda desde o início')
    eventually(lambda: len(a.conversation.turns()) == 2)
    assert a.conversation.turns()[0]['status'] == 'interrupted'
    assert a.history.messages()[1]['content'] == INTERRUPTED_CONTEXT
    a.speaker.allow.set()
    eventually(lambda: a.conversation.turns()[-1]['status'] == 'complete')
    for number in range(8):
        cb['on_speech']()
        cb['on_utterance'](f'pergunta {number}')
        eventually(lambda: len(a.conversation.turns()) == number + 3 and a.conversation.turns()[-1]['status'] == 'complete')
    assert a.state.snapshot()['session_active']
    assert c.stop_session()
    eventually(lambda: not c.busy)
    assert not a.state.snapshot()['listening']
    c.shutdown()


def test_manual_release_id_and_shutdown_while_speaking(tmp_path):
    a, c = setup(tmp_path)
    assert c.set_mode('push-to-talk')
    assert not c.start_session('continuous')
    assert c.start_session('push-to-talk', 'capture-1')
    assert a.speech_input.ready.wait(1)
    assert not c.stop_session(capture_id='old', release=True)
    assert c.stop_session(capture_id='capture-1', release=True)
    assert a.speaker.started.wait(1)
    c.shutdown()
    assert not c.busy
    assert a.conversation.turns()[0]['status'] == 'interrupted'
    assert not c.start_session('push-to-talk', 'capture-2')


def test_input_failure_stops_session_and_allows_explicit_retry(tmp_path):
    a, c = setup(tmp_path)
    def fail(**callbacks):
        raise RuntimeError('rede indisponível')
    a.speech_input.listen_session = fail
    assert c.start_session('continuous')
    eventually(lambda: not c.busy)
    snapshot = a.state.snapshot()
    assert snapshot['status'] == 'error'
    assert snapshot['error'] == 'rede indisponível'
    assert not snapshot['session_active']
    a.speech_input = Input()
    assert c.start_session('continuous')
    c.shutdown()


def test_cancel_during_generation_rejects_late_tokens(tmp_path):
    a, _ = setup(tmp_path)
    entered = threading.Event()
    class LateLLM:
        def stream(self, messages, *, cancel):
            entered.set()
            assert cancel.event.wait(1)
            yield 'texto atrasado'
    a.llm = LateLLM()
    cancel = Cancellation()
    thread = threading.Thread(target=respond, args=(a, 'pergunta', cancel))
    thread.start()
    assert entered.wait(1)
    cancel.cancel()
    thread.join(2)
    assert not thread.is_alive()
    assert a.speaker.calls == 0
    assert a.conversation.turns()[0]['answer'] == ''
    assert a.conversation.turns()[0]['status'] == 'interrupted'
