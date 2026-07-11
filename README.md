# Creation Intent Gate / 创造意图门

一个用于 Codex 的公开 Skill：在创建产品、项目、服务、自动化、工作流、内容体系等长期资产前，先通过 Mission / Vision / Values 提高意图质量，再进入计划和构建。

它解决的不是“AI 不够快”，而是 AI 执行越来越快之后更危险的问题：方向还没想清楚，功能和系统就已经被造出来了。

## 它会做什么

- 把功能冲动改写为可观察的状态转化 Mission。
- 展开多个真正不同的 Vision，而不是给同一路径换名字。
- 用自洽、他洽、代价和证据完成 Values 取舍。
- 锁定一个 1–3 天可进入真实流程的最小创造物。
- 保留原预测、现实反馈和预测偏差，让判断可以持续校准。
- 对复杂系统补充端到端回路、人机责任和质量门设计。

## 安装

在 Codex 中使用 `skill-installer` 安装：

```text
$skill-installer install https://github.com/kellanxu/creation-intent-gate/tree/main/skills/creation-intent-gate
```

也可以将 [`skills/creation-intent-gate`](skills/creation-intent-gate) 复制到本机的 Skill 目录。

## 使用

```text
使用 $creation-intent-gate，先从 Mission、Vision、Values 梳理这个创造物，再决定是否进入构建。
```

也可以直接说：

```text
我想做一个长期项目。先别列功能，帮我看看这件事有多少种长法，并用 MVV 收敛。
```

## 适用边界

适合：公开内容、多人项目、客户服务、产品、自动化、长期工作流、涉及数据或持续维护的系统。

不适合：普通讨论、资料查询、状态汇报、意图和范围已经确认的窄修复任务。

如果是一天内可完成、单人、可逆且没有外部承诺的小创造物，Skill 会使用轻量门，避免把思考本身变成拖延。

## 方法结构

这个 Skill 把 Mission / Vision / Values、现实碰撞和端到端回路组合成一套自包含的创造流程，并增加运行深度分级、Build Gate、证据边界、可视化交付、现实碰撞卡和文件固化规则。

完整的方法解释见 [`references/method.md`](skills/creation-intent-gate/references/method.md)。

## License

MIT
