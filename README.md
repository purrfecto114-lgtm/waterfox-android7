# buildstate 分支（孤儿分支：只存最近一次编译产物快照，不保留历史）

- 还原：`cat parts/* > buildstate-gradled.tar.zst && tar --zstd -xf buildstate-gradled.tar.zst`
- 90MB 分块 part-00 ~ part-41（3744 MB）
- 来源 run: 43554048519 / commit b50ef8f4216916bb50c265520258becc19821294 / 2026-11-14 04:52 UTC
- 每次构建成功整体替换本分支；staging 为推送中的临时分支
