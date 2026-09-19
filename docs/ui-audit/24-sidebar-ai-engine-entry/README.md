# 24 · Sidebar AI Engine 入口收敛（消除重复导航）

Project 区 IA **保持冻结**。本轮只做一件事：删掉「工作区」分组里的独立「⚙ 设置」行，
因为它的落点与贴底 AI Engine status module 上的「管理」完全同义。

## 结论

| | 之前 | 之后 |
| --- | --- | --- |
| 「工作区」分组 | 历史任务 / 术语与翻译记忆 / **设置** | 历史任务 / 术语与翻译记忆 |
| AI Engine 入口 | 「设置」行 + footer「管理」（两个入口，同一页面） | 只剩 footer「管理」（`manage_provider`） |

Model Center 自身的 route（`app_view == "settings"`）与页面功能**未改动** —— 主工作区里
「前往设置 / 检查设置 / 测试连接 / 前往 AI 设置」这些就地入口仍然复用它。

## 复现步骤

```bash
# 1) 起应用（仓库根目录，用隔离端口避免撞掉正在跑的实例）
venv/bin/python -m streamlit run app.py --server.port 8533 --server.headless true

# 2) 截图（本机 playwright-core + Chrome）
FOLIO_URL=http://127.0.0.1:8533 \
venv/bin/python scripts/ui_screenshot.py --out docs/ui-audit/24-sidebar-ai-engine-entry/sidebar-after.png
```

## 截图核对点

`sidebar-after.png`（1440×900，新建任务首屏）：

- 「工作区」分组只有两行：`历史任务` / `术语与翻译记忆`，**没有「设置」**；
- 贴底 status module：`○ AI引擎`（status label，不可点）+ 右对齐 `管理`（文字 action，
  **不是描边按钮**）；
- 第二行 `deepseek-v4-flash-0731`（secondary text，当前模型）；
- 第三行 `尚未验证连接`（tertiary / status text，连接状态）。

> 这一块**不是** `library_nav` 的导航行：48px 行高 / hover 面 / primary 选中态都不适用，
> 整块也不可点击 —— 只有「管理」是可点元素。

## 两个容易踩的坑

1. **别给「管理」加 `help=`**：tooltip 会把 `button` 包进 `stTooltipHoverTarget`，
   而 `.st-key-provider_status .stButton > button` 用的是**直接子选择器**，会静默落空、
   退回 Streamlit 默认的描边按钮（截图里那块会变成"两颗按钮"）。
   回归测试 `test_manage_action_has_no_tooltip_wrapper` 钉住了这一条。
2. **别把 AI Engine 区塞进 `library_nav`**：那套样式是导航行语法，会让它和
   「历史任务 / 术语与翻译记忆」读成同一类东西。status module 必须有自己的语法。
