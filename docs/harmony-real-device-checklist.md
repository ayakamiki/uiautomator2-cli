# Harmony 真机验证 Checklist

English version: [docs/harmony-real-device-checklist.en.md](docs/harmony-real-device-checklist.en.md)

用于验证 Harmony backend 当前已开放能力，重点覆盖本轮新增或变更的 `dump-hierarchy` 与 `xpath-*` 路径。

适用范围：

- Harmony 真机
- 本地源码运行的 `uiautomator2-cli`
- 验证 normalized hierarchy / XPath service 在真机上的实际行为

不在本次通过标准内的能力：

- `app-install`
- `app-uninstall`
- `open-notification` 的 panel 打开校验
- `open-quick-settings` 的 panel 打开校验

## 1. 前置条件

- [ ] `hdc list targets` 能看到目标设备 serial
- [ ] 当前环境已安装 Harmony 依赖：`pip install -e '.[harmony]'`
- [ ] 优先使用 `--no-daemon`，避免命中旧 daemon 缓存
- [ ] 如果不用 `--no-daemon`，先执行 `u2cli --platform harmony -s <SERIAL> daemon restart`

连接稳定性提示：

- [ ] 做定点排查或刚改完代码时，优先使用 `--no-daemon`，避免命中旧 backend / 旧 Python 代码缓存
- [ ] 如果进入高频真机调试，尤其是需要连续执行多条 Harmony 命令或反复操作系统 UI（如 `open-notification`、`open-quick-settings`）时，建议先执行一次 `u2cli --platform harmony -s <SERIAL> daemon restart`，再切回 daemon 模式，减少每条命令都重建 HDC / UITest 通道
- [ ] 对系统 UI 做完手势或点击后，不要立刻连发多条新命令；先给 HDC / UITest 通道一个短暂恢复窗口，再继续抓图、抓 hierarchy 或发下一条命令

### 模式选择说明

`--no-daemon` 和 daemon 模式的区别，不在于命令语义，而在于执行路径：

- `--no-daemon`：当前命令在当前 Python 进程里直接执行，更容易暴露 fresh bootstrap、`UITest` 会话重建、`hmdriver2` 初始化、`HDC fport` 等底层问题
- daemon：CLI 先把命令转发给后台常驻进程执行，后台会复用已有 backend，通常更接近日常高频使用场景

推荐使用规则：

- [ ] 做代码排查、刚改完 transport / backend / XPath / hierarchy 相关代码时，优先使用 `--no-daemon`，确认当前磁盘代码真实生效
- [ ] 做高频真机操作、长链路回归、反复点系统 UI 或连续跑多条命令时，优先使用 daemon 模式，减少每条命令都重建 Harmony `UITest` 会话的开销
- [ ] 如果准备使用 daemon 模式且刚改过代码，先执行一次 `u2cli --platform harmony -s <SERIAL> daemon restart`，避免后台仍持有旧代码或脏 backend 状态
- [ ] 如果怀疑问题发生在 transport / bootstrap 层，而不是业务命令本身，回到 `--no-daemon` 复现，信息量通常更高

当前实机证据：

- [ ] `--no-daemon` 模式下，“通知栏媒体控制 + `playback-info`”链路已通过 `10/10` 轮真机稳定性压测
- [ ] daemon 模式下，同一条链路在执行 `daemon restart` 后也已通过 `10/10` 轮真机稳定性压测

建议先记录：

- [ ] 设备型号
- [ ] HarmonyOS 版本
- [ ] 目标 app / 页面名称
- [ ] 设备 serial

## 2. 基础连通性检查

执行：

```bash
hdc list targets
u2cli --platform harmony --no-daemon -s <SERIAL> device-info
u2cli-smoke --platform harmony -s <SERIAL> --screenshot smoke.png
```

通过标准：

- [ ] `device-info` 成功返回
- [ ] `u2cli-smoke` 成功返回
- [ ] 成功生成截图文件 `smoke.png`

## 3. `dump-hierarchy` 验证

