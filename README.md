# codex-cu

English | [简体中文](README.zh-CN.md)

Use the **Codex Computer Use** runtime that ships with the ChatGPT macOS app from **Claude Code**, so Claude can
operate native Mac apps in the background: launch them, read their UI, click, type and read results back.

> Unofficial. Not affiliated with, endorsed by, or supported by OpenAI or Anthropic. It relies on undocumented
> internals of the ChatGPT app that can change or break with any update. Use at your own risk.

The repository contains two pieces:

- **`codex-cu-mcp`**: a small launcher that registers as a stdio MCP server. It starts the ChatGPT app's own
  `cua_repl` server with the configuration Codex uses, and proxies the MCP stream.
- **`computer-use` skill**: tells Claude how to drive the runtime well: the first-call rule, the operating loop,
  done criteria, cleanup, which actions need your confirmation, and troubleshooting.

## How it works

```
Claude Code
└── codex-cu-mcp                       launcher in this repo, stdio MCP server
    └── node cua-repl.mjs              from ChatGPT.app; command, args and env read from the Codex plugin cache
        └── node_repl
            └── SkyComputerUseService  Codex Computer Use.app, drives native macOS apps
```

The launcher does three things:

1. **Follows ChatGPT updates.** On every start it reads the newest
   `~/.codex/plugins/cache/openai-bundled/unified-computer-use/<version>/.mcp.json` (versions compared
   numerically) and starts its `cua_repl` server with exactly that command, args and env. No re-registration after
   ChatGPT updates.
2. **Makes one click approve an app for good.** Before touching an app, the runtime asks
   `Allow Computer Use to use "<App>"?` through an MCP elicitation. Claude Code only offers Accept / Decline, while
   Codex also offers "Always allow". When you Accept and the runtime allows persistence, the launcher adds
   `persist: "always"` to the reply, so Codex itself writes the app to its permanent approval list. Decline is passed
   through untouched; audio recording requests and apps that Codex only allows once are never upgraded.
3. **Exits with the server.** If `cua_repl` exits, the launcher exits with the same code, so the client sees the
   disconnect.

## Requirements

- macOS on Apple Silicon (tested with ChatGPT 26.930.61225).
- The ChatGPT app in `/Applications`, with Computer Use enabled for Codex and run at least once, so the plugin cache
  and `~/.codex/computer-use/Codex Computer Use.app` exist and have Accessibility and Screen Recording permission.
  The ChatGPT app does not need to be running afterwards; the service starts on demand.
- Claude Code (`claude` on `PATH`), `/usr/bin/python3` (Xcode Command Line Tools) and, for the skill, Node.js `npx`.

## Install

```bash
git clone https://github.com/syanbo/codex-cu.git
cd codex-cu
./install.sh
```

`install.sh` is idempotent. It checks the runtime with `codex-cu-mcp --dry-run`, installs the launcher to
`~/.local/bin/codex-cu-mcp`, registers the user-scope MCP server `codex-cu`, and installs the skill with
`npx skills add syanbo/codex-cu --skill computer-use -g -a claude-code`. Set `CODEX_CU_BIN_DIR` to install the
launcher elsewhere, or `CODEX_CU_SKILL_SOURCE=.` to install the skill from your local clone.

Manual install:

```bash
install -m 755 bin/codex-cu-mcp ~/.local/bin/codex-cu-mcp
claude mcp add codex-cu -s user -- ~/.local/bin/codex-cu-mcp
npx skills add syanbo/codex-cu --skill computer-use -g -a claude-code -y
```

Start a new Claude Code session (or `/mcp` → `codex-cu` → Reconnect) and check with `claude mcp get codex-cu`.

## Usage

Just ask in plain language and mention computer use:

- "Use computer use to calculate 12 × 12 in Calculator and tell me the result."
- "Use computer use to count how many notes I have in Notes."

Claude loads the skill, binds the app, acts on accessibility element indices, reads the UI back to confirm the
result, and cleans up when done. Headless runs work for apps that are already approved:

