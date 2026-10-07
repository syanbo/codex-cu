# codex-cu

[English](README.md) | 简体中文

让 **Claude Code** 用上 ChatGPT macOS 应用自带的 **Codex Computer Use** 运行时，在后台操作 Mac 原生应用：
启动应用、读取界面、点击、输入，并读回结果。

> 非官方项目，与 OpenAI、Anthropic 无关，也未获得其认可或支持。它依赖 ChatGPT 应用未公开的内部实现，
> 任何一次更新都可能导致它失效。使用风险自负。

仓库包含两部分：

- **`codex-cu-mcp`**：一个小启动脚本，注册为 stdio MCP 服务。它按 Codex 使用的配置启动 ChatGPT 应用自带的
  `cua_repl` 服务，并转发 MCP 消息。
- **`computer-use` 技能**：告诉 Claude 怎样用好这个运行时，包括首次调用规则、操作循环、完成标准、收尾、
  哪些操作需要你确认，以及排障。

## 原理

```
Claude Code
└── codex-cu-mcp                       本仓库的启动脚本，stdio MCP 服务
    └── node cua-repl.mjs              来自 ChatGPT.app；命令、参数和环境变量读自 Codex 插件缓存
        └── node_repl
            └── SkyComputerUseService  Codex Computer Use.app，负责操作 macOS 原生应用
```

启动脚本做三件事：

1. **跟随 ChatGPT 更新。** 每次启动都读取最新的
   `~/.codex/plugins/cache/openai-bundled/unified-computer-use/<版本>/.mcp.json`（版本号按数字比较），
   用其中 `cua_repl` 的命令、参数和环境变量原样启动。ChatGPT 更新后不用重新注册。
2. **点一次就永久授权。** 运行时操作某个应用前，会通过 MCP 输入请求询问 `Allow Computer Use to use "<App>"?`。
   Claude Code 的弹窗只有 Accept 和 Decline，Codex 里还有「始终允许」。你点 Accept 且运行时允许永久授权时，
   启动脚本在回复里补上 `persist: "always"`，由 Codex 自己把应用写进永久授权名单。Decline 原样转发；
   录音授权，以及 Codex 只允许单次授权的应用，都不会被改成永久。
3. **随服务退出。** `cua_repl` 退出时，启动脚本带着同样的退出码一起退出，客户端能马上发现连接断开。

## 环境要求

- Apple Silicon 的 macOS（已在 ChatGPT 26.930.61225 上测试）。
- `/Applications` 里装有 ChatGPT 应用，并且在 Codex 里开启过 Computer Use、至少运行过一次，这样插件缓存和
  `~/.codex/computer-use/Codex Computer Use.app` 才会存在，并已获得「辅助功能」和「屏幕录制」权限。
  之后不需要一直开着 ChatGPT，服务会按需自动启动。
- Claude Code（`claude` 在 `PATH` 里）、`/usr/bin/python3`（Xcode 命令行工具），安装技能还需要 Node.js 的 `npx`。

## 安装

```bash
git clone https://github.com/syanbo/codex-cu.git
cd codex-cu
./install.sh
```

`install.sh` 可以重复执行。它先用 `codex-cu-mcp --dry-run` 检查运行时，再把启动脚本装到
`~/.local/bin/codex-cu-mcp`，注册用户级 MCP 服务 `codex-cu`，最后用
`npx skills add syanbo/codex-cu --skill computer-use -g -a claude-code` 安装技能。想把启动脚本装到别处，
设置 `CODEX_CU_BIN_DIR`；想从本地克隆安装技能，设置 `CODEX_CU_SKILL_SOURCE=.`。

手动安装：

```bash
install -m 755 bin/codex-cu-mcp ~/.local/bin/codex-cu-mcp
claude mcp add codex-cu -s user -- ~/.local/bin/codex-cu-mcp
npx skills add syanbo/codex-cu --skill computer-use -g -a claude-code -y
```

装好后开一个新的 Claude Code 会话（或在 `/mcp` 里重连 `codex-cu`），用 `claude mcp get codex-cu` 确认连接正常。

## 使用

直接用自然语言说，提到 computer use 即可：

- 「用 computer use 在计算器里算 12 × 12，告诉我结果」
- 「用 computer use 看看备忘录里一共有多少篇」

Claude 会加载技能、绑定应用、按可访问性元素编号操作、读回界面确认结果，做完后收尾。已授权过的应用也可以用
无头模式：

