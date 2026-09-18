# 21 · 侧栏「项目」分组：Project Context 与 Project Management 归并

捕获日期：2026-09-18 · Streamlit 1.63.0 · Python 3.11.3 · 视口 1440 × 900

数据：直接对**本机 `outputs/`** 抓图（3 个活动项目 + 20 条未分类任务）。本轮只改
侧栏信息架构，不涉及数据形态，因此没有另起隔离种子；截图里的项目名是本地开发数据。

设计与实现说明见 [`docs/sidebar-project-group-ia.md`](../../sidebar-project-group-ia.md)。
侧栏语义边界见 [`docs/project-memory.md`](../../project-memory.md) §「Project 只占一个分组」。

| 截图 | 状态 | 可见内容 | 审阅重点 |
|---|---|---|---|
| [01-project-group-unselected.png](01-project-group-unselected.png) | 新建任务 · 侧栏 | 「项目」分组 → 中性 selector「未选择项目 ▾」（42px、1px 边框）→ 扁平「项目中心」；分隔线后是「当前任务」四步，再是「工作区」三项 | 两个 Project 条目是否读起来是**同一个分组**；「项目中心」是否明显轻于 selector；「项目中心」是否已离开「工作区」列 |
| [02-project-center-current.png](02-project-center-current.png) | `/projects` 列表页 · 侧栏 | 「项目中心」带当前页标记（中性面 + 左侧 3px 蓝色竖条）；selector 仍是最重的控件 | 同组里"你在这儿"是否只亮一次；标记是否**没有**复制 selector 的 `primary-soft` 填充观感 |
| [03-context-selected-linkage.png](03-context-selected-linkage.png) | 新建任务 · 已选上下文 | 侧栏 selector 显示 `测试1`（填充态）；正文「项目上下文」块显示同一个 `测试1` + 「继承项目术语、翻译记忆和规则」+ `更改` | 侧栏与正文是否给出**同一个答案**；正文是否只是复述（没有第二个选择器） |

## 本轮修掉的三个观感问题

1. **同属 Project 却被拆散**：改造前「项目上下文」在顶上、「项目中心」埋在底部「工作区」
   里，读起来像两套系统。现在它们是同一个容器里的上下两项。
2. **「项目中心」被读成第三个资料库**：它此前与「历史任务 / 术语与翻译记忆」同列。现在
   它在 Project 分组内，且是扁平行（36px / 透明底 / 500 字重），不与那三项同类。
3. **当前页标记与 selector 撞衫**：`项目中心` 的"当前页"用过 `primary-soft`
   （与 selector 选中态同色），会读成两个等价入口；现在改成中性面 + 3px 竖条。

## 复现方式

```bash
# 1. 启动应用（本机 outputs/ 数据）
cd /Users/xueyang/Dev/FolioThread
./venv/bin/streamlit run app.py --server.headless true --server.port 8602 --server.address 127.0.0.1

# 2. 首屏（新建任务）：等到页面真正渲染完（首次约 20s）再截
FOLIO_URL=http://127.0.0.1:8602 ./venv/bin/python scripts/ui_screenshot.py \
  --out /tmp/sidebar-01.png --url http://127.0.0.1:8602 --wait-ms 8000

# 3. 点侧栏「项目中心」再截当前页态（脚本见下）
node tmp/shot_projects.js http://127.0.0.1:8602 /tmp/sidebar-02.png list 2000
```

两个容易踩的坑（都会让截图骗人）：

- **截太早**：应用首次渲染约 20s，早了只会拍到一张只有 Logo 的空白页；
- **hover 污染**：Playwright 点击后指针停在按钮上，`:hover` 会盖掉当前页样式 ——
  两张意图不同的图会截出**字节完全相同**的文件。截图前必须 `page.mouse.move()` 移开
  指针，并用 `page.getByText('我的项目').waitFor()` 等列表页真正出现。
