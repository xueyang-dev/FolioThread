# 历史任务（Translation Task list）

这一页列出的是 **Translation Tasks**——一次具体的文档翻译执行。Task 属于某个
Project 只是它的一个属性，**不改变列表的对象语义**。

因此页面自称「历史任务」，左侧导航同名，卡片动作叫「打开任务」。Project 有自己
的入口（侧栏「项目」）。仅因为 Task 属于 Project 就把 Task list 命名为
「历史项目」，会让两个实体在文案层面混成一个——这是被回归测试守住的。

| 实体 | 是什么 | 保存什么 | 导航状态 | 入口 |
| --- | --- | --- | --- | --- |
| **Project** | 跨任务复用的长期 workspace | 术语、风格、人工确认记忆、项目级设置 | `active_project_id` | 侧栏「项目」 |
| **Translation Task** | 一次具体文档翻译执行 | 文档、段落、译文、审校与交付状态 | `active_job_id` | 侧栏「历史任务」 |

## Task 的身份：文档身份 + 本地化上下文

**同一份文档不等于同一个任务。** 同一份 PDF 在「生态恢复」项目下译成简体中文、
在「无人机论文」项目下译成 Français，是**两个独立任务**：注入的项目记忆与术语不同，
译文语言也不同。它们各有各的段落、审校与交付状态。

因此 Task 的身份由两部分组成，概念上分开、实现上也分开：

| 身份 | 函数 | 是什么 |
| --- | --- | --- |
| **文档身份** | `file_job_id(bytes)` | 文件内容哈希。同一份文件重传得到同一个值——用于**去重**。 |
| **任务身份** | `task_job_id(bytes, ctx)` | 文档身份 + 本地化上下文（项目 / 目标语言 / 源语言）。 |

打开任务时走 `resolve_task_id(bytes, project_id=…, target_lang=…)`：

1. 该上下文下的任务已存在 → 续做它（"同一个文件、同一个项目、同一种目标语言"
   就是同一个任务，重传即续传）；
2. 否则，若历史版本留下的、以**内容哈希**命名的旧任务存在，且它记录的项目 /
   目标语言与请求的上下文**可证明一致** → 沿用它（旧任务不因这次修复而失联）；
3. 否则 → 用推导出的新 ID 建一个**独立**任务。

第 2 条里的"可证明一致"是保守的一侧：旧任务**没有**目标语言记录时不会被认领，
宁可让用户重建一个任务，也不把另一种语言的旧任务当成这个活——一次跨语言误认领
会让用户在不知情的情况下续做并交付一个错误语言的文档。

这也是为什么历史列表里会出现"同一个文件名、不同项目/语言"的多张卡片：它们不是
重复项，而是不同的活。`file_job_id` 的文档字符串里显式写了它**不是**任务身份，
防止下一次有人再用内容哈希当任务 ID。

## 卡片结构

固定四行，密度目标 **105–120px**（1280 / 1440 / 1536 实测 116.7px）：

```text
display title
author · source type · target language · domain
status chip · segment progress · issue count   （· 所属项目）
最近更新 …                                     contextual CTA →
```

- **标题**优先取 `task.display_name`，其次文档画像的 `display_name`，再由文件名
  派生（剥掉 `Part 3` / `提取` / `translation` / `final` 这类工序噪声与作者括号
  尾注，作者另行展示）。
- **内部 identifier 不作为标题**：`audit-blocking-no-suggestion` 这类"分隔串 +
  内部标记词（audit / fixture / sample / test / …）"会被判定为 fixture 标识，
  卡片显示「未命名任务」，标识仍保留在 hover 提示与搜索里。
  普通分隔串（`field-notes-2026`）会被 humanize 成 `Field Notes 2026`。
- 完整源文件名**不作为主标题**，只作为 hover 提示保留。
- 项目归属是次级信息，只在任务真的有项目时出现。

## 布局：CTA 在卡片内部，整卡仍然可点

```python
with st.container(key=f"history_item_{job_id}"):
    with st.container(key=f"history_cardframe_{job_id}"):   # 唯一定位容器
        st.markdown(_history_card_html(view), ...)           # 视觉（pointer-events:none）
        st.button("打开任务", key=f"history_card_{job_id}")   # 点击层：铺满整卡
        st.button(view["cta"]["label"], key=f"history_cta_{job_id}")  # 卡片内 CTA
```

CSS 层级（自下而上）：

| 层 | 选择器 | 定位 | 作用 |
| --- | --- | --- | --- |
| 1 | `.tp-hcard` | 静态 | 视觉；`pointer-events:none` 让点击穿透 |
| 2 | `…st-key-history_card_*` | `absolute; inset:0` | 整卡 → Task Overview |
| 3 | `…st-key-history_cta_*` | `absolute; right/bottom` | contextual CTA → 对应 workflow |

两个按钮是**兄弟节点**（不是父子），CTA 的 `z-index` 更高，所以：

- 点标题 / 空白 / 卡片任意处 → 只有整卡导航触发；
- 点 CTA → 只有 CTA 触发，**不会**冒泡到整卡导航（浏览器实测：点「准备交付」
  落在交付页，不是 Overview）；
- 两者不是同一个 widget key，不存在双触发；
- 两个都是真实 `<button>`，键盘可达、`focus-visible` 有焦点环。

> 定位容器必须叫 `history_cardframe_*`：`[class*="st-key-history_card_"]` 是
> 子串匹配，若容器以 `history_card_` 开头会被同一条规则一起绝对定位，CTA 就会
> 锚到整页底部而不是卡片右下角。

## CTA 与落点

| 状态 | CTA | 落点 |
| --- | --- | --- |
| 运行中 | 查看进度 | Overview |
| 运行中断 | 继续处理（真的恢复任务） | Overview |
| 未翻译完 | 继续翻译 | 翻译页 |
| 有 blocker | 继续审校 | 审校页（**不经过 Overview**） |
| 报告待更新 | 更新报告 | 报告流程 |
| 已冻结交付 | 查看交付 | 交付页 |
| 其余已完成 | 准备交付 | 交付页 |
| 兜底 | 打开任务 | Overview |

`_cta()` 的选择顺序是有意的：先解决"卡住流程"的问题。「继续处理」是唯一带副作用
的 CTA。

## 顶部控件比例

search 是主控件，status / sort 是紧凑 select，三者**不等宽**：

```python
st.columns([5.5, 2.3, 2.2])   # search ≈ 55.7%
```

## 与 Project 页的分工

- 本页回答"我有哪些翻译任务、各自进行到哪一步"；
- 项目页回答"我长期复用的术语/风格/记忆沉淀在哪些容器里"；
- 侧栏「当前项目」显示当前任务所属的 Project，点击进入 **Project Overview**
  （不是任务 Overview）；任务没有项目时如实显示「当前任务未归入项目」，
  不回落成任务标题。

## 已知限制

浏览器 back 无法回到历史页。Streamlit 单页模型只有一个 URL，视图切换不产生
history entry，back 会离开应用。真正满足它需要给视图切换加 URL routing
（query params + `popstate`），是独立功能；用 history trap 伪造 back 会让浏览器
back 表现得像坏掉，比诚实不支持更糟。应用内返回路径是左侧导航或工作区顶栏。
