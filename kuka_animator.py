#!/usr/bin/env python3
"""
KUKA .src 文件动画播放器
顺序播放加工路径，像看视频一样
支持播放、暂停、快进、慢放
"""

import sys
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.widgets import Button, Slider
from mpl_toolkits.mplot3d import Axes3D
from kuka_src_parser import KUKASrcParser
import copy
import os
import glob

# Try to import tkinter for file dialogs (cross-platform)
try:
    import tkinter as tk
    from tkinter import filedialog
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False


def simple_file_picker(title="Select file", file_pattern="*.src"):
    """Simple text-based file picker when GUI not available"""
    print(f"\n{'=' * 60}")
    print(f"{title}")
    print(f"{'=' * 60}")

    src_files = glob.glob(file_pattern)
    if src_files:
        print(f"\nAvailable {file_pattern} files:")
        for i, f in enumerate(src_files, 1):
            size = os.path.getsize(f) / 1024  # KB
            print(f"  [{i}] {f:<30} ({size:.1f} KB)")

        print(f"\nOptions:")
        print(f"  • Enter number (1-{len(src_files)}) to select file")
        print(f"  • Enter full path for other file")
        print(f"  • Press Enter to cancel")

        try:
            choice = input(f"\nYour choice: ").strip()
            if not choice:
                return None
            if choice.isdigit() and 1 <= int(choice) <= len(src_files):
                return src_files[int(choice) - 1]
            else:
                return choice if choice else None
        except (EOFError, KeyboardInterrupt):
            print("\n✗ Cancelled")
            return None
    else:
        print(f"\n✗ No {file_pattern} files found in current directory")
        try:
            path = input("Enter full file path (or press Enter to cancel): ").strip()
            return path if path else None
        except (EOFError, KeyboardInterrupt):
            print("\n✗ Cancelled")
            return None


