#!/bin/sh
# Install the slides-to-lab-wall skill for Claude Code without the plugin system.
# Copies skills/slides-to-lab-wall into ~/.claude/skills/ (or $CLAUDE_SKILLS_DIR).
set -e
here=$(cd "$(dirname "$0")" && pwd)
dest="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}/slides-to-lab-wall"
mkdir -p "$(dirname "$dest")"
rm -rf "$dest"
cp -R "$here/skills/slides-to-lab-wall" "$dest"
echo "Installed to $dest"
echo "Start a new Claude Code session and say, for example: put my slides talk.pptx on the lab wall"
