# shizhen

拾帧（ClearMark）的命令行工具：识别短视频、图集的分享链接，提取视频或音频并下载到本地。只依赖 Python 标准库，需要 Python 3.9 及以上。

> 状态：开发中，尚未发布到 PyPI。服务端令牌功能默认关闭，开放时间以拾帧小程序为准。

## 安装

发布后：

```bash
pipx install shizhen
```

现在从源码安装：

```bash
pipx install .        # 或 pip install .
```

## 获取令牌

在拾帧小程序“账号设置 → Agent 令牌”里生成。令牌等同于你的账号，只显示一次，不要分享给他人；每个账号最多 3 个，90 天过期，可随时在小程序里吊销。

## 登录

令牌从标准输入读取（不接受命令行参数，避免留在 shell 历史里），保存前会向服务端验证：

```bash
shizhen login          # 终端里粘贴，输入不显示
echo "$TOKEN" | shizhen login
```

令牌读取顺序：环境变量 `SHIZHEN_TOKEN` 优先，其次 `shizhen login` 保存的配置文件。

- Linux/macOS：`~/.config/shizhen/config.json`（权限 600）
- Windows：`%APPDATA%\shizhen\config.json`

`shizhen logout` 只删除本地令牌，服务端吊销请在小程序里操作。

## 命令

| 命令 | 作用 |
|---|---|
| `shizhen parse <链接或分享文本>` | 识别：平台、标题、作者、时长、可选清晰度 |
| `shizhen extract <链接> [--audio] [--quality ID] [-o 目录] [--no-wait] [--timeout 600]` | 识别、创建任务、等待完成、下载 |
| `shizhen jobs [任务ID]` | 任务列表或单个任务状态 |
| `shizhen download <任务ID> [-o 目录]` | 下载已完成任务的成品 |
| `shizhen usage` | 当日额度：已用、剩余、重置时间 |

所有命令支持 `--json`：标准输出只有一个 JSON 对象；不加时输出中文说明。

约定：

- 轮询从 3 秒开始逐步放宽到 15 秒，默认最多等 600 秒；超时输出任务 ID 并以退出码 5 结束，任务不会被取消。
- 文件名为标题（去掉话题标签，最多 30 个字符）加扩展名，音频为 `标题-音频.m4a`；同名文件不覆盖，依次加 `(2)`、`(3)`。
- 下载先写 `.part` 临时文件，完成后改名，中断不留半个文件。
- 命令行不做额度计算，余量以服务端为准。
- 暂不支持图集下载。
- 受平台保护的音频（如 Suno）没有下载任务：命令行直接以退出码 2、错误码 `AUTHORIZED_EXPORT_REQUIRED` 结束，请在小程序里打开或转发。

## 退出码

| 退出码 | 含义 |
|---|---|
| 0 | 成功 |
| 2 | 输入问题（链接无效、平台未开放、参数错误） |
| 3 | 额度用完或调用过快（`DAILY_*`、`SERVICE_BUDGET_PAUSED`、`TOKEN_RATE_LIMIT`） |
| 4 | 令牌缺失、无效、过期、已吊销，或权限不足（`TOKEN_SCOPE`） |
| 5 | 服务暂时不可用（502/503/超时）或等待超时 |
| 6 | 命令行版本过旧，请升级 |

`--json` 失败输出包含 `code`、`message`、`retryable`，有则带 `resetAt`、`jobId`。

## 环境变量

| 变量 | 说明 |
|---|---|
| `SHIZHEN_TOKEN` | 令牌，优先于配置文件 |
| `SHIZHEN_API` | 服务地址，默认 `https://jesxion.com` |
| `SHIZHEN_CONFIG_DIR` | 覆盖配置目录（主要用于测试） |

## 配套 skill

`skill/shizhen/SKILL.md` 是给 AI agent 用的说明。复制到 Claude Code 的技能目录即可：

```bash
mkdir -p ~/.claude/skills && cp -r skill/shizhen ~/.claude/skills/
```

其他 agent 可把该文件内容作为提示词使用。

## 版权与使用

只处理你本人拥有或已获授权的内容，并遵守各平台的使用规则。

## 开发与测试

```bash
python -m unittest discover -s tests -t .
```

测试使用本地假 HTTP 服务，不联网，也不需要真实令牌。
