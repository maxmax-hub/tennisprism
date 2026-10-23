# TennisPrism · 网球复盘教练

**看清这一拍，知道下一次怎么练。**

[skills.sh 技能页](https://skills.sh/maxmax-hub/tennisprism/tennisprism) · [v1.0.2 下载](https://github.com/maxmax-hub/tennisprism/releases/tag/v1.0.2) · [验证记录](STATUS.md)

免费、MIT 开源的 Agent Skill。把网球视频交给你正在使用的 AI Agent，一次得到有画面依据的水平判断、具体训练建议，以及带视频、逐帧回看和可选人体骨架的本地 H5 报告。

默认分析**离镜头最近的球员**。只有你主动指定时，才分析远端或其他人。

English: an open-source tennis video review Skill for your existing coding agent. Send a video in chat to receive timestamped evidence, a provisional level estimate, actionable practice and a local HTML report together. The current interface and coaching instructions are primarily Chinese.

## 你会得到什么

- **初步判断**：NTRP 尺度的视频估计、独立置信度、已具备的能力和最值得练的 1–3 项。
- **具体练法**：准备条件、步骤、建议时长、动作提示、难度调整，以及练完记录什么。
- **潜在问题也有行动建议**：分清直接观察与原因推测，提供对照试练，说明什么结果支持调整、什么结果应保留原动作。
- **H5 复盘报告**：对话发视频后默认生成，包含本地视频播放、证据跳转、逐帧与慢放；成功运行并复核姿态模型时，增加真实骨架与人物跟随放大。

## 安装

需要一个能**运行本地命令、读取文件、查看图片**的 Agent，以及 **Python 3.10+（推荐 3.12）**。使用下方安装命令还需要 Node.js 22.20+。首次运行时 Agent 会检查并安装 Python 依赖；骨架模型是可选项，初步分析不需要先下载模型。

### 推荐：通过 skills CLI

在终端执行，选择要安装到的 Agent：

```bash
npx skills add maxmax-hub/tennisprism --skill tennisprism -g
```

也可以明确指定宿主：

```bash
# Codex
npx skills add maxmax-hub/tennisprism --skill tennisprism -a codex -g

# Claude Code
npx skills add maxmax-hub/tennisprism --skill tennisprism -a claude-code -g
```

`-g` 表示跨项目使用；去掉它则安装到当前项目。安装完成后打开一个新对话，让 Agent 重新读取技能。

### 不使用 Node.js：手动安装

下载 [v1.0.2 Skill 安装包](https://github.com/maxmax-hub/tennisprism/releases/download/v1.0.2/tennisprism-1.0.2.zip)，解压后复制完整的 `tennisprism` 文件夹；也可以下载本仓库中的 `skills/tennisprism` 文件夹。不要只复制 `SKILL.md`：

| 宿主 | 个人 Skill 目录 |
|---|---|
| Codex | `~/.agents/skills/tennisprism/` |
| Claude Code | `~/.claude/skills/tennisprism/` |
| 千问办公桌面端 | `~/.qwenworkcn/skills/tennisprism/`（完整文件夹；网页链路待宿主实测） |
| 其他 Agent | 按其官方 Skill 导入方式安装整个文件夹 |

如果之前安装过同名 Skill，先核对现有版本，避免重复安装或覆盖自己的修改。Codex 安装目录参考[官方说明](https://learn.chatgpt.com/docs/build-skills)，Claude Code 参考[官方说明](https://code.claude.com/docs/en/skills)，千问办公参考[官方 Skill 说明](https://docs.qwenwork.cn/features/skills)。

## 用法一：直接给视频

把视频附在对话里，或提供 Agent 能读取的本地绝对路径，然后说：

```text
使用 tennisprism 分析这段网球视频，重点告诉我下一次怎么练。
```

Codex 可使用 `$tennisprism`；Claude Code 可使用 `/tennisprism`。例如：

```text
$tennisprism 分析 /绝对路径/我的网球视频.mp4，重点看反手高球和脚步。
```

Agent 会整理并实际查看视频画面，必要时补采动作过程，保存报告并自动生成 H5，**在同一次回复中给出简短结论、具体练习和可打开的报告链接**。不用再说“生成完整复盘页”，也不用先回答“分析哪一个人”。想看远端球员时主动说明即可。

只想看文字时加一句「只要文字，不生成网页」。骨架不可用时仍会生成视频与训练报告，并注明缺少骨架；不会让可选模型阻塞整份报告。H5 链接在本机服务运行期间有效，关闭后可让 Agent 重新打开。

## 用法二：让 Agent 打开视频选择页

不用先附视频，直接说：

```text
使用 tennisprism 分析我打的网球，打开视频选择页面。
```

1. Agent 启动本地页面并保持当前任务运行，等待你提交视频。
2. 页面显示「分析端已连接」后选择视频，等待预览就绪。默认近端球员；关注问题可以不填。
3. 在网页点击「开始分析」。Agent 自动接收任务、实际看图并提交报告，**结果直接显示在网页，不需要回聊天发送“继续分析”**。
4. 需要时在网页点击「生成完整视频复盘」。本机服务直接生成 H5，不再等待第二条聊天指令。已复核的姿态数据可显示骨架；没有则交付明确标注的无骨架版本。

请保持宿主 Agent 的这次任务运行。网页入口依赖宿主支持连续的短等待与工具执行，**不是可以脱离 Agent 独立推理的常驻网站**。连接断开会显示真实状态，保留视频与任务，停止接受新提交；恢复后可继续。宿主若强制结束任务，Skill 不能自行唤醒它，不能承诺所有平台都已支持自动接续。

完成这一段后，H5 按钮与结果仍可使用；分析新视频需要再次启用 Skill。关闭本机服务后，可让 Agent 使用同一任务目录重新打开结果。

### 从旧版本更新

重新从本仓库安装完整 Skill，保留你自己的本地定制与运行目录；不要只替换 `SKILL.md`。让 Agent 重新读取 1.0.2（可打开新对话），并重新启动本地服务。旧版正在运行的进程不会随文件更新而自动升级。1.0.2 将直接发视频改为结论与 H5 一次交付；1.0.1 的网页自动接收流程保留。已有视频不需要删除：网页流程可使用原来的 workspace 启动并等待，接收未完成的任务。若安装工具提示覆盖，请先确认没有需要保留的自定义修改。

## 第一次试用建议

先选 **20–60 秒、有几次连续击球**的短片，固定机位、能看清全身，MP4 或 MOV 均可。先确认近端球员、证据跳转和训练方法对你有用，再尝试更长视频。

长视频使用概览和短时序抽样，不等于看完每一拍。关注某段动作时可以直接指定时间，例如「重点看 02:15 前后这一拍」。上传上限默认 4 GB，媒体处理上限为 6 小时；这不是整场分析质量保证。

## 费用、隐私与边界

Skill 本身免费，不内置付费 AI 服务，不要求另填 API Key。**当前 Agent 的模型额度、订阅或 API 费用仍按宿主计费**。

视频在本机整理，选中的抽样画面由当前 Agent 所用模型分析；这不等于离线 AI。不会默认启动另一个 Codex/Claude CLI，也不提取账号令牌。源文件不被修改，报告和运行资料放在独立任务目录中。

NTRP 是主观视频估计，**不是官方评级**。置信度不是校准后的正确概率。目前没有教练标注集或个人训练效果验证；不会把推测当作观察，也不提供医学诊断。通用自动落点预测、球速旋转测量、自动挑选整场回合尚未集成。

H5 中的骨架必须来自真实模型并经 Agent 视觉复核。安装失败或结果不可靠时，仍可交付视频与训练报告，明确说明骨架缺失。120 秒以上的视频默认只在报告证据附近运行姿态。不要把人体检测覆盖率当成动作判断准确率。

## 兼容性与排错

已完成 macOS / Python 3.12 / Codex 的真实视频分析与浏览器交互验证。千问办公、Claude Code、WorkBuddy 等是标准 Skill 格式适配目标，**尚未完成各宿主的端到端验收**。普通只聊天、不能运行本地程序或看图片的界面无法完成这条工作流。

视频打不开、页面一直等待、没有骨架、远程环境的本地链接打不开：见[常见问题](docs/troubleshooting.md)。欢迎通过 Issues 反馈宿主、系统、执行到哪一步和脱敏错误信息；不必公开私人视频。

## 开发与验证

完整运行代码、页面和参考规范都在 `skills/tennisprism/`，不依赖其他私有项目。结构与验证方式见[开发说明](docs/development.md)。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/test_skill.py -q -p no:cacheprovider
python3 tools/package_skill.py
```

Windows 的虚拟环境解释器位于 `.venv\Scripts\python.exe`。公开仓库不包含用户媒体、个人分析报告、模型权重或虚拟环境。许可见 [MIT LICENSE](LICENSE)。

skills.sh 从公开 GitHub 仓库安装并按真实安装记录自动收录；目录更新可能晚于源码发布。[skills.sh 官方说明](https://skills.sh/docs/faq)
