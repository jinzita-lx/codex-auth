# Changelog

## v0.1.4

- 修复外部 API key 登录改写 `auth.json` 后，active profile 标记可能误导
  `list/status` 的问题。
- 切换 profile 前的自动保存改为必须验证账号身份，避免把 API key 登录态
  覆盖到原 ChatGPT profile。
- `codex-auth switch` 默认停止旧 app-server/proxy 并重启 app-server，避免后台服务
  继续使用旧认证缓存；可用 `--no-restart-app-server` 跳过。
- 支持 `codex-auth save --with-config <name>` 保存 `config.toml` sidecar；
  切换到带配置的 profile 时会同步恢复配置，适配 API 计费 provider。
- 新增纯交互式 `codex-auth login-api`，用于创建 API 计费 profile，API key
  通过隐藏输入读取，不支持命令行参数传递密钥。

## v0.1.3

- 修复 PATH 入口通过符号链接启动时无法加载 `codex_auth` 模块的问题。
- 安装器改为生成固定项目路径的可执行 wrapper，提升一键安装可靠性。
- 增加 Python 版本检查和安装 smoke test。

## v0.1.2

- 支持 `codex-auth status <name>` 查看指定 profile 的详细状态。

## v0.1.1

- 将 GitHub 仓库调整为 public 后，README 默认使用 `curl` 一键安装。
- 修复 `curl | bash` 安装时通过 GitHub CLI 拉取 tag 可能失败的问题。

## v0.1.0

- 初始化 `codex-auth` 项目结构。
- 支持保存、切换、重命名、删除 Codex auth profile。
- 支持不调用 `codex logout` 的新账号登录流程。
- 支持账号可用性检查和 5h / 7d 使用量展示。
- 支持终端颜色、中文默认 README、英文 README 和脱敏效果图。
- 提供一键安装脚本 `install.sh`。
