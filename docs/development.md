# 开发说明

## 目录与职责

| 路径 | 内容 |
|---|---|
| `skills/tennisprism/SKILL.md` | 宿主 Agent 的入口与工作流 |
| `skills/tennisprism/references/` | 等级、训练、报告结构、H5 和能力边界 |
| `skills/tennisprism/scripts/coach.py` | 检查环境、整理媒体、等待任务、保存报告、生成 H5 |
| `skills/tennisprism/scripts/pose.py` | 可选的真实姿态推理及复核标记 |
| `skills/tennisprism/scripts/tennis_runtime/` | 本地 API、媒体与证据处理、报告校验、存储 |
| `skills/tennisprism/assets/` | 视频选择页与 H5 报告模板 |
| `tests/test_skill.py` | 针对默认对象、来源保护、证据引用和状态流转的行为测试 |
| `tools/package_skill.py` | 只打包允许分发的 Skill 资源，生成 ZIP 和 SHA 清单 |

本地程序不内置远程 AI 调用。当前宿主 Agent 必须实际查看抽样图片并形成结论。报告 schema 3.0 绑定本次 evidence_id、真实帧 ID 与时间，区分 observed / potential / development 三类训练重点。格式校验不能证明教练结论正确。

## 网页任务连接

网页不直接调用模型。`coach.py wait` 通过本机 HTTP 长轮询接收一条真实任务，宿主在当前执行中连续等待；45 秒未继续等待则连接过期。接收任务后每约 60 秒执行 heartbeat，180 秒未续期在页面显示中断。浏览器轮询不续期，完成或取消后 disconnect。没有后台假在线循环，也没有结束聊天的通用唤醒器。

网页上传和新建分析都检查接收状态。补采样使用 `sample --run` 继承目标并关联新任务，页面跟随；证据身份不混用。H5 请求由服务后台线程实际构建，具备重复请求保护和可重试错误，不依赖 Agent 第二轮指令。状态过期不删除或作废真实证据，迟到但有效的报告仍可保存。

## 运行与验证

按 README 创建虚拟环境并安装开发依赖，运行 `tests/test_skill.py`。测试使用明确标注的合成接口数据，写入 `work/skill-tests/`，不依赖用户媒体、不调用 AI，也不自动清理历史资料。

修改媒体、分析或 H5 行为时，还需要用经授权的实际视频验证：准备证据、宿主看图、submit、H5、浏览器播放/证据跳转/逐帧。可选姿态要核对人物、预览哈希和时间戳。只运行合成测试不能宣称完整体验或分析准确率通过。

首次版本的本地验收覆盖 macOS / Python 3.12 / Codex；12 项行为测试通过，真实短片完成报告和 H5，复核了姿态、逐帧、慢放和跟随。其他宿主、系统、训练有效性与教练评级准确率未验收。私人验收资料不在公开仓库中。

GitHub Actions 的 `Validate Skill` 检查接口行为、页面脚本和分发包；`Verify public installation` 可手动执行一次真实的 skills CLI 安装，并逐文件比较、检查运行依赖。安装验证在临时 CI 环境执行，不替代宿主 Agent 的实际视频分析验收。CLI 使用默认匿名安装遥测；不会伪造安装量，也不保证 skills.sh 立即收录。验证结果以 Actions 实际记录和 STATUS.md 为准。

## 分发

使用 `python3 tools/package_skill.py`。它只包含 Skill 文件夹的允许文件，不含运行资料、模型或环境。已有版本 ZIP 不会覆盖；代码变化时更新 Skill metadata.version，并创建新版本。

基础 Python 依赖单独安装，受各自许可证约束。USTA 原始资料只保留链接和必要概括；MediaPipe 权重从官方来源另取，MIT 不对外部依赖和权重重新授权。不要向仓库提交个人视频、报告或密钥。
