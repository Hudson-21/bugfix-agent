# inventory：失败订单造成部分库存扣减

## 目的与业务约定

这是 AI 辅助设计的小型合成案例，侧重多步骤修改的完整性，不是生产事故或开源基准题。它沿用本项目原有工作流；独立验收集的意义是防止只凭模型自编测试和 Reviewer 判断接受错误修复。

接口：`inventory.reserve(stock: dict[str, int], lines: list[tuple[str, int]]) -> None`。

- `stock` 是可信的普通字典，商品名为字符串，库存为非负整数；`lines` 是有限列表，每项为商品名与数量。
- 数量必须为正整数，拒绝布尔值、非整数、零和负数，抛 `ValueError`。
- 未知商品、库存不足均抛 `ValueError`；重复商品按数量累计，不能仅分别与初始库存比较。
- 成功时原地扣减传入字典并返回 `None`，保留无关商品和库存为零的键。
- 任一行校验或库存检查失败，整个字典保持调用前内容；输入订单列表始终不变。
- 空订单不修改库存。只讨论单线程、普通字典和列表；不提供数据库事务、并发锁或持久化保证。

复现：库存 `{"tea": 5, "coffee": 1}`，订单 `[("tea", 2), ("coffee", 2)]`。原实现抛出库存不足后，茶叶已经从 5 变为 3。期望抛出异常且库存仍为 `{"tea": 5, "coffee": 1}`。

## 简短分阶段计划与验收

1. 先写 `evals/inventory/` 的独立业务验收以及项目集成测试。验收覆盖失败后无副作用、重复商品、成功原地扣减、空订单、输入保护；期望值为手工列出的常量。
2. 新建 `bugfix_agent/cases/inventory/{issue.json,replay.json,repo/}`，CLI 加入 inventory。Bug 源码保留逐行检查并立即扣减；基线覆盖正常路径和第一行失败，因此仍能全通过。用新测试证明后续行失败会污染库存，再实现 replay 补丁。
3. 完整测试、CLI 演示和 wheel 外部安装验证。更新 README、开发日志与 handoff，提交、推送并核对 CI。

推荐修复思路为先累计需求、完整校验，再统一扣减；备选是在副本中模拟成功后提交。两者都允许，验收只检查业务行为，不强制某种代码结构。仅逐行预检查而不累计重复商品，仍可能造成负库存。

## 独立验收的边界

`evals/inventory/` 不在案例的 `repo/` 中，现有引擎只向模型提供源 repo 和生成的回归测试，因此这组验收不进入模型上下文。它是在修复结束后对工作副本的额外检查，结果不写回原始 `report.json`，不计入其中的测试数、耗时或 tokens。

验收集与 replay 都由本次开发过程编写，公开可读；不能称为独立团队出题、隐藏基准或对开发助手的盲测。当前尚未运行 inventory live。

## 运行与验收

在已克隆项目根目录打开 CMD，运行无需密钥的演示：

```cmd
python -m bugfix_agent demo --case inventory --output runs/inventory-demo --open
python -m pytest -q evals/inventory --inventory-workspace runs/inventory-demo/workspace --junitxml=runs/inventory-demo/acceptance.xml
```

`--output` 必须为新目录；重复运行时将两条命令中的 `inventory-demo` 一起改成新名称。第二条命令执行仓库里的独立验收，支持本机可信修复副本，不能用于不可信代码；XML 与原始 `report.json` 分开保存。`evals/` 随 Git 仓库提供，不打包到 wheel，验收命令须在克隆的项目根目录运行。

不指定输出目录也可以演示，随后把终端打印的报告目录末尾换成 `workspace` 传给 `--inventory-workspace`。该参数必填，以防误测本机另一个同名模块。验收退出码以 pytest 为准：0 为全通过，1 为存在失败；报错、跳过或未运行不算验证成功。

需要真实调用时，按 [README](../../README.md#接入-deepseek-官方-api) 配置官方接口，在交互终端输入密钥：

```cmd
python -m bugfix_agent demo --case inventory --live --ask-key --output runs/inventory-live --open
python -m pytest -q evals/inventory --inventory-workspace runs/inventory-live/workspace --junitxml=runs/inventory-live/acceptance.xml
```

`inventory-live` 也须为新目录。真实模型生成的测试数可能与 replay 不同；先核对 `report.json` 是否成功，再独立验收。独立验收失败时应保留两份结果，即使报告显示 success，也不能把补丁称为完整通过。

## 验收集能发现什么

| 实现 | 预期结果 | 检验重点 |
|---|---|---|
| 原始逐行扣减 | 4 通过、8 断言失败 | 后续行失败导致库存被部分修改 |
| replay：累计需求、检查后扣减 | 12 通过 | 成功与失败路径均符合约定 |
| 错误补丁：只在副本中扣减，漏掉提交 | 必须失败 | 不能为避免失败副作用而破坏成功扣减 |
| 错误补丁：逐行预检查，再统一扣减 | 必须失败 | 重复商品累计超出库存不能通过 |

项目测试会实际运行以上错误补丁作为对照，而不是只检查源码文字。它们是构造的测试变体，不是模型产生的失败样本。

原始 repo 中的 Bug 故意保留，避免下次演示失去复现条件。补丁在运行工作副本里；验收通过不改变输入仓库。
