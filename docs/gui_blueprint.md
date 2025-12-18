# MintChat GUI 结构蓝图（用于二次元风格重设计 + 性能优化）

本文根据现有代码抽象出 GUI「形状」（布局骨架、模块边界、关键交互流），用于后续的界面美化与性能优化迭代。

## 0. 入口与窗口关系（从启动到聊天）

入口文件：`MintChat.py`

启动流程（简化）：

1) 创建 `QApplication`，加载 Material Symbols 字体（图标字体）  
2) 后台初始化 TTS（避免阻塞首帧）  
3) 尝试恢复登录会话：成功 → 直接打开 `LightChatWindow`  
4) 未登录 → 打开 `AuthManager`（登录/注册/找回密码），登录成功后再打开 `LightChatWindow`

相关代码：
- `MintChat.py`
- `src/gui/auth_manager.py`（认证窗口容器）
- `src/gui/light_chat_window.py`（主聊天窗口）

## 1. AuthManager（登录/注册/找回密码）界面形状

文件：`src/gui/auth_manager.py`

布局骨架（AuthManager docstring 已给出示意）：

```
┌─────────────────────────────────────────────┐
│  ┌──────────┬──────────────────────────┐   │
│  │ 插画面板  │  表单堆叠区（Stacked）    │   │
│  │  500px    │  登录 / 注册 / 找回密码   │   │
│  └──────────┴──────────────────────────┘   │
└─────────────────────────────────────────────┘
```

交互流：
- 表单切换：`QStackedWidget` + 淡入淡出动画
- 登录成功：向外 emit `login_success`，由 `MintChat.py` 负责关闭认证窗口并打开主窗口

## 2. LightChatWindow（主聊天窗口）界面形状

文件：`src/gui/light_chat_window.py`

顶层结构（`setup_content()`）：

```
┌──────────────────────────────────────────────────────────────────────────┐
│ LightFramelessWindow                                                     │
├────────┬──────────────────────┬──────────────────────────────────────────┤
│ 左侧图标│ 联系人面板           │ 主内容区（QStackedWidget）               │
│ 侧边栏  │ ContactsPanel         │ 0: ChatArea  1: SettingsPanel(懒加载)   │
│ (64px) │ (可折叠/展开)         │                                          │
└────────┴──────────────────────┴──────────────────────────────────────────┘
```

对应组件：
- 左侧图标侧边栏：`src/gui/light_sidebar.py`（`LightIconSidebar`）
- 联系人面板：`src/gui/contacts_panel.py`（`ContactsPanel`）
- 主内容区：`QStackedWidget`（聊天页/设置页切换；设置页懒加载以减少启动卡顿）

### 2.1 ChatArea（聊天页）内部布局骨架

ChatArea 主要由三块组成：

```
┌─────────────────────────────────────────────────────────────┐
│ Header：头像 + 名称 + 在线状态 + 更多菜单                    │
├─────────────────────────────────────────────────────────────┤
│ Messages：QScrollArea（消息列表容器 + 气泡 widget）          │
├─────────────────────────────────────────────────────────────┤
│ Composer：输入区（EnhancedInputWidget + 附件/表情/发送）     │
└─────────────────────────────────────────────────────────────┘
```

重点对象：
- Header：`self.avatar_label / self.name_label / self.status_label / self.more_btn`
- Messages：`self.scroll_area` → `self.messages_widget` → `self.messages_layout`
- Composer：`EnhancedInputWidget`（`src/gui/enhanced_rich_input.py`）+ 发送按钮
- 表情选择器：`EmojiPicker`（`src/gui/emoji_picker.py`，通常是弹出/浮层）

### 2.2 SettingsPanel（设置页）骨架

文件：`src/gui/settings_panel.py`

结构：Header + 左侧导航 + 右侧内容 `QStackedWidget`，页面按需构建（lazy build）降低打开设置时的卡顿。

## 3. 消息气泡层（Message Bubble）结构

消息展示主要由消息气泡 widget 组成（含文本、图片、音频/动画等类型）。

相关文件：
- `src/gui/light_message_bubble.py`
- `src/gui/optimized_message_bubble.py`

设计要点：
- 气泡是“多 widget 的列表”，数量大时容易拖慢滚动与重绘，因此有「最大渲染条数」等保护策略（见性能章节）。

## 4. 异步与后台任务（性能关键）

GUI 里重负载任务全部应避免占用主线程：Agent 初始化、历史记录加载、TTS 合成、图片识别等。

相关 worker：
- Agent/对话线程：`src/gui/workers/agent_chat.py`
  - `AgentInitThread`：初始化 Agent
  - `ChatThread`：流式输出/对话执行
- 聊天历史加载：`src/gui/workers/chat_history_loader.py`
- TTS 合成：`src/gui/workers/tts_synthesis.py`（`QRunnable` + `QThreadPool`）
- 视觉识别：
  - 单图：`src/gui/workers/vision_analysis.py`（`QRunnable`）
  - 批量：`src/gui/workers/vision_batch.py`（`QThread`）

交互流（核心）：
- 发送文本 → `ChatThread` → 分段 emit → 主线程逐步渲染流式气泡 → 结束后落库/更新 UI
- 输入含图片 → 视觉识别 worker → 识别结果拼入上下文/消息 → 再走对话线程
- 开启 TTS → 流式文本分句 → `TTSSynthesisTask` 合成 → 音频播放器队列播放

## 5. 性能优化点位（当前已有的“护栏”）

主窗口内已经存在的一些性能护栏（便于后续继续迭代）：
- 流式渲染节流：`MINTCHAT_GUI_STREAM_RENDER_MS` 等环境变量控制刷新间隔/每次字符量
- 长对话保护：`MAX_RENDERED_MESSAGES`（限制渲染的气泡总数，避免滚动掉帧）
- 滚动更新优化：`QScrollArea` 使用 `MinimalViewportUpdate`（可用时）
- 后台加载聊天历史：避免 UI 卡顿
- 任务引用管理：对 `QRunnable` 任务保留引用，防止 GC 导致崩溃

后续建议继续关注：
- 减少重绘与阴影数量（阴影是昂贵操作）
- 限制高频动画（默认关闭动画，按需开启）
- 对图片/动图资源做可见性驱动（屏幕外暂停）

## 6. 二次元风格（Anime/Kawaii）设计落点（建议对齐“形状”）

二次元风格建议落点优先级（不改变布局骨架，只换“皮肤 + 细节”）：

1) 色彩体系（主题化）：Sakura Pink / Lavender / Sky Blue 的柔和渐变  
2) 圆角与高光：更大的圆角、轻微内高光（但避免过多阴影导致卡顿）  
3) Header 与侧边栏：加入轻渐变、强调色描边、状态点更“可爱”  
4) 气泡：用户气泡可用渐变，AI 气泡用浅色磨砂；边框更柔和  
5) 微交互：悬停/按压用更轻的色层变化（减少大范围透明度动画）

下一步实现建议（落到代码）：
- 以“主题系统”统一输出颜色/圆角/状态层 → 让各组件从同一套 tokens 取值
- 在 SettingsPanel 提供主题切换项，并提示“切换后需重启生效”（避免运行期改常量带来的复杂性）