```bash
claude -p "用 computer use 在计算器里算 6 × 7" --allowedTools "Skill ToolSearch mcp__codex-cu Bash(pkill:*)"
```

## 应用授权

- 第一次操作某个应用时会询问 `Allow Computer Use to use "<App>"?`，**点 Accept 即永久授权**。
- 永久授权名单和 Codex 共用：
  `~/Library/Group Containers/2DC432GLL2.com.openai.sky.CUAService/Library/Application Support/Software/ComputerUseAppApprovals.json`
- 想撤销某个应用，从这个文件的 `approvedBundleIdentifiers` 里删掉它的 bundle id。
- 无头模式没法回答授权请求，新应用要先在交互会话里授权一次。

## 收尾与代理光标

Computer Use 工作时，服务会在屏幕上显示代理光标和「Agent 正在控制」提示条。Codex 每轮结束会发 `turn-ended`
把它们收起来。但通过 codex-cu 发起的会话，即使带上会话 ID 和回合 ID，服务也会拒绝 `turn-ended`，光标就会一直
留在屏幕上。所以技能在每个任务结束时执行：

```bash
pkill -TERM -x SkyComputerUseService
```

下次调用时服务会自动重启，REPL 里的绑定还能继续用。**这个服务全机只有一个**，所有 Claude 会话、无头任务和
Codex 共用。结束它会打断其他使用方正在执行的操作，本会话授权也会丢失。所以你说过有其他会话或 Codex 正在用
Computer Use 时，技能会跳过收尾。

## 限制

- 只支持 macOS 原生应用。浏览器控制会报 `Missing required Codex turn metadata: session_id, turn_id`。
- 微信这类自绘界面几乎没有可访问性元素，按坐标点击会报 `AXError.notImplemented`；输入框已有焦点时可以直接输入。
  自动操作这类应用可能触发应用自己的风控，测试时微信曾把账号强制下线过一次。
- 屏幕锁定或显示器熄灭时，所有应用都会报 `cgWindowNotFound`。
- 依赖 ChatGPT 应用的内部实现（`cua_repl`、`node_repl`、Sky）。ChatGPT 更新后可能失效，届时启动脚本会给出
  明确的报错，不会出现看似正常、实际出错的情况。

## 排障

| 现象 | 处理 |
| --- | --- |
| `claude mcp get codex-cu` 失败 | 运行 `~/.local/bin/codex-cu-mcp --dry-run`，查看解析到的版本、命令和环境变量名 |
| Claude 里找不到工具 | 新注册的 MCP 要在新会话里才加载；或在 `/mcp` 里重连 `codex-cu` |
| 点击没反应 | 给 `~/.codex/computer-use/Codex Computer Use.app` 开「辅助功能」和「屏幕录制」权限 |
| `Computer Use was not approved to use <App>` | 在交互会话里对授权请求点 Accept |
| 同一个应用反复询问授权 | 确认装的是新版启动脚本：`grep -c persist ~/.local/bin/codex-cu-mcp` 应大于 0 |
| 光标和提示条一直留在屏幕上 | `pkill -TERM -x SkyComputerUseService` |

## 安全说明

- `js` 工具能执行任意 JavaScript，可以操控你的桌面应用。请保留 Claude Code 的权限确认或自动模式的检查。
- 对某个应用点 Accept 是永久的，Claude 和 Codex 都会生效。
- 启动脚本不发起任何网络请求，只读取本地的 Codex 插件缓存，并启动 `/Applications/ChatGPT.app` 里的程序。
- 技能会在删除数据、发消息、付款、修改系统设置或输入敏感信息之前先征得你的确认。

## 开发

```bash
python3 -m unittest discover -s tests -v   # 版本选择、授权转发和退出处理，不需要 ChatGPT.app
bash -n install.sh
```

```
codex-cu/
├── bin/codex-cu-mcp              启动脚本：版本选择、授权转发、退出处理
├── skills/computer-use/SKILL.md  Claude Code 加载的技能
├── tests/test_launcher.py        用假插件缓存和假 MCP 服务端做的测试
├── install.sh                    安装脚本
├── README.md / README.zh-CN.md   文档
└── LICENSE                       MIT
```

## 卸载

```bash
claude mcp remove codex-cu -s user
rm ~/.local/bin/codex-cu-mcp
npx skills remove computer-use -g -y
```

已授权的应用仍留在共用的授权名单里，不想保留的话从 JSON 文件里删掉。

## 许可证

[MIT](LICENSE)
