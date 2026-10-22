from types import SimpleNamespace

import pytest

from raspberry_phone.llm import LLMError, OpenRouterProvider


class FakeCompletions:
    def __init__(self, chunks: list[object] | None = None, error: Exception | None = None):
        self.chunks = chunks or []
        self.error = error
        self.request: dict[str, object] | None = None

    def create(self, **request: object) -> list[object]:
        self.request = request
        if self.error:
            raise self.error
        return self.chunks


def chunk(content: str | None) -> object:
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content))]
    )


def test_openrouter_stream_yields_text_and_sends_expected_request() -> None:
    completions = FakeCompletions([chunk("Olá"), chunk(None), chunk(", mundo!")])
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    provider = OpenRouterProvider(
        api_key="secret",
        base_url="https://openrouter.ai/api/v1",
        model="google/gemini-3.1-flash-lite",
        max_tokens=180,
        temperature=0.3,
        reasoning_effort="none",
        timeout_seconds=30,
        system_prompt="Responda em português.",
        client=client,
    )

    result = list(provider.stream([{"role": "user", "content": "Oi"}]))

    assert result == ["Olá", ", mundo!"]
    assert completions.request == {
        "model": "google/gemini-3.1-flash-lite",
        "messages": [
            {"role": "system", "content": "Responda em português."},
            {"role": "user", "content": "Oi"},
        ],
        "max_tokens": 180,
        "temperature": 0.3,
        "extra_body": {"reasoning": {"effort": "minimal"}, "provider": {"sort": "latency"}},
        "stream_options": {"include_usage": True},
        "stream": True,
    }


@pytest.mark.parametrize("error", [RuntimeError("401 unauthorized"), TimeoutError("timeout")])
def test_openrouter_errors_use_a_stable_application_exception(error: Exception) -> None:
    completions = FakeCompletions(error=error)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    provider = OpenRouterProvider(
        api_key="secret",
        base_url="https://openrouter.ai/api/v1",
        model="model",
        max_tokens=180,
        temperature=0.3,
        reasoning_effort="none",
        timeout_seconds=30,
        system_prompt="prompt",
        client=client,
    )

    with pytest.raises(LLMError, match=str(error)):
        list(provider.stream([]))


def test_reasoning_exhaustion_has_actionable_error_instead_of_empty_answer():
    usage = SimpleNamespace(completion_tokens_details=SimpleNamespace(reasoning_tokens=100))
    completions = FakeCompletions([SimpleNamespace(choices=[], usage=usage)])
    provider = OpenRouterProvider(api_key='secret', base_url='https://openrouter.ai/api/v1',
        model='qwen/qwen3.8-27b', max_tokens=100, temperature=.3, reasoning_effort='low',
        timeout_seconds=20, system_prompt='Responda em português.',
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)))
    with pytest.raises(LLMError, match='raciocínio'):
        list(provider.stream([{'role':'user','content':'Qual a capital do Brasil?'}]))


def test_cancel_while_waiting_for_http_headers_closes_client(monkeypatch):
    import asyncio
    import threading
    import sys
    from raspberry_phone.cancellation import Cancellation, ResponseCancelled
    from types import SimpleNamespace
    from raspberry_phone.llm import OpenRouterProvider
    entered, closed = threading.Event(), threading.Event()
    class AsyncClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=self)
        async def create(self, **kwargs):
            entered.set()
            await asyncio.Future()
        async def close(self): closed.set()
    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(AsyncOpenAI=AsyncClient))
    provider = OpenRouterProvider(api_key='test', base_url='https://example.com', model='test',
        max_tokens=10, temperature=.2, reasoning_effort='none', timeout_seconds=30, system_prompt='test', client=object())
    cancel = Cancellation()
    results = []
    def generate():
        try:
            list(provider.stream([], cancel=cancel))
        except ResponseCancelled:
            results.append('cancelled')
    thread = threading.Thread(target=generate)
    thread.start()
    assert entered.wait(2)
    cancel.cancel()
    thread.join(2)
    assert not thread.is_alive()
    assert results == ['cancelled']
    assert closed.is_set()
