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

如果需要 Harmony 支持：

```bash
pip install 'uiautomator2-cli[harmony]'
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

如果需要 Harmony 支持：
- `hdc` 已加入 `PATH`（或通过 `HDC_BIN` 指定）
- 通过 `harmony` extra 安装 `hmdriver2`

## Android 与 Harmony 对比

| 项目 | Android | Harmony |
| --- | --- | --- |
| 安装 | `pip install uiautomator2-cli` | `pip install 'uiautomator2-cli[harmony]'` |
| 传输链路 | ADB | HDC |
| Driver 运行时 | `uiautomator2` | `hmdriver2` |
| 推荐 CLI 参数 | `--platform android` | `--platform harmony` |
| 不显式指定时 | `auto` 会解析为 Android | 需要显式选择 |
| `--package` 语义 | 原生 package selector | 先按 hierarchy 中的 bundle/package 过滤，再回落到具体 native selector |
| 动态 selector 路径 | 走原生 `uiautomator2` selector 字段 | 先做 hierarchy 辅助解析，再回落到具体 native selector |

## 快速开始

```bash
# 查看帮助
u2cli --help

# 点击文本
u2cli click --text "Settings"

# 通过 resource/element ID 获取文本
u2cli get-text --resource-id entry_title

# 截图
u2cli screenshot screen.png

# 查看当前前台 app
u2cli current-app

# 按一个常用命名键
u2cli press back

# Harmony 真机已验证 alias：recent / menu / enter / delete /
# volume_up / volume_down / power
u2cli --platform harmony press recent

# Android / Harmony 查看当前媒体播放信息
# `u2_code` 会在 Android 上显示 `dumpsys media_session`，在 Harmony 上显示 `AVSessionService` hidumper
u2cli playback-info

# Android / Harmony 控制媒体播放
u2cli media-control play-pause

# Harmony 也支持通过 hdc + uitest 走零安装媒体控制
u2cli --platform harmony media-control next

# Harmony 上 `stop` 能送达，但测试过的播放器可能把它当成暂停
u2cli --platform harmony media-control stop

# Harmony element 示例：通过 description 正则点击
u2cli --platform harmony click --description-matches "Login.*button"

# Harmony element 示例：按 bundle/package + 文本前缀获取文本
u2cli --platform harmony get-text --package com.demo.app --text-starts-with "Welcome"

# Harmony element 示例：按 bundle/package + 文本包含判断元素是否存在
u2cli --platform harmony exists --package com.demo.app --text-contains "Login"
```

## Daemon 设计（新版）

`u2cli` 现在是 daemon-first 设计。

普通业务命令会自动走后台 daemon：
- 首次命令：自动启动 daemon
- 后续命令：复用同一个 daemon 进程
- 如果磁盘上的 Python 代码发生变化，CLI 会识别 stale daemon 并自动重启
- 目标：减少每次命令的连接开销

不会被转发到 daemon 的命令：
- `u2cli daemon ...`（管理 daemon 本身）
- `u2cli repl`（交互模式，单进程内执行）

开发调试控制：
- `u2cli --no-daemon ...`：当前命令直接在前台进程执行，绕过后台 daemon
- `u2cli daemon restart`：对当前 platform/serial 目标强制重启 daemon

## 多设备隔离模型

daemon 现在以 platform + serial 作为隔离维度。

- `--platform <platform>` + `-s <serial>`：使用该平台和该设备对应的 daemon 实例
- 只传 `--platform <platform>`：使用该平台下的 default daemon
- 每个 platform/serial 组合都拥有独立的 socket、pid 文件、日志文件

建议：Android 与 Harmony 混用时始终显式传 `--platform`。多设备场景再额外显式传 `-s`，避免 default 通道混用。

## 连接与重连行为

连接策略在 `connect_device()` 中实现：

- daemon 进程内：`u2.connect` 失败会自动重试 1 次（共最多 2 次）
- 非 daemon 直连路径：只尝试 1 次
- 命中缓存时优先复用同 serial 的 `Device` 对象

## 真机 Smoke 检查

可以用 `u2cli-smoke` 对已连接设备做一轮快速 sanity check。

```bash
# Android smoke，包含 playback-info
u2cli-smoke --platform android -s DEVICE-001 --json

# Harmony smoke，并保存截图产物
u2cli-smoke --platform harmony -s TARGET-001 --screenshot smoke.png
```

这组 smoke 会检查 device info、window size、current app、screenshot、hierarchy dump 和 `playback-info`。
Android 上，`playback-info` 基于 `dumpsys media_session` 读取播放态；对于会员歌曲这类可能被付费弹窗打断的媒体场景，应优先用它校验，而不是只看 UI。
Harmony 上，`playback-info` 基于 `AVSessionService` 读取播放元数据；即使音乐应用退到后台、前台停在别的 app，也能继续看到活跃播放会话。

`media-control` 会把 `play`、`pause`、`play-pause`、`next`、`previous`、`stop` 映射到对应平台的媒体控制。
Harmony 上，`u2cli` 通过 `hdc` 调用设备内建的零安装 `uitest uiInput keyEvent` 路径实现媒体控制。
在已验证的 Harmony 真机上，`play`、`pause`、`play-pause`、`next`、`previous` 都能按预期改变活跃 AVSession。`stop` 也能成功送达，但华为音乐、QQ 音乐和酷狗都会把它解释成更接近暂停的状态切换，而不是独立的 stopped 态。所以 Harmony 上的 `stop` 更准确的理解应是“命令送达有保证，但结果播放态依赖具体播放器”，不要默认它一定会进入严格 stopped。

## 日志设计

### 日志位置

按 platform + serial 分文件：

```bash
~/.u2cli/logs/
```

例如：
- `u2cli-daemon-android-default.log`
- `u2cli-daemon-android-s-xxxxxxxxxx.log`
- `u2cli-daemon-harmony-default.log`
- `u2cli-daemon-harmony-s-xxxxxxxxxx.log`

### 日志轮转（文件切割）

已开启 `RotatingFileHandler`：
- `maxBytes = 5MB`
- `backupCount = 3`

即：每个 platform/serial 组合最多保留当前日志 + 3 个历史切片。

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
export ANDROID_SERIAL=TARGET-001
export U2CLI_DAEMON_LOG_FULL_OUTPUT=1
u2cli device-info
```