选择一个当前屏幕上有明确文本、按钮或输入框的页面。

执行：

```bash
u2cli --platform harmony --no-daemon -s <SERIAL> dump-hierarchy
u2cli --platform harmony --no-daemon -s <SERIAL> dump-hierarchy --raw
```

通过标准：

- [ ] 默认输出是树状文本，而不是原始 XML
- [ ] `--raw` 输出是 backend 原始 XML
- [ ] 默认输出与 `--raw` 输出中的关键节点能够相互对应
- [ ] 默认输出中能看出当前页面的主要控件层次

建议留档：

- [ ] 保存默认输出
- [ ] 保存 `--raw` 输出
- [ ] 如有必要，保存同屏截图用于对照

## 4. `xpath-exists` 验证

先从 `dump-hierarchy` 中找一个稳定元素。优先使用：

- 可见文本
- `content-desc`
- `resource-id`

执行示例：

```bash
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-exists "%Login%"
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-exists "//Button[contains(@content-desc, 'Primary')]"
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-exists "//*[@resource-id='entry.login.primary']"
```

通过标准：

- [ ] shorthand 定位至少成功 1 例
- [ ] full XPath 定位至少成功 1 例
- [ ] 不再出现 Harmony 上 `xpath-*` 被 gate 的错误

## 5. `xpath-get-text` 验证

执行示例：

```bash
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-get-text "%Login%"
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-get-text "//Button[contains(@content-desc, 'Primary')]"
```

通过标准：

- [ ] 返回文本与屏幕上实际显示一致
- [ ] shorthand 与 full XPath 各至少成功 1 例

## 6. `xpath-click` 验证

选择一个点击后有明确视觉反馈的控件，例如：

- 按钮点击后页面跳转
- 展开面板
- 弹出对话框

执行示例：

```bash
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-click "%Login%"
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-click "//Button[@text='Login'][2]"
```

通过标准：

- [ ] 点击目标正确
- [ ] 页面发生预期变化
- [ ] 不存在“命令成功但没有任何 UI 变化”的假阳性

建议留档：

- [ ] 点击前截图
- [ ] 点击后截图
- [ ] 如使用位置索引 `[2]`，记录同类元素数量与目标位置

## 7. `xpath-set-text` 验证

选择一个可肉眼确认变化的输入框页面，例如：

- 备忘录编辑器
- 登录页输入框
- 搜索框

执行流程：

```bash
u2cli --platform harmony --no-daemon -s <SERIAL> dump-hierarchy
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-set-text "<INPUT_XPATH>" "copilot-xpath-123"
u2cli --platform harmony --no-daemon -s <SERIAL> screenshot after-set-text.png
```

通过标准：

- [ ] 输入框内容肉眼可见变成 `copilot-xpath-123`
- [ ] 命令执行后界面没有跑偏到错误控件
- [ ] 如再次 `dump-hierarchy`，能看到对应文本变化

如果页面是 Harmony 通用 `TextInput`，建议追加下面这组“替换语义”回归，避免只验证“首次输入成功”，却漏掉“二次覆盖仍会残留旧文本”的问题。

建议页面：

- Kugou / 其他音乐 App 搜索框
- 登录页单行输入框
- 任意非 `RichEditor` 的 `TextInput`

执行流程：

```bash
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-get-text "//TextInput"
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-set-text "//TextInput" "TEXTINPUT_REPLACED_OK"
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-get-text "//TextInput"
u2cli --platform harmony --no-daemon -s <SERIAL> screenshot textinput-replaced-ok.png
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-set-text "//TextInput" "ZX9"
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-get-text "//TextInput"
u2cli --platform harmony --no-daemon -s <SERIAL> screenshot textinput-replaced-zx9.png
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-set-text "//TextInput" ""
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-get-text "//TextInput"
u2cli --platform harmony --no-daemon -s <SERIAL> screenshot textinput-restored-empty.png
```

附加通过标准：

