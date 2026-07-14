# Codex 完成任务后推送 Bark

这个仓库把 Codex 的任务完成通知推送到 iPhone/iPad 上的 Bark。它使用 Codex 用户级 `notify` 配置，不是 MCP、Skill、Hook 或定时任务。

安装后，这台电脑上的所有 Codex 主任务都会使用同一套规则：

- 主任务完成时推送一次，标题为 `codex叫你干活啦`。
- 通知内容包含项目目录和最终回复摘要。
- 使用 Codex 彩色图标和 Bark 的 `minuet` 轻提示音。
- 点击发送、等待输入、审批以及子 agent 完成时都不推送。
- Bark 失败不会让已经完成的 Codex 任务报错。
- Codex 原有的桌面通知器或其他通知脚本会被保留，且只调用一次。

## 先准备

1. 在手机上安装 Bark，并确认 Bark 自己的测试通知可以收到。
2. 准备 Bark 设备 URL，格式类似 `https://api.day.app/<YOUR_KEY>`。
3. 在电脑上安装 Git 和 Python 3.9 或更高版本。

真实 Bark URL 不写入仓库。首次安装时脚本会隐藏输入，并只保存到当前电脑的 `~/.codex/bark-notify.conf`。同一个 URL 可以在 Mac 和 Windows 上重复使用，但两台电脑必须分别安装一次。

## macOS 安装

打开“终端”，执行：

```bash
git clone https://github.com/Melon1234123/codexnotes.git
cd codexnotes
python3 --version
python3 install.py
```

出现 `Bark device URL (input hidden):` 后粘贴完整 Bark 设备 URL并回车。终端不会显示粘贴内容。安装完成后完全退出并重新打开 Codex。

如果仓库已经存在：

```bash
cd codexnotes
git pull --ff-only
python3 install.py
```

重复安装会复用本机私密配置，不会产生第二层通知。

## Windows 安装

打开 PowerShell，执行：

```powershell
git clone https://github.com/Melon1234123/codexnotes.git
Set-Location codexnotes
py -3 --version
py -3 install.py
```

出现 `Bark device URL (input hidden):` 后粘贴完整 Bark 设备 URL并回车。安装完成后完全退出并重新打开 Codex。

如果系统没有 `py` 命令，但 `python --version` 显示 3.9 或更高版本，把上面的 `py -3` 替换为 `python`：

```powershell
python install.py
```

## 验证

默认验证只读本地配置，不联网，也不会发测试通知。

macOS：

```bash
python3 verify.py
```

Windows：

```powershell
py -3 verify.py
```

成功时最后一行是：

```text
Offline verification passed. No Bark push was sent.
```

只有明确需要测试手机链路时才运行下面的命令。它会发送一次真实 Bark 通知。

macOS：

```bash
python3 verify.py --send-test
```

Windows：

```powershell
py -3 verify.py --send-test
```

## 静音和声音

`minuet` 只是 Bark 请求的提示音。iPhone/iPad 的静音模式、专注模式、通知摘要以及 Bark 的系统通知设置都可能让声音不响；通知本身通常仍会到达。这个项目没有开启 Bark 的“时效性通知”或“重要警告”，因此不会绕过系统静音。要听到轻提示音，需要在系统“设置 > 通知 > Bark”中允许声音，并关闭会拦截 Bark 的专注模式。

## 卸载

macOS：

```bash
python3 uninstall.py
```

Windows：

```powershell
py -3 uninstall.py
```

卸载会恢复安装前的顶层 `notify` 配置，并删除安装的脚本、私密配置和状态文件。安装时生成的 `config.toml.bak-bark-*` 备份会保留。如果安装后手动改过 `notify`，卸载器会停止并提示，不会覆盖新配置。

## 自定义 Codex 目录

脚本按以下顺序选择 Codex 目录：`--codex-home`、`CODEX_HOME`、`~/.codex`。例如：

```bash
python3 install.py --codex-home /path/to/codex-home
python3 verify.py --codex-home /path/to/codex-home
```

PowerShell 示例：

```powershell
py -3 install.py --codex-home "D:\Codex Data\.codex"
py -3 verify.py --codex-home "D:\Codex Data\.codex"
```

路径中的空格和 Windows 反斜杠会被安全写入 TOML。

## 故障排查

- 收不到通知：先在 Bark App 中发送测试，再运行 `verify.py`。检查手机网络和 Bark 通知权限。
- 验证通过但没有声音：检查静音模式、专注模式和 Bark 的“允许声音”；这不是电脑端安装失败。
- 图标没有立即更新：iOS/Bark 可能缓存远程图标，稍后再看或重启 Bark。
- 出现重复通知：再次运行 `install.py`，然后运行 `verify.py`；验证器要求通知链中只能有一个 Bark 命令。
- 子 agent 仍然通知：确认 `verify.py` 报告安装脚本与仓库版本一致，并完全重启 Codex。
- Bark 发送失败：查看 `~/.codex/bark-notify.log`。日志只记录错误类型，不记录 Bark URL。
- 卸载提示 `notify changed since installation`：先检查 `~/.codex/config.toml`，不要删除状态文件后强行覆盖。

## 安全规则

- 不要把真实 URL 写进 `config/bark-notify.conf.example`、README、issue、截图或提交记录。
- 不要提交 `~/.codex/bark-notify.conf` 或 `bark-notify-install-state.json`。
- 默认先运行离线验证；只有明确同意发送时才用 `--send-test`。
- 更换 Bark key 后，删除本机的 `~/.codex/bark-notify.conf`，再运行安装器并通过隐藏提示输入新 URL；不要把新 URL 写进仓库。

开发和 agent 复现约束见 [AGENTS.md](AGENTS.md)。
