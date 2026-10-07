# 用假插件目录和假 MCP 服务端测试启动脚本：版本选择、授权转发和退出处理，不依赖 ChatGPT.app
import importlib.machinery
import importlib.util
import json
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parent.parent / "bin" / "codex-cu-mcp"


def load_launcher():
    loader = importlib.machinery.SourceFileLoader("codex_cu_mcp", str(LAUNCHER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


cu = load_launcher()


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.original_dir = cu.PLUGIN_DIR
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        cu.PLUGIN_DIR = self.root

    def tearDown(self):
        cu.PLUGIN_DIR = self.original_dir
        self.tmp.cleanup()

    def make(self, name, key="cua_repl", version=None):
        directory = self.root / name
        directory.mkdir()
        if version is not None:
            server = {"command": "/bin/echo", "args": [version], "env": {"BROWSER_USE_CODEX_APP_VERSION": version}}
            (directory / ".mcp.json").write_text(json.dumps({"mcpServers": {key: server}}))

    def test_picks_numerically_newest_version_with_config(self):
        self.make("26.930.61225", version="26.930.61225")
        self.make("26.1001.100", version="26.1001.100")  # 按字符串排序会输给 26.930
        self.make("26.2000.1")  # 新目录但还没写入配置
        self.make("latest-tmp", version="bogus")  # 不是版本号
        _, server = cu.resolve()
        self.assertEqual(server["env"]["BROWSER_USE_CODEX_APP_VERSION"], "26.1001.100")

    def test_missing_server_key_exits(self):
        self.make("27.1.1", key="renamed_server", version="27.1.1")
        with self.assertRaises(SystemExit) as caught:
            cu.resolve()
        self.assertIn("has no cua_repl", str(caught.exception))

    def test_missing_plugin_dir_exits(self):
        cu.PLUGIN_DIR = self.root / "absent"
        with self.assertRaises(SystemExit) as caught:
            cu.resolve()
        self.assertIn("no versioned", str(caught.exception))


FAKE_SERVER = textwrap.dedent('''
    import json, sys
    def ask(i, params):
        print(json.dumps({"jsonrpc": "2.0", "id": i, "method": "elicitation/create", "params": params}), flush=True)
        return json.loads(sys.stdin.readline())
    app_meta = {"connector_id": "computer-use", "persist": ["session", "always"], "tool_params": {"app": "com.apple.Notes"}}
    got = [
        ask(1, {"message": 'Allow Computer Use to use "Notes"?', "_meta": app_meta}),
        ask(2, {"message": 'Allow Computer Use to use "Notes"?', "_meta": app_meta}),
        ask(3, {"message": "Allow Computer Use to record computer audio?",
                "_meta": {"connector_id": "computer-use", "persist": ["session"], "tool_params": {}}}),
        ask(4, {"message": 'Allow Computer Use to use "Risky"?',
                "_meta": {"connector_id": "computer-use", "persist": ["session"], "tool_params": {"app": "x.risky"}}}),
    ]
    got.append(json.loads(sys.stdin.readline()))
    print(json.dumps({"jsonrpc": "2.0", "method": "test/report", "params": {"got": got}}), flush=True)
''')


class ProxyTest(unittest.TestCase):
    def test_proxy_upgrades_only_persistable_accepts_and_exits_with_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = Path(tmp) / "fake_server.py"
            server.write_text(FAKE_SERVER)
            runner = (
                "import importlib.machinery, sys;"
                f"cu = importlib.machinery.SourceFileLoader('cu', {str(LAUNCHER)!r}).load_module();"
                f"sys.exit(cu.proxy([sys.executable, {str(server)!r}], None))"
            )
            proc = subprocess.Popen([sys.executable, "-c", runner], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, text=True)
            # 代理不随服务端退出时会一直等，超时就杀掉并判失败
            watchdog = threading.Timer(20, proc.kill)
            watchdog.start()
            replies = {1: "accept", 2: "decline", 3: "accept", 4: "accept"}
            report = None
            for line in proc.stdout:
                message = json.loads(line)
                if message.get("method") == "elicitation/create":
                    reply = {"jsonrpc": "2.0", "id": message["id"],
                             "result": {"action": replies[message["id"]], "content": {}}}
                    proc.stdin.write(json.dumps(reply) + "\n")
                    if message["id"] == 4:
                        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 99, "result": {"tools": []}}) + "\n")
                    proc.stdin.flush()
                elif message.get("method") == "test/report":
                    report = message["params"]["got"]
            code = proc.wait()
            timed_out = not watchdog.is_alive() and code != 0
            watchdog.cancel()
            proc.stdin.close()
            proc.stdout.close()

        self.assertFalse(timed_out, "proxy did not exit after the server exited")
        self.assertEqual(code, 0)
        self.assertIsNotNone(report)
        self.assertEqual(report[0]["result"].get("_meta"), {"persist": "always"})
        self.assertNotIn("_meta", report[1]["result"])
        self.assertEqual(report[1]["result"]["action"], "decline")
        self.assertNotIn("_meta", report[2]["result"])
        self.assertNotIn("_meta", report[3]["result"])
        self.assertEqual(report[4], {"jsonrpc": "2.0", "id": 99, "result": {"tools": []}})

    def test_message_text_is_used_when_meta_is_missing(self):
        self.assertTrue(cu.is_persistable_app_approval({"message": 'Allow Computer Use to use "WeChat"?'}))
        self.assertFalse(cu.is_persistable_app_approval({"message": "Something else"}))


if __name__ == "__main__":
    unittest.main()
