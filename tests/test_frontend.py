from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="Node.js não está disponível")
def test_frontend_logic_executes_status_scroll_and_safe_text_behaviors() -> None:
    module_url = (
        Path(__file__).parents[1] / "src" / "raspberry_phone" / "web" / "ui.mjs"
    ).as_uri()
    script = f"""
        import assert from "node:assert/strict";
        import {{
          controlsDisabled,
          followBehavior,
          shouldFollow,
          statusCopy,
          writeText,
        }} from {module_url!r};

        const copy = statusCopy(11);
        assert.equal(copy.ready.action, "Falar");
        assert.match(copy.recording.detail, /11s/);
        assert.equal(controlsDisabled(true, false, copy.ready), false);
        assert.equal(controlsDisabled(true, false, copy.thinking), true);
        assert.equal(controlsDisabled(false, false, copy.ready), true);
        assert.equal(controlsDisabled(true, true, copy.ready), true);
        assert.equal(shouldFollow(1000, 650, 300), true);
        assert.equal(shouldFollow(1000, 300, 300), false);
        assert.equal(followBehavior(true), "auto");
        assert.equal(followBehavior(false), "auto");

        const element = {{ textContent: "", innerHTML: "intacto" }};
        const hostile = "<img src=x onerror=alert(1)>";
        writeText(element, hostile);
        assert.equal(element.textContent, hostile);
        assert.equal(element.innerHTML, "intacto");
    """

    subprocess.run(
        [NODE, "--input-type=module", "--eval", script],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(NODE is None, reason="Node.js não está disponível")
def test_hold_to_talk_serializes_early_release_repeat_and_cancel():
    module_url = (Path(__file__).parents[1] / 'src/raspberry_phone/web/ui.mjs').as_uri()
    script = f'''
      import assert from "node:assert/strict";
      import {{ HoldToTalk }} from {module_url!r};
      const calls = [];
      let acknowledge;
      let id = 0;
      const hold = new HoldToTalk((path, payload) => {{
        calls.push([path, payload.capture_id]);
        if (path.endsWith("press")) return new Promise(resolve => acknowledge = resolve);
        return Promise.resolve(true);
      }}, () => `capture-${{++id}}`);
      hold.press();
      hold.press(); // repeated keydown
      const released = hold.finish();
      assert.deepEqual(calls, [["/api/ptt/press", "capture-1"]]);
      acknowledge(true);
      await released;
      assert.deepEqual(calls[1], ["/api/ptt/release", "capture-1"]);
      hold.press();
      const cancelled = hold.finish(true); // blur, pointercancel or pagehide
      acknowledge(true);
      await cancelled;
      assert.deepEqual(calls[3], ["/api/ptt/cancel", "capture-2"]);
      await hold.finish(true); // lostpointercapture after pointerup is harmless
      assert.equal(calls.length, 4);
      hold.press();
      const rejected = hold.finish();
      acknowledge(false);
      await rejected;
      assert.equal(calls.length, 5);
    '''
    subprocess.run([NODE, '--input-type=module', '--eval', script], check=True, capture_output=True, text=True)


@pytest.mark.skipif(NODE is None, reason="Node.js não está disponível")
def test_browser_entry_point_handles_live_updates_and_microphone_controls():
    subprocess.run(
        [NODE, str(Path(__file__).with_name("frontend_app.mjs"))],
        check=True, capture_output=True, text=True,
    )
