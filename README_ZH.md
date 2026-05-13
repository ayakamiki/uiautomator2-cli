# uiautomator2-cli

[English](README.md) | 中文

`u2cli` 是一个基于 [uiautomator2](https://github.com/openatx/uiautomator2) 的命令行工具。

核心目标：
- 用 CLI 直接操作 Android 设备
- 每条命令输出对应 `uiautomator2` Python 代码（`u2_code`）
- 通过 daemon 常驻进程复用连接，避免每次命令重复初始化

## 安装

```bash
pip install uiautomator2-cli
```

或使用 [uv](https://github.com/astral-sh/uv)：

```bash
uv tool install uiautomator2-cli
```

开发环境：

```bash
uv sync --all-groups
```

## 运行要求

- Python >= 3.8
- 已连接 Android 设备（USB 或网络 ADB）

## 快速开始

```bash
# 查看帮助
u2cli --help

# 点击文本
u2cli click --text "Settings"

# 获取文本
u2cli get-text --resource-id com.android.settings:id/title

# 截图
u2cli screenshot screen.png

# 查看当前前台 app
u2cli current-app
```

## Daemon 设计（新版）

`u2cli` 现在是 daemon-first 设计。

普通业务命令会自动走后台 daemon：
- 首次命令：自动启动 daemon
- 后续命令：复用同一个 daemon 进程
- 目标：减少每次命令的连接开销

不会被转发到 daemon 的命令：
- `u2cli daemon ...`（管理 daemon 本身）
- `u2cli repl`（交互模式，单进程内执行）

## 多设备隔离模型

daemon 以 serial 作为隔离维度。

- `-s <serial>`：使用该设备专属 daemon
- 不传 `-s`：使用 default daemon
- 每个 serial 拥有独立：socket、pid 文件、日志文件

建议：多设备场景始终显式传 `-s`，避免 default 通道和显式 serial 混用。

## 连接与重连行为

连接策略在 `connect_device()` 中实现：

- daemon 进程内：`u2.connect` 失败会自动重试 1 次（共最多 2 次）
- 非 daemon 直连路径：只尝试 1 次
- 命中缓存时优先复用同 serial 的 `Device` 对象

## 日志设计

### 日志位置

按 serial 分文件：

```bash
~/.u2cli/logs/
```

例如：
- `u2cli-daemon-default.log`
- `u2cli-daemon-s-xxxxxxxxxx.log`

### 日志轮转（文件切割）

已开启 `RotatingFileHandler`：
- `maxBytes = 5MB`
- `backupCount = 3`

即：单设备最多保留当前日志 + 3 个历史切片。

### 日志内容

默认记录：
- daemon 启停
- 请求类型（ping/run/stop）
- 命令参数（argv）
- 执行耗时
- exit code
- stdout/stderr 字节数
- 异常信息与堆栈
- 设备连接尝试与重试

可选增强（完整输出落盘）：
- run stdout 全量内容
- run stderr(full) 全量内容

## Daemon 管理命令

```bash
# 启动 daemon（可自动启动，一般不必手动）
u2cli daemon start

# 启动并开启完整输出日志
u2cli daemon start --full-output-log

# 查看状态
u2cli daemon status

# 查看最近 N 行日志
u2cli daemon logs --lines 300

# 停止 daemon
u2cli daemon stop
```

`daemon status` 会显示：
- `running`
- `socket`
- `pid_file`
- `log_file`
- `full_output_log`
- `pid`（运行中时）

## 环境变量

- `ANDROID_SERIAL`
  - 作用：默认目标设备 serial（等价于全局 `-s`）

- `U2CLI_DAEMON_LOG_FULL_OUTPUT=1`
  - 作用：当普通命令触发自动启动 daemon 时，启用完整 stdout/stderr 日志

示例：

```bash
export ANDROID_SERIAL=emulator-5554
export U2CLI_DAEMON_LOG_FULL_OUTPUT=1
u2cli device-info
```

## 全局参数

在子命令前使用：

- `-s, --serial`：指定设备 serial
- `--json`：JSON 输出
- `--version`：查看版本

## 命令总览

### 元素操作

- `click`
- `long-click`
- `get-text`
- `set-text`
- `clear-text`
- `exists`
- `wait`
- `element-info`
- `swipe-element`
- `scroll`

### XPath 操作

- `xpath-click`
- `xpath-exists`
- `xpath-get-text`
- `xpath-set-text`

### 设备/屏幕操作

- `screenshot`
- `dump-hierarchy`
- `device-info`
- `ui-info`
- `window-size`
- `screen-on`
- `screen-off`
- `orientation`
- `press`
- `swipe`
- `swipe-ext`
- `click-coord`
- `double-click`
- `long-click-coord`
- `send-keys`
- `open-notification`
- `open-quick-settings`
- `open-url`
- `shell`
- `current-app`

### 应用管理

- `app-start`
- `app-stop`
- `app-clear`
- `app-install`
- `app-uninstall`
- `app-info`
- `app-list`
- `app-list-running`
- `app-wait`

### 其它

- `repl`
- `daemon start|status|logs|stop`

## 常用示例

```bash
# 指定设备点击
u2cli -s emulator-5554 click --text "Wi-Fi"

# JSON 输出
u2cli --json exists --text "Settings"

# 检查 daemon 状态
u2cli -s emulator-5554 daemon status

# 查看该设备日志
u2cli -s emulator-5554 daemon logs --lines 200
```

## JSON 输出示例

```bash
$ u2cli --json exists --text "Settings"
{"u2_code": "d(text='Settings').exists", "result": true}

$ u2cli --json get-text --resource-id com.android.settings:id/title
{"u2_code": "d(resourceId='com.android.settings:id/title').get_text(timeout=3.0)", "result": "Settings"}
```

## 故障排查

- 命令执行失败，先看：
  - `u2cli daemon status`
  - `u2cli daemon logs --lines 300`

- 某 serial 连接异常：
  1. `u2cli -s <serial> daemon stop`
  2. `u2cli -s <serial> daemon start`
  3. 重试业务命令

- 多设备并行：
  - 强烈建议始终传 `-s`，避免 default 通道不确定性

## License

MIT
