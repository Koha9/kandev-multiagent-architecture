"""额度账本：真实 AI / 付费 API 等消耗额度的调用，每次调用前在账本里记一笔，超过上限就拒绝。

账本是一个 JSON 文件（默认 <mgmt_root>/quota/ledger.json），写者是本脚本，不要手改。

命令行：
  python quota.py --ledger <账本> init claude_cli=2 codex_cli=2   # 设置上限；已有账本时只更新上限，保留已用次数
  python quota.py --ledger <账本> consume claude_cli --note "冒烟"  # 记一笔；超限时不记，退出码 3
  python quota.py --ledger <账本> show                             # 打印用量

在测试里使用（conftest.py 或真实调用的入口）。账本路径通过环境变量 MA_QUOTA_LEDGER 传入：
  import importlib.util, os
  spec = importlib.util.spec_from_file_location("quota", os.environ["MA_QUOTA_TOOL"])  # <mgmt_root>/tools/quota.py
  quota = importlib.util.module_from_spec(spec); spec.loader.exec_module(quota)
  quota.consume("claude_cli", note=request.node.nodeid)   # 超限抛 quota.QuotaExceeded，测试失败

没有设置 MA_QUOTA_LEDGER 时 consume 直接抛 QuotaExceeded：不知道账本在哪就不允许真实调用。
退出码：0 成功；2 参数或文件错误；3 超出上限或种类未登记。只用标准库。
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime


class QuotaExceeded(Exception):
    pass


class _Lock:
    def __init__(self, path, timeout=15):
        self.path, self.timeout = path + ".lock", timeout

    def __enter__(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        deadline = time.time() + self.timeout
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                if time.time() > deadline:
                    raise RuntimeError(f"账本被锁超过 {self.timeout} 秒：{self.path}（确认没有其他进程后可删除该锁文件）")
                time.sleep(0.2)

    def __exit__(self, *exc):
        os.close(self.fd)
        os.remove(self.path)


def _load(ledger):
    if not os.path.exists(ledger):
        return {"limits": {}, "used": {}, "events": []}
    with open(ledger, encoding="utf-8") as f:
        return json.load(f)


def _save(ledger, data):
    os.makedirs(os.path.dirname(os.path.abspath(ledger)), exist_ok=True)
    tmp = ledger + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ledger)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init(ledger, limits):
    with _Lock(ledger):
        data = _load(ledger)
        data["limits"].update(limits)
        for kind in limits:
            data["used"].setdefault(kind, 0)
        data["events"].append({"at": _now(), "kind": "*", "note": f"init {limits}"})
        _save(ledger, data)
    return data


def consume(kind, ledger=None, note=""):
    ledger = ledger or os.environ.get("MA_QUOTA_LEDGER")
    if not ledger:
        raise QuotaExceeded("没有设置 MA_QUOTA_LEDGER，不允许消耗额度的调用")
    with _Lock(ledger):
        data = _load(ledger)
        if kind not in data["limits"]:
            raise QuotaExceeded(f"额度种类 {kind} 没有在账本中登记上限")
        used, limit = data["used"].get(kind, 0), data["limits"][kind]
        if used >= limit:
            raise QuotaExceeded(f"{kind} 已用 {used} 次，达到上限 {limit}")
        data["used"][kind] = used + 1
        data["events"].append({"at": _now(), "kind": kind, "note": note})
        _save(ledger, data)
    return used + 1, limit


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--ledger", default=os.environ.get("MA_QUOTA_LEDGER"))
    sub = p.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("init")
    pi.add_argument("limits", nargs="+", help="种类=上限")
    pc = sub.add_parser("consume")
    pc.add_argument("kind")
    pc.add_argument("--note", default="")
    sub.add_parser("show")
    a = p.parse_args()
    if not a.ledger:
        print("ERROR 需要 --ledger 或环境变量 MA_QUOTA_LEDGER")
        return 2
    try:
        if a.cmd == "init":
            limits = {}
            for item in a.limits:
                k, _, v = item.partition("=")
                limits[k] = int(v)
            init(a.ledger, limits)
            print(f"OK 上限已设置：{limits}")
        elif a.cmd == "consume":
            n, limit = consume(a.kind, a.ledger, a.note)
            print(f"OK {a.kind} {n}/{limit}")
        else:
            data = _load(a.ledger)
            for k, limit in sorted(data["limits"].items()):
                print(f"{k}: {data['used'].get(k, 0)}/{limit}")
    except QuotaExceeded as e:
        print(f"REFUSED {e}")
        return 3
    except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as e:
        print(f"ERROR {e}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
