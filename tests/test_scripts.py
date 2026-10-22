from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def fake_audio_tools(tmp_path: Path, *, capture: str, playback: str) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    executable(bin_dir / "arecord", f"#!/bin/sh\nprintf '%s\\n' '{capture}'\n")
    executable(bin_dir / "aplay", f"#!/bin/sh\nprintf '%s\\n' '{playback}'\n")
    environment = os.environ.copy()
    environment["PATH"] = f"{bin_dir}:{environment['PATH']}"
    return environment


def test_audio_detection_preserves_capture_and_playback_device_numbers(
    tmp_path: Path,
) -> None:
    environment = fake_audio_tools(
        tmp_path,
        capture="card 2: Phone [USB Phone], device 1: USB Audio [USB Audio]",
        playback="card 2: Phone [USB Phone], device 3: USB Audio [USB Audio]",
    )

    result = subprocess.run(
        [ROOT / "scripts/detect_audio_device.sh"],
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )

    assert result.stdout.splitlines() == [
        "AUDIO_CAPTURE_DEVICE=plughw:CARD=Phone,DEV=1",
        "AUDIO_PLAYBACK_DEVICE=plughw:CARD=Phone,DEV=3",
    ]


def test_audio_detection_rejects_multiple_bidirectional_cards(tmp_path: Path) -> None:
    capture = "\n".join(
        [
            "card 1: First [First], device 0: USB Audio [USB Audio]",
            "card 2: Second [Second], device 0: USB Audio [USB Audio]",
        ]
    )
    playback = capture
    environment = fake_audio_tools(tmp_path, capture=capture, playback=playback)

    result = subprocess.run(
        [ROOT / "scripts/detect_audio_device.sh"],
        env=environment,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "encontrei 2" in result.stderr
    assert "First" in result.stderr
    assert "Second" in result.stderr


def test_audio_detection_rejects_missing_bidirectional_card(tmp_path: Path) -> None:
    environment = fake_audio_tools(tmp_path, capture="", playback="")

    result = subprocess.run(
        [ROOT / "scripts/detect_audio_device.sh"],
        env=environment,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "encontrei 0" in result.stderr


def test_deploy_explicitly_preserves_remote_runtime_and_secrets(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "commands.log"
    executable(bin_dir / "ssh", "#!/bin/sh\nexit 0\n")
    executable(
        bin_dir / "rsync",
        '#!/bin/sh\nprintf "%s\\n" "$@" >"$COMMAND_LOG"\n',
    )
    environment = os.environ.copy()
    environment["PATH"] = f"{bin_dir}:{environment['PATH']}"
    environment["COMMAND_LOG"] = str(log)
    environment["PI_HOST"] = "user@pi"
    environment["PI_DIR"] = "/home/user/app"

    subprocess.run(
        [ROOT / "scripts/deploy.sh"], env=environment, check=True, capture_output=True
    )
    arguments = log.read_text(encoding="utf-8").splitlines()

    pairs = list(zip(arguments, arguments[1:]))
    for preserved in [".env", ".venv/", ".deps/", "models/", "runtime/"]:
        assert ("--exclude", preserved) in pairs, f"faltou preservar {preserved}"
    assert "--delete" not in arguments
    assert arguments.index(".env.example") < arguments.index(".env.*")
    assert ("--include", ".env.example") in pairs
    assert ("--exclude", ".env.*") in pairs


def test_bootstrap_restricts_env_permissions() -> None:
    bootstrap = (ROOT / "scripts/bootstrap_pi.sh").read_text(encoding="utf-8")

    assert 'chmod 600 "$project_root/.env"' in bootstrap


def test_deploy_requires_explicit_destination() -> None:
    environment = os.environ.copy()
    environment.pop("PI_HOST", None)
    environment.pop("PI_DIR", None)
    result = subprocess.run(
        [ROOT / "scripts/deploy.sh"], env=environment, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "Defina PI_HOST" in result.stderr


def test_deploy_rejects_remote_shell_characters(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment["PI_HOST"] = "user@pi"
    environment["PI_DIR"] = "/home/user/app'; touch /tmp/unsafe; '"
    result = subprocess.run(
        [ROOT / "scripts/deploy.sh"], env=environment, capture_output=True, text=True
    )
    assert result.returncode == 2
    assert "inválido" in result.stderr
