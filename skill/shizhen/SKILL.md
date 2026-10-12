---
name: shizhen
description: 当用户给出抖音、快手、小红书、TikTok、X、YouTube、哔哩哔哩等短视频或图集的分享链接，想要标题、视频文件或音频文件时使用。通过拾帧命令行 shizhen 识别链接、提取并下载到本地。
---

# 拾帧（shizhen）

用命令行 `shizhen` 识别分享链接，并把视频或音频保存到本地。令牌由用户在小程序“账号设置 → Agent 令牌”里生成，并已通过 `shizhen login` 或环境变量 `SHIZHEN_TOKEN` 配置好。

## 何时使用

- 用户给出短视频或图集的分享链接（或整段分享文本），想知道标题、作者、时长。
- 用户想把视频或音频文件保存下来。

## 怎么用

一律加 `--json`，标准输出只有一个 JSON 对象，用退出码决定下一步。

```bash
shizhen parse "<链接或整段分享文本>" --json          # 只识别：平台、标题、作者、时长、可选清晰度
shizhen extract "<链接>" --json -o <目录>             # 识别、创建任务、等待、下载视频
shizhen extract "<链接>" --audio --json -o <目录>     # 提取音频
shizhen extract "<链接>" --no-wait --json            # 只创建任务，返回 jobId
shizhen jobs [jobId] --json                          # 任务列表或状态
shizhen download <jobId> --json -o <目录>            # 下载已完成任务
shizhen usage --json                                 # 当日额度
```

成功时 JSON 里 `ok` 为 true，`file` 是保存的文件路径。失败时 `ok` 为 false，带 `code`、`message`、`retryable`，有则带 `resetAt`、`jobId`。

## 按退出码处理

| 退出码 | 含义 | 你该做的 |
|---|---|---|
| 0 | 成功 | 继续 |
| 2 | 输入问题（链接无效、平台未开放、图集、参数错误） | 告诉用户原因，不重试 |
| 3 | 额度用完或调用过快 | 告诉用户何时恢复（`resetAt`），不重试，不换方式绕开 |
| 4 | 令牌缺失、无效、过期、已吊销或权限不足 | 请用户到小程序重新生成令牌，再运行 `shizhen login` |
| 5 | 服务暂时不可用，或等待超时 | 可稍后重试一次；等待超时时任务仍在，用 `shizhen download <jobId>` 取回，不要重复创建 |
| 6 | 命令行版本过旧 | 请用户升级：`pipx upgrade shizhen` |

## 版权提醒

只处理用户本人拥有或已获授权的内容。如果用户明确要批量抓取他人作品，先提醒对方注意版权与平台规则，不要主动批量执行。

## 不要做

- 不读取、不打印、不转述令牌；不要把令牌写进命令行参数或日志。
- 不调用 `shizhen` 以外的接口，不自己拼请求去访问拾帧服务。
- 不把下载地址发给第三方。
- 额度用完或令牌失效时停下来告诉用户，不重试、不想办法绕开。
