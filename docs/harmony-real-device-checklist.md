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

## 8. XPath 子集能力验证

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

## 9. 负例验证

执行示例：

```bash
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-exists "//Button[@text='DefinitelyNotThere']"
u2cli --platform harmony --no-daemon -s <SERIAL> xpath-click "//Button[@text='DefinitelyNotThere']"
```

通过标准：

- [ ] `xpath-exists` 对不存在节点返回 `false`
- [ ] `xpath-click` 对不存在节点明确失败
- [ ] 不会误点击其他元素

## 10. 边界确认

本轮通过标准只应得出以下结论：

- [ ] Harmony 上 `dump-hierarchy` 已走 normalized hierarchy 输出
- [ ] Harmony 上 `xpath-*` 已重新开放并可用
- [ ] Harmony 上 shorthand 与 full XPath 都可用

本轮不应顺带得出以下结论：

- [ ] `open-notification` 已具备严格 panel 校验
- [ ] `open-quick-settings` 已具备严格 panel 校验
- [ ] `app-install` / `app-uninstall` 已开放

## 11. 建议记录模板

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

## 12. 推荐最小验收集

如果只做一轮最小真机回归，建议至少完成下面 6 项：

- [ ] `u2cli-smoke --platform harmony -s <SERIAL> --screenshot smoke.png`
- [ ] `dump-hierarchy`
- [ ] `dump-hierarchy --raw`
- [ ] `xpath-exists` 成功 1 例
- [ ] `xpath-click` 成功 1 例
- [ ] `xpath-set-text` 成功 1 例且肉眼可见变化