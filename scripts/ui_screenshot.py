#!/usr/bin/env python3
"""给运行中的译页界面截图（UI 改动的视觉验证工具）。

为什么需要它：界面改动的验收不能只看 `AppTest` 的元素树——纵向留白、文字截断、
列宽这类问题只有在真实渲染里才看得出来。这个脚本让"改完看一眼"变成一条命令。

依赖（本机已有的浏览器，不需要额外安装）：

    FOLIO_PLAYWRIGHT_CORE  playwright-core 的路径
    FOLIO_CHROME           Chrome/Chromium 可执行文件路径
    FOLIO_URL              应用地址，默认 http://127.0.0.1:8501

用法：

    # 首屏
    python scripts/ui_screenshot.py --out /tmp/shot.png

    # 打开某个任务的某个工作区页面（按最近更新取第一个任务）
    python scripts/ui_screenshot.py --out /tmp/translate.png --section 翻译

缺少依赖时会打印可操作的提示并返回非零，不会静默失败。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_PLAYWRIGHT_CANDIDATES = (
    "~/Dev/grok-workspace/node_modules/playwright-core",
    "~/.hermes/hermes-agent/node_modules/playwright-core",
)
CHROME_GLOB = "~/Library/Caches/ms-playwright/chromium-*/chrome-mac-arm64/*.app/Contents/MacOS/*"

_SCRIPT = r"""
const PW = process.env.FOLIO_PLAYWRIGHT_CORE;
const CHROME = process.env.FOLIO_CHROME;
const { chromium } = require(PW);
const [url, out, section, waitMs] = process.argv.slice(2);

(async () => {
  const browser = await chromium.launch({
    executablePath: CHROME, args: ['--no-sandbox', '--disable-gpu'],
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1,
  });
  page.on('pageerror', (e) => console.error('[pageerror]', e.message));
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForSelector('[data-testid="stAppViewContainer"]', { timeout: 30000 });
  await page.waitForTimeout(4000);

  if (section) {
    const history = page.locator('button', { hasText: '历史任务' }).first();
    if (await history.count()) { await history.click(); await page.waitForTimeout(2500); }
    // 列表按最近更新排序，第一个任务就是最近处理的
    const action = /打开任务|继续审校|查看交付|继续处理|更新报告|打开/;
    const firstAction = page.locator('button').filter({ hasText: action }).first();
    if (await firstAction.count()) { await firstAction.click(); await page.waitForTimeout(3500); }
    const navRoot = page.locator('[class*="st-key-workspace_nav"]').first();
    const nav = (await navRoot.count())
      ? navRoot.locator('button').filter({ hasText: section }).first()
      : page.locator('button').filter({ hasText: section }).first();
    if (await nav.count()) { await nav.click(); await page.waitForTimeout(3000); }
    else console.error('[warn] 未找到导航项:', section);
  }
  await page.waitForTimeout(Number(waitMs || 2500));
  await page.screenshot({ path: out, fullPage: false });
  console.log('saved', out);
  await browser.close();
})().catch((e) => { console.error('FAILED', e.message); process.exit(1); });
"""


def _resolve_playwright() -> str | None:
    explicit = os.environ.get("FOLIO_PLAYWRIGHT_CORE")
    if explicit and Path(explicit).is_dir():
        return explicit
    for candidate in DEFAULT_PLAYWRIGHT_CANDIDATES:
        path = Path(candidate).expanduser()
        if (path / "package.json").is_file():
            return str(path)
    found = shutil.which("playwright-core")
    return found


def _resolve_chrome() -> str | None:
    explicit = os.environ.get("FOLIO_CHROME")
    if explicit and Path(explicit).is_file():
        return explicit
    for match in sorted(Path("~").expanduser().glob(
            CHROME_GLOB.replace("~/", ""))):
        if match.is_file():
            return str(match)
    for name in ("Google Chrome", "Chromium"):
        found = shutil.which(name)
        if found:
            return found
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="输出 PNG 路径")
    parser.add_argument("--section", default="",
                        help="工作区页面（概览/翻译/术语/审校/交付）；留空则截首屏")
    parser.add_argument("--url", default=os.environ.get("FOLIO_URL",
                                                        "http://127.0.0.1:8501"))
    parser.add_argument("--wait-ms", default="2500", help="渲染后额外等待毫秒数")
    args = parser.parse_args(argv)

    if shutil.which("node") is None:
        print("[错误] 未找到 node。截图需要 node + playwright-core。", file=sys.stderr)
        return 2
    playwright = _resolve_playwright()
    if playwright is None:
        print("[错误] 未找到 playwright-core。请设置 FOLIO_PLAYWRIGHT_CORE 指向"
              "包含 package.json 的 playwright-core 目录。", file=sys.stderr)
        return 2
    chrome = _resolve_chrome()
    if chrome is None:
        print("[错误] 未找到 Chrome/Chromium。请设置 FOLIO_CHROME 指向可执行文件。",
              file=sys.stderr)
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as handle:
        handle.write(_SCRIPT)
        script_path = handle.name
    env = {**os.environ, "FOLIO_PLAYWRIGHT_CORE": playwright, "FOLIO_CHROME": chrome}
    try:
        result = subprocess.run(
            ["node", script_path, args.url, str(args.out), args.section,
             str(args.wait_ms)],
            env=env, capture_output=True, text=True)
    finally:
        Path(script_path).unlink(missing_ok=True)

    if result.stdout.strip():
        print(result.stdout.strip())
    if result.returncode != 0:
        if result.stderr.strip():
            print(result.stderr.strip(), file=sys.stderr)
        return result.returncode
    if not args.out.is_file():
        print(f"[错误] 未生成截图：{args.out}", file=sys.stderr)
        return 1
    print(f"尺寸 {args.out.stat().st_size / 1024:.0f} KB -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
