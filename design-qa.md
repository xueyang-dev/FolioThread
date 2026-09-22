# Folith / 译页 品牌应用与工作台验收

final result: passed

> 2026-09-19 follow-up: this earlier pass covered the brand refresh and the
> first compact-workspace implementation. Stakeholder review reopened the
> workspace acceptance because the overview surface, repeated indicators and
> card density still need redesign. See [the current UX audit](docs/ui-audit/24-minimal-workspace/README.md)
> for the evidence and remediation plan.

## 范围与参照

参照：本机一份品牌展示板截图（1448×1086）。该文件是 local-only 的参考素材，未入库，
故此处不记录本机路径。
本次是将现有品牌应用到工作台，非展示板页面的逐像素复刻；保留仓库已有 logo 资产。
品牌展示板的构图不作为应用布局约束。

## 渲染证据

- `docs/ui-audit/brand-refresh/new-task.png`：1440×1000 桌面新建任务首屏。
- `docs/ui-audit/brand-refresh/workspace.png`：1440×1000 已有任务概览。
- `docs/ui-audit/brand-refresh/narrow.png`：621×752 窄窗口首屏。
- 截图按浏览器 CSS 视口检查，展示板不进行密度归一化或 UI 像素差分。

## 视觉核对

- 字体：保持 Manrope 与系统中文回退；标题、说明、表单层级清楚。
- 布局：侧栏独立品牌面、新建按钮、当前步骤和内容面在桌面正常显示；窄窗口沿用可滚动布局。
- 颜色：沿用钴蓝、深海军蓝与 logo 青色；上传图标改钴蓝，提升浅底辨识度。
- 资产：复用原有 PNG/SVG，未重画或拉伸 logo。品牌板与现有矢量细节并非逐像素相同，本次未修改源图形。
- 内容：保留任务、项目和交付文案；新增品牌眉题。
- 全视图：已检查新建任务、项目列表、任务概览，无本次改动导致的遮挡或截断。
- 局部：检查 logo 卡片、选中步骤、上传区和工作台顶栏，边距与颜色一致。

## 工作台结构重构验收（2026-09-19 早一轮，已被后续整改取代）

> **这一段描述的是已被取代的状态。** 下面提到的「概览 / 查看概览」在随后按
> [UX 审计](docs/ui-audit/24-minimal-workspace/README.md) 施工时**整页删除**，
> 「任务详情 / 运行控制」也迁到了任务 Banner 与工具栏；当前状态的证据与实测值在
> [docs/ui-audit/24-minimal-workspace/phase1/](docs/ui-audit/24-minimal-workspace/phase1/README.md)。
> 保留本段只是为了让当时的验收记录可追溯。

本轮按产品设计稿将任务工作区改为“横幅 + 横向工具栏 + 工作台正文”的结构：

- 打开历史任务、新任务启动和侧栏回到任务时，默认进入「翻译」工作台。
- 顶部横幅保留文档标题、原始文件名、段落/术语/发现数和交付判断；完整概览改为按需打开。
- 「概览 / 翻译 / 术语 / 审校 / 交付」收敛为横向工具栏，窄窗口下可横向滚动，不再占用整列侧栏。
- 翻译表格与右侧段落 Inspector 保持原有交互；术语、审校、交付仍使用原有路由和按钮 key。

实时浏览器预览（本地 Streamlit，CSS 视口 877×752）已检查：

- 横幅信息在一屏内可识别，交付 CTA 与 canonical 状态并列。
- 工具栏保持单行，正文从翻译表格开始；Inspector 仍在右侧。
- 「查看概览」位于横幅下方右侧，点击后可回到完整状态页。

## 验证

- 新建任务 → 项目 → 历史任务 → 打开已有任务 → 主页，导航正常。
- 浏览器 error 日志为空。
- `venv/bin/python -m pytest tests/brand_assets_test.py tests/app_boot_test.py -q`：10 passed。
- 首轮视觉检查后补充统一确认面板和任务顶栏；修改后已检查任务概览截图。
- `python3 -m pytest tests/translation_workbench_ui_test.py tests/task_overview_ui_test.py tests/ui_console_test.py tests/agent_inspector_ui_test.py -q`：29 passed。

未验证：真实文件上传、付费模型调用、全量翻译/交付流程、全部工作台子页面及手机尺寸。
本次没有改变对应业务逻辑。现有窄窗口固定侧栏布局保持原状，不视为移动端适配完成。
