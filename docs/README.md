# MintChat 项目文档

> **版本**: v2.54.1
> **更新日期**: 2025-11-19
> **作者**: MintChat Team

欢迎来到 MintChat 项目文档！本文档提供了项目的全面指南，帮助您快速了解和使用 MintChat。

---

## 📚 文档导航

### 快速开始
- **[用户使用指南](USER_GUIDE.md)** - 安装、配置和使用说明
- **[开发指南](DEVELOPMENT_GUIDE.md)** - 开发环境搭建和开发规范

### 技术文档
- **[架构设计](ARCHITECTURE.md)** - 项目整体架构和模块说明
- **[API 参考](API_REFERENCE.md)** - 核心类和方法的 API 文档

### 其他
- **[更新日志](CHANGELOG.md)** - 版本更新记录

---

## 🎯 项目简介

**MintChat** 是一个基于 LangChain 1.0.x 的高质量、沉浸式多模态猫娘女仆智能体项目。

### 核心特性

✅ **智能对话系统**
- 流式输出，实时响应
- 支持同步和异步对话
- 上下文感知，对话连贯

✅ **4层记忆系统**
- 短期记忆：保持对话连贯性
- 长期记忆：语义检索重要信息
- 核心记忆：存储用户关键信息
- 日记功能：自动记录对话历史

✅ **情感与情绪系统**
- 12 种情感类型
- 基于 PAD 模型的情绪计算
- 情感持久化和自然衰减

✅ **多模态支持**
- 图像分析（GPT-4V、Claude 3、Gemini Pro Vision）
- OCR 文字提取
- 语音识别（Whisper API）
- 语音合成（TTS API）

✅ **丰富的工具系统**
- 时间查询、天气查询
- 网络搜索（Bing）
- 地图服务（高德地图）
- 文件操作（读取、写入、列出）
- 计算器、提醒设置

✅ **Material Design 3 GUI**
- 浅色主题，现代化界面
- QQ 风格设计，熟悉易用
- 流畅动画，60fps 性能
- 用户认证系统

---

## 🛠️ 技术栈

### 核心框架
- **Python 3.12+** - 编程语言
- **LangChain 1.0.x** - LLM 应用框架
- **LangGraph** - Agent 编排和状态管理

### GUI 框架
- **PyQt6** - 跨平台 GUI 框架
- **Material Design 3** - 设计规范

### 数据存储
- **ChromaDB** - 向量数据库（长期记忆）
- **SQLite** - 关系数据库（用户数据、聊天历史）

### 多模态处理
- **Pillow / OpenCV** - 图像处理
- **OpenAI Whisper** - 语音识别
- **OpenAI TTS** - 语音合成

---

## 🚀 快速开始

### 安装

```bash
# 克隆项目
git clone https://github.com/your-repo/MintChat.git
cd MintChat

# 创建 conda 环境
conda env create -f environment.yml
conda activate mintchat

# 安装依赖
pip install -r requirements.txt
```

### 配置

编辑 `config.yaml` 文件，填入您的 API Key：

```yaml
LLM:
  key: "your-api-key-here"
  api: "https://api.siliconflow.cn/v1"
  model: "Qwen/Qwen2.5-7B-Instruct"
```

### 运行

```bash
# Windows
python MintChat.py

# Linux/macOS
python3 MintChat.py
```

---

## 📖 详细文档

请查看以下文档了解更多信息：

- **[用户使用指南](USER_GUIDE.md)** - 详细的安装和使用说明
- **[开发指南](DEVELOPMENT_GUIDE.md)** - 开发环境搭建和代码规范
- **[架构设计](ARCHITECTURE.md)** - 项目架构和模块说明
- **[API 参考](API_REFERENCE.md)** - API 文档和使用示例

---

## 🤝 贡献

欢迎贡献代码、报告问题或提出建议！

---

## 📄 许可证

本项目采用 MIT 许可证。详见 [LICENSE](../LICENSE) 文件。