## 全局参数

在子命令前使用：

- `-s, --serial`：指定设备 serial
- `--platform`：指定后端平台（`android`、`harmony`、`auto`）
- `--json`：JSON 输出
- `--version`：查看版本

## Selector 说明

元素命令在 Android 和 Harmony 下共用同一套跨平台 selector 语义。

- `--description-matches`：按正则匹配 accessibility description
- `--description-starts-with`：按前缀匹配 accessibility description
- `--package`：包名 / bundle 过滤

`--package` 的实际语义依赖平台：

- Android：对应原生 package name selector
- Harmony：先按 hierarchy 中的 bundle/package 属性过滤，再回落成具体 native selector 执行

示例：

```bash
u2cli --platform harmony click \
  --description-matches "Login.*button" \
  --package com.demo.app
```

## Harmony Selector 语义

当启用 `--platform harmony` 时：

- CLI 已直接暴露并支持 `--description-matches` 与 `--description-starts-with`
- `--text-contains`、`--text-starts-with`、`--text-matches`、`--description-matches`、`--description-starts-with`、`--package` 都会先经过 hierarchy 辅助解析，再执行具体操作
- `--package` 在 Harmony 下表示 selector 解析阶段的 bundle/package 过滤，不是一个直接下发给原生驱动的字段
- 混合平台脚本里建议始终显式传 `--platform harmony`，不要依赖默认值

## Harmony current-app 说明

在 Harmony 设备上，`current-app` 现在采用分层识别：

- 普通前台页面优先使用 `aa dump` 里的前台 mission 信息，返回 `package + activity/ability`
- Home/launcher 场景回退到 hierarchy 顶层 focused bundle
- 在已验证的真机上，主页会返回 `com.ohos.sceneboard`

示例：

```bash
u2cli --platform harmony current-app
# 主页示例结果：{"package": "com.ohos.sceneboard", "activity": null}
```

## Harmony XPath 示例

`xpath-*` 命令既支持完整 XPath，也支持 service 层 locator shorthand：

- `Login`：精确文本
- `%Login%`：文本包含
- `Welcome%`：文本前缀匹配
- `%button`：文本后缀匹配
- `^Login.*`：文本正则匹配
- `@entry_button`：resource/element ID shorthand，会解析成 Harmony 的 `id`

示例：

```bash
u2cli --platform harmony xpath-click "%Login%"
u2cli --platform harmony xpath-get-text "Welcome%"
u2cli --platform harmony xpath-exists "^Login.*"
```

## 命令总览

### 元素操作

基于统一 selector 语义的元素操作，Android 与 Harmony 共用同一套入口。

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

基于 locator 的元素操作，既支持完整 XPath，也支持 service 层 shorthand。

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

`press KEY` 在所有 backend 上都接受整数 keycode。对命名键，当前统一文档集合是
`home`、`back`、`menu`、`enter`、`delete`、`recent`、`volume_up`、`volume_down`、`power`。
在当前连接的 Harmony 真机上，`home`、`back`、`recent`、`menu`、`enter`、`delete`、
`volume_up`、`volume_down`、`power` 都已经验证能真实派发到设备键事件。
其中 `power` 有明确的灭屏和唤醒恢复效果；`volume_up` / `volume_down` 也观察到了可见屏幕变化。
`enter` / `delete` 还进一步在真实的 Harmony 备忘录编辑器里做了端到端验证：先输入 `AB`，再按
`delete`，正文会可见地变成 `A`；再按 `enter` 并继续输入 `C`，正文会形成第二行（`A` 换行 `C`）。
`recent`、`menu` 虽然也派发成功，但在本次测试的 launcher / Settings 场景下，最终可见效果仍然依赖具体界面上下文。

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
# 对指定 platform/serial 目标执行点击
u2cli -s TARGET-001 click --text "Wi-Fi"

# JSON 输出
u2cli --json exists --text "Settings"

# 检查当前 platform/serial 目标的 daemon 状态
u2cli -s TARGET-001 daemon status

# 查看当前 platform/serial 目标的 daemon 日志
u2cli -s TARGET-001 daemon logs --lines 200
```

## JSON 输出示例

```bash
$ u2cli --json exists --text "Settings"
{"u2_code": "d(text='Settings').exists", "result": true}

# 通过 resource/element ID 获取文本
$ u2cli --json get-text --resource-id entry_title
{"u2_code": "d(resourceId='entry_title').get_text(timeout=3.0)", "result": "Welcome"}

# Android 上的 playback-info 输出
$ u2cli --json playback-info
{"u2_code": "d.shell('dumpsys media_session')", "result": {"source": "media_session", "package": "com.tencent.qqmusic", "state": {"code": 3, "name": "playing"}}}

# Harmony 上的 playback-info 输出
$ u2cli --json --platform harmony playback-info
{"u2_code": "d.shell(\"hidumper -s AVSessionService -a '-show_session_info'\")", "result": {"source": "avsession", "package": "com.huawei.hmsapp.music", "state": {"code": 2, "name": "paused"}}}
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