- [ ] 首次写入后，输入框肉眼可见变成 `TEXTINPUT_REPLACED_OK`
- [ ] 第二次写入 `ZX9` 后，旧文本被完整替换，而不是残留成拼接字符串
- [ ] 写入空字符串后，输入框恢复为空，而不是继续保留旧值
- [ ] 三次 `xpath-get-text` 返回值分别与页面可见结果一致

建议留档：

- [ ] `textinput-replaced-ok.png`
- [ ] `textinput-replaced-zx9.png`
- [ ] `textinput-restored-empty.png`

## 8. `press delete / enter` 可见验证

该用例用于验证 Harmony 上命名键 `delete` / `enter` 不只是成功派发，而且会在真实输入场景里产生可见结果。

建议页面：

- Harmony 备忘录编辑器
- 任意纯文本、多行输入框

前提：

- [ ] 输入焦点已明确落在正文输入框内
- [ ] 当前页面不会把 `enter` 拦截成“发送”或“提交”动作

执行流程：

```bash
u2cli --platform harmony --no-daemon -s <SERIAL> send-keys --no-clear "AB"
u2cli --platform harmony --no-daemon -s <SERIAL> screenshot before-delete.png
u2cli --platform harmony --no-daemon -s <SERIAL> press delete
u2cli --platform harmony --no-daemon -s <SERIAL> screenshot after-delete.png
u2cli --platform harmony --no-daemon -s <SERIAL> press enter
u2cli --platform harmony --no-daemon -s <SERIAL> send-keys --no-clear "C"
u2cli --platform harmony --no-daemon -s <SERIAL> screenshot after-enter.png
```

通过标准：

- [ ] 输入 `AB` 后，正文里肉眼可见 `AB`
- [ ] 执行 `press delete` 后，正文可见地从 `AB` 变成 `A`
- [ ] 执行 `press enter` 并继续输入 `C` 后，正文变成两行：第一行 `A`，第二行 `C`
- [ ] 整个过程不依赖系统 toast 或日志推断，单看屏幕即可确认结果

建议留档：

- [ ] `before-delete.png`
- [ ] `after-delete.png`
- [ ] `after-enter.png`
- [ ] 如输入框支持层次抓取，可附上前后 `dump-hierarchy` 输出

失败排查提示：

- 如果 `enter` 触发了发送/搜索/提交，换成一个纯正文输入框再测
- 如果 `delete` 没有可见变化，先确认焦点确实在文本末尾且输入法没有接管按键行为

## 9. XPath 子集能力验证

建议至少覆盖以下表达式各 1 例：

- [ ] 精确文本：`Login`
- [ ] 文本包含：`%Login%`
- [ ] 文本前缀：`Welcome%`
- [ ] 文本后缀：`%button`
- [ ] 正则：`^Login.*`
- [ ] 资源 ID shorthand：`@entry_button`
- [ ] `contains(...)` 谓词：`//Button[contains(@content-desc, 'Primary')]`
- [ ] 位置索引：`//Button[@text='Login'][2]`

通过标准：

- [ ] shorthand 至少覆盖 3 种不同形式
- [ ] full XPath 至少覆盖谓词与位置索引两类能力

## 10. 负例验证

执行示例：

```bash
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-exists "//Button[@text='DefinitelyNotThere']"
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-click "//Button[@text='DefinitelyNotThere']"
```

通过标准：

- [ ] `xpath-exists` 对不存在节点返回 `false`
- [ ] `xpath-click` 对不存在节点明确失败
- [ ] 不会误点击其他元素

## 11. 边界确认

本轮通过标准只应得出以下结论：

- [ ] Harmony 上 `dump-hierarchy` 已走 normalized hierarchy 输出
- [ ] Harmony 上 `xpath-*` 已重新开放并可用
- [ ] Harmony 上 shorthand 与 full XPath 都可用

本轮不应顺带得出以下结论：

- [ ] `open-notification` 已具备严格 panel 校验
- [ ] `open-quick-settings` 已具备严格 panel 校验
- [ ] `app-install` / `app-uninstall` 已开放

## 12. 建议记录模板

每个用例建议至少记录以下字段：

