"""
TTS性能监控面板组件 - v2.45.0

实时显示TTS系统性能指标，包括图表可视化
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QFrame, QGridLayout, QTabWidget
)
from PyQt6.QtCore import Qt, pyqtSlot, QTimer
from PyQt6.QtGui import QFont

from src.gui.widgets.performance_chart import PerformanceChart  # v2.45.0
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TTSPerformanceMonitor(QWidget):
    """TTS性能监控面板 (v2.45.0 - 增强图表可视化)"""

    def __init__(self, tts_manager=None, parent=None):
        super().__init__(parent)
        self.tts_manager = tts_manager

        # v2.45.0: 图表组件
        self.success_rate_chart = None
        self.cache_hit_rate_chart = None

        self.setup_ui()

        # v2.44.0: 定时更新性能数据（每秒更新一次）
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_performance_data)
        self.update_timer.start(1000)  # 1秒更新一次
        
    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        
        # 标题
        title_label = QLabel("📊 性能监控")
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

        # v2.45.0: 使用Tab切换指标和图表
        tab_widget = QTabWidget()
        tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid rgba(255, 255, 255, 0.1);
                background: rgba(0, 0, 0, 0.2);
                border-radius: 4px;
            }
            QTabBar::tab {
                background: rgba(255, 255, 255, 0.05);
                color: rgba(255, 255, 255, 0.7);
                padding: 6px 12px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: rgba(255, 107, 157, 0.3);
                color: white;
            }
        """)

        # 指标Tab
        metrics_widget = QWidget()
        metrics_layout = QVBoxLayout(metrics_widget)
        metrics_layout.setContentsMargins(8, 8, 8, 8)

        # v2.44.0: 性能指标网格
        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(8)
        
        # 第一行：请求统计
        row = 0
        metrics_grid.addWidget(self._create_label("总请求数:", bold=False), row, 0)
        self.total_requests_label = self._create_label("0", bold=True)
        metrics_grid.addWidget(self.total_requests_label, row, 1)
        
        metrics_grid.addWidget(self._create_label("成功率:", bold=False), row, 2)
        self.success_rate_label = self._create_label("0%", bold=True)
        metrics_grid.addWidget(self.success_rate_label, row, 3)
        
        # 第二行：缓存统计
        row += 1
        metrics_grid.addWidget(self._create_label("缓存命中:", bold=False), row, 0)
        self.cache_hits_label = self._create_label("0", bold=True)
        metrics_grid.addWidget(self.cache_hits_label, row, 1)
        
        metrics_grid.addWidget(self._create_label("命中率:", bold=False), row, 2)
        self.cache_hit_rate_label = self._create_label("0%", bold=True)
        metrics_grid.addWidget(self.cache_hit_rate_label, row, 3)
        
        # 第三行：错误统计
        row += 1
        metrics_grid.addWidget(self._create_label("重试次数:", bold=False), row, 0)
        self.retry_count_label = self._create_label("0", bold=True)
        metrics_grid.addWidget(self.retry_count_label, row, 1)
        
        metrics_grid.addWidget(self._create_label("超时错误:", bold=False), row, 2)
        self.timeout_errors_label = self._create_label("0", bold=True)
        metrics_grid.addWidget(self.timeout_errors_label, row, 3)
        
        # 第四行：网络和API错误
        row += 1
        metrics_grid.addWidget(self._create_label("网络错误:", bold=False), row, 0)
        self.network_errors_label = self._create_label("0", bold=True)
        metrics_grid.addWidget(self.network_errors_label, row, 1)
        
        metrics_grid.addWidget(self._create_label("API错误:", bold=False), row, 2)
        self.api_errors_label = self._create_label("0", bold=True)
        metrics_grid.addWidget(self.api_errors_label, row, 3)
        
        # 第五行：队列和缓存大小
        row += 1
        metrics_grid.addWidget(self._create_label("队列大小:", bold=False), row, 0)
        self.queue_size_label = self._create_label("0", bold=True)
        metrics_grid.addWidget(self.queue_size_label, row, 1)
        
        metrics_grid.addWidget(self._create_label("缓存大小:", bold=False), row, 2)
        self.cache_size_label = self._create_label("0", bold=True)
        metrics_grid.addWidget(self.cache_size_label, row, 3)

        metrics_layout.addLayout(metrics_grid)
        metrics_layout.addStretch()

        # v2.45.0: 图表Tab
        charts_widget = QWidget()
        charts_layout = QVBoxLayout(charts_widget)
        charts_layout.setContentsMargins(8, 8, 8, 8)
        charts_layout.setSpacing(12)

        # 成功率图表
        self.success_rate_chart = PerformanceChart("成功率趋势 (%)", max_points=60)
        self.success_rate_chart.setMinimumHeight(120)
        charts_layout.addWidget(self.success_rate_chart)

        # 缓存命中率图表
        self.cache_hit_rate_chart = PerformanceChart("缓存命中率趋势 (%)", max_points=60)
        self.cache_hit_rate_chart.setMinimumHeight(120)
        charts_layout.addWidget(self.cache_hit_rate_chart)

        charts_layout.addStretch()

        # 添加Tab
        tab_widget.addTab(metrics_widget, "📊 指标")
        tab_widget.addTab(charts_widget, "📈 图表")

        layout.addWidget(tab_widget)

        # 设置面板样式
        self.setStyleSheet("""
            TTSPerformanceMonitor {
                background: rgba(0, 0, 0, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
            }
        """)
    
    def _create_label(self, text: str, bold: bool = False) -> QLabel:
        """创建标签"""
        label = QLabel(text)
        label.setStyleSheet("color: rgba(255, 255, 255, 0.7); font-size: 9pt;")
        if bold:
            font = label.font()
            font.setBold(True)
            label.setFont(font)
        return label
    
    def _update_performance_data(self):
        """更新性能数据 (v2.45.0 - 增强图表数据)"""
        if not self.tts_manager:
            return

        try:
            # 获取统计数据
            stats = self.tts_manager.get_stats()

            # 更新请求统计
            total_requests = stats.get("total_requests", 0)
            successful_requests = stats.get("successful_requests", 0)
            self.total_requests_label.setText(str(total_requests))

            # 计算成功率
            success_rate = 0.0
            if total_requests > 0:
                success_rate = (successful_requests / total_requests) * 100
                self.success_rate_label.setText(f"{success_rate:.1f}%")
                # 根据成功率设置颜色
                if success_rate >= 95:
                    color = "#4CAF50"  # 绿色
                elif success_rate >= 80:
                    color = "#FFC107"  # 黄色
                else:
                    color = "#F44336"  # 红色
                self.success_rate_label.setStyleSheet(f"color: {color}; font-size: 9pt;")
            else:
                self.success_rate_label.setText("N/A")

            # v2.45.0: 更新成功率图表
            if self.success_rate_chart and total_requests > 0:
                self.success_rate_chart.add_data_point(success_rate)

            # 更新缓存统计
            cache_hits = stats.get("cache_hits", 0)
            cache_misses = stats.get("cache_misses", 0)
            self.cache_hits_label.setText(str(cache_hits))

            # 计算缓存命中率
            cache_hit_rate = 0.0
            total_cache_requests = cache_hits + cache_misses
            if total_cache_requests > 0:
                cache_hit_rate = (cache_hits / total_cache_requests) * 100
                self.cache_hit_rate_label.setText(f"{cache_hit_rate:.1f}%")
                # 根据命中率设置颜色
                if cache_hit_rate >= 80:
                    color = "#4CAF50"  # 绿色
                elif cache_hit_rate >= 50:
                    color = "#FFC107"  # 黄色
                else:
                    color = "#F44336"  # 红色
                self.cache_hit_rate_label.setStyleSheet(f"color: {color}; font-size: 9pt;")
            else:
                self.cache_hit_rate_label.setText("N/A")

            # v2.45.0: 更新缓存命中率图表
            if self.cache_hit_rate_chart and total_cache_requests > 0:
                self.cache_hit_rate_chart.add_data_point(cache_hit_rate)

            # 更新错误统计
            self.retry_count_label.setText(str(stats.get("retry_count", 0)))
            self.timeout_errors_label.setText(str(stats.get("timeout_errors", 0)))
            self.network_errors_label.setText(str(stats.get("network_errors", 0)))
            self.api_errors_label.setText(str(stats.get("api_errors", 0)))

            # 更新队列和缓存大小
            self.queue_size_label.setText(str(stats.get("queue_size", 0)))
            self.cache_size_label.setText(str(stats.get("cache_size", 0)))

        except Exception as e:
            logger.error(f"更新性能数据失败: {e}")

    def set_tts_manager(self, tts_manager):
        """设置TTS管理器"""
        self.tts_manager = tts_manager
        self._update_performance_data()  # 立即更新一次


