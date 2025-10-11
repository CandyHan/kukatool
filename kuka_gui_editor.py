#!/usr/bin/env python3
"""
KUKA .src File Interactive Graphical Editor
支持在3D可视化中直接操作：
- Mouse selection of points
- Real-time coordinate modification
- Visual preview of modifications
"""

import sys
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Button, TextBox, CheckButtons
from mpl_toolkits.mplot3d import Axes3D
from kuka_src_parser import KUKASrcParser
import copy
from enum import Enum
from dataclasses import dataclass
from typing import List, Tuple, Dict
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


# ===== Operation Detection Classes =====

class OperationType(Enum):
    """Operation type enumeration / 操作类型枚举"""
    DRILLING = "drilling"        # 钻孔
    CONTOURING = "contouring"    # 轮廓加工
    POSITIONING = "positioning"   # 定位移动


@dataclass
class OperationGroup:
    """Operation group data structure / 操作组数据结构"""
    name: str                    # e.g., "Drilling_1", "Contour_1"
    type: OperationType          # DRILLING or CONTOURING
    indices: List[int]           # Indices in motion_commands
    center: np.ndarray           # Center point coordinates
    bounds: Tuple[float, ...]    # Bounding box (xmin, xmax, ymin, ymax, zmin, zmax)
    properties: Dict             # Additional properties


class OperationDetector:
    """Automatic operation type detector / 自动操作类型检测器"""

    def __init__(self, motion_commands):
        self.motion_commands = motion_commands
        self.drilling_operations = []
        self.contouring_operations = []

    def detect_all_operations(self):
        """Detect all operations in the program / 检测程序中的所有操作"""
        i = 0
        drill_count = 0
        contour_count = 0

        while i < len(self.motion_commands):
            # Check for drilling pattern
            if self._is_drilling_pattern(i):
                drill_group = self._extract_drilling_group(i, drill_count)
                self.drilling_operations.append(drill_group)
                i += len(drill_group.indices)
                drill_count += 1

            # Check for contouring pattern
            elif self._is_contouring_pattern(i):
                contour_group = self._extract_contour_group(i, contour_count)
                self.contouring_operations.append(contour_group)
                i += len(contour_group.indices)
                contour_count += 1

            else:
                i += 1

        print(f"✓ Detected {len(self.drilling_operations)} drilling operations")
        print(f"✓ Detected {len(self.contouring_operations)} contour operations")

        return self.drilling_operations, self.contouring_operations

    def _is_drilling_pattern(self, start_idx):
        """Check if drilling pattern exists / 检查是否为钻孔模式
        Pattern: Fast down -> Fast approach -> Slow drill -> Fast up
        """
        if start_idx + 3 >= len(self.motion_commands):
            return False

        # Check 4 consecutive LIN commands
        cmds = self.motion_commands[start_idx:start_idx+4]
        for cmd in cmds:
            if cmd.command_type != 'LIN' or not cmd.position:
                return False

        # Check Z-coordinate pattern: high -> mid -> low -> high
        z_coords = [cmd.position.z for cmd in cmds]

        # Pattern recognition: Z decreases then increases
        if (z_coords[0] > z_coords[1] > z_coords[2] and z_coords[3] > z_coords[2]):
            # Check X, Y remain constant (drilling at same XY position)
            x_coords = [cmd.position.x for cmd in cmds]
            y_coords = [cmd.position.y for cmd in cmds]

            x_range = max(x_coords) - min(x_coords)
            y_range = max(y_coords) - min(y_coords)

            # XY variation should be very small (<1mm)
            if x_range < 1.0 and y_range < 1.0:
                return True

        return False

    def _extract_drilling_group(self, start_idx, drill_num):
        """Extract drilling operation group / 提取钻孔操作组"""
        indices = list(range(start_idx, start_idx + 4))

        # Calculate center point (use first point's XY, average Z)
        first_cmd = self.motion_commands[start_idx]
        center_x = first_cmd.position.x
        center_y = first_cmd.position.y

        z_coords = [self.motion_commands[i].position.z for i in indices]
        center_z = sum(z_coords) / len(z_coords)

        center = np.array([center_x, center_y, center_z])

        # Calculate bounds
        all_coords = [(self.motion_commands[i].position.x,
                      self.motion_commands[i].position.y,
                      self.motion_commands[i].position.z) for i in indices]
        xs, ys, zs = zip(*all_coords)
        bounds = (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))

        # Extract properties
        properties = {
            'drill_depth': max(z_coords) - min(z_coords),
            'safe_height': max(z_coords),
            'bottom_depth': min(z_coords)
        }

        return OperationGroup(
            name=f"Drill_{drill_num+1}",
            type=OperationType.DRILLING,
            indices=indices,
            center=center,
            bounds=bounds,
            properties=properties
        )

    def _is_contouring_pattern(self, start_idx):
        """Check if contouring pattern exists / 检查是否为轮廓加工模式
        Pattern: Z remains relatively constant, XY changes continuously
        """
        if start_idx + 5 >= len(self.motion_commands):
            return False

        # Check at least 5 consecutive points
        cmds = self.motion_commands[start_idx:start_idx+5]

        z_coords = []
        for cmd in cmds:
            if cmd.position:
                z_coords.append(cmd.position.z)

        if len(z_coords) < 5:
            return False

        # Z should remain relatively constant (within 2mm)
        z_range = max(z_coords) - min(z_coords)

        # Check if Z is in "machining depth" range (negative Z typically)
        avg_z = sum(z_coords) / len(z_coords)

        # Contouring usually happens at negative Z (below reference)
        # and Z variation is small
        if z_range < 2.0 and avg_z < -20:  # -20mm threshold for machining depth
            return True

        return False

    def _extract_contour_group(self, start_idx, contour_num):
        """Extract contour operation group / 提取轮廓操作组"""
        # Find all consecutive points with similar Z
        indices = [start_idx]
        base_z = self.motion_commands[start_idx].position.z

        i = start_idx + 1
        while i < len(self.motion_commands):
            cmd = self.motion_commands[i]
            if cmd.position:
                if abs(cmd.position.z - base_z) < 2.0:  # Same Z level
                    indices.append(i)
                    i += 1
                else:
                    break
            else:
                i += 1

        # Calculate center
        points = [self.motion_commands[i].position for i in indices if self.motion_commands[i].position]
        if not points:
            return None

        center_x = sum(p.x for p in points) / len(points)
        center_y = sum(p.y for p in points) / len(points)
        center_z = sum(p.z for p in points) / len(points)
        center = np.array([center_x, center_y, center_z])

        # Calculate bounds
        xs = [p.x for p in points]
        ys = [p.y for p in points]
        zs = [p.z for p in points]
        bounds = (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))

        properties = {
            'point_count': len(indices),
            'machining_depth': center_z
        }

        return OperationGroup(
            name=f"Contour_{contour_num+1}",
            type=OperationType.CONTOURING,
            indices=indices,
            center=center,
            bounds=bounds,
            properties=properties
        )


