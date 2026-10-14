#!/usr/bin/env bash
# CapitalBeep -- Installer
#
# Installs CapitalBeep as an Orca 51 user extension, into
# ~/.local/share/orca/extensions/, and approves it so Orca will load it.
#
# Only code goes in the extension package. The generated beep and the
# on/off state live in ~/.local/share/orca/capitalbeep/, which is where
# the add-on has always kept them -- and where they need to stay, because
# Orca approves an extension by hashing every file in its directory and
# refuses to load it if anything changed.
#
# Re-running is safe. Because approval is by content hash, the script
# re-approves on every run, which is what you want after editing.

set -euo pipefail

ADDON_NAME="capitalbeep"
ORCA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/orca"
ADDON_DIR="$ORCA_DIR/extensions/$ADDON_NAME"
DATA_DIR="$ORCA_DIR/$ADDON_NAME"
CUSTOMIZATIONS="$ORCA_DIR/orca-customizations.py"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_DIR="$SCRIPT_DIR/$ADDON_NAME"

BEGIN_MARKER="# --- capitalbeep begin ---"
END_MARKER="# --- capitalbeep end ---"

info()  { echo "  [+] $*"; }
error() { echo "  [ERROR] $*" >&2; exit 1; }

echo ""
echo "=== CapitalBeep -- Installer ==="
echo ""

# Probe via extension_loader, not orca.extension: importing orca.extension
# first hits a circular import inside Orca itself (live_region_presenter
# imports it mid-initialisation). extension_loader pulls in command_manager
# ahead of it, so this import order is the one that works.
if ! python3 -c "import orca.extension_loader" 2>/dev/null; then
    error "Orca 51 or later with extension support not found."
fi
info "Orca with extension support found."

[ -d "$SOURCE_DIR" ] || error "Source directory '$SOURCE_DIR' not found."
rm -rf "$SOURCE_DIR/__pycache__"

# The beep is rendered on first run and the state file written on first
# toggle, so this only needs to exist.
mkdir -p "$DATA_DIR"

mkdir -p "$ADDON_DIR"
# Remove files that no longer exist in the source, so the installed
# package -- and therefore its approval hash -- matches the source.
find "$ADDON_DIR" -maxdepth 1 -name '*.py' -delete
rm -rf "$ADDON_DIR/__pycache__"
cp "$SOURCE_DIR"/*.py "$ADDON_DIR/"
info "Installed extension package to $ADDON_DIR"

if orca --approve-extension "$ADDON_NAME" >/dev/null 2>&1; then
    info "Approved '$ADDON_NAME' with Orca."
else
    error "Could not approve the extension. Run: orca --approve-extension $ADDON_NAME"
fi

# Clean up after the pre-extension installer, if its block is still there.
if [ -f "$CUSTOMIZATIONS" ] && grep -qF "$BEGIN_MARKER" "$CUSTOMIZATIONS" 2>/dev/null; then
    sed -i "/${BEGIN_MARKER//\//\\/}/,/${END_MARKER//\//\\/}/d" "$CUSTOMIZATIONS"
    info "Removed the obsolete CapitalBeep block from orca-customizations.py."
fi

echo ""
echo "=== Installation complete ==="
echo ""
echo "  Restart Orca to activate:"
echo "    orca --replace &"
echo ""
echo "  Toggle with Orca+Ctrl+Shift+C. Beep and state: $DATA_DIR"
echo ""
