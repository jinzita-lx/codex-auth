# codex-auth

中文 | [English](README.en.md)

`codex-auth` 是一个 Codex CLI 本地登录态 profile 切换器。

它保留同一套 Codex home、配置、会话历史、skills 和 plugins，只把不同账号的
`auth.json` 保存成命名 profile。切换账号时只替换本地 `~/.codex/auth.json`，
不会执行 `codex logout`，因此不会主动注销或撤销原账号登录态。

## 效果展示

下面的截图使用脱敏示例账号。截图中不包含真实 token、账号 ID 或完整邮箱。

### 账号列表

![codex-auth list](docs/assets/list-summary.svg)

### 当前账号状态

![codex-auth status](docs/assets/status-detail.svg)

### 登录新账号

![codex-auth login](docs/assets/login-flow.svg)

## 功能

- 将当前 Codex 登录态保存成命名 profile。
- 通过替换本地 `auth.json` 在多个 profile 间切换。
- 新增账号时不调用 `codex logout`，避免主动撤销当前账号 token。
- 用精简列表展示 profile、状态、套餐、5h/7d 剩余额度。
- 用详细状态页展示当前账号额度、reset 时间和 credits。
- 根据状态和剩余额度自动上色。
- 可执行入口保持很薄，核心逻辑拆分在 Python 模块中维护。

## 安装

推荐使用安装脚本。脚本会把项目安装到 `~/.local/share/codex-auth`，并在
`~/.local/bin/codex-auth` 注册命令。

### 一键安装

直接执行：

```bash
curl -fsSL https://raw.githubusercontent.com/jinzita-lx/codex-auth/v0.1.3/install.sh | bash
```

### 验证安装

安装后执行：

```bash
codex-auth --help
codex-auth path
```

正常情况下，`codex-auth path` 会显示当前使用的 `CODEX_HOME`、`auth.json`
和 profile 目录。

如果提示 `codex-auth: command not found`，把 `~/.local/bin` 加入 `PATH`：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

### 依赖

- macOS 或 Linux shell
- Python 3.9+
- 已安装 Codex CLI，且命令名为 `codex`
- `~/.local/bin` 已加入 `PATH`

### 安装位置

默认安装后会使用：

```text
~/.local/share/codex-auth/     # 项目代码
~/.local/bin/codex-auth        # PATH 中的可执行入口
~/.codex/auth-profiles/        # 保存的登录态 profile
~/.codex/auth.json             # 当前生效的 Codex 登录态
```

需要指定版本或安装位置时：

```bash
curl -fsSL https://raw.githubusercontent.com/jinzita-lx/codex-auth/v0.1.3/install.sh | CODEX_AUTH_REF=v0.1.3 CODEX_AUTH_PREFIX="$HOME/.local" bash
```

## 快速开始

保存当前已登录的 Codex 账号：

```bash
codex-auth save personal
```

登录另一个账号，但不注销当前账号：

```bash
codex-auth login work
```

切换账号：

```bash
codex-auth switch personal
codex-auth switch work
```

查看已保存 profile：

```bash
codex-auth list
```

查看当前账号详细状态：

```bash
codex-auth status
codex-auth status work
```

## 命令说明

### `codex-auth login <name> [--replace] [codex-login-options...]`

登录一个新的 Codex 账号，并保存为 `<name>`。

这个命令不会调用 `codex logout`。它的流程是：

1. 在安全的情况下保存当前 active profile 的最新登录态。
2. 临时把当前 `auth.json` 挪开。
3. 执行 `codex login`。
4. 将新的 `auth.json` 保存为 `auth-profiles/<name>.json`。
5. 将 `<name>` 标记为 active。

如果登录失败，会自动恢复原来的 `auth.json`。

示例：

```bash
codex-auth login work
codex-auth login work --replace
codex-auth login work --device-auth
```

### `codex-auth save <name>`

将当前 `~/.codex/auth.json` 保存为命名 profile。

```bash
codex-auth save personal
```

### `codex-auth switch <name>`

切换到已保存的 profile。

```bash
codex-auth switch work
```

### `codex-auth list [--no-check]`

展示精简 profile 列表。

```text
profile            status    plan    5h    7d    account
* pro              ok        prolite 100%  97%   ji***@gmail.com
  plus             ok        plus    28%   89%   xi***@gmail.com
```