class InteractiveKUKAEditor:
    """Interactive KUKA Editor / 交互式KUKA编辑器"""

    def __init__(self, parser: KUKASrcParser = None):
        self.parser = parser
        self.original_parser = copy.deepcopy(parser) if parser else None

        # Initialize data structures
        self.points = []
        self.point_indices = []
        self.colors = []
        self.drilling_operations = []
        self.contouring_operations = []
        self.selected_drilling_names = set()
        self.selected_contour_names = set()

        # Extract data if parser is provided
        if parser:
            self.extract_data()

        # Create GUI / 创建GUI
        self.create_gui()

    def extract_data(self):
        """Extract all data from parser"""
        # Extract all Cartesian coordinate points
        self.points = []
        self.point_indices = []
        self.colors = []

        for i, cmd in enumerate(self.parser.motion_commands):
            if cmd.position:
                self.points.append([cmd.position.x, cmd.position.y, cmd.position.z])
                self.point_indices.append(i)
                # Color based on velocity
                if cmd.velocity and cmd.velocity < 0.05:
                    self.colors.append('red')
                else:
                    self.colors.append('green')

        self.points = np.array(self.points) if self.points else np.array([])

        # Detect operations
        if self.parser and self.parser.motion_commands:
            print("\n=== Detecting Operations ===")
            detector = OperationDetector(self.parser.motion_commands)
            self.drilling_operations, self.contouring_operations = detector.detect_all_operations()

    def create_gui(self):
        """Create graphical interface / 创建图形界面"""
        self.fig = plt.figure(figsize=(16, 10))

        # 3D view (left large window) / 3D视图 (左侧大窗口)
        self.ax_3d = self.fig.add_subplot(121, projection='3d')

        # Draw initial path / 绘制初始路径
        self.update_3d_plot()

        # Control panel (right side) / 控制面板 (右侧)
        panel_left = 0.55

        # 标题 (Title)
        self.fig.text(panel_left + 0.15, 0.95, 'KUKA Interactive Editor',  # KUKA交互式编辑器
                     fontsize=14, fontweight='bold', ha='center')

        # Instruction text
        if not self.parser:
            self.fig.text(panel_left + 0.15, 0.92, 'Click "Open" button below or run with file argument',
                         fontsize=9, ha='center', style='italic', color='blue')

        # === Advanced Operations Panel / 高级操作面板 ===
        # This section provides drilling and contouring specific operations

        self.fig.text(panel_left, 0.88, 'Drilling Operations:', fontsize=11, fontweight='bold')  # 钻孔操作

        # Delete selected drilling button / 删除选中钻孔按钮
        ax_delete_drill = self.fig.add_axes([panel_left, 0.82, 0.32, 0.05])
        self.btn_delete_drill = Button(ax_delete_drill, 'Delete Selected Drilling', color='salmon')  # 删除选中钻孔
        self.btn_delete_drill.on_clicked(self.delete_selected_drilling)

        # Move drilling offset inputs / 移动钻孔偏移输入
        self.fig.text(panel_left, 0.78, 'Move Selected Drilling:', fontsize=10)  # 移动选中钻孔

        ax_drill_dx = self.fig.add_axes([panel_left, 0.73, 0.08, 0.03])
        self.textbox_drill_dx = TextBox(ax_drill_dx, 'ΔX:', initial='0')

        ax_drill_dy = self.fig.add_axes([panel_left + 0.09, 0.73, 0.08, 0.03])
        self.textbox_drill_dy = TextBox(ax_drill_dy, 'ΔY:', initial='0')

        ax_drill_dz = self.fig.add_axes([panel_left + 0.18, 0.73, 0.08, 0.03])
        self.textbox_drill_dz = TextBox(ax_drill_dz, 'ΔZ:', initial='0')

        ax_move_drill = self.fig.add_axes([panel_left + 0.27, 0.73, 0.05, 0.03])
        self.btn_move_drill = Button(ax_move_drill, 'Move', color='lightblue')  # 移动
        self.btn_move_drill.on_clicked(self.move_selected_drilling)

        # Contour Operations / 轮廓操作
        self.fig.text(panel_left, 0.66, 'Contour Operations:', fontsize=11, fontweight='bold')  # 轮廓操作

        # Move contour offset inputs / 移动轮廓偏移输入
        self.fig.text(panel_left, 0.62, 'Move Selected Contours:', fontsize=10)  # 移动选中轮廓

        ax_contour_dx = self.fig.add_axes([panel_left, 0.57, 0.08, 0.03])
        self.textbox_contour_dx = TextBox(ax_contour_dx, 'ΔX:', initial='0')

        ax_contour_dy = self.fig.add_axes([panel_left + 0.09, 0.57, 0.08, 0.03])
        self.textbox_contour_dy = TextBox(ax_contour_dy, 'ΔY:', initial='0')

        ax_contour_dz = self.fig.add_axes([panel_left + 0.18, 0.57, 0.08, 0.03])
        self.textbox_contour_dz = TextBox(ax_contour_dz, 'ΔZ:', initial='0')

        ax_move_contour = self.fig.add_axes([panel_left + 0.27, 0.57, 0.05, 0.03])
        self.btn_move_contour = Button(ax_move_contour, 'Move', color='lightgreen')  # 移动
        self.btn_move_contour.on_clicked(self.move_entire_contour)

        # 撤销和保存 (Undo and Save)
        self.fig.text(panel_left, 0.50, 'File Operations:', fontsize=11, fontweight='bold')  # 文件操作

        ax_open = self.fig.add_axes([panel_left, 0.44, 0.10, 0.04])
        self.btn_open = Button(ax_open, 'Open',  # 打开
                              color='lightskyblue', hovercolor='deepskyblue')
        self.btn_open.on_clicked(self.open_file)

        ax_undo = self.fig.add_axes([panel_left + 0.11, 0.44, 0.10, 0.04])
        self.btn_undo = Button(ax_undo, 'Undo All',  # 撤销所有
                              color='lightcoral', hovercolor='red')
        self.btn_undo.on_clicked(self.undo)

        ax_save = self.fig.add_axes([panel_left + 0.22, 0.44, 0.10, 0.04])
        self.btn_save = Button(ax_save, 'Save File',  # 保存文件
                              color='lightgreen', hovercolor='green')
        self.btn_save.on_clicked(self.save_file)

        # Usage instructions / 使用说明
        self.fig.text(panel_left, 0.38, 'Instructions:', fontsize=11, fontweight='bold')  # 使用说明
        if not self.parser:
            self.fig.text(panel_left, 0.34, '• Click [Open] button to load .src file', fontsize=8, color='red')
            self.fig.text(panel_left, 0.31, '• Or check terminal for file picker', fontsize=8, color='red')
        else:
            self.fig.text(panel_left, 0.34, '1. Click blue triangles to select drilling', fontsize=8)
            self.fig.text(panel_left, 0.31, '2. Click green lines to select contours', fontsize=8)
            self.fig.text(panel_left, 0.28, '3. Selected items show in red/orange', fontsize=8)
            self.fig.text(panel_left, 0.25, '4. Enter offset and click Move button', fontsize=8)

        # Statistics info display / 统计信息显示
        self.info_text = self.fig.text(panel_left, 0.03, '', fontsize=9,
                                       family='monospace', verticalalignment='bottom')
        self.update_info()

        # Connect mouse click event for selection
        self.fig.canvas.mpl_connect('button_press_event', self.on_canvas_click)

    def update_3d_plot(self):
        """Update 3D view / 更新3D视图"""
        self.ax_3d.clear()

        # Check if parser exists
        if not self.parser:
            self.ax_3d.text2D(0.5, 0.5, 'No file loaded\n\nClick "Open" to load a file',
                            transform=self.ax_3d.transAxes,
                            fontsize=16, ha='center', va='center',
                            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
            self.ax_3d.set_xlabel('X (mm)', fontweight='bold')
            self.ax_3d.set_ylabel('Y (mm)', fontweight='bold')
            self.ax_3d.set_zlabel('Z (mm)', fontweight='bold')
            self.ax_3d.set_title('KUKA Interactive Editor - 3D Path View', fontweight='bold')
            return

        # Re-extract points / 重新提取点
        self.points = []
        self.point_indices = []
        self.colors = []

        for i, cmd in enumerate(self.parser.motion_commands):
            if cmd.position:
                self.points.append([cmd.position.x, cmd.position.y, cmd.position.z])
                self.point_indices.append(i)
                if cmd.velocity and cmd.velocity < 0.05:
                    self.colors.append('red')
                else:
                    self.colors.append('green')

        if not self.points:
            self.ax_3d.text(0, 0, 0, 'No points to display', fontsize=14)  # 没有可显示的点
            return

        self.points = np.array(self.points)

        # Draw path / 绘制路径
        self.ax_3d.plot(self.points[:, 0], self.points[:, 1], self.points[:, 2],
                       'gray', linewidth=0.5, alpha=0.3)

        # Draw points / 绘制点
        self.ax_3d.scatter(self.points[:, 0], self.points[:, 1], self.points[:, 2],
                          c=self.colors, s=20, alpha=0.6)

        # Draw drilling operations / 绘制钻孔操作
        first_selected = True
        first_unselected = True
        for drill_op in self.drilling_operations:
            if drill_op.name in self.selected_drilling_names:
                # Selected drilling - red triangle / 选中的钻孔 - 红色三角形
                self.ax_3d.scatter(drill_op.center[0], drill_op.center[1], drill_op.center[2],
                                  c='red', s=300, marker='v', edgecolors='darkred', linewidths=2,
                                  label='Selected Drilling' if first_selected else '')
                first_selected = False
            else:
                # Unselected drilling - blue triangle / 未选中的钻孔 - 蓝色三角形
                self.ax_3d.scatter(drill_op.center[0], drill_op.center[1], drill_op.center[2],
                                  c='dodgerblue', s=200, marker='v', edgecolors='blue', linewidths=1.5,
                                  label='Drilling' if first_unselected else '', alpha=0.7)
                first_unselected = False

        # Draw contouring operations / 绘制轮廓加工操作
        first_selected_contour = True
        first_unselected_contour = True
        for contour_op in self.contouring_operations:
            # Get all points in this contour with bounds checking
            contour_points = [self.parser.motion_commands[i].position for i in contour_op.indices
                            if i < len(self.parser.motion_commands) and self.parser.motion_commands[i].position]

            if contour_points:
                xs = [p.x for p in contour_points]
                ys = [p.y for p in contour_points]
                zs = [p.z for p in contour_points]

                if contour_op.name in self.selected_contour_names:
                    # Selected contour - orange line / 选中的轮廓 - 橙色线
                    self.ax_3d.plot(xs, ys, zs, color='orange', linewidth=3, alpha=0.9,
                                   label='Selected Contour' if first_selected_contour else '')
                    first_selected_contour = False
                else:
                    # Unselected contour - green line / 未选中的轮廓 - 绿色线
                    self.ax_3d.plot(xs, ys, zs, color='limegreen', linewidth=2, alpha=0.6,
                                   label='Contour' if first_unselected_contour else '')
                    first_unselected_contour = False

        # Mark start and end points / 标注起点和终点
        self.ax_3d.scatter(self.points[0, 0], self.points[0, 1], self.points[0, 2],
                          c='lime', s=200, marker='o', label='Start', edgecolors='black', linewidths=2)  # 起点
        self.ax_3d.scatter(self.points[-1, 0], self.points[-1, 1], self.points[-1, 2],
                          c='red', s=200, marker='X', label='End', edgecolors='black', linewidths=2)  # 终点

        # Set labels / 设置标签
        self.ax_3d.set_xlabel('X (mm)', fontweight='bold')
        self.ax_3d.set_ylabel('Y (mm)', fontweight='bold')
        self.ax_3d.set_zlabel('Z (mm)', fontweight='bold')
        self.ax_3d.set_title(f'{self.parser.program_name} - 3D Path View', fontweight='bold')  # 3D路径视图
        self.ax_3d.legend(loc='upper right', fontsize=8)
        self.ax_3d.grid(True, alpha=0.3)

        # Set equal aspect ratio / 设置相同比例
        if len(self.points) > 0:
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

        self.fig.canvas.draw_idle()

    def on_canvas_click(self, event):
        """Handle mouse click on 3D canvas / 处理3D画布上的鼠标点击"""
        # Only handle clicks in 3D axes
        if event.inaxes != self.ax_3d:
            return

        if event.button != 1:  # Only left click
            return

        # Get click coordinates
        if event.x is None or event.y is None:
            return

        from mpl_toolkits.mplot3d import proj3d

        # Find nearest drilling operation based on screen distance
        min_drill_distance = float('inf')
        selected_drill = None

        for drill_op in self.drilling_operations:
            # Project 3D point to 2D screen space
            try:
                x2d, y2d, _ = proj3d.proj_transform(drill_op.center[0],
                                                     drill_op.center[1],
                                                     drill_op.center[2],
                                                     self.ax_3d.get_proj())
                x_disp, y_disp = self.ax_3d.transData.transform((x2d, y2d))
                distance = np.sqrt((event.x - x_disp)**2 + (event.y - y_disp)**2)

                if distance < min_drill_distance:
                    min_drill_distance = distance
                    selected_drill = drill_op

            except Exception:
                continue

        # Find nearest contour operation based on screen distance to contour path
        min_contour_distance = float('inf')
        selected_contour = None

        for contour_op in self.contouring_operations:
            try:
                # Check distance to contour center point
                x2d, y2d, _ = proj3d.proj_transform(contour_op.center[0],
                                                     contour_op.center[1],
                                                     contour_op.center[2],
                                                     self.ax_3d.get_proj())
                x_disp, y_disp = self.ax_3d.transData.transform((x2d, y2d))
                distance_to_center = np.sqrt((event.x - x_disp)**2 + (event.y - y_disp)**2)

                # Also check distance to contour path points
                min_path_distance = distance_to_center
                for idx in contour_op.indices[:10]:  # Sample first 10 points for performance
                    if idx >= len(self.parser.motion_commands):
                        continue
                    cmd = self.parser.motion_commands[idx]
                    if cmd.position:
                        x2d, y2d, _ = proj3d.proj_transform(cmd.position.x,
                                                             cmd.position.y,
                                                             cmd.position.z,
                                                             self.ax_3d.get_proj())
                        x_disp, y_disp = self.ax_3d.transData.transform((x2d, y2d))
                        dist = np.sqrt((event.x - x_disp)**2 + (event.y - y_disp)**2)
                        min_path_distance = min(min_path_distance, dist)

                if min_path_distance < min_contour_distance:
                    min_contour_distance = min_path_distance
                    selected_contour = contour_op

            except Exception:
                continue

        # Determine which object to select (drilling or contour)
        # Priority: prefer the closest one, but drilling has slight preference if very close
        threshold_drill = 50  # pixels
        threshold_contour = 60  # pixels - slightly larger for contours

        if min_drill_distance < threshold_drill and min_drill_distance < min_contour_distance:
            # Select drilling
            if selected_drill.name in self.selected_drilling_names:
                self.selected_drilling_names.remove(selected_drill.name)
            else:
                self.selected_drilling_names.add(selected_drill.name)

            # Update visualization
            self.update_3d_plot()
            self.update_info()

        elif min_contour_distance < threshold_contour:
            # Select contour
            if selected_contour.name in self.selected_contour_names:
                self.selected_contour_names.remove(selected_contour.name)
            else:
                self.selected_contour_names.add(selected_contour.name)

            # Update visualization
            self.update_3d_plot()
            self.update_info()

    def update_info(self):
        """Update statistics info / 更新统计信息"""
        if not self.parser:
            info = """No file loaded

Click 'Open' button to
load a KUKA .src file"""
            self.info_text.set_text(info)
            self.fig.canvas.draw_idle()
            return

        total = len(self.parser.motion_commands)
        cartesian = len([c for c in self.parser.motion_commands if c.position])

        if cartesian > 0:
            x_coords = [c.position.x for c in self.parser.motion_commands if c.position]
            y_coords = [c.position.y for c in self.parser.motion_commands if c.position]
            z_coords = [c.position.z for c in self.parser.motion_commands if c.position]

            info = f"""Statistics:
Total Commands: {total}
Cartesian Points: {cartesian}

Workspace:
X: [{min(x_coords):.1f}, {max(x_coords):.1f}] mm
Y: [{min(y_coords):.1f}, {max(y_coords):.1f}] mm
Z: [{min(z_coords):.1f}, {max(z_coords):.1f}] mm

Operations:
Drilling: {len(self.drilling_operations)} ({len(self.selected_drilling_names)} selected)
Contouring: {len(self.contouring_operations)} ({len(self.selected_contour_names)} selected)"""
        else:
            info = f"Total Commands: {total}\nCartesian Points: 0"  # 总指令/笛卡尔点

        self.info_text.set_text(info)
        self.fig.canvas.draw_idle()

    def apply_offset(self, event):
        """Apply coordinate offset / 应用坐标偏移"""
        try:
            dx = float(self.textbox_dx.text)
            dy = float(self.textbox_dy.text)
            dz = float(self.textbox_dz.text)

            self.parser.offset_all_points(dx, dy, dz)
            self.update_3d_plot()
            self.update_info()

            # Reset input boxes / 重置输入框
            self.textbox_dx.set_val('0')
            self.textbox_dy.set_val('0')
            self.textbox_dz.set_val('0')

            print(f"✓ Offset applied: ΔX={dx}, ΔY={dy}, ΔZ={dz}")  # 已应用偏移
        except ValueError:
            print("✗ Please enter valid numbers")  # 请输入有效的数值

    def apply_scale(self, event):
        """Apply spacing scale / 应用间距缩放"""
        try:
            factor = float(self.textbox_scale.text)
            status = self.check_scale_axis.get_status()

            if status[0]:  # X轴
                self.scale_axis('x', factor)
            if status[1]:  # Y轴
                self.scale_axis('y', factor)
            if status[2]:  # Z轴
                self.scale_axis('z', factor)

            self.update_3d_plot()
            self.update_info()
            print(f"✓ Scale applied: {factor}x")  # 已应用缩放
        except ValueError:
            print("✗ Please enter valid scale factor")  # 请输入有效的缩放倍数

    def scale_axis(self, axis, factor):
        """Scale specified axis / 缩放指定轴"""
        coords = []
        for cmd in self.parser.motion_commands:
            if cmd.position:
                if axis == 'x':
                    coords.append(cmd.position.x)
                elif axis == 'y':
                    coords.append(cmd.position.y)
                else:
                    coords.append(cmd.position.z)

        if not coords:
            return

        center = sum(coords) / len(coords)

        for cmd in self.parser.motion_commands:
            if cmd.position:
                if axis == 'x':
                    cmd.position.x = center + (cmd.position.x - center) * factor
                elif axis == 'y':
                    cmd.position.y = center + (cmd.position.y - center) * factor
                else:
                    cmd.position.z = center + (cmd.position.z - center) * factor

            if cmd.auxiliary_point:
                if axis == 'x':
                    cmd.auxiliary_point.x = center + (cmd.auxiliary_point.x - center) * factor
                elif axis == 'y':
                    cmd.auxiliary_point.y = center + (cmd.auxiliary_point.y - center) * factor
                else:
                    cmd.auxiliary_point.z = center + (cmd.auxiliary_point.z - center) * factor

    def apply_mirror(self, axis):
        """Apply mirror flip / 应用镜像翻转"""
        for cmd in self.parser.motion_commands:
            if cmd.position:
                if axis == 'x':
                    cmd.position.x = -cmd.position.x
                elif axis == 'y':
                    cmd.position.y = -cmd.position.y
                else:
                    cmd.position.z = -cmd.position.z

            if cmd.auxiliary_point:
                if axis == 'x':
                    cmd.auxiliary_point.x = -cmd.auxiliary_point.x
                elif axis == 'y':
                    cmd.auxiliary_point.y = -cmd.auxiliary_point.y
                else:
                    cmd.auxiliary_point.z = -cmd.auxiliary_point.z

        # Mirror BASE / 镜像BASE
        if self.parser.base_frame:
            if axis == 'x':
                self.parser.base_frame.x = -self.parser.base_frame.x
            elif axis == 'y':
                self.parser.base_frame.y = -self.parser.base_frame.y
            else:
                self.parser.base_frame.z = -self.parser.base_frame.z

        self.update_3d_plot()
        self.update_info()
        print(f"✓ Mirrored along {axis.upper()}-axis")  # 已沿X/Y/Z轴镜像

    def delete_range(self, event):
        """Delete specified range / 删除指定范围"""
        try:
            start = int(self.textbox_del_start.text) - 1
            end = int(self.textbox_del_end.text)

            if 0 <= start < end <= len(self.parser.motion_commands):
                deleted = end - start
                del self.parser.motion_commands[start:end]
                self.update_3d_plot()
                self.update_info()
                print(f"✓ Deleted points {start+1} to {end}, total {deleted} points")  # 已删除点
            else:
                print(f"✗ Invalid index range")  # 索引范围无效
        except ValueError:
            print("✗ Please enter valid integers")  # 请输入有效的整数

    def delete_condition(self, event):
        """Delete by condition / 根据条件删除"""
        condition = self.textbox_condition.text.strip()
        original_count = len(self.parser.motion_commands)

        try:
            if condition.startswith('x>'):
                threshold = float(condition[2:])
                self.parser.motion_commands = [
                    cmd for cmd in self.parser.motion_commands
                    if not (cmd.position and cmd.position.x > threshold)
                ]
            elif condition.startswith('x<'):
                threshold = float(condition[2:])
                self.parser.motion_commands = [
                    cmd for cmd in self.parser.motion_commands
                    if not (cmd.position and cmd.position.x < threshold)
                ]
            elif condition.startswith('y>'):
                threshold = float(condition[2:])
                self.parser.motion_commands = [
                    cmd for cmd in self.parser.motion_commands
                    if not (cmd.position and cmd.position.y > threshold)
                ]
            elif condition.startswith('y<'):
                threshold = float(condition[2:])
                self.parser.motion_commands = [
                    cmd for cmd in self.parser.motion_commands
                    if not (cmd.position and cmd.position.y < threshold)
                ]
            elif condition.startswith('z>'):
                threshold = float(condition[2:])
                self.parser.motion_commands = [
                    cmd for cmd in self.parser.motion_commands
                    if not (cmd.position and cmd.position.z > threshold)
                ]
            elif condition.startswith('z<'):
                threshold = float(condition[2:])
                self.parser.motion_commands = [
                    cmd for cmd in self.parser.motion_commands
                    if not (cmd.position and cmd.position.z < threshold)
                ]
            else:
                print(f"✗ Unsupported condition: {condition}")  # 不支持的条件
                return

            deleted = original_count - len(self.parser.motion_commands)
            self.update_3d_plot()
            self.update_info()
            print(f"✓ Deleted {deleted} points by condition '{condition}'")  # 根据条件删除了点
        except ValueError:
            print(f"✗ Invalid condition format: {condition}")  # 条件格式错误

    def undo(self, event):
        """Undo all changes / 撤销所有修改"""
        self.parser = copy.deepcopy(self.original_parser)

        # Re-detect operations after undo
        self.selected_drilling_names.clear()
        self.selected_contour_names.clear()
        detector = OperationDetector(self.parser.motion_commands)
        self.drilling_operations, self.contouring_operations = detector.detect_all_operations()

        self.update_3d_plot()
        self.update_info()
        print("✓ All changes undone")  # 已撤销所有修改

    def delete_selected_drilling(self, event):
        """Delete selected drilling operations / 删除选中的钻孔操作"""
        if not self.selected_drilling_names:
            print("✗ No drilling operations selected")  # 未选中钻孔操作
            return

        # Collect all indices to delete
        indices_to_delete = set()
        for drill_op in self.drilling_operations:
            if drill_op.name in self.selected_drilling_names:
                indices_to_delete.update(drill_op.indices)

        # Keep only commands that are NOT in the delete list
        original_count = len(self.parser.motion_commands)
        self.parser.motion_commands = [
            cmd for i, cmd in enumerate(self.parser.motion_commands)
            if i not in indices_to_delete
        ]
        deleted_count = original_count - len(self.parser.motion_commands)

        # Clear selection and re-detect operations
        self.selected_drilling_names.clear()
        detector = OperationDetector(self.parser.motion_commands)
        self.drilling_operations, self.contouring_operations = detector.detect_all_operations()

        # Update display
        self.update_3d_plot()
        self.update_info()
        print(f"✓ Deleted {deleted_count} commands from selected drilling operations")

    def move_selected_drilling(self, event):
        """Move selected drilling operations / 移动选中的钻孔操作"""
        if not self.selected_drilling_names:
            print("✗ No drilling operations selected")  # 未选中钻孔操作
            return

        try:
            dx = float(self.textbox_drill_dx.text)
            dy = float(self.textbox_drill_dy.text)
            dz = float(self.textbox_drill_dz.text)

            # Move all points in selected drilling operations
            for drill_op in self.drilling_operations:
                if drill_op.name in self.selected_drilling_names:
                    for idx in drill_op.indices:
                        if idx >= len(self.parser.motion_commands):
                            continue
                        cmd = self.parser.motion_commands[idx]
                        if cmd.position:
                            cmd.position.x += dx
                            cmd.position.y += dy
                            cmd.position.z += dz
                        if cmd.auxiliary_point:
                            cmd.auxiliary_point.x += dx
                            cmd.auxiliary_point.y += dy
                            cmd.auxiliary_point.z += dz

                    # Update operation center
                    drill_op.center[0] += dx
                    drill_op.center[1] += dy
                    drill_op.center[2] += dz

            # Update display
            self.update_3d_plot()
            self.update_info()

            # Reset input boxes
            self.textbox_drill_dx.set_val('0')
            self.textbox_drill_dy.set_val('0')
            self.textbox_drill_dz.set_val('0')

            print(f"✓ Moved {len(self.selected_drilling_names)} drilling operation(s): ΔX={dx}, ΔY={dy}, ΔZ={dz}")
        except ValueError:
            print("✗ Please enter valid numbers")  # 请输入有效的数值

    def move_entire_contour(self, event):
        """Move selected contour operations / 移动选中的轮廓操作"""
        if not self.selected_contour_names:
            print("✗ No contour operations selected")  # 未选中轮廓操作
            return

        try:
            dx = float(self.textbox_contour_dx.text)
            dy = float(self.textbox_contour_dy.text)
            dz = float(self.textbox_contour_dz.text)

            # Move only selected contour operations
            for contour_op in self.contouring_operations:
                if contour_op.name in self.selected_contour_names:
                    for idx in contour_op.indices:
                        if idx >= len(self.parser.motion_commands):
                            continue
                        cmd = self.parser.motion_commands[idx]
                        if cmd.position:
                            cmd.position.x += dx
                            cmd.position.y += dy
                            cmd.position.z += dz
                        if cmd.auxiliary_point:
                            cmd.auxiliary_point.x += dx
                            cmd.auxiliary_point.y += dy
                            cmd.auxiliary_point.z += dz

                    # Update operation center
                    contour_op.center[0] += dx
                    contour_op.center[1] += dy
                    contour_op.center[2] += dz

            # Update display
            self.update_3d_plot()
            self.update_info()

            # Reset input boxes
            self.textbox_contour_dx.set_val('0')
            self.textbox_contour_dy.set_val('0')
            self.textbox_contour_dz.set_val('0')

            print(f"✓ Moved {len(self.selected_contour_names)} contour operation(s): ΔX={dx}, ΔY={dy}, ΔZ={dz}")
        except ValueError:
            print("✗ Please enter valid numbers")  # 请输入有效的数值

    def load_file_from_path(self, file_path):
        """Load file from given path / 从给定路径加载文件"""
        if file_path and os.path.exists(file_path):
            try:
                print(f"\n✓ Loading file: {file_path}")
                # Parse new file
                new_parser = KUKASrcParser(file_path)
                new_parser.parse()

                # Update current parser
                self.parser = new_parser
                self.original_parser = copy.deepcopy(new_parser)

                # Clear selections
                self.selected_drilling_names.clear()
                self.selected_contour_names.clear()

                # Re-detect operations
                detector = OperationDetector(self.parser.motion_commands)
                self.drilling_operations, self.contouring_operations = detector.detect_all_operations()

                # Update display
                self.update_3d_plot()
                self.update_info()

                print(f"✓ File loaded successfully: {file_path}")
            except Exception as e:
                print(f"✗ Error loading file: {e}")
        elif file_path:
            print(f"✗ File not found: {file_path}")

    def open_file(self, event):
        """Open file dialog to select a .src file / 打开文件对话框选择.src文件"""
        file_path = None

        if HAS_TKINTER:
            # Use tkinter file dialog (cross-platform GUI)
            root = tk.Tk()
            root.withdraw()  # Hide the main window
            root.attributes('-topmost', True)  # Make dialog appear on top

            # Open file dialog
            file_path = filedialog.askopenfilename(
                title='Select KUKA .src file',
                filetypes=[('KUKA Source Files', '*.src'), ('All Files', '*.*')],
                initialdir='.'
            )

            root.destroy()  # Clean up
        else:
            # Use simple text-based file picker
            file_path = simple_file_picker(title="Select KUKA .src file", file_pattern="*.src")

        # Load the selected file
        if file_path:
            self.load_file_from_path(file_path)

    def save_file(self, event):
        """Save file / 保存文件"""
        if not self.parser:
            print("\n✗ No file loaded. Please open a file first.")
            return

        file_path = None

        if HAS_TKINTER:
            # Use tkinter save dialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)

            # Open save dialog
            file_path = filedialog.asksaveasfilename(
                title='Save Modified File',
                defaultextension='.src',
                filetypes=[('KUKA Source Files', '*.src'), ('All Files', '*.*')],
                initialfile=self.parser.filename.replace('.src', '_modified.src')
            )

            root.destroy()
        else:
            # Simple text-based save dialog
            default_name = self.parser.filename.replace('.src', '_modified.src')
            print(f"\n{'=' * 60}")
            print(f"Save Modified File")
            print(f"{'=' * 60}")
            print(f"\nDefault: {default_name}")
            print(f"Options:")
            print(f"  • Press Enter to use default")
            print(f"  • Enter new filename")
            print(f"  • Type 'cancel' to abort")
            try:
                user_input = input(f"\nSave as: ").strip()
                if user_input.lower() == 'cancel':
                    print("✗ Save cancelled")
                    return
                file_path = user_input if user_input else default_name
            except (EOFError, KeyboardInterrupt):
                print("\n✗ Save cancelled")
                return

        if file_path:
            try:
                self.parser.export_to_src(file_path)
                print(f"\n✓ File saved to: {file_path}")
            except Exception as e:
                print(f"✗ Error saving file: {e}")

    def show(self):
        """Display GUI / 显示GUI"""
        plt.show()


def main():
    parser = None

    # Only use command line argument if provided
    if len(sys.argv) >= 2:
        src_file = sys.argv[1]
        print(f"Loading file: {src_file}")
        parser = KUKASrcParser(src_file)
        parser.parse()

    print("\nLaunching KUKA Interactive Editor...")
    print("=" * 60)
    print("Instructions:")
    print("  1. Click 'Open' to load a file")
    print("  2. Select drilling/contour operations by clicking")
    print("  3. Enter parameters and apply modifications")
    print("  4. Click 'Save File' to export changes")
    print("=" * 60)

    editor = InteractiveKUKAEditor(parser)
    editor.show()


if __name__ == "__main__":
    main()
