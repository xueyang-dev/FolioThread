# 19 · Project Center / New Task：Inbox 与 Project 的语义分离

捕获日期：2026-09-17 · Streamlit 1.63.0 · Python 3.11.3 · 视口 1440 × 1080

数据：`outputs/` 隔离到临时目录后由脚本播种（4 个项目：1 个有任务+知识资产、
1 个有任务、1 个空、1 个已归档；2 条未分类任务），不使用仓库里的真实数据。

设计与实现说明见 [`docs/project-center-inbox-ia.md`](../../project-center-inbox-ia.md)。

| 截图 | 状态 | 可见内容 | 审阅重点 |
|---|---|---|---|
| [01-project-center.png](01-project-center.png) | Project Center 首屏 | 工具栏 →「系统任务区」（虚线 + sunken 面 + 灰色 inbox 图标 + `Inbox` 小标签 + `2 个 / 查看 →`）→「我的项目 3」（三张白面卡片） | 未分类入口与项目卡是否读起来是两类对象；两个区块标题是否成组 |
| [02-new-task-inbox.png](02-new-task-inbox.png) | 新建任务 · 未分类态 | 「项目上下文」标签 + sunken context block（图标 + `未分类任务` 主状态 + 低对比 `Inbox` 标签 + 后果说明）+ `选择项目` | 英文 Inbox 是否退到次要层级；说明文案是否回答了"不继承什么" |
| [03-new-task-project.png](03-new-task-project.png) | 新建任务 · 已选项目态 | 同一个 context block 的 selected 态（primary-soft 面 + 蓝色 folder 图标 + 项目名 + 继承说明）+ `更改` | 两种状态是否共用同一容器语法、只换语气 |

## 本次截图发现并修掉的缺陷

首次捕获时，新建任务页的图标位置**渲染成了字面文本** `inbox` / `folder_open`。

原因是 `.tp-project-context` 的图标规则没有声明
`font-family: "Material Symbols Rounded"` —— 本项目没有全局图标字体规则，每个
使用点都必须自己绑定。漏掉它不会报错，只会把图标名当文字画出来，所以界面上会
出现一个蓝色的 `inbox` 字样，看起来就像"英文 Inbox 成了主视觉标题"。

已修复，并补了一条结构性回归测试（`test_every_icon_rule_binds_the_icon_font`）
防止其他使用点再犯。

## 复现方式

```bash
# 1. 在隔离目录播种数据（不写仓库 outputs/）
/tmp/folio-shot/seed.py

# 2. 用隔离 OUTPUT_DIR 启动应用
cd /tmp/folio-shot && venv/bin/python -m streamlit run /tmp/folio-shot/run_app.py \
  --server.port 8511 --server.headless true --server.fileWatcherType none

# 3. 截图（需要 node + playwright-core，见 scripts/ui_screenshot.py 的依赖说明）
```

截图脚本本身是临时的（`/tmp/folio-shot/shot.js`）：`scripts/ui_screenshot.py`
目前只支持"首屏"与"工作区小节"两种导航，Project Center / 新建任务页需要自定义
点击路径。若这类截图会长期做，建议把"按侧栏入口导航"提升为该脚本的一个参数。