默认情况下，`list` 会联网检查账号是否可用以及 5h/7d 剩余额度。使用
`--no-check` 可以只读取本地 profile，速度更快：

```bash
codex-auth list --no-check
```

### `codex-auth status [name]`

展示当前 active profile 或指定 profile 的详细状态。

```text
* pro
  account: ji***@gmail.com
  status:  ok
  plan:    prolite
  usage:
    5h    0% used  100% left  resets 2026-05-26 23:10:00 CST
    7d    3% used   97% left  resets 2026-06-01 19:25:16 CST
  credits: balance=0, reset-credits=0
```

示例：

```bash
codex-auth status
codex-auth status work
```

### `codex-auth check [name|--all]`

检查单个 profile 的详细状态，或用列表格式检查全部 profile。

```bash
codex-auth check work
codex-auth check --all
```

### `codex-auth rename <old> <new>`

重命名已保存的 profile。

```bash
codex-auth rename personal private
```

### `codex-auth remove <name>`

删除已保存的 profile。

```bash
codex-auth remove private
```

### `codex-auth path`

输出当前使用的路径。

```bash
codex-auth path
```

## 状态说明

| 状态 | 含义 |
| --- | --- |
| `ok` | 登录态可用，且当前没有触发 Codex 使用限制。 |
| `limited` | 登录态可用，但当前 Codex 使用受限。 |
| `unusable` | token/key 被拒绝、撤销或不可用。 |
| `missing` | profile 中没有可用 token/key。 |
| `error` | 网络或服务检查失败。 |
| `unchecked` | 只读取本地信息，没有执行在线检查。 |

## 使用量窗口

Codex 当前暴露两个使用量窗口：

- `5h`：短周期滚动额度窗口。
- `7d`：七天滚动额度窗口。

`list` 展示剩余额度；`status` 展示已用额度、剩余额度以及两个窗口的 reset 时间。

## 颜色

交互终端中默认自动启用颜色；管道或重定向输出默认禁用颜色。

```bash
CODEX_AUTH_COLOR=auto
CODEX_AUTH_COLOR=always
CODEX_AUTH_COLOR=never
NO_COLOR=1 codex-auth status
```

颜色含义：

- 绿色：账号可用，或剩余额度健康。
- 黄色：受限/未知状态，或剩余额度中等。
- 红色：不可用/错误/缺失状态，或剩余额度较低。
- 灰色：标签、未检查值和已用百分比。

## 安全说明

- `codex-auth switch` 只替换本地 `auth.json`。
- `codex-auth login` 刻意避免调用 `codex logout`。
- `codex logout` 可能撤销当前 token，不建议用于 profile 切换。
- profile 存放在 `~/.codex/auth-profiles/`，文件权限为 `0600`。
- 在线使用量检查会从 Python 里直接把 token 放进 Authorization header；
  token 不会作为命令行参数暴露。
- 自动保存 active profile 前，`codex-auth` 会比较账号身份；如果当前
  `auth.json` 属于另一个账号，会跳过写入，避免覆盖错误 profile。

## 项目结构

```text
codex-auth/
├── README.md
├── README.en.md
├── bin/
│   └── codex-auth
├── codex_auth/
│   ├── __main__.py
│   ├── cli.py
│   ├── colors.py
│   ├── store.py
│   ├── ui.py
│   ├── usage.py
│   └── utils.py
├── docs/
│   └── assets/
│       ├── list-summary.svg
│       ├── login-flow.svg
│       └── status-detail.svg
└── pyproject.toml
```

模块职责：

- `cli.py`：命令解析和分发。
- `store.py`：profile 存储、锁、登录、保存、切换、重命名、删除。
- `usage.py`：账号可用性和额度检查。
- `ui.py`：终端输出渲染。
- `colors.py`：颜色策略。
- `utils.py`：JSON、JWT payload 解析、身份提取、时间格式化。

## 开发

本地安装当前工作区：

```bash
./install.sh
```

语法和 import 检查：

```bash
python3 -m compileall -q ~/.local/share/codex-auth/codex_auth
```

安装 smoke test：

```bash
bash tests/install-smoke.sh
```

不安装，直接从项目运行：

```bash
CODEX_AUTH_PROJECT=~/.local/share/codex-auth ~/.local/share/codex-auth/bin/codex-auth --help
```

使用临时 Codex home 测试：

```bash
tmp="$(mktemp -d)"
CODEX_HOME="$tmp" codex-auth path
```
