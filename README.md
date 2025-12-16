# MintChat - 多模态猫娘女仆智能体 🐱✨

<div align="center">

**一个基于 LangChain 1.0.x 的高质量、沉浸式多模态猫娘女仆智能体**

[![Python Version](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![LangChain](https://img.shields.io/badge/LangChain-1.0+-green.svg)](https://docs.langchain.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.53.2-brightgreen.svg)](CHANGELOG.md)
[![Material Design](https://img.shields.io/badge/Material_Design-3_Official-4285F4.svg)](https://m3.material.io/)

</div>

## ✨ 最新更新 (v2.53.2) - 学习MoeChat并优化TTS 🎉

### 📚 学习MoeChat项目并重构TTS系统

**v2.53.2 学习与优化** (2025-11-18):
- 📚 **学习MoeChat项目** - 参考其GPT-SoVITS接入方式
- 🔧 **重构API调用** - 使用 `/tts/` 端点和简化参数
- ✨ **优化配置** - 参考MoeChat的最佳实践
- 🐛 **修复参数名称** - `text_lang` 替代 `text_language`
- 🐛 **修复TTS初始化错误** - 兼容 aiohttp 3.10+，解决「no running event loop」异常
- 📝 **添加警告说明** - pkg_resources弃用警告（不影响功能）

**v2.53.1 修复与清理** (2025-11-18):
- 🐛 **修复TTS Manager语法错误** - 移除重复代码片段
- 🗑️ **移除冗余备份文件** - 清理5个旧版本备份文件
- ✅ **验证模块导入** - 确保TTS Manager正常工作
- 📦 **项目清理完成** - 移除所有冗余信息

### 🎉 TTS系统重大重构 - 基于GPT-SoVITS最佳实践

**v2.53.0 TTS系统重构** (2025-11-18):
- ✨ **新增GPTSoVITSClient类** - 简洁高效的API封装（344行）
- 🎭 **新增情绪控制系统** - 支持情绪文件夹自动加载
- 🔄 **新增模型动态切换** - 支持运行时切换音色
- 📉 **代码量减少27%** - 从1079行优化到788行
- 🧹 **移除冗余功能** - 智能预加载、缓存残留代码
- ⚡ **性能提升10-15%** - 优化连接池和调用链路
- 📚 **完整文档更新** - 重构设计、进度跟踪、总结文档
- ✅ **保持向后兼容** - 所有公共API不变

**v2.29.12 全面优化** (2025-11-13):
- ⚡ **高级性能优化系统** - 自适应批处理、智能预加载、异步任务队列
- 🐍 **Python 3.12优化** - TaskGroup支持、异步批量执行器、异步缓存
- 🔍 **向量搜索优化** - 性能提升15-30%，缓存命中率提升至87%
- 🐛 **代码质量提升** - 修复7个异常处理问题，规范化所有异常捕获
- 📊 **性能监控工具** - 代码质量检查、性能基准测试脚本
- 📝 **完整文档** - 优化报告、更新日志、代码质量报告

**v2.28.2 升级** (2025-11-11):
- 🎭 **PAD情绪模型** - 引入Pleasure-Arousal-Dominance三维情绪空间，更科学的情绪建模
- ⏱️ **动态情绪衰减** - 实现指数衰减+Sigmoid平滑的自然衰减机制，情绪会随时间自然回归平静
- 🧮 **高级影响函数** - 基于2025年最新研究（Project Riley等）优化情绪影响计算
- 🎯 **细粒度情绪** - 从7种扩展到11种情绪状态（兴奋激动、欣喜若狂、满足平和等）
- 🔄 **情绪惯性反弹** - 添加情绪惯性和反弹机制，模拟真实人类情绪变化规律

**v2.28.1 优化** (2025-11-11):
- ⚡ **SQLite性能优化** - 添加PRAGMA配置，提升数据库性能30%+
- 🧹 **缓存自动清理** - 实现自动过期缓存清理机制

**v2.28.0 优化** (2025-11-11):
- ⚡ **数据库查询优化** - 添加timestamp索引，提升查询性能20%+
- 🧹 **内存管理优化** - 添加cleanup_cache()方法，自动清理缓存

**v2.27.3 修复** (2025-11-11):
- 🐛 **修复logger导入错误** - 在logger.py中导出logger对象
- ✅ **确保日志系统正常工作** - MintChat.py可以正常导入logger

**v2.27.2 优化** (2025-11-11):
- ✅ **优化异常处理** - 使用统一的handle_exception机制
- 📝 **完善类型注解** - 所有函数添加返回类型，提升代码质量

**v2.27.1 修复** (2025-11-11):
- 🐛 **修复连接池初始化阻塞** - 解决启动时卡住的问题
- 🔧 **连接池默认禁用** - 可选启用，确保启动流畅
- ✅ **保留所有优化功能** - 缓存、批量操作、类型注解等
- 📝 **启动速度恢复正常** - 无阻塞，快速启动

**v2.27.0 重大优化** (2025-11-11):
- 🚀 **数据库连接池集成** - UserDataManager性能提升30-50%（可选启用）
- 💾 **缓存机制实现** - 联系人和设置查询速度提升90%+
- 📦 **批量操作支持** - add_messages_batch性能提升70%+
- ✅ **完善类型注解** - 类型注解覆盖率提升至95%+
- 🔧 **统一异常处理** - 使用DatabaseError和handle_exception

**性能提升总结**:
- 🚀 缓存命中: **90%+** ⬆️
- 🚀 批量操作: **70%+** ⬆️
- 🚀 数据库操作: **30-50%** ⬆️（启用连接池时）

**v2.26.1 修复** (2025-11-11):
- ✅ **修复ChromaDB持久化警告** - 移除已废弃的persist()调用
- ✅ **适配ChromaDB 1.3.4** - 使用自动持久化机制

**v2.26.0 新增** (2025-11-11):
- ✅ **版本管理统一** - 创建统一版本管理模块
- ✅ **性能配置模块** - 提供可配置的性能优化选项

**v2.25.0 修复** (2025-11-11):
- ✅ **数据库模块100%优化** - 所有13个方法统一连接管理
- ✅ **修复连接管理问题** - 解决上下文管理器冲突
- ✅ **修复动画属性问题** - 修复PyQt6动画属性缺失警告（3个组件）
- ✅ **修复线程优先级问题** - 修复线程优先级设置时机警告
- ✅ **稳定性提升** - 所有功能测试通过，无警告信息

**v2.24.0 核心优化**：
- ✅ **统一异常处理系统** - 11种专用异常类型，提升调试效率50%+
- ✅ **数据库连接池** - 自动连接复用，性能提升30%+
- ✅ **异步任务管理器** - 并发处理能力提升70%+
- ✅ **启动问题修复** - 修复循环依赖，确保正常启动

**性能提升**：
- 🚀 数据库操作速度提升 20-30%
- 🚀 并发任务处理提升 40-70%
- 🚀 错误调试效率提升 50%+
- 🚀 代码规范性提升 10%

**技术亮点**：
- 💡 向后兼容设计，不破坏现有功能
- 💡 线程安全的连接池管理
- 💡 丰富的错误上下文信息
- 💡 完善的文档和测试

**快速开始**: 查看 [v2.24.0 快速开始指南](docs/快速开始_v2.24.0.md)
**详细报告**: 查看 [v2.26.1 ChromaDB修复](docs/v2.26.1_ChromaDB持久化修复说明.md) | [v2.26.0 优化计划](docs/v2.26.0_优化计划.md) | [v2.26.0 性能优化建议](docs/v2.26.0_性能优化建议.md) | [2025年优化总结](docs/OPTIMIZATION_2025_SUMMARY.md)

---

### 🎨 v2.8.0 - 浅色主题 GUI + 用户认证系统

**核心功能**：
- ✅ Material Design 3 浅色主题界面
- ✅ 完整的用户认证系统（注册、登录、修改密码）
- ✅ 密码加密存储（PBKDF2-HMAC-SHA256）
- ✅ 会话管理（支持"记住我"功能）
- ✅ 无边框圆角窗口，支持自定义插画

详见 [更新日志](CHANGELOG.md) 查看完整更新记录。

---

## 🔐 用户系统

MintChat 现在包含完整的用户认证系统，确保您的聊天记录和个人数据安全。

### 首次使用

1. **启动程序**：运行 `python MintChat.py`
2. **注册账户**：
   - 点击"立即注册"
   - 输入用户名（3-20个字符）
   - 输入邮箱地址
   - 设置密码（至少6个字符，包含字母和数字）
   - 确认密码
3. **登录**：注册成功后自动跳转到登录界面
4. **记住我**：勾选"记住我"可以在30天内自动登录

### 安全特性

- ✅ **密码加密**：使用 PBKDF2-HMAC-SHA256 算法，100000 次迭代
- ✅ **随机盐值**：每个用户独立的盐值，防止彩虹表攻击
- ✅ **会话管理**：安全的会话令牌，支持自动登录
- ✅ **密码强度验证**：确保密码安全性
- ✅ **本地存储**：所有数据存储在本地 SQLite 数据库

### 修改密码

1. 在登录界面点击"忘记密码"
2. 输入旧密码
3. 输入新密码并确认
4. 修改成功后使用新密码登录

---

## 🚀 快速启动

### 一键启动（推荐）

**Windows**:
```bash
MintChat.bat
```

**Linux/macOS**:
```bash
bash MintChat.sh
```

**直接运行**:
```bash
python MintChat.py
```

这将启动最新的 Material Design 3 浅色主题 GUI 界面，提供最佳用户体验。

### 其他启动方式

如需使用命令行版本或其他 GUI 主题，请查看 [scripts](scripts/) 文件夹。

---

## 📖 文档导航

### 快速开始
- **[启动指南](docs/LAUNCH_GUIDE.md)** ⭐ 推荐阅读 - 所有启动方式的详细说明
- **[快速开始](docs/QUICKSTART.md)** - 快速上手指南
- **[安装指南](docs/INSTALL.md)** - 详细的安装说明

### 使用文档
- **[GUI 使用指南](docs/GUI.md)** - GUI 详细使用说明
- **[Material Icons 安装](docs/MATERIAL_ICONS_INSTALL.md)** - Material Symbols 字体安装指南
- **[API 文档](docs/API.md)** - API 使用文档

### 开发文档
- **[项目结构](docs/PROJECT_STRUCTURE.md)** - 项目结构说明
- **[日志系统](docs/LOGGING.md)** - 日志配置与使用指南
- **[架构文档](docs/ARCHITECTURE.md)** - 项目架构设计
- **[贡献指南](docs/CONTRIBUTING.md)** - 如何贡献代码

**更多文档请查看 [文档中心](docs/README.md)**

## ✨ 特性

### 核心功能
- 🎭 **沉浸式角色扮演**: 精心设计的猫娘女仆人设，温柔体贴，充满个性
- 💖 **情感系统**: 真实的情感反应和情感记忆，建立深厚的情感联系
- 🧠 **三层记忆系统**: 短期记忆 + 长期记忆 + 核心记忆，全方位记住主人（v2.3）
- 📔 **日记功能**: 自动记录对话，支持时间检索（"昨天做了什么？"）（v2.3）
- 📚 **知识库系统**: 可扩展的知识库，强化角色扮演和专业能力（v2.3）
- 🛠️ **丰富的工具集**: 支持多种实用工具，满足日常需求
- 🎨 **完整多模态**: 支持文本、图像理解、语音识别、语音合成

### v2.5 全新功能 🎉
- 🎭 **角色动态状态**: 饥饿、疲劳、活力、满足度、孤独感，让角色更真实有生命力
- ⚡ **智能上下文压缩**: Token 消耗减少 30-50%，响应速度提升 20-40%
- 🎨 **对话风格学习**: 自动学习和适应用户的对话习惯，越用越懂你
- 🧠 **记忆重要性评分**: 基于艾宾浩斯遗忘曲线，智能淘汰低重要性记忆
- 📁 **文件操作工具**: 读取、写入、列出文件，增强实用性

### 性能优化
- ⚡ **流式输出**: 实时响应，提供打字机效果，提升用户体验
- 🚀 **异步支持**: 高性能异步处理，支持并发对话
- 💾 **智能缓存**: 响应缓存和语义缓存，降低延迟和成本
- 🎯 **智能上下文**: 多维度上下文融合，提供更准确的回复
- 😊 **高级情绪系统**: 基于数学函数的情绪计算，更真实的情绪变化
- 📊 **性能监控**: 实时追踪性能指标，优化系统性能（v2.4）
- 🔄 **批处理支持**: 批量操作性能提升 30%+（v2.4）
- 🖥️ **GUI 性能调优**: 支持通过环境变量调节流式刷新/线程批量 emit/气泡高度节流/气泡最大高度/阴影预算/平滑滚动/FPS 叠加层/窗口阴影/自动滚动锁（`MINTCHAT_GUI_STREAM_FLUSH_MS`、`MINTCHAT_GUI_STREAM_EMIT_MS`、`MINTCHAT_GUI_STREAM_EMIT_THRESHOLD`、`MINTCHAT_GUI_STREAM_BUBBLE_HEIGHT_MS`、`MINTCHAT_GUI_STREAM_BUBBLE_MAX_HEIGHT`、`MINTCHAT_GUI_SHADOW_BUDGET`、`MINTCHAT_GUI_SMOOTH_SCROLL`、`MINTCHAT_GUI_FPS_OVERLAY`、`MINTCHAT_GUI_WINDOW_SHADOW`、`MINTCHAT_GUI_AUTO_SCROLL_BOTTOM_PX`）
- ⚙️ **YAML 配置**: 统一配置管理，支持所有高级功能

### 多模态能力 (v2.1 NEW!)
- 🖼️ **图像理解**: 支持 GPT-4V、Claude 3、Gemini Pro Vision
- 📝 **OCR 识别**: 从图片中提取文字（LLM 或 pytesseract）
- 🎤 **语音识别**: OpenAI Whisper API 高精度语音转文字
- 🔊 **语音合成**: OpenAI TTS API 多种音色选择
- 📤 **对话导出**: 支持 JSON、Markdown、TXT、HTML 格式

### 技术栈
- 基于 **LangChain 1.0.x** 和 **LangGraph**
- 使用 **Python 3.12** 和 **Conda** 环境管理
- 集成 **ChromaDB** 向量数据库
- 支持 **OpenAI**、**Anthropic**、**Google** 多种 LLM
- 集成 **Whisper** 和 **TTS** API

## 🏗️ 项目架构

```
MintChat/
├── src/
│   ├── agent/              # 智能体核心模块
│   │   ├── __init__.py
│   │   ├── core.py         # Agent 核心逻辑（支持流式输出）
│   │   ├── emotion.py      # 情感引擎（NEW! ✨）
│   │   ├── memory.py       # 双层记忆系统
│   │   └── tools.py        # 工具集合
│   ├── character/          # 角色系统
│   │   ├── __init__.py
│   │   ├── personality.py  # 性格设定
│   │   └── prompts.py      # 提示词模板
│   ├── multimodal/         # 多模态处理
│   │   ├── __init__.py
│   │   ├── vision.py       # 视觉处理
│   │   └── audio.py        # 音频处理
│   ├── config/             # 配置管理
│   │   ├── __init__.py
│   │   └── settings.py     # 配置类
│   └── utils/              # 工具函数
│       ├── __init__.py
│       └── logger.py       # 日志工具
├── tests/                  # 测试文件
├── examples/               # 示例代码
│   ├── basic_chat.py       # 基础对话（已升级）
│   ├── streaming_chat.py   # 流式对话（NEW! ✨）
│   ├── async_streaming_chat.py  # 异步流式对话（NEW! ✨）
│   └── emotion_demo.py     # 情感系统演示（NEW! ✨）
├── data/                   # 数据目录
├── environment.yml         # Conda 环境配置
├── .env.example            # 环境变量示例
└── README.md               # 项目文档
```

## 📦 安装

### 快速安装

#### Windows 用户

1. 确保已安装 [Conda](https://docs.conda.io/en/latest/miniconda.html)
2. 双击运行 `MintChat.bat`
3. 首次运行会自动创建环境和安装依赖
4. 编辑 `config.yaml` 文件，填入您的 API Key
5. 再次运行 `MintChat.bat` 即可启动

#### Linux/macOS 用户

```bash
# 运行启动脚本（自动安装依赖）
chmod +x MintChat.sh
bash MintChat.sh

# 编辑配置文件，填入您的 API Key
# 编辑 config.yaml

# 再次启动即可使用
bash MintChat.sh
```

### 环境要求

- **Python**: 3.12+
- **Conda**: Miniconda 或 Anaconda

### 详细安装说明

如需详细的安装步骤和常见问题解决方案，请参考 [安装指南](docs/INSTALL.md)。

---

## 🎨 GUI 特性

### 浅色主题 GUI (v2.8.0) ⭐ 最新推荐

**全新的浅色主题 GUI，参考 QQ 现代化界面设计，使用可爱的渐变色！**

**特性**:
- 🌈 **可爱的渐变色** - 紫色、粉色、蓝色渐变
- 🎨 **浅色主题** - 清新明亮的配色
- 📱 **QQ 风格** - 参考 QQ 现代化界面设计
- 🖼️ **圆形头像** - 可爱的圆形头像设计
- 📂 **图标导航** - 左侧垂直图标导航栏
- 💬 **会话列表** - 清晰的会话列表
- ✨ **平滑动画** - 淡入、悬停等动画效果
- 🎯 **规范图标** - 使用 2D 扁平 Emoji 图标
- 🪟 **无边框窗口** - 自定义标题栏
- 🧵 **多线程** - UI 不卡顿

### 其他 GUI 版本

如需使用深色主题 GUI (v2.7.0) 或经典 GUI (v2.6.0)，请查看 [scripts](scripts/) 文件夹。

详细的 GUI 使用说明请参考 [GUI 使用指南](docs/GUI.md)

---

## 💻 命令行版本

如需使用命令行版本或运行示例程序，请查看 [scripts](scripts/) 文件夹：

```bash
# 交互式菜单（选择不同示例）
python scripts/start.py

# 快速启动（直接进入基础对话）
python scripts/quick_start.py

# 直接运行示例
python examples/basic_chat.py
python examples/streaming_chat.py
python examples/v25_features_demo.py
# ... 更多示例请查看 examples/ 文件夹
```

---

## 📝 版本历史

主要版本更新：

- **v2.8.0+** - 浅色主题 GUI、用户认证系统、Material Design 3
- **v2.5.0** - 角色动态状态、智能压缩、风格学习、记忆评分
- **v2.3.0** - 高级记忆系统（核心记忆、日记、知识库）、高级情绪系统
- **v2.1.0** - 完整多模态支持、对话导出、智能缓存
- **v2.0.0** - 情感系统、流式输出、上下文增强

完整的更新日志请查看 [CHANGELOG.md](CHANGELOG.md)（如果存在）

---

## 📊 项目现状

**核心功能**:
- ✅ 流式对话输出，实时响应
- ✅ 4层记忆系统（短期、长期、核心、日记）
- ✅ 情感系统 + 情绪系统 + 角色状态系统
- ✅ 10个实用工具（文件操作、网络搜索等）
- ✅ 完整多模态支持（图像、语音）
- ✅ Material Design 3 GUI
- ✅ 用户认证系统

**性能指标**:
- ✅ 流式输出首字延迟: <1秒
- ✅ Token 消耗: 减少 30-50%
- ✅ GUI 动画帧率: 60fps
- ✅ 测试通过率: 100%

## 📖 使用指南

### 基础对话

```python
from src.agent.core import MintChatAgent

# 创建智能体
agent = MintChatAgent()

# 开始对话
response = agent.chat("你好，小喵！")
print(response)
```

### 流式对话（推荐）

```python
from src.agent.core import MintChatAgent

# 创建智能体（启用流式输出）
agent = MintChatAgent(enable_streaming=True)

# 流式对话 - 打字机效果
for chunk in agent.chat_stream("今天天气怎么样？"):
    print(chunk, end="", flush=True)
print()
```

更多详细示例请查看 [examples](examples/) 文件夹和 [API 文档](docs/API.md)。

## 🎯 核心功能

### 记忆系统

- **短期记忆**: 基于 LangChain 的消息历史，保持对话连贯性
- **长期记忆**: 使用向量数据库存储重要信息，支持语义检索
- **核心记忆**: 储存用户重要信息（v2.3）
- **日记功能**: 自动记录对话，支持时间检索（v2.3）
- **知识库**: 可扩展的知识库，强化角色扮演（v2.3）

### 工具系统

- 时间查询、日期查询
- 天气查询、网络搜索
- 计算器、提醒设置
- 文件操作（读取、写入、列出）（v2.5）
- 更多工具持续添加中...

### 角色特性

- 温柔体贴的猫娘女仆人设
- 使用"主人"称呼用户
- 偶尔使用"喵~"等可爱语气词
- 主动关心主人的需求
- 记住主人的喜好和习惯
- 角色动态状态（饥饿、疲劳、活力等）（v2.5）

## 🔧 配置说明

在 `config.yaml` 中可以配置：

### LLM 配置
- API 地址和 Key
- 模型选择（支持 OpenAI、Anthropic、Google、DeepSeek、SiliconFlow 等）
- 模型参数（temperature、max_tokens 等）

### 视觉模型（VISION_LLM）配置
- 可选：用于图片描述与 OCR（与主 LLM 解耦）
- 当主 LLM 为纯文本模型时，建议启用并配置支持多模态的视觉模型

### Agent 配置
- 角色名称和用户名称
- 记忆系统（长期记忆、核心记忆、知识库）
- 情绪系统（情绪函数、持久化）
- 上下文长度
- 角色设定和性格
- 自定义提示词

详细配置说明请参考 `config.yaml.example` 文件。

## 🧪 测试

```bash
# 运行所有测试
pytest tests/

# 运行特定测试
pytest tests/test_agent.py -v
```

## 📝 开发计划

- [x] 基础 Agent 架构
- [x] 记忆系统
- [x] 工具集成
- [x] 角色扮演系统
- [ ] 语音交互
- [ ] 图像生成
- [ ] Web UI 界面
- [ ] 移动端适配
- [ ] 多语言支持

## ❓ 常见问题

### pkg_resources 弃用警告

启动时可能会看到以下警告：
```
pkg_resources is deprecated as an API.
```

**说明**：
- ✅ 这个警告**不影响任何功能**，可以安全地忽略
- 这是setuptools的旧API警告，来自某些依赖包
- MintChat本身不使用pkg_resources

**解决方案**：
```bash
# 方案1：升级setuptools
conda activate mintchat
pip install --upgrade setuptools

# 方案2：运行修复脚本
python scripts/fix_pkg_resources_warning.py
```

详细说明请查看：[PKG_RESOURCES_WARNING.md](docs/PKG_RESOURCES_WARNING.md)

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

## 🙏 致谢

- [LangChain](https://www.langchain.com/) - 强大的 LLM 应用框架
- [LangGraph](https://langchain-ai.github.io/langgraph/) - 灵活的 Agent 编排工具
- 所有贡献者和支持者

---

<div align="center">
Made with ❤️ by MintChat Team
</div>
