#!/usr/bin/env bash
# 安装 codex-cu：启动脚本、Claude Code 用户级 MCP、computer-use 技能。可重复执行。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${CODEX_CU_BIN_DIR:-$HOME/.local/bin}"
TARGET="$BIN_DIR/codex-cu-mcp"
# 默认从 GitHub 装技能，npx skills update 才能追踪更新；改技能时可指向本地克隆
SKILL_SOURCE="${CODEX_CU_SKILL_SOURCE:-syanbo/codex-cu}"

step() { printf '==> %s\n' "$*"; }
fail() { printf 'error: %s\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = Darwin ] || fail "codex-cu only supports macOS"
[ -d /Applications/ChatGPT.app ] || fail "ChatGPT.app not found in /Applications"
[ -x /usr/bin/python3 ] || fail "/usr/bin/python3 not found; install the Xcode Command Line Tools"
command -v claude >/dev/null || fail "claude (Claude Code CLI) not found on PATH"

step "Checking the Codex Computer Use runtime"
/usr/bin/python3 "$REPO_DIR/bin/codex-cu-mcp" --dry-run >/dev/null \
  || fail "Codex Computer Use runtime not found; in the ChatGPT app, enable Computer Use for Codex and run it once"

step "Installing the launcher to $TARGET"
mkdir -p "$BIN_DIR"
install -m 755 "$REPO_DIR/bin/codex-cu-mcp" "$TARGET"

step "Registering the codex-cu MCP server (user scope)"
if claude mcp get codex-cu >/dev/null 2>&1; then
  echo "    codex-cu is already registered; skipped"
else
  claude mcp add codex-cu -s user -- "$TARGET"
fi

step "Installing the computer-use skill from $SKILL_SOURCE"
if command -v npx >/dev/null; then
  npx -y skills add "$SKILL_SOURCE" --skill computer-use -g -a claude-code -y
else
  echo "    npx not found; copy $REPO_DIR/skills/computer-use to ~/.claude/skills/ instead"
fi

step "Done. Start a new Claude Code session (or /mcp -> codex-cu -> Reconnect) and try:"
echo '    use computer use to calculate 12 x 12 in Calculator'
