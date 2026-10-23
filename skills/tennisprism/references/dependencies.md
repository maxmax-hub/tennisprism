# 依赖与分发说明

技能内的说明、程序与页面来自本 TennisAI 项目的实现，按随包 MIT LICENSE 发布。分发包不含用户媒体、分析报告、依赖虚拟环境、第三方仓库或模型权重。

运行时依赖通过各项目正规分发源安装，并受各自许可证约束；本技能的 MIT 许可不重新许可这些依赖或外部资料。基础依赖见 scripts/requirements.txt；姿态可选依赖见 scripts/requirements-pose.txt。媒体编码器由 imageio-ffmpeg 提供，版本、构建和分发条款应按该包核对。

USTA 资料只作带链接的练习原则参考，没有复制完整教材。MediaPipe 使用公开官方 API；权重从官方模型页面独立取得。公开训练来源和模型结果均不构成个人训练效果验证。

验证状态在项目根 STATUS.md，不将某一次私人视频的数据写入公开 Skill。Codex 当前环境已做运行验证；Claude Code/WorkBuddy 是标准格式适配目标，完整体验必须另行实测。
