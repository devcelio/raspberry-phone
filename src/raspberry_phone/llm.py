from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from typing import Any
import asyncio

from .cancellation import Cancellation, ResponseCancelled


class LLMError(RuntimeError):
    pass


class OpenRouterProvider:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        max_tokens: int,
        temperature: float,
        reasoning_effort: str,
        timeout_seconds: float,
        system_prompt: str,
        client: Any | None = None,
    ) -> None:
        self._connection = dict(api_key=api_key, base_url=base_url, timeout=timeout_seconds)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.reasoning_effort = reasoning_effort
        self.system_prompt = system_prompt
        self.usage: Any = None
        self._client = client or self._build_client(
            api_key=api_key, base_url=base_url, timeout_seconds=timeout_seconds
        )

    @staticmethod
    def _build_client(*, api_key: str, base_url: str, timeout_seconds: float) -> Any:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise LLMError(
                "Dependência openai ausente; execute o bootstrap do projeto"
            ) from exc
        return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_seconds)

    def stream(self, messages: Sequence[dict[str, str]], *, cancel: Cancellation | None = None) -> Iterator[str]:
        request_messages = [
            {"role": "system", "content": self.system_prompt},
            *messages,
        ]
        self.usage = None
        received_text = False
        remove_cancel = lambda: None
        response: Any = None
        try:
            if cancel:
                cancel.check()
            request = dict(
                model=self.model,
                messages=request_messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                extra_body={"reasoning": {"effort": "minimal" if "gemini-3.1-flash-lite" in self.model and self.reasoning_effort == "none" else self.reasoning_effort}, "provider": {"sort": "latency"}},
                stream_options={"include_usage": True},
                stream=True,
            )
            response = (self._cancellable_chunks(request, cancel) if cancel
                        else self._client.chat.completions.create(**request))
            if cancel:
                cancel.check()
            for chunk in response:
                if cancel:
                    cancel.check()
                if getattr(chunk, "usage", None):
                    self.usage = chunk.usage
                if not chunk.choices:
                    continue
                content = chunk.choices[0].delta.content
                if content:
                    received_text = True
                    yield content
            if not received_text:
                details = getattr(self.usage, "completion_tokens_details", None)
                if getattr(details, "reasoning_tokens", 0):
                    raise LLMError("O limite de tokens foi consumido pelo raciocínio. Configure OPENROUTER_REASONING_EFFORT=none para este modelo e reinicie o telefone.")
                raise LLMError("O provedor encerrou a resposta sem texto. Tente novamente.")
        except ResponseCancelled:
            raise
        except LLMError:
            raise
        except Exception as exc:
            if cancel:
                cancel.check()
            raise LLMError(f"Falha no OpenRouter: {exc}") from exc
        finally:
            remove_cancel()
            if response is not None and hasattr(response, "close"):
                response.close()

    def _cancellable_chunks(self, request: dict[str, Any], cancel: Cancellation):
        """Cancel even while awaiting HTTP headers, without orphan request threads."""
        from openai import AsyncOpenAI
        loop = asyncio.new_event_loop()
        client = AsyncOpenAI(**self._connection, max_retries=0)
        response = None

        def run(awaitable):
            async def wait():
                return await awaitable
            task = loop.create_task(wait())
            def interrupt():
                loop.call_soon_threadsafe(task.cancel)
            remove = cancel.register(interrupt)
            try:
                return loop.run_until_complete(task)
            except asyncio.CancelledError:
                raise ResponseCancelled() from None
            finally:
                remove()

        try:
            cancel.check()
            response = run(client.chat.completions.create(**request))
            iterator = response.__aiter__()
            while True:
                cancel.check()
                try:
                    yield run(anext(iterator))
                except StopAsyncIteration:
                    return
        finally:
            try:
                if response is not None:
                    loop.run_until_complete(response.close())
                loop.run_until_complete(client.close())
            finally:
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()
