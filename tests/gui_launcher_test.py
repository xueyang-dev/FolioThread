"""HTML GUI 启动器（gui.py）测试：不真正启动 Streamlit、不打开窗口。

绑定语义用**真实的监听 socket** 验证，而不是只断言配置字符串：配置写对了
但没生效（例如被 Streamlit 的隐式默认值覆盖）一样会把无认证层的应用暴露到
局域网，那种情况只有真的连一次才看得出来。

**夹具约定（踩过坑）**：每个探测都用**全新的**监听 socket，且**只连一次**。
原因是 `listen(1)` 的 backlog 只有 1，而 `accept()` 永远不会被调用——同一个
监听 socket 上连第二次时，内核会直接 RST 掉多余的连接，`connect_ex` 返回
`ECONNRESET(54)`。那看起来像"绑定错了"，其实是夹具把 backlog 挤爆了：
一度造成这个用例约 1/3 的运行概率性失败。
"""
import errno
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gui

# backlog 给足余量，避免"第二次连接被 RST"再次伪装成绑定错误。
_LISTEN_BACKLOG = 8
# 明确的"不可达"信号。ECONNRESET / ETIMEDOUT **不在此列**：它们指向
# 夹具或网络栈的问题，不能拿来当"默认模式没有暴露"的证据。
_UNREACHABLE = {errno.ECONNREFUSED, errno.EHOSTUNREACH}


def test_brand_title():
    assert gui.APP_TITLE == "FolioThread · 长文档翻译工作空间"
    print("  ✓ 桌面窗口品牌标题")


def test_server_args():
    args = gui.server_args(8501, lan=False)
    assert args[:3] == ["-m", "streamlit", "run"]
    assert Path(args[3]) == gui.ROOT / "app.py"
    assert "--server.headless" in args and "true" in args
    assert "--server.port" in args and "8501" in args
    assert args[args.index("--theme.primaryColor") + 1] == "#004cfd"
    assert args[args.index("--theme.textColor") + 1] == "#131c2e"

    # 默认必须**显式**绑定回环：不能依赖 Streamlit 的隐式默认值（那是 0.0.0.0）。
    assert args.count("--server.address") == 1, "默认模式必须显式给出绑定地址"
    assert args[args.index("--server.address") + 1] == "127.0.0.1"

    lan_args = gui.server_args(9000, lan=True)
    assert lan_args.count("--server.address") == 1
    assert lan_args[lan_args.index("--server.address") + 1] == "0.0.0.0"
    print("  ✓ server_args（headless/端口/默认回环/lan 显式绑定）")


def _connect_result(host, port):
    """从 `host` 连一次，返回 `connect_ex` 的 errno（0 = 可达）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(2.0)
        return probe.connect_ex((host, port))


def _probe_binding(address, host):
    """新起一个绑在 `address` 的监听 socket，只探测一次，然后关掉。

    每个断言一条独立 socket：既避开 backlog 溢出，也让各条断言之间
    没有任何共享状态可互相干扰。
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((address, 0))
    server.listen(_LISTEN_BACKLOG)
    try:
        return _connect_result(host, server.getsockname()[1])
    finally:
        server.close()


def test_default_binding_serves_loopback_and_not_lan():
    """默认绑定：回环可达、局域网明确拒绝。`--lan`：两者都可达。"""
    lan = gui.lan_ip()
    lan_is_distinct = not lan.startswith("127.")

    # 默认模式：本机可达
    assert _probe_binding(gui.bind_address(lan=False), "127.0.0.1") == 0, \
        "默认模式必须能本机访问"

    # 默认模式：局域网必须**明确拒绝**。断言具体 errno 而不是 `!= 0`，
    # 否则 ECONNRESET 这类夹具问题会伪装成"没暴露"而让用例假通过。
    if lan_is_distinct:
        result = _probe_binding(gui.bind_address(lan=False), lan)
        assert result in _UNREACHABLE, \
            f"默认模式必须从局域网 IP 明确拒绝，实际 errno={result}"

    # --lan 模式：本机与局域网都必须可达
    assert _probe_binding(gui.bind_address(lan=True), "127.0.0.1") == 0, \
        "lan 模式也必须能本机访问"
    if lan_is_distinct:
        assert _probe_binding(gui.bind_address(lan=True), lan) == 0, \
            "显式 --lan 必须真的能局域网访问"

    if not lan_is_distinct:
        print("  ✓ 绑定语义（回环可达；本环境无独立局域网 IP，跳过 LAN 探测）")
    else:
        print(f"  ✓ 绑定语义（默认仅回环且 LAN 明确拒绝；--lan 后 {lan} 可达）")


def test_pick_port():
    # 占用一个端口后，pick_port 应顺延到下一个可用端口
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        taken = s.getsockname()[1]
        picked = gui.pick_port(taken)
        assert picked != taken, "被占用端口应被跳过"
        assert taken < picked < taken + 20
    print("  ✓ pick_port（端口顺延）")


def test_url_for():
    assert gui.url_for(8501, lan=False) == "http://127.0.0.1:8501"
    lan_url = gui.url_for(9000, lan=True)
    assert lan_url == f"http://{gui.lan_ip()}:9000"
    print("  ✓ url_for（本机 / 局域网）")


def test_lan_ip_is_ipv4():
    ip = gui.lan_ip()
    parts = ip.split(".")
    assert len(parts) == 4 and all(p.isdigit() for p in parts)
    print("  ✓ lan_ip 返回 IPv4 地址")


def main():
    test_brand_title()
    test_server_args()
    test_default_binding_serves_loopback_and_not_lan()
    test_pick_port()
    test_url_for()
    test_lan_ip_is_ipv4()
    print("GUI 启动器逻辑测试通过 ✅")


if __name__ == "__main__":
    main()
