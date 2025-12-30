"""
参考音频选择器组件 - v2.36.0

支持切换和管理参考音频
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QFrame,
    QFileDialog,
    QDialog,
    QLineEdit,
    QDialogButtonBox,
    QFormLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from src.utils.logger import get_logger

logger = get_logger(__name__)


class AddReferenceAudioDialog(QDialog):
    """添加参考音频对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加参考音频")
        self.setModal(True)
        self.setFixedWidth(400)

        self.audio_path = ""
        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)

        # 表单布局
        form_layout = QFormLayout()
        form_layout.setSpacing(12)

        # 名称输入
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("例如: happy, sad, excited")
        form_layout.addRow("名称:", self.name_input)

        # 音频文件选择
        audio_layout = QHBoxLayout()
        self.audio_path_label = QLabel("未选择文件")
        self.audio_path_label.setStyleSheet("color: gray;")
        audio_layout.addWidget(self.audio_path_label)

        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self.browse_audio_file)
        audio_layout.addWidget(browse_btn)

        form_layout.addRow("音频文件:", audio_layout)

        # 参考文本输入
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("参考音频的文本内容")
        form_layout.addRow("参考文本:", self.text_input)

        # 情感标签输入
        self.emotion_input = QLineEdit()
        self.emotion_input.setPlaceholderText("例如: happy, sad, neutral")
        self.emotion_input.setText("neutral")
        form_layout.addRow("情感标签:", self.emotion_input)

        layout.addLayout(form_layout)

        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def browse_audio_file(self):
        """浏览音频文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择音频文件", "", "音频文件 (*.wav *.mp3 *.ogg);;所有文件 (*.*)"
        )

        if file_path:
            self.audio_path = file_path
            # 显示文件名
            import os

            filename = os.path.basename(file_path)
            self.audio_path_label.setText(filename)
            self.audio_path_label.setStyleSheet("color: white;")

    def get_data(self):
        """获取输入数据"""
        return {
            "name": self.name_input.text().strip(),
            "path": self.audio_path,
            "text": self.text_input.text().strip(),
            "emotion": self.emotion_input.text().strip() or "neutral",
        }


class ReferenceAudioSelector(QWidget):
    """参考音频选择器 (v2.36.0)"""

    # 信号
    audio_changed = pyqtSignal(str)  # 参考音频变化信号

    def __init__(self, tts_manager=None, parent=None):
        super().__init__(parent)
        self.tts_manager = tts_manager
        self.setup_ui()

        # 初始加载参考音频
        if self.tts_manager:
            self.refresh_audios()

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # 标题
        title_label = QLabel("🎭 参考音频")
        title_font = QFont()
        title_font.setPointSize(10)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("background: rgba(255, 255, 255, 0.1);")
        layout.addWidget(separator)

        # 选择区域
        select_layout = QVBoxLayout()
        select_layout.setSpacing(8)

        # 下拉框
        self.audio_combo = QComboBox()
        self.audio_combo.setFixedHeight(32)
        self.audio_combo.currentTextChanged.connect(self.on_audio_changed)
        self.audio_combo.setStyleSheet(
            """
            QComboBox {
                background: rgba(0, 0, 0, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
                padding: 4px 8px;
                color: white;
                font-size: 9pt;
            }
            QComboBox:hover {
                border: 1px solid rgba(255, 255, 255, 0.3);
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid white;
                margin-right: 8px;
            }
            QComboBox QAbstractItemView {
                background: rgba(30, 30, 30, 0.95);
                border: 1px solid rgba(255, 255, 255, 0.2);
                selection-background-color: rgba(255, 107, 157, 0.3);
                color: white;
            }
        """
        )
        select_layout.addWidget(self.audio_combo)

        # 按钮布局
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        # 添加按钮
        self.add_btn = QPushButton("➕ 添加")
        self.add_btn.setFixedHeight(28)
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.clicked.connect(self.on_add_audio)
        self.add_btn.setStyleSheet(
            """
            QPushButton {
                background: rgba(255, 107, 157, 0.2);
                border: 1px solid rgba(255, 107, 157, 0.3);
                border-radius: 14px;
                color: white;
                font-size: 9pt;
            }
            QPushButton:hover {
                background: rgba(255, 107, 157, 0.3);
                border: 1px solid rgba(255, 107, 157, 0.5);
            }
            QPushButton:pressed {
                background: rgba(255, 107, 157, 0.4);
            }
        """
        )
        btn_layout.addWidget(self.add_btn)

        # v2.37.0: 批量导入按钮
        self.batch_import_btn = QPushButton("📁 批量导入")
        self.batch_import_btn.setFixedHeight(28)
        self.batch_import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.batch_import_btn.clicked.connect(self.on_batch_import)
        self.batch_import_btn.setStyleSheet(
            """
            QPushButton {
                background: rgba(107, 157, 255, 0.2);
                border: 1px solid rgba(107, 157, 255, 0.3);
                border-radius: 14px;
                color: white;
                font-size: 9pt;
            }
            QPushButton:hover {
                background: rgba(107, 157, 255, 0.3);
                border: 1px solid rgba(107, 157, 255, 0.5);
            }
            QPushButton:pressed {
                background: rgba(107, 157, 255, 0.4);
            }
        """
        )
        btn_layout.addWidget(self.batch_import_btn)

        select_layout.addLayout(btn_layout)

        layout.addLayout(select_layout)

        # 设置面板样式
        self.setStyleSheet(
            """
            ReferenceAudioSelector {
                background: rgba(0, 0, 0, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
            }
        """
        )

    def refresh_audios(self):
        """刷新参考音频列表"""
        if not self.tts_manager:
            return

        self.audio_combo.clear()

        try:
            audios = self.tts_manager.get_reference_audios()
            current_audio = self.tts_manager.get_current_reference_audio()

            for audio in audios:
                display_text = f"{audio.name} ({audio.emotion})"
                self.audio_combo.addItem(display_text, audio.name)

            # 设置当前选中项
            if current_audio:
                for i in range(self.audio_combo.count()):
                    if self.audio_combo.itemData(i) == current_audio.name:
                        self.audio_combo.setCurrentIndex(i)
                        break

            logger.debug(f"已加载 {len(audios)} 个参考音频")

        except Exception as e:
            logger.error(f"刷新参考音频列表失败: {e}")

    def on_audio_changed(self, text: str):
        """参考音频变化"""
        if not self.tts_manager or not text:
            return

        audio_name = self.audio_combo.currentData()
        if audio_name:
            try:
                self.tts_manager.set_current_reference_audio(audio_name)
                self.audio_changed.emit(audio_name)
                logger.info(f"已切换参考音频: {audio_name}")
            except Exception as e:
                logger.error(f"切换参考音频失败: {e}")

    def on_add_audio(self):
        """添加参考音频"""
        dialog = AddReferenceAudioDialog(self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()

            # 验证数据
            if not data["name"] or not data["path"] or not data["text"]:
                logger.warning("参考音频信息不完整")
                return

            # 添加到TTS管理器
            if self.tts_manager:
                try:
                    self.tts_manager.add_reference_audio(
                        name=data["name"],
                        path=data["path"],
                        text=data["text"],
                        emotion=data["emotion"],
                    )

                    # 刷新列表
                    self.refresh_audios()

                    logger.info(f"已添加参考音频: {data['name']}")

                except Exception as e:
                    logger.error(f"添加参考音频失败: {e}")

    def on_batch_import(self):
        """批量导入参考音频 (v2.37.0)"""
        if not self.tts_manager:
            logger.warning("TTS管理器未初始化")
            return

        # 选择多个音频文件
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "选择参考音频文件", "", "音频文件 (*.wav *.mp3 *.ogg);;所有文件 (*.*)"
        )

        if not file_paths:
            return

        # 批量添加
        success_count = 0
        for file_path in file_paths:
            try:
                # 从文件名提取名称（去除扩展名）
                import os

                file_name = os.path.splitext(os.path.basename(file_path))[0]

                # 使用文件名作为参考音频名称
                # 默认文本为文件名，情感为neutral
                self.tts_manager.add_reference_audio(
                    name=file_name,
                    path=file_path,
                    text=file_name,  # 默认使用文件名作为文本
                    emotion="neutral",
                )

                success_count += 1
                logger.info(f"已导入参考音频: {file_name}")

            except Exception as e:
                logger.error(f"导入参考音频失败 ({file_path}): {e}")

        # 刷新列表
        self.refresh_audios()

        # 显示结果
        logger.info(f"批量导入完成: 成功 {success_count}/{len(file_paths)}")

        # 显示Toast提示
        try:
            from src.gui.components.toast import show_toast, Toast

            show_toast(
                self.window(),
                f"已导入 {success_count}/{len(file_paths)} 个参考音频",
                Toast.Type.SUCCESS if success_count == len(file_paths) else Toast.Type.WARNING,
            )
        except:
            pass
