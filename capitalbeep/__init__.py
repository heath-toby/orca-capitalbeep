"""CapitalBeep: a short tone for capital letters during character navigation.

Orca 51 user extension. Install to $XDG_DATA_HOME/orca/extensions/ and
approve with ``orca --approve-extension capitalbeep``; Orca re-checks the
hash of every file in the package on each start, so re-approve after
editing. The generated beep and the on/off state live in
$XDG_DATA_HOME/orca/capitalbeep/, outside the package, so that writing
them cannot invalidate that approval.
"""

__version__ = "2.2.1"

from orca.extension import Extension
from orca.extension_preferences import ExtensionPreference

# Import submodules as `from .module import name`, never as
# `from . import module`. The loader imports us as
# orca_user_extension.<name> but never creates `orca_user_extension`
# itself, and `from . import module` goes through __import__ with the
# full dotted path, which insists on importing that absent grandparent.
from .capitalbeep import CAPS_FREQUENCY_HZ as _CAPS_FREQUENCY_HZ
from .capitalbeep import CAPS_MODE_DEFAULT as _CAPS_MODE_DEFAULT
from .capitalbeep import CAPS_MODE_EVERY as _CAPS_MODE_EVERY
from .capitalbeep import CAPS_MODE_LOWERCASE as _CAPS_MODE_LOWERCASE
from .capitalbeep import CAPS_MODE_OFF as _CAPS_MODE_OFF
from .capitalbeep import install as _install
from .capitalbeep import toggle as _toggle
from .capitalbeep import uninstall as _uninstall


class CapitalBeep(Extension):
    """Beeps whenever a capital letter is read out as a character."""

    GROUP_LABEL = "Capital Beep"
    DESCRIPTION = "Plays a short tone whenever a capital letter is read as a character, during navigation, spelling and typing echo, and a second, higher tone to warn that caps lock is on."
    VERSION = "2.2.1"  # keep in sync with __version__; read by AST, must be a literal
    AUTHOR = "Toby"

    def _get_commands(self) -> list:
        """Returns this extension's keyboard commands."""

        from orca import command_manager, keybindings

        keybinding = keybindings.KeyBinding(
            "c",
            keybindings.ORCA_CTRL_MODIFIER_MASK | keybindings.SHIFT_MODIFIER_MASK,
        )
        return [
            command_manager.KeyboardCommand(
                name="capitalBeepToggle",
                function=_toggle,
                group_label=self.GROUP_LABEL,
                description="Toggle the capital letter beep",
                desktop_keybinding=keybinding,
                laptop_keybinding=keybinding,
            )
        ]

    # These two are the only preferences, and they are declared rather than
    # given a dialog of their own, because they are a radio group and a number
    # -- nothing a generated form cannot render. The on/off switch is still
    # deliberately absent from here: Orca+Ctrl+Shift+C announces and persists
    # the state, and the extension's own enable/disable sits in User
    # Extensions already. A third control saying the same thing would only
    # confuse.
    def get_preferences(self) -> list[ExtensionPreference]:
        """Returns this extension's declarative preferences."""

        return [
            ExtensionPreference.enum(
                "caps-lock-beep",
                "Warn that caps lock is on",
                (
                    (_CAPS_MODE_LOWERCASE,
                     "When a lowercase letter is typed, because caps lock is on"),
                    (_CAPS_MODE_EVERY, "On every letter typed while caps lock is on"),
                    (_CAPS_MODE_OFF, "Never"),
                ),
                _CAPS_MODE_DEFAULT,
            ),
            ExtensionPreference.integer(
                "caps-lock-pitch",
                "Pitch of the caps lock warning, in hertz",
                _CAPS_FREQUENCY_HZ, 100, 8000,
            ),
            ExtensionPreference.boolean(
                "debug", "Log diagnostics to capitalbeep/debug.log", False,
            ),
        ]

    def on_ready(self) -> None:
        """Starts beeping once Orca is up."""

        _install(lambda: self.settings)

    def on_enabled(self) -> None:
        """Starts beeping after a reload."""

        _install(lambda: self.settings)

    def on_disabled(self) -> None:
        """Removes the hooks, restoring Orca's own speech methods."""

        _uninstall()

    def on_shutdown(self) -> None:
        """Deliberately does nothing.

        Orca runs shutdown hooks in a daemon thread with a timeout, but
        tearing this extension down means GLib source removal, GStreamer
        state changes and un-monkey-patching, all of which are main-thread
        work. Doing it off-thread risks a warning, an assertion or a hung
        exit -- and buys nothing, because the process is exiting anyway.
        on_disabled, which Orca does call on the main thread, still does
        the real teardown when the extension is disabled or reloaded.
        """
