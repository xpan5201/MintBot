# MintChat 脚本文件夹

本文件夹包含 MintChat 的所有启动脚本和工具脚本。

---

## 📋 推荐使用方式

**请使用根目录的主启动文件：**

- **Windows**: `MintChat.bat`
- **Linux/macOS**: `bash MintChat.sh`
- **直接运行**: `python MintChat.py`

这些主启动文件提供最新的浅色主题 GUI 界面，基于 Material Design 3 设计规范。

---

## 📂 文件说明

### 命令行启动脚本

- `start.py` - 交互式菜单，选择不同示例程序
- `quick_start.py` - 快速启动，直接进入基础对话
- `run.bat` / `run.sh` - 命令行版本启动脚本

### GUI 启动脚本

#### 浅色主题 GUI (v2.8.0) ⭐ 最新
- `mintchat_light_gui.py` - Python 启动器
- `run_light_gui.bat` - Windows 启动脚本
- `run_light_gui.sh` - Linux/macOS 启动脚本

#### 深色主题 GUI (v2.7.0)
- `mintchat_modern_gui.py` - Python 启动器
- `run_modern_gui.bat` - Windows 启动脚本
- `run_modern_gui.sh` - Linux/macOS 启动脚本

#### 经典 GUI (v2.6.0)
- `mintchat_gui.py` - Python 启动器
- `run_gui.bat` - Windows 启动脚本
- `run_gui.sh` - Linux/macOS 启动脚本

### 工具脚本

- `check_install.py` - 依赖检查脚本
- `setup.py` - 项目安装配置

### 修复和诊断脚本 (v2.29.1 新增)

#### 表情包上传修复

**fix_emoji_upload.py** - 表情包上传功能诊断工具

功能：
- ✅ 检查依赖是否正确安装
- ✅ 检查方法是否存在
- ✅ 检查文件对话框配置
- ✅ 测试文件选择功能
- ✅ 检查用户目录权限
- ✅ 提供详细的诊断报告

使用方法：
```bash
# 在 conda 环境中运行
conda activate mintchat
python scripts/fix_emoji_upload.py
```

**test_emoji_upload_simple.py** - 简单的文件对话框测试

功能：
- ✅ 测试 QFileDialog 基本功能
- ✅ 测试表情包上传配置
- ✅ 验证文件大小和类型

使用方法：
```bash
# 在 conda 环境中运行
conda activate mintchat
python scripts/test_emoji_upload_simple.py
```

#### 其他修复脚本

- `fix_encoding.py` - 修复编码问题
- `fix_code_style.py` - 修复代码风格
- `check_memory_leaks.py` - 检查内存泄漏
- `optimize_gui_code.py` - 优化 GUI 代码

---

## 🚀 使用说明

### 方式 1：使用主启动文件（推荐）

返回项目根目录，使用主启动文件：

```bash
# Windows
cd ..
MintChat.bat

# Linux/macOS
cd ..
bash MintChat.sh
```

### 方式 2：使用本文件夹的脚本

如果您想使用特定版本的 GUI 或命令行版本：

```bash
# 浅色主题 GUI（最新）
python mintchat_light_gui.py

# 深色主题 GUI
python mintchat_modern_gui.py

# 经典 GUI
python mintchat_gui.py

# 命令行交互式菜单
python start.py

# 快速启动
python quick_start.py
```

---

## 📚 更多信息

- [启动指南](../docs/LAUNCH_GUIDE.md) - 详细的启动说明
- [GUI 使用指南](../docs/GUI.md) - GUI 详细使用说明
- [快速开始](../docs/QUICKSTART.md) - 快速上手指南

---

**MintChat v2.8.0 - 致力于打造最接近人类的多模态猫娘女仆智能体** 🐱✨