class KUKAAnimator:
    """KUKA路径动画播放器"""

    def __init__(self, parser: KUKASrcParser = None):
        self.parser = parser
        self.original_parser = copy.deepcopy(parser) if parser else None

        # 动画状态
        self.current_frame = 0
        self.is_playing = False
        self.speed = 1.0
        self.breakpoint = None  # 断点：执行到某点停止
        self.step_mode = False  # 单步模式

        # 初始化数据
        self.points = np.array([])
        self.orientations = np.array([])
        self.velocities = []
        self.command_types = []
        self.total_points = 0

        # 提取数据
        if parser:
            self.extract_data()

        # 创建GUI
        self.create_animation()

    def extract_data(self):
        """从parser中提取所有笛卡尔坐标点和姿态"""
        self.points = []
        self.orientations = []  # 存储姿态角度 (A, B, C)
        self.velocities = []
        self.command_types = []

        if self.parser:
            for cmd in self.parser.motion_commands:
                if cmd.position:
                    self.points.append([cmd.position.x, cmd.position.y, cmd.position.z])
                    self.orientations.append([cmd.position.a, cmd.position.b, cmd.position.c])
                    self.velocities.append(cmd.velocity if cmd.velocity else 0)
                    self.command_types.append(cmd.command_type)

        self.points = np.array(self.points) if self.points else np.array([])
        self.orientations = np.array(self.orientations) if self.orientations else np.array([])
        self.total_points = len(self.points)

    def create_animation(self):
        """创建动画界面"""
        self.fig = plt.figure(figsize=(16, 10))

        # 主3D视图
        self.ax_3d = self.fig.add_subplot(121, projection='3d')

        # 侧视图（XZ平面）
        self.ax_xz = self.fig.add_subplot(222)

        # 俯视图（XY平面）
        self.ax_xy = self.fig.add_subplot(224)

        # 初始化绘图
        self.init_plots()

        # 控制面板
        self.create_controls()

        # 创建动画
        self.anim = FuncAnimation(
            self.fig,
            self.update_animation,
            interval=50,  # 50ms = 20fps，通过speed调整
            repeat=False,  # 不自动重复，到终点停止
            blit=False,
            cache_frame_data=False  # 不缓存帧数据
        )

    def init_plots(self):
        """初始化所有视图"""
        if self.total_points == 0:
            # Show message when no file is loaded
            self.ax_3d.text2D(0.5, 0.5, 'No file loaded\n\nClick "Open" to load a file',
                            transform=self.ax_3d.transAxes,
                            fontsize=16, ha='center', va='center',
                            bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.5))
            self.ax_3d.set_xlabel('X (mm)', fontweight='bold')
            self.ax_3d.set_ylabel('Y (mm)', fontweight='bold')
            self.ax_3d.set_zlabel('Z (mm)', fontweight='bold')
            self.ax_3d.set_title('KUKA Path Animator - 3D Animation', fontweight='bold')

            # Show message in side views too
            self.ax_xz.text(0.5, 0.5, 'No file loaded',
                          transform=self.ax_xz.transAxes,
                          fontsize=12, ha='center', va='center')
            self.ax_xz.set_xlabel('X (mm)')
            self.ax_xz.set_ylabel('Z (mm)')
            self.ax_xz.set_title('Side View (XZ)')

            self.ax_xy.text(0.5, 0.5, 'No file loaded',
                          transform=self.ax_xy.transAxes,
                          fontsize=12, ha='center', va='center')
            self.ax_xy.set_xlabel('X (mm)')
            self.ax_xy.set_ylabel('Y (mm)')
            self.ax_xy.set_title('Top View (XY)')
            return

        # 3D视图 - 显示完整路径（半透明）
        self.ax_3d.plot(self.points[:, 0], self.points[:, 1], self.points[:, 2],
                       'gray', linewidth=0.5, alpha=0.2, label='Full Path')  # 完整路径

        # 当前点
        self.current_point_3d, = self.ax_3d.plot([], [], [], 'ro',
                                                  markersize=10, label='TCP')  # TCP: Tool Center Point

        # 工具坐标系箭头（X-红, Y-绿, Z-蓝）
        self.tool_x_arrow = self.ax_3d.quiver([], [], [], [], [], [],
                                               color='red', arrow_length_ratio=0.3, linewidth=2, label='Tool X')
        self.tool_y_arrow = self.ax_3d.quiver([], [], [], [], [], [],
                                               color='green', arrow_length_ratio=0.3, linewidth=2, label='Tool Y')
        self.tool_z_arrow = self.ax_3d.quiver([], [], [], [], [], [],
                                               color='blue', arrow_length_ratio=0.3, linewidth=2, label='Tool Z')

        # 已走过的路径
        self.path_traveled_3d, = self.ax_3d.plot([], [], [], 'b-',
                                                  linewidth=2, alpha=0.8, label='Traveled')  # 已完成

        # 起点和终点
        self.ax_3d.scatter(self.points[0, 0], self.points[0, 1], self.points[0, 2],
                          c='lime', s=200, marker='o', label='Start', edgecolors='black', linewidths=2)  # 起点
        self.ax_3d.scatter(self.points[-1, 0], self.points[-1, 1], self.points[-1, 2],
                          c='red', s=200, marker='X', label='End', edgecolors='black', linewidths=2)  # 终点

        self.ax_3d.set_xlabel('X (mm)', fontweight='bold')
        self.ax_3d.set_ylabel('Y (mm)', fontweight='bold')
        self.ax_3d.set_zlabel('Z (mm)', fontweight='bold')
        self.ax_3d.set_title(f'{self.parser.program_name} - 3D Animation', fontweight='bold')  # 3D动画播放
        self.ax_3d.legend(loc='upper right')
        self.ax_3d.grid(True, alpha=0.3)

        # 设置相同比例
        max_range = np.array([
            self.points[:, 0].max() - self.points[:, 0].min(),
            self.points[:, 1].max() - self.points[:, 1].min(),
            self.points[:, 2].max() - self.points[:, 2].min()
        ]).max() / 2.0

        mid_x = (self.points[:, 0].max() + self.points[:, 0].min()) * 0.5
        mid_y = (self.points[:, 1].max() + self.points[:, 1].min()) * 0.5
        mid_z = (self.points[:, 2].max() + self.points[:, 2].min()) * 0.5

        self.ax_3d.set_xlim(mid_x - max_range, mid_x + max_range)
        self.ax_3d.set_ylim(mid_y - max_range, mid_y + max_range)
        self.ax_3d.set_zlim(mid_z - max_range, mid_z + max_range)

        # XZ侧视图
        self.ax_xz.plot(self.points[:, 0], self.points[:, 2], 'gray',
                       linewidth=0.5, alpha=0.2)
        self.current_point_xz, = self.ax_xz.plot([], [], 'ro', markersize=10)
        self.path_traveled_xz, = self.ax_xz.plot([], [], 'b-', linewidth=2)
        self.ax_xz.scatter(self.points[0, 0], self.points[0, 2], c='lime', s=100, marker='o')
        self.ax_xz.scatter(self.points[-1, 0], self.points[-1, 2], c='red', s=100, marker='X')
        self.ax_xz.set_xlabel('X (mm)')
        self.ax_xz.set_ylabel('Z (mm)')
        self.ax_xz.set_title('Side View (XZ)')  # 侧视图
        self.ax_xz.grid(True, alpha=0.3)
        self.ax_xz.axis('equal')

        # XY俯视图
        self.ax_xy.plot(self.points[:, 0], self.points[:, 1], 'gray',
                       linewidth=0.5, alpha=0.2)
        self.current_point_xy, = self.ax_xy.plot([], [], 'ro', markersize=10)
        self.path_traveled_xy, = self.ax_xy.plot([], [], 'b-', linewidth=2)
        self.ax_xy.scatter(self.points[0, 0], self.points[0, 1], c='lime', s=100, marker='o')
        self.ax_xy.scatter(self.points[-1, 0], self.points[-1, 1], c='red', s=100, marker='X')
        self.ax_xy.set_xlabel('X (mm)')
        self.ax_xy.set_ylabel('Y (mm)')
        self.ax_xy.set_title('Top View (XY)')  # 俯视图
        self.ax_xy.grid(True, alpha=0.3)
        self.ax_xy.axis('equal')

    def create_controls(self):
        """创建控制面板"""
        # 打开文件按钮
        ax_open = self.fig.add_axes([0.03, 0.02, 0.08, 0.04])
        self.btn_open = Button(ax_open, 'Open', color='lightskyblue')  # 打开
        self.btn_open.on_clicked(self.open_file)

        # 播放/暂停按钮
        ax_play = self.fig.add_axes([0.15, 0.02, 0.08, 0.04])
        self.btn_play = Button(ax_play, 'Play', color='lightgreen')  # 播放
        self.btn_play.on_clicked(self.toggle_play)

        # 停止按钮
        ax_stop = self.fig.add_axes([0.24, 0.02, 0.08, 0.04])
        self.btn_stop = Button(ax_stop, 'Stop', color='lightcoral')  # 停止
        self.btn_stop.on_clicked(self.stop_animation)

        # 重置按钮
        ax_reset = self.fig.add_axes([0.33, 0.02, 0.08, 0.04])
        self.btn_reset = Button(ax_reset, 'Reset', color='lightblue')  # 重置
        self.btn_reset.on_clicked(self.reset_animation)

        # 单步执行按钮
        ax_step = self.fig.add_axes([0.42, 0.02, 0.08, 0.04])
        self.btn_step = Button(ax_step, 'Step >', color='lightyellow')  # 单步
        self.btn_step.on_clicked(self.step_forward)

        # 速度滑块
        ax_speed = self.fig.add_axes([0.55, 0.03, 0.25, 0.02])
        self.slider_speed = Slider(
            ax_speed, 'Speed', 0.1, 5.0, valinit=1.0,  # 速度
            valstep=0.1, color='skyblue'
        )
        self.slider_speed.on_changed(self.update_speed)

        # 进度条
        ax_progress = self.fig.add_axes([0.15, 0.08, 0.65, 0.02])
        self.slider_progress = Slider(
            ax_progress, 'Progress', 0, self.total_points-1, valinit=0,  # 进度
            valstep=1, color='orange'
        )
        self.slider_progress.on_changed(self.seek_position)

        # 断点设置输入框
        from matplotlib.widgets import TextBox
        ax_breakpoint = self.fig.add_axes([0.15, 0.12, 0.10, 0.03])
        self.textbox_breakpoint = TextBox(ax_breakpoint, 'Stop at:', initial='')  # 停止于
        self.textbox_breakpoint.on_submit(self.set_breakpoint)

        # 清除断点按钮
        ax_clear_bp = self.fig.add_axes([0.26, 0.12, 0.08, 0.03])
        self.btn_clear_bp = Button(ax_clear_bp, 'Clear BP', color='lightgray')  # 清除断点
        self.btn_clear_bp.on_clicked(self.clear_breakpoint)

        # 信息文本
        self.info_text = self.fig.text(0.55, 0.17, '', fontsize=10,
                                       family='monospace')

    def rotation_matrix_from_euler_zyx(self, a, b, c):
        """根据欧拉角ZYX（KUKA的ABC）计算旋转矩阵"""
        # KUKA使用ZYX顺序: 先绕Z轴转A，再绕Y'轴转B，最后绕X''轴转C
        a_rad = np.radians(a)
        b_rad = np.radians(b)
        c_rad = np.radians(c)

        # Z旋转 (A)
        Rz = np.array([
            [np.cos(a_rad), -np.sin(a_rad), 0],
            [np.sin(a_rad),  np.cos(a_rad), 0],
            [0, 0, 1]
        ])

        # Y旋转 (B)
        Ry = np.array([
            [ np.cos(b_rad), 0, np.sin(b_rad)],
            [0, 1, 0],
            [-np.sin(b_rad), 0, np.cos(b_rad)]
        ])

        # X旋转 (C)
        Rx = np.array([
            [1, 0, 0],
            [0, np.cos(c_rad), -np.sin(c_rad)],
            [0, np.sin(c_rad),  np.cos(c_rad)]
        ])

        # 组合旋转: R = Rz * Ry * Rx
        return Rz @ Ry @ Rx

    def render_current_frame(self):
        """渲染当前帧到显示（独立于播放状态）"""
        if self.total_points == 0:
            # Update info text when no file loaded
            info = """No file loaded

Click 'Open' button to
load a KUKA .src file"""
            self.info_text.set_text(info)
            return

        if self.current_frame >= self.total_points:
            return

        # 更新当前点
        current_pos = self.points[self.current_frame]
        current_ori = self.orientations[self.current_frame]

        # 3D视图
        self.current_point_3d.set_data([current_pos[0]], [current_pos[1]])
        self.current_point_3d.set_3d_properties([current_pos[2]])

        # 更新工具坐标系箭头
        arrow_length = 30  # 箭头长度 (mm)
        R = self.rotation_matrix_from_euler_zyx(current_ori[0], current_ori[1], current_ori[2])

        # 计算三个坐标轴方向
        x_axis = R @ np.array([arrow_length, 0, 0])
        y_axis = R @ np.array([0, arrow_length, 0])
        z_axis = R @ np.array([0, 0, arrow_length])

        # 移除旧箭头
        self.tool_x_arrow.remove()
        self.tool_y_arrow.remove()
        self.tool_z_arrow.remove()

        # 绘制新箭头
        self.tool_x_arrow = self.ax_3d.quiver(
            current_pos[0], current_pos[1], current_pos[2],
            x_axis[0], x_axis[1], x_axis[2],
            color='red', arrow_length_ratio=0.2, linewidth=2.5, alpha=0.9
        )
        self.tool_y_arrow = self.ax_3d.quiver(
            current_pos[0], current_pos[1], current_pos[2],
            y_axis[0], y_axis[1], y_axis[2],
            color='green', arrow_length_ratio=0.2, linewidth=2.5, alpha=0.9
        )
        self.tool_z_arrow = self.ax_3d.quiver(
            current_pos[0], current_pos[1], current_pos[2],
            z_axis[0], z_axis[1], z_axis[2],
            color='blue', arrow_length_ratio=0.2, linewidth=2.5, alpha=0.9
        )

        # 已走过的路径
        traveled = self.points[:self.current_frame+1]
        if len(traveled) > 1:
            self.path_traveled_3d.set_data(traveled[:, 0], traveled[:, 1])
            self.path_traveled_3d.set_3d_properties(traveled[:, 2])

            # XZ视图
            self.path_traveled_xz.set_data(traveled[:, 0], traveled[:, 2])
            self.current_point_xz.set_data([current_pos[0]], [current_pos[2]])

            # XY视图
            self.path_traveled_xy.set_data(traveled[:, 0], traveled[:, 1])
            self.current_point_xy.set_data([current_pos[0]], [current_pos[1]])

        # 更新进度条（不触发回调）
        self.slider_progress.eventson = False
        self.slider_progress.set_val(self.current_frame)
        self.slider_progress.eventson = True

        # 更新信息
        vel = self.velocities[self.current_frame]
        cmd_type = self.command_types[self.current_frame]
        progress = (self.current_frame + 1) / self.total_points * 100

        # 信息显示 (英文)
        bp_info = f"\nBreakpoint: {self.breakpoint + 1}" if self.breakpoint is not None else "\nBreakpoint: None"
        info = f"""Progress: {self.current_frame+1}/{self.total_points} ({progress:.1f}%)
Motion: {cmd_type}
Velocity: {vel*1000:.0f} mm/s
Position (TCP):
  X: {current_pos[0]:8.2f} mm
  Y: {current_pos[1]:8.2f} mm
  Z: {current_pos[2]:8.2f} mm
Orientation:
  A: {current_ori[0]:8.2f}°
  B: {current_ori[1]:8.2f}°
  C: {current_ori[2]:8.2f}°{bp_info}"""

        self.info_text.set_text(info)

    def update_animation(self, frame):
        """更新动画帧（仅在播放时调用）"""
        if not self.is_playing:
            return

        # 检查是否到达终点
        if self.current_frame >= self.total_points - 1:
            self.is_playing = False
            self.current_frame = self.total_points - 1
            self.btn_play.label.set_text('Play')
            self.btn_play.color = 'lightgreen'
            print(f"✓ Animation completed")
            self.render_current_frame()
            return

        # 检查是否到达断点
        if self.breakpoint is not None and self.current_frame >= self.breakpoint:
            self.is_playing = False
            self.current_frame = self.breakpoint
            self.btn_play.label.set_text('Play')
            self.btn_play.color = 'lightgreen'
            print(f"⏸ Breakpoint reached at point {self.breakpoint + 1}")
            self.render_current_frame()
            return

        # 正常前进一帧
        self.current_frame += 1
        self.render_current_frame()

        return (self.current_point_3d, self.path_traveled_3d,
                self.current_point_xz, self.path_traveled_xz,
                self.current_point_xy, self.path_traveled_xy)

    def toggle_play(self, event):
        """播放/暂停"""
        # 如果已经到达终点，重置到开始
        if self.current_frame >= self.total_points - 1 and not self.is_playing:
            self.current_frame = 0
            print("↺ Reset to start")  # 重置到起点

        self.is_playing = not self.is_playing
        if self.is_playing:
            self.btn_play.label.set_text('Pause')  # 暂停
            self.btn_play.color = 'yellow'
            # 应用当前速度：停止后重启timer
            new_interval = int(50 / self.speed)
            self.anim.event_source.stop()
            self.anim.event_source.interval = new_interval
            self.anim.event_source.start()
            print(f"▶ Play started at speed {self.speed}x (interval={new_interval}ms)")  # 开始播放
        else:
            self.btn_play.label.set_text('Play')  # 播放
            self.btn_play.color = 'lightgreen'
            self.anim.event_source.stop()
            print(f"⏸ Paused at point {self.current_frame + 1}")  # 暂停
        self.fig.canvas.draw_idle()

    def stop_animation(self, event):
        """停止并重置到开头"""
        self.is_playing = False
        self.current_frame = 0
        self.btn_play.label.set_text('Play')  # 播放
        self.btn_play.color = 'lightgreen'
        self.render_current_frame()
        self.fig.canvas.draw_idle()

    def reset_animation(self, event):
        """重置到开头但保持播放状态"""
        self.current_frame = 0
        self.render_current_frame()
        self.fig.canvas.draw_idle()

    def update_speed(self, val):
        """更新播放速度"""
        self.speed = val
        # speed越小，interval越大（播放越慢）
        # speed=1.0 -> interval=50ms
        # speed=0.1 -> interval=500ms (慢10倍)
        # speed=5.0 -> interval=10ms (快5倍)
        new_interval = int(50 / self.speed)

        # 如果正在播放，需要重启timer以应用新速度
        if self.is_playing:
            self.anim.event_source.stop()
            self.anim.event_source.interval = new_interval
            self.anim.event_source.start()
            print(f"⚙ Speed changed to {self.speed}x (interval={new_interval}ms) - timer restarted")
        else:
            self.anim.event_source.interval = new_interval
            print(f"⚙ Speed set to {self.speed}x (interval={new_interval}ms)")  # 调试信息

    def seek_position(self, val):
        """跳转到指定位置"""
        self.current_frame = int(val)
        self.render_current_frame()
        self.fig.canvas.draw_idle()

    def step_forward(self, event):
        """单步前进"""
        if self.current_frame < self.total_points - 1:
            self.is_playing = False  # 停止自动播放
            self.current_frame += 1
            self.render_current_frame()
            self.fig.canvas.draw_idle()
            print(f"▶ Step to point {self.current_frame+1}/{self.total_points}")  # 单步到点
        else:
            print("⚠ Already at end")  # 已在终点

    def set_breakpoint(self, text):
        """设置断点"""
        try:
            bp = int(text)
            if 1 <= bp <= self.total_points:
                self.breakpoint = bp - 1  # 转换为0索引
                print(f"✓ Breakpoint set at point {bp}")  # 断点已设置
                self.render_current_frame()  # 刷新显示
                self.fig.canvas.draw_idle()
            else:
                print(f"✗ Invalid point number. Valid range: 1-{self.total_points}")  # 无效点号
        except ValueError:
            print("✗ Please enter a valid number")  # 请输入有效数字

    def clear_breakpoint(self, event):
        """清除断点"""
        self.breakpoint = None
        self.textbox_breakpoint.set_val('')
        print("✓ Breakpoint cleared")  # 断点已清除
        self.render_current_frame()  # 刷新显示
        self.fig.canvas.draw_idle()

    def load_file_from_path(self, file_path):
        """Load file from given path / 从给定路径加载文件"""
        if file_path and os.path.exists(file_path):
            try:
                print(f"\n✓ Loading file: {file_path}")
                # Parse new file
                new_parser = KUKASrcParser(file_path)
                new_parser.parse()

                # Update parser
                self.parser = new_parser
                self.original_parser = copy.deepcopy(new_parser)

                # Reset animation state
                self.current_frame = 0
                self.is_playing = False
                self.breakpoint = None
                self.textbox_breakpoint.set_val('')

                # Re-extract data
                self.extract_data()

                # Update progress slider range
                self.slider_progress.valmin = 0
                self.slider_progress.valmax = self.total_points - 1
                self.slider_progress.ax.set_xlim(0, self.total_points - 1)
                self.slider_progress.set_val(0)

                # Recreate plots
                self.recreate_plots()

                print(f"✓ File loaded successfully: {file_path}")
            except Exception as e:
                print(f"✗ Error loading file: {e}")
        elif file_path:
            print(f"✗ File not found: {file_path}")

    def open_file(self, event):
        """打开文件对话框选择.src文件"""
        # Pause animation if playing
        if self.is_playing:
            self.is_playing = False
            self.btn_play.label.set_text('Play')
            self.btn_play.color = 'lightgreen'
            self.anim.event_source.stop()

        file_path = None

        if HAS_TKINTER:
            # Use tkinter file dialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)

            file_path = filedialog.askopenfilename(
                title='Select KUKA .src file',
                filetypes=[('KUKA Source Files', '*.src'), ('All Files', '*.*')],
                initialdir='.'
            )

            root.destroy()
        else:
            # Use simple text-based file picker
            file_path = simple_file_picker(title="Select KUKA .src file", file_pattern="*.src")

        # Load the selected file
        if file_path:
            self.load_file_from_path(file_path)

    def recreate_plots(self):
        """重新创建所有绘图（用于加载新文件）"""
        # Clear all axes
        self.ax_3d.clear()
        self.ax_xz.clear()
        self.ax_xy.clear()

        # Reinitialize plots
        self.init_plots()

        # Render first frame
        self.render_current_frame()

        # Redraw
        self.fig.canvas.draw_idle()

    def show(self):
        """显示动画"""
        plt.show()


def main():
    parser = None

    # Only use command line argument if provided
    if len(sys.argv) >= 2:
        src_file = sys.argv[1]
        print(f"正在加载文件: {src_file}")
        parser = KUKASrcParser(src_file)
        parser.parse()

    print("\n启动KUKA动画播放器...")
    print("=" * 60)
    print("控制说明:")
    print("  [打开]     - 打开文件")
    print("  [播放 ▶]   - 开始/暂停播放")
    print("  [停止 ■]   - 停止并回到开头")
    print("  [重置 ⟲]   - 重置到开头")
    print("  [单步 >]   - 单步执行")
    print("  速度滑块   - 调整播放速度 (0.1x - 5.0x)")
    print("  进度条     - 拖动跳转到任意位置")
    print("  3D视图     - 可用鼠标旋转查看不同角度")
    print("=" * 60)

    animator = KUKAAnimator(parser)
    animator.show()


if __name__ == "__main__":
    main()
