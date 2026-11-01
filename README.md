# Codex macOS 中文缓存工具

通过本机 Chromium DevTools 协议，将 Codex 使用的 Statsig 缓存中 i18n 开关设为启用。基于 [Windows 版缓存工具](https://gitee.com/zhenglei410/codex-i18n-cache-seeder)的页面处理逻辑移植。

**当前状态：macOS 移植版尚未经实际运行验证。** 已在本机 Codex 26.1027.30824 的应用代码中确认存在相同的 Layer、开关和中文资源，不保证其他版本适用。

## 使用

需要 macOS、已安装的 Codex 桌面应用及 Python 3（无需第三方 Python 包）。先完全退出 Codex，包括菜单栏中的进程，然后从**外部终端**运行：

```bash
curl -fsSL https://raw.githubusercontent.com/zhenglei410/codex-i18n-cache-seeder-macos/main/codex_i18n_macos.py -o /tmp/codex_i18n_macos.py
python3 /tmp/codex_i18n_macos.py
```

建议先检查下载的脚本；固定版本时请把 `main` 替换为经核对的提交哈希。执行后完全退出 Codex，再正常启动。语言未自动变为中文时检查系统语言和 Codex 中的语言设置。

如果报告未找到缓存或目标 Layer，可以选择创建最小缓存：

```bash
python3 /tmp/codex_i18n_macos.py --bootstrap-missing
```

此模式只构造 i18n Layer 的评估结果，其他 Statsig 功能使用缺失时的默认行为，可能改变其他功能表现。已有缓存时优先保留原内容。`--app` 可指定应用路径，`--port` 可指定本机端口，`--timeout` 控制启动等待时间。

## 工作方式与限制

工具临时使用仅限本机的调试端口启动 Codex，借助页面中的 `localStorage` 修改 `statsig.cached.evaluations.*` 中的 `72216192` Layer；不修改应用包。若内存中有评估结果而本地无缓存，会从当前客户端生成缓存。执行完请完全退出调试启动的 Codex，关闭调试端口；不要在不可信的多用户环境中运行。

这是缓存，不是官方配置。服务端刷新可能覆盖结果；清理站点数据、更换账号或更新应用可能令其失效。此工具不承诺完整翻译或永久生效。请勿跨设备复制缓存。

源代码以 MIT 许可证开源。页面补丁源自同作者的 Windows 版项目。
