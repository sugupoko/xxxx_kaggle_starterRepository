#!/bin/bash
# Language setup script for Competition Workspace Template
# Usage: ./setup.sh [ja|en]

set -e

# NOTE: named LOCALE (not LANG) on purpose -- LANG would clobber the POSIX locale env var
LOCALE="${1:-ja}"

if [[ "$LOCALE" != "ja" && "$LOCALE" != "en" ]]; then
    echo "Usage: ./setup.sh [ja|en]"
    echo "  ja - Japanese (default)"
    echo "  en - English"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCALE_DIR="$SCRIPT_DIR/locales/$LOCALE"

if [ ! -d "$LOCALE_DIR" ]; then
    echo "Error: Locale directory not found: $LOCALE_DIR"
    exit 1
fi

echo "Setting up language: $LOCALE"

# Copy a user-editable template, but never clobber user content:
# overwrite only if the current file byte-matches the ja or en template
# (= pristine). If the user has edited it, keep it and say so.
copy_user_template() {
    local rel="$1"
    local dst="$SCRIPT_DIR/$rel"
    if [ -f "$dst" ] \
        && ! cmp -s "$dst" "$SCRIPT_DIR/locales/ja/$rel" \
        && ! cmp -s "$dst" "$SCRIPT_DIR/locales/en/$rel"; then
        echo "  $rel: user content, skipped"
        return 0
    fi
    mkdir -p "$(dirname "$dst")"
    cp "$LOCALE_DIR/$rel" "$dst"
}

# Copy main files
cp "$LOCALE_DIR/CLAUDE.md" "$SCRIPT_DIR/CLAUDE.md"
cp "$LOCALE_DIR/KAGGLE_DIRECTION.md" "$SCRIPT_DIR/KAGGLE_DIRECTION.md"

# Copy agent / skill definitions (recursive copy so newly added files are never missed)
mkdir -p "$SCRIPT_DIR/.claude/agents" "$SCRIPT_DIR/.claude/skills"
cp -r "$LOCALE_DIR/.claude/agents/." "$SCRIPT_DIR/.claude/agents/"
cp -r "$LOCALE_DIR/.claude/skills/." "$SCRIPT_DIR/.claude/skills/"

# Copy knowledge-wiki scaffolding (docs are safe to refresh; INDEX is user content -> only refresh if pristine)
mkdir -p "$SCRIPT_DIR/knowledge/technique" "$SCRIPT_DIR/knowledge/data" \
         "$SCRIPT_DIR/knowledge/error" "$SCRIPT_DIR/knowledge/decision"
cp "$LOCALE_DIR/knowledge/README.md" "$SCRIPT_DIR/knowledge/README.md"
cp "$LOCALE_DIR/knowledge/_template.md" "$SCRIPT_DIR/knowledge/_template.md"
copy_user_template "knowledge/INDEX.md"

# Copy templates (user content once edited -> only refresh if pristine)
copy_user_template "submit/SUBMISSIONS.md"

# Enable the secret-blocking pre-commit hook (idiot-proofing) if this is a git repo
if git -C "$SCRIPT_DIR" rev-parse --git-dir >/dev/null 2>&1; then
    chmod +x "$SCRIPT_DIR/tools/git-hooks/pre-commit" 2>/dev/null || true
    git -C "$SCRIPT_DIR" config core.hooksPath "tools/git-hooks"
    echo "Enabled git pre-commit hook (blocks committing secrets): core.hooksPath=tools/git-hooks"
fi

echo "Done! Language set to: $LOCALE"
echo ""
echo "Files updated:"
echo "  - CLAUDE.md"
echo "  - KAGGLE_DIRECTION.md"
echo "  - .claude/agents/ (all agent definitions)"
echo "  - .claude/skills/ (all skill definitions)"
echo "  - knowledge/ (wiki scaffolding; INDEX.md only if unedited)"
echo "  - submit/SUBMISSIONS.md (only if unedited)"
