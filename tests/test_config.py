from pathlib import Path

import pytest

from raspberry_phone.config import AppConfig, ConfigurationError


def test_config_loads_defaults_and_resolves_project_paths(tmp_path: Path) -> None:
    config = AppConfig.from_mapping(
        {
            "OPENROUTER_API_KEY": "secret",
            "AUDIO_CAPTURE_DEVICE": "plughw:CARD=Phone,DEV=0",
            "AUDIO_PLAYBACK_DEVICE": "plughw:CARD=Phone,DEV=0",
        },
        root=tmp_path,
    )

    assert config.record_seconds == 10
    assert config.openrouter_model == "google/gemini-3.1-flash-lite"
    assert config.openrouter_reasoning_effort == "none"
    assert config.web_host == "127.0.0.1"
    assert config.web_port == 8080
    assert config.whisper_cli == tmp_path / ".deps/whisper.cpp/build/bin/whisper-cli"
    assert config.whisper_model == tmp_path / "models/ggml-tiny.bin"
    assert config.runtime_dir == tmp_path / "runtime"


def test_config_rejects_unknown_reasoning_effort(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="OPENROUTER_REASONING_EFFORT"):
        AppConfig.from_mapping(
            {
                "OPENROUTER_API_KEY": "secret",
                "AUDIO_CAPTURE_DEVICE": "capture",
                "AUDIO_PLAYBACK_DEVICE": "playback",
                "OPENROUTER_REASONING_EFFORT": "gigantic",
            },
            root=tmp_path,
        )


def test_config_rejects_invalid_web_port(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="WEB_PORT"):
        AppConfig.from_mapping(
            {
                "OPENROUTER_API_KEY": "secret",
                "AUDIO_CAPTURE_DEVICE": "capture",
                "AUDIO_PLAYBACK_DEVICE": "playback",
                "WEB_PORT": "70000",
            },
            root=tmp_path,
        )


@pytest.mark.parametrize(
    ("missing_name", "environment"),
    [
        (
            "OPENROUTER_API_KEY",
            {
                "AUDIO_CAPTURE_DEVICE": "capture",
                "AUDIO_PLAYBACK_DEVICE": "playback",
            },
        ),
        (
            "AUDIO_CAPTURE_DEVICE",
            {
                "OPENROUTER_API_KEY": "secret",
                "AUDIO_PLAYBACK_DEVICE": "playback",
            },
        ),
        (
            "AUDIO_PLAYBACK_DEVICE",
            {
                "OPENROUTER_API_KEY": "secret",
                "AUDIO_CAPTURE_DEVICE": "capture",
            },
        ),
    ],
)
def test_config_fails_fast_when_required_value_is_missing(
    missing_name: str, environment: dict[str, str], tmp_path: Path
) -> None:
    with pytest.raises(ConfigurationError, match=missing_name):
        AppConfig.from_mapping(environment, root=tmp_path)
