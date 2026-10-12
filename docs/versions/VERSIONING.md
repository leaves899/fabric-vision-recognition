# 版本管理约定

## 已收录基线

| 标识 | 范围 | 冻结策略 | 验收状态 |
|---|---|---|---|
| V4 frozen | `demo/v5/v4_frozen/frozen/reoptimize_v4_quadgrid.py` | SHA256 固定；任何变动必须专项评审 | 候选轨迹算法，非真实纱线精度验收 |
| V5 Demo | `demo/v5/` | 初始导入原版源码与报告 | 原有测试报告为 15 passed；需本环境复测 |
| Engine V1.5 | `docs/references/` | 作为方案文档保存 | 新算法未实现/未通过实测 |

冻结 V4 源码 SHA256：`dde5d84193a3f3d02bb55ad72a8c2b9f2a640034563ed936736ad46808b8dad1`。

## 分支与提交

- `main`：经过评审的集成基线。
- `feature/<name>`：功能实现，必须有针对性的测试。
- `experiment/<name>`：可以失败的算法实验，必须保留 Benchmark 和差异报告，不在验证前替代基线。
- `fix/<name>`：修复问题，补回归测试。
- `docs/<name>`：文档更新。

使用 Conventional Commits：`feat:` / `fix:` / `test:` / `docs:` / `refactor:` / `experiment:`。

对已冻结文件的任何有意修改，须说明为什么不另建新版本，并更新测试、哈希、迁移说明。不要将未验收实验结果写成已确定的产品指标。

建议后续发布标签 `demo-v5.0.1`、`engine-v0.1.0-experimental` 等分别命名。最终的 `engine-v1.0.0` 只有正式计量验收后才能打标签。