- [ ] 测试日期
- [ ] 测试人
- [ ] 设备型号 / 系统版本
- [ ] 页面名称
- [ ] 命令
- [ ] XPath 表达式
- [ ] 实际结果
- [ ] 是否通过
- [ ] 截图路径
- [ ] hierarchy 输出路径

可直接复制下面模板：

```text
日期：
测试人：
设备：
系统版本：
页面：
命令：
XPath：
结果：
是否通过：
截图：
Hierarchy 输出：
备注：
```

## 13. 推荐最小验收集

如果只做一轮最小真机回归，建议至少完成下面 6 项：

- [ ] `u2cli-smoke --platform harmony -s <SERIAL> --screenshot smoke.png`
- [ ] `dump-hierarchy`
- [ ] `dump-hierarchy --raw`
- [ ] `xpath-exists` 成功 1 例
- [ ] `xpath-click` 成功 1 例
- [ ] `xpath-set-text` 成功 1 例且肉眼可见变化

如果这轮还要覆盖 Harmony 按键 alias 的可见行为，再额外完成：

- [ ] `press delete` 让正文从 `AB` 可见地变成 `A`
- [ ] `press enter` 后继续输入，正文可见地形成第二行

如果这轮还要覆盖 Harmony 通用输入框的真实“替换”能力，再额外完成：

- [ ] 对 `//TextInput` 连续执行两次 `xpath-set-text`，第二次能完整覆盖第一次内容
- [ ] 对 `//TextInput` 执行 `xpath-set-text ''` 后，输入框可见恢复为空

## 14. 已验证的连续重建会话稳定性证据

下面这组结果是已经在真机上跑过的实测证据，用来说明“连续重建 Harmony `UITest` 会话”在当前代码状态下已经有一组通过样本。它不是永久免测结论；当 transport、`hmdriver2` 版本、HarmonyOS 版本或设备型号变化后，仍应重新执行。

已验证样本 A：

- 日期：`2026-05-30`
- 设备 serial：`4VF0225708007870`
- 执行模式：`--platform harmony --no-daemon`
- 压测轮次：`10` 轮

每轮步骤：

- `open-notification`
- 点击通知栏媒体卡片的播放 / 暂停按钮一次
- 再点击同一按钮一次
- 上划收起通知栏
- 追加执行 `playback-info`

样本 A 实测结果：

- [x] `10/10` 轮全部通过
- [x] 每轮都能完成“下拉 -> 播放/暂停 -> 暂停/播放 -> 收起 -> playback-info”整条链路
- [x] 日志中未命中以下异常关键字：`No devices found`、`HDC forward port error`、`communication channel is being established`、`JSONDecodeError`、`did not reappear via hdc`、`ruler is not exist`

已验证样本 B：

- 日期：`2026-05-30`
- 设备 serial：`4VF0225708007870`
- 执行模式：`--platform harmony`（daemon 模式，压测前已执行 `daemon restart`）
- 压测轮次：`10` 轮

每轮步骤：

- `open-notification`
- 点击通知栏媒体卡片的播放 / 暂停按钮一次
- 再点击同一按钮一次
- 上划收起通知栏
- 追加执行 `playback-info`

样本 B 实测结果：

- [x] `10/10` 轮全部通过
- [x] 每轮都能完成“下拉 -> 播放/暂停 -> 暂停/播放 -> 收起 -> playback-info”整条链路
- [x] `daemon restart` 返回成功
- [x] 日志中未命中以下异常关键字：`No devices found`、`HDC forward port error`、`communication channel is being established`、`JSONDecodeError`、`did not reappear via hdc`、`ruler is not exist`

结论边界：

- 这两组证据支持“当前代码版本下，通知栏媒体控制 + 后续 `playback-info` 的连续重建会话链路在 `--no-daemon` 和 daemon 两种模式下都已通过 10 轮真机稳定性压测”
- 它不自动代表其他系统 UI 序列、其他命令组合、其他设备型号或其他 HarmonyOS 版本都已同等通过