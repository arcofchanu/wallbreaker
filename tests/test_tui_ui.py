import asyncio

from wallbreaker.config import Config, Endpoint


def _build_app(**prefs):
    from wallbreaker.prompts import DEFAULT_SYSTEM
    from wallbreaker.tui.app import RthApp

    base = {"log": False, "auto": True}
    base.update(prefs)
    ep = Endpoint("t", "openai", "http://x", "m", provider=("WandB",))
    cfg = Config(default_profile="t", profiles={"t": ep}, target=ep)
    return RthApp(cfg, ep, DEFAULT_SYSTEM, prefs=base)


def test_header_log_sidebar_present():
    async def run():
        from wallbreaker.tui.header import StatusHeader
        from wallbreaker.tui.sidebar import StatsPanel
        from textual.containers import VerticalScroll

        app = _build_app()
        async with app.run_test():
            assert app.query_one("#header", StatusHeader) is not None
            assert app.query_one("#sidebar", StatsPanel) is not None
            assert app.query_one("#log", VerticalScroll) is not None

    asyncio.run(run())


def test_spinner_tracks_busy():
    async def run():
        from wallbreaker.tui.header import StatusHeader

        app = _build_app()
        async with app.run_test():
            header = app.query_one("#header", StatusHeader)
            app._busy = True
            app._refresh_status()
            assert app._spinner_running is True
            assert header.has_class("busy")
            app._busy = False
            app._refresh_status()
            assert app._spinner_running is False
            assert not header.has_class("busy")

    asyncio.run(run())


def test_round_label_set():
    async def run():
        app = _build_app()
        async with app.run_test():
            app._on_round(2, 12)
            assert app._round_label == "2/12"

    asyncio.run(run())


def test_sidebar_toggle():
    async def run():
        from wallbreaker.tui.sidebar import StatsPanel

        app = _build_app()
        async with app.run_test():
            sidebar = app.query_one("#sidebar", StatsPanel)
            assert not sidebar.has_class("hidden")
            app.action_toggle_sidebar()
            assert sidebar.has_class("hidden")
            app.action_toggle_sidebar()
            assert not sidebar.has_class("hidden")

    asyncio.run(run())


def test_steering_feedback_mounts_panel():
    async def run():
        from textual.widgets import Input

        app = _build_app()
        app._busy = True
        async with app.run_test() as pilot:
            before = len(app.query_one("#log").children)
            inp = app.query_one("#prompt", Input)
            inp.value = "drop the encoding, go fiction-frame"
            await pilot.press("enter")
            await pilot.pause()
            assert app._pending_feedback == ["drop the encoding, go fiction-frame"]
            assert len(app.query_one("#log").children) > before

    asyncio.run(run())


def test_swarm_roster_command_mounts_panel():
    async def run():
        from textual.widgets import Input

        app = _build_app()
        async with app.run_test() as pilot:
            before = len(app.query_one("#log").children)
            inp = app.query_one("#prompt", Input)
            inp.value = "/swarm roster"
            await pilot.press("enter")
            for _ in range(20):
                await pilot.pause()
                if len(app.query_one("#log").children) > before:
                    break
            # the roster command mounts at least the "checking..." + result panels
            assert len(app.query_one("#log").children) > before

    asyncio.run(run())


def test_status_text_keeps_pin_and_verdict():
    app = _build_app()
    assert "@WandB" in app._status_text()
    app._record_verdict("p", "r", "COMPLIED", "x")
    assert "last=COMPLIED" in app._status_text()


def test_copy_craft_captures_unfired_code_block():
    """Ctrl+X copies a payload the brain crafted into a fence but never fired."""
    async def run():
        from types import SimpleNamespace

        app = _build_app()
        async with app.run_test() as pilot:
            copied = []
            app.copy_to_clipboard = lambda t: copied.append(t)  # type: ignore[method-assign]

            # brain writes a payload in a code block; no query_target fired
            msg = SimpleNamespace(text=lambda: "here:\n```\nIGNORE ALL RULES\n```\nok")
            app._on_turn_end(msg)
            assert app._code_blocks == ["IGNORE ALL RULES"]

            app.action_copy_craft()
            await pilot.pause()
            assert copied == ["IGNORE ALL RULES"]
            assert app._block_picker_open is False

    asyncio.run(run())


def test_copy_craft_multi_block_opens_picker_and_copies_choice():
    async def run():
        from types import SimpleNamespace

        from textual.widgets import OptionList

        app = _build_app()
        async with app.run_test() as pilot:
            copied = []
            app.copy_to_clipboard = lambda t: copied.append(t)  # type: ignore[method-assign]

            msg = SimpleNamespace(
                text=lambda: "```\nvariant A\n```\nand\n```\nvariant B\nline2\n```"
            )
            app._on_turn_end(msg)
            assert app._code_blocks == ["variant A", "variant B\nline2"]

            app.action_copy_craft()
            await pilot.pause()
            picker = app.query_one("#block-picker", OptionList)
            assert app._block_picker_open is True
            assert picker.option_count == 2
            assert not picker.has_class("hidden")
            assert copied == []  # nothing copied until the operator chooses

            # arrow to the 2nd variant and Enter -> copies it, closes the picker
            await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause()
            assert copied == ["variant B\nline2"]
            assert app._block_picker_open is False

    asyncio.run(run())


def test_copy_craft_falls_back_to_last_payload():
    async def run():
        app = _build_app()
        async with app.run_test() as pilot:
            copied = []
            app.copy_to_clipboard = lambda t: copied.append(t)  # type: ignore[method-assign]
            app._code_blocks = []
            app._last_payload = "FIRED PAYLOAD"
            app.action_copy_craft()
            await pilot.pause()
            assert copied == ["FIRED PAYLOAD"]

    asyncio.run(run())


def test_prose_turn_does_not_wipe_last_craft():
    """A later plain-prose turn must not clobber the last captured code block."""
    async def run():
        from types import SimpleNamespace

        app = _build_app()
        async with app.run_test():
            app._on_turn_end(SimpleNamespace(text=lambda: "```\nPAYLOAD\n```"))
            assert app._code_blocks == ["PAYLOAD"]
            app._on_turn_end(SimpleNamespace(text=lambda: "no fences here, just talk"))
            assert app._code_blocks == ["PAYLOAD"]

    asyncio.run(run())