```bash
claude -p "use computer use to calculate 6 x 7 in Calculator" --allowedTools "Skill ToolSearch mcp__codex-cu Bash(pkill:*)"
```

## App approvals

- The first action on an app asks `Allow Computer Use to use "<App>"?`. **Accept approves it permanently.**
- The permanent list is shared with Codex:
  `~/Library/Group Containers/2DC432GLL2.com.openai.sky.CUAService/Library/Application Support/Software/ComputerUseAppApprovals.json`
- To revoke an app, remove its bundle id from `approvedBundleIdentifiers` in that file.
- Headless runs cannot answer the request, so approve new apps once in an interactive session first.

## Cleanup and the agent cursor

While Computer Use works, the service shows an agent cursor and an "Agent is controlling" banner. Codex hides them
by sending `turn-ended` at the end of every turn. For sessions started through codex-cu, the service rejects
`turn-ended` even when a session id and turn id are supplied, so the cursor stays on screen. The skill therefore ends
every task with:

```bash
pkill -TERM -x SkyComputerUseService
```

The service restarts on the next call and REPL bindings keep working. **There is only one service per machine**,
shared by every Claude session, headless run and Codex. Stopping it interrupts any other client's in-flight action
and drops session-scoped approvals, so the skill skips cleanup when you say another session or Codex is using
Computer Use.

## Limitations

- Native macOS apps only. Browser control fails with `Missing required Codex turn metadata: session_id, turn_id`.
- Custom-drawn apps such as WeChat expose almost no accessibility elements; coordinate clicks fail with
  `AXError.notImplemented`. Typing works when the input field already has focus. Automating such apps may trigger
  the app's own risk controls; in testing, WeChat signed the account out once.
- While the screen is locked or the display is asleep, every app fails with `cgWindowNotFound`.
- Depends on ChatGPT app internals (`cua_repl`, `node_repl`, Sky). A ChatGPT update can break it; the launcher then
  exits with a clear error instead of misbehaving.

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| `claude mcp get codex-cu` fails | Run `~/.local/bin/codex-cu-mcp --dry-run` to see the resolved version, command and env keys |
| Tools not found in Claude | A newly registered MCP server loads in a new session; or run `/mcp` → `codex-cu` → Reconnect |
| Clicks do nothing | Grant Accessibility and Screen Recording to `~/.codex/computer-use/Codex Computer Use.app` |
| `Computer Use was not approved to use <App>` | Click Accept on the request in an interactive session |
| The same app keeps asking | Make sure the installed launcher is current: `grep -c persist ~/.local/bin/codex-cu-mcp` must be greater than 0 |
| Cursor and banner stay on screen | `pkill -TERM -x SkyComputerUseService` |

## Security notes

- The `js` tool runs arbitrary JavaScript with control over your desktop apps. Keep Claude Code's permission prompts
  or auto-mode checks on.
- Accept is permanent for that app, for both Claude and Codex.
- The launcher makes no network requests. It reads the local Codex plugin cache and starts binaries from
  `/Applications/ChatGPT.app`.
- The skill asks for confirmation before deleting data, sending messages, paying, changing system settings or typing
  sensitive data.

## Development

```bash
python3 -m unittest discover -s tests -v   # version selection, approval proxy and exit handling; no ChatGPT.app needed
bash -n install.sh
```

```
codex-cu/
├── bin/codex-cu-mcp              launcher: version resolution, approval proxy, exit handling
├── skills/computer-use/SKILL.md  skill loaded by Claude Code
├── tests/test_launcher.py        tests with a fake plugin cache and a fake MCP server
├── install.sh                    installer
├── README.md / README.zh-CN.md   documentation
└── LICENSE                       MIT
```

## Uninstall

```bash
claude mcp remove codex-cu -s user
rm ~/.local/bin/codex-cu-mcp
npx skills remove computer-use -g -y
```

Approved apps stay on the shared approval list; remove them from the JSON file if you no longer want them approved.

## License

[MIT](LICENSE)
