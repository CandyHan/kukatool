#!/usr/bin/env python3
"""
KUKA File Interactive Graphical Editor
支持在3D可视化中直接操作：
- Mouse selection of points
- Real-time coordinate modification
- Visual preview of modifications
- 支持文件格式: .src (KUKA), .nc/.NC (G-code)
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


def simple_file_picker(title="Select file", file_patterns=["*.src", "*.nc", "*.NC"]):
    """Simple text-based file picker when GUI not available"""
    print(f"\n{'=' * 60}")
    print(f"{title}")
    print(f"{'=' * 60}")

    # 收集所有匹配的文件
    all_files = []
    for pattern in file_patterns:
        all_files.extend(glob.glob(pattern))

    # 去重并排序
    all_files = sorted(set(all_files))

    if all_files:
        print(f"\nAvailable files (.src, .nc, .NC):")
        for i, f in enumerate(all_files, 1):
            size = os.path.getsize(f) / 1024  # KB
            file_type = f.split('.')[-1].upper()
            print(f"  [{i}] {f:<30} ({size:.1f} KB) [{file_type}]")

        print(f"\nOptions:")
        print(f"  • Enter number (1-{len(all_files)}) to select file")
        print(f"  • Enter full path for other file")
        print(f"  • Press Enter to cancel")

        try:
            choice = input(f"\nYour choice: ").strip()
            if not choice:
                return None
            if choice.isdigit() and 1 <= int(choice) <= len(all_files):
                return all_files[int(choice) - 1]
            else:
                return choice if choice else None
        except (EOFError, KeyboardInterrupt):
            print("\n✗ Cancelled")
            return None
    else:
        print(f"\n✗ No .src or .nc files found in current directory")
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
        self.z_direction = self._detect_z_direction()

    def _detect_z_direction(self):
        """Detect Z coordinate system direction / 检测Z坐标系方向
        Returns: 'negative' if most Z coords are negative, 'positive' if positive
        """
        z_coords = []
        for cmd in self.motion_commands:
            if cmd.position:
                z_coords.append(cmd.position.z)

        if not z_coords:
            return 'negative'  # Default

        # Calculate average Z
        avg_z = sum(z_coords) / len(z_coords)

        # Detect direction based on average
        if avg_z < 0:
            print(f"  ℹ Z-direction: Negative (avg Z = {avg_z:.1f}mm)")
            return 'negative'
        else:
            print(f"  ℹ Z-direction: Positive (avg Z = {avg_z:.1f}mm)")
            return 'positive'

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

        # 后处理：将大孔（闭合环形轮廓）识别为钻孔操作
        self._convert_large_holes_to_drilling()

        print(f"✓ Detected {len(self.drilling_operations)} drilling operations")
        print(f"✓ Detected {len(self.contouring_operations)} contour operations")

        return self.drilling_operations, self.contouring_operations

    def _is_drilling_pattern(self, start_idx):
        """Check if drilling pattern exists / 检查是否为钻孔模式
        Pattern:
        - KUKA .src: Fast down -> Fast approach -> Slow drill -> Fast up (4 steps)
        - NC G-code: Fast to high -> Slow drill down -> Fast up (3 steps)
        """
        # 先检查3步模式 (NC/G-code钻孔)
        if start_idx + 2 < len(self.motion_commands):
            cmds_3 = self.motion_commands[start_idx:start_idx+3]

            # 检查指令类型的多种组合:
            # 模式1: PTP(G00) -> LIN(G01) -> PTP(G00)
            # 模式2: LIN -> LIN -> PTP (404座板.NC.nc的模式)
            is_valid_type_pattern = False

            if len(cmds_3) == 3:
                types = [cmd.command_type for cmd in cmds_3]

                # 模式1: PTP -> LIN -> PTP
                if types == ['PTP', 'LIN', 'PTP']:
                    is_valid_type_pattern = True

                # 模式2: LIN -> LIN -> PTP (快速到高位->进给下钻->快速退回)
                elif types == ['LIN', 'LIN', 'PTP']:
                    is_valid_type_pattern = True

                # 模式3: 任意 -> LIN -> PTP (通用模式)
                elif types[1] == 'LIN' and types[2] == 'PTP':
                    is_valid_type_pattern = True

            if is_valid_type_pattern:
                # 检查都有坐标
                if all(cmd.position for cmd in cmds_3):
                    z_coords = [cmd.position.z for cmd in cmds_3]
                    x_coords = [cmd.position.x for cmd in cmds_3]
                    y_coords = [cmd.position.y for cmd in cmds_3]

                    # 检查XY基本不变（钻孔在同一XY位置）
                    x_range = max(x_coords) - min(x_coords)
                    y_range = max(y_coords) - min(y_coords)

                    if x_range < 50.0 and y_range < 50.0:  # 放宽到50mm容差
                        # 检查Z坐标模式：高->低->高 (向下钻孔)
                        if z_coords[0] > z_coords[1] and z_coords[2] > z_coords[1]:
                            z_depth = z_coords[0] - z_coords[1]
                            # 钻孔深度应该合理（5mm以上）
                            if z_depth > 5.0:
                                return True

        # 检查4步模式 (KUKA .src钻孔)
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
        # 先检查是3步还是4步模式
        step_count = 4  # 默认4步（KUKA .src）

        # 检查是否为3步模式 (NC G-code)
        if start_idx + 2 < len(self.motion_commands):
            cmds_3 = self.motion_commands[start_idx:start_idx+3]
            if len(cmds_3) == 3 and all(cmd.position for cmd in cmds_3):
                types = [cmd.command_type for cmd in cmds_3]

                # 检查多种3步模式
                is_3step = False
                if types == ['PTP', 'LIN', 'PTP'] or types == ['LIN', 'LIN', 'PTP']:
                    is_3step = True
                elif types[1] == 'LIN' and types[2] == 'PTP':
                    is_3step = True

                if is_3step:
                    z_coords_test = [cmd.position.z for cmd in cmds_3]
                    if z_coords_test[0] > z_coords_test[1] and z_coords_test[2] > z_coords_test[1]:
                        step_count = 3

        indices = list(range(start_idx, start_idx + step_count))

        # Calculate center point (use first point's XY, average Z)
        first_cmd = self.motion_commands[start_idx]
        center_x = first_cmd.position.x
        center_y = first_cmd.position.y

        z_coords = [self.motion_commands[i].position.z for i in indices if i < len(self.motion_commands)]
        center_z = sum(z_coords) / len(z_coords) if z_coords else 0

        center = np.array([center_x, center_y, center_z])

        # Calculate bounds
        all_coords = [(self.motion_commands[i].position.x,
                      self.motion_commands[i].position.y,
                      self.motion_commands[i].position.z) for i in indices
                      if i < len(self.motion_commands) and self.motion_commands[i].position]
        xs, ys, zs = zip(*all_coords)
        bounds = (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))

        # Extract properties
        properties = {
            'drill_depth': max(z_coords) - min(z_coords),
            'safe_height': max(z_coords),
            'bottom_depth': min(z_coords),
            'step_count': step_count
        }

        return OperationGroup(
            name=f"Drill_{drill_num+1}",
            type=OperationType.DRILLING,
            indices=indices,
            center=center,
            bounds=bounds,
            properties=properties
        )

    def _convert_large_holes_to_drilling(self):
        """将大孔（闭合环形轮廓）转换为钻孔操作"""
        # 识别需要转换的轮廓
        large_hole_contours = []
        remaining_contours = []

        for contour in self.contouring_operations:
            # 获取轮廓点
            points = [self.motion_commands[i].position for i in contour.indices
                     if i < len(self.motion_commands) and self.motion_commands[i].position]

            if not points:
                remaining_contours.append(contour)
                continue

            # 计算半径
            center_x = contour.center[0]
            center_y = contour.center[1]
            distances = [np.sqrt((p.x - center_x)**2 + (p.y - center_y)**2) for p in points]
            avg_radius = sum(distances) / len(distances)

            # 检查闭合度
            start = np.array([points[0].x, points[0].y])
            end = np.array([points[-1].x, points[-1].y])
            closure = np.linalg.norm(end - start)

            # 大孔条件：半径2-20mm，点数>20，闭合良好(<10mm)
            if 2.0 < avg_radius < 20.0 and len(points) > 20 and closure < 10.0:
                large_hole_contours.append((contour, avg_radius))
            else:
                remaining_contours.append(contour)

        # 将大孔转换为钻孔操作
        drill_start_num = len(self.drilling_operations)
        for i, (contour, radius) in enumerate(large_hole_contours):
            # 获取轮廓的索引列表（副本）
            indices = list(contour.indices)

            # 向前查找并包含快速定位指令（作为钻孔操作的一部分）
            # 这样移动和删除时会一起处理
            start_idx = indices[0]
            end_idx = indices[-1]
            transition_indices_before = []
            transition_indices_after = []

            # 向前查找进入孔的过渡指令
            for idx in range(max(0, start_idx - 3), start_idx):
                cmd = self.motion_commands[idx]
                if cmd.position:
                    # 检查是否是快速定位到这个孔附近（XY距离<100mm，Z>600mm）
                    dx = cmd.position.x - contour.center[0]
                    dy = cmd.position.y - contour.center[1]
                    distance = (dx**2 + dy**2)**0.5

                    if distance < 100.0 and cmd.position.z > 600.0:
                        # 这是定位到当前孔的指令，应该包含在钻孔操作中
                        transition_indices_before.append(idx)

            # 向后查找退出孔的快速返回指令
            # 查找紧接在轮廓结束后的1-2个指令
            for idx in range(end_idx + 1, min(end_idx + 3, len(self.motion_commands))):
                cmd = self.motion_commands[idx]
                if cmd.position:
                    # 检查是否是快速返回到安全高度（Z>600mm，且命令类型为PTP/G00）
                    # 且XY位置接近孔中心（距离<100mm）
                    dx = cmd.position.x - contour.center[0]
                    dy = cmd.position.y - contour.center[1]
                    distance = (dx**2 + dy**2)**0.5

                    if distance < 100.0 and cmd.position.z > 600.0 and cmd.command_type in ['PTP', 'G00']:
                        # 这是从当前孔快速退回的指令
                        transition_indices_after.append(idx)
                    else:
                        # 遇到非快速返回指令，停止查找
                        break

            # 将过渡指令添加到索引的开头和结尾
            indices = transition_indices_before + indices + transition_indices_after

            # 创建钻孔操作组
            drill_op = OperationGroup(
                name=f"Drill_{drill_start_num + i + 1}",
                type=OperationType.DRILLING,
                indices=indices,  # 现在包含了进入和退出的过渡指令
                center=contour.center,
                bounds=contour.bounds,
                properties={
                    'drill_depth': radius * 2,  # 用直径作为深度
                    'safe_height': contour.center[2],
                    'bottom_depth': contour.center[2],
                    'step_count': len(indices),  # 更新步骤数
                    'is_large_hole': True,  # 标记为大孔
                    'radius': radius
                }
            )
            self.drilling_operations.append(drill_op)

        # 更新轮廓列表
        self.contouring_operations = remaining_contours

    def _is_contouring_pattern(self, start_idx):
        """Check if contouring pattern exists / 检查是否为轮廓加工模式
        Pattern: Z remains relatively constant, XY changes continuously
        """
        if start_idx >= len(self.motion_commands):
            return False

        # 只检查LIN指令作为轮廓起点（排除PTP快速定位）
        start_cmd = self.motion_commands[start_idx]
        if start_cmd.command_type != 'LIN' or not start_cmd.position:
            return False

        # Check at least 5 consecutive points with positions
        # 向后查找足够的点（最多检查20个指令以收集5个有效点）
        z_coords = []
        xy_positions = []
        check_limit = min(start_idx + 20, len(self.motion_commands))

        for idx in range(start_idx, check_limit):
            cmd = self.motion_commands[idx]
            if cmd.position:
                z_coords.append(cmd.position.z)
                xy_positions.append((cmd.position.x, cmd.position.y))
                if len(z_coords) >= 5:
                    break

        if len(z_coords) < 5:
            return False

        # Z should remain relatively constant (within 2mm)
        z_range = max(z_coords) - min(z_coords)

        # Check if Z is at "machining depth" range
        avg_z = sum(z_coords) / len(z_coords)

        # Adaptive Z direction detection
        # For negative Z: below -20mm (machining below reference)
        # For positive Z: above 300mm (machining above reference, like A005SM at ~391mm)
        z_threshold_min = 20.0  # Minimum depth threshold

        if self.z_direction == 'negative':
            # Negative Z system: machining below reference plane
            z_at_machining_depth = avg_z < -z_threshold_min
        else:
            # Positive Z system: machining above reference plane
            z_at_machining_depth = avg_z > z_threshold_min

        # Check XY movement (contours should have significant XY motion)
        if len(xy_positions) >= 2:
            xy_distances = []
            for i in range(1, len(xy_positions)):
                dx = xy_positions[i][0] - xy_positions[i-1][0]
                dy = xy_positions[i][1] - xy_positions[i-1][1]
                distance = (dx**2 + dy**2)**0.5
                xy_distances.append(distance)

            total_xy_motion = sum(xy_distances)
        else:
            total_xy_motion = 0

        # Contouring criteria:
        # 1. Z variation is small (within 2mm)
        # 2. Z is at machining depth
        # 3. XY motion is significant (>1mm total for 5 points, 降低阈值以识别小圆弧)
        if z_range < 2.0 and z_at_machining_depth and total_xy_motion > 1.0:
            return True

        return False

    def _extract_contour_group(self, start_idx, contour_num):
        """Extract contour operation group / 提取轮廓操作组"""
        # Find all consecutive points with similar Z
        indices = [start_idx]
        base_z = self.motion_commands[start_idx].position.z

        i = start_idx + 1
        consecutive_breaks = 0  # 连续中断计数

        while i < len(self.motion_commands):
            cmd = self.motion_commands[i]

            # 如果是LIN指令且有位置信息
            if cmd.command_type == 'LIN' and cmd.position:
                if abs(cmd.position.z - base_z) < 2.0:  # Same Z level
                    indices.append(i)
                    consecutive_breaks = 0  # 重置中断计数
                    i += 1
                else:
                    # Z变化过大，轮廓结束
                    break
            else:
                # 非LIN指令或无位置，允许少量中断（如PTP定位）
                consecutive_breaks += 1
                if consecutive_breaks > 2:  # 连续超过2个非加工指令，轮廓结束
                    break
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

        # Initialize view state variables
        self.initial_xlim = None
        self.initial_ylim = None
        self.initial_zlim = None
        self.user_has_zoomed = False

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

        # === View Control Panel / 视图控制面板 ===
        view_panel_top = 0.20
        self.fig.text(0.02, view_panel_top + 0.02, 'View Controls:', fontsize=10, fontweight='bold')

        # Zoom buttons / 缩放按钮
        ax_zoom_in = self.fig.add_axes([0.02, view_panel_top - 0.03, 0.08, 0.03])
        self.btn_zoom_in = Button(ax_zoom_in, 'Zoom In (+)', color='lightblue')
        self.btn_zoom_in.on_clicked(self.zoom_in)

        ax_zoom_out = self.fig.add_axes([0.11, view_panel_top - 0.03, 0.08, 0.03])
        self.btn_zoom_out = Button(ax_zoom_out, 'Zoom Out (-)', color='lightblue')
        self.btn_zoom_out.on_clicked(self.zoom_out)

        ax_reset_view = self.fig.add_axes([0.20, view_panel_top - 0.03, 0.08, 0.03])
        self.btn_reset_view = Button(ax_reset_view, 'Reset View', color='lightgray')
        self.btn_reset_view.on_clicked(self.reset_view)

        # View presets / 视角预设
        ax_view_top = self.fig.add_axes([0.02, view_panel_top - 0.07, 0.06, 0.03])
        self.btn_view_top = Button(ax_view_top, 'Top', color='wheat')
        self.btn_view_top.on_clicked(lambda e: self.set_view_angle(90, -90))

        ax_view_front = self.fig.add_axes([0.09, view_panel_top - 0.07, 0.06, 0.03])
        self.btn_view_front = Button(ax_view_front, 'Front', color='wheat')
        self.btn_view_front.on_clicked(lambda e: self.set_view_angle(0, -90))

        ax_view_side = self.fig.add_axes([0.16, view_panel_top - 0.07, 0.06, 0.03])
        self.btn_view_side = Button(ax_view_side, 'Side', color='wheat')
        self.btn_view_side.on_clicked(lambda e: self.set_view_angle(0, 0))

        ax_view_iso = self.fig.add_axes([0.23, view_panel_top - 0.07, 0.06, 0.03])
        self.btn_view_iso = Button(ax_view_iso, 'Iso', color='wheat')
        self.btn_view_iso.on_clicked(lambda e: self.set_view_angle(30, -60))

        # Connect mouse events for selection and zoom
        self.fig.canvas.mpl_connect('button_press_event', self.on_canvas_click)
        self.fig.canvas.mpl_connect('scroll_event', self.on_scroll)

    def update_3d_plot(self):
        """Update 3D view / 更新3D视图"""
        # Save current view limits if user has zoomed
        saved_xlim = None
        saved_ylim = None
        saved_zlim = None
        saved_elev = None
        saved_azim = None

        if self.user_has_zoomed:
            try:
                saved_xlim = self.ax_3d.get_xlim()
                saved_ylim = self.ax_3d.get_ylim()
                saved_zlim = self.ax_3d.get_zlim()
                saved_elev = self.ax_3d.elev
                saved_azim = self.ax_3d.azim
            except:
                pass

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

            # Only set default view limits if user hasn't zoomed
            if not self.user_has_zoomed or saved_xlim is None:
                self.ax_3d.set_xlim(mid_x - max_range, mid_x + max_range)
                self.ax_3d.set_ylim(mid_y - max_range, mid_y + max_range)
                self.ax_3d.set_zlim(mid_z - max_range, mid_z + max_range)
            else:
                # Restore user's zoom state
                self.ax_3d.set_xlim(saved_xlim)
                self.ax_3d.set_ylim(saved_ylim)
                self.ax_3d.set_zlim(saved_zlim)
                if saved_elev is not None and saved_azim is not None:
                    self.ax_3d.view_init(elev=saved_elev, azim=saved_azim)

            # Save initial view limits for reset (only once)
            if self.initial_xlim is None:
                self.initial_xlim = (mid_x - max_range, mid_x + max_range)
                self.initial_ylim = (mid_y - max_range, mid_y + max_range)
                self.initial_zlim = (mid_z - max_range, mid_z + max_range)

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

        # Reset zoom state
        self.user_has_zoomed = False
        self.initial_xlim = None
        self.initial_ylim = None
        self.initial_zlim = None

        self.update_3d_plot()
        self.update_info()
        print("✓ All changes undone")  # 已撤销所有修改

    def delete_selected_drilling(self, event):
        """Delete selected drilling operations / 删除选中的钻孔操作"""
        if not self.selected_drilling_names:
            print("✗ No drilling operations selected")  # 未选中钻孔操作
            return

        # Collect all indices to delete
        # 注意：大孔的indices已经在_convert_large_holes_to_drilling()中包含了前面的过渡指令
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

                # 根据文件扩展名选择合适的解析器
                file_ext = os.path.splitext(file_path)[1].lower()

                if file_ext in ['.nc', '.NC']:
                    # 使用NC解析器
                    from kuka_nc_parser import KukaNCParser
                    new_parser = KukaNCParser(file_path)
                    print("  ℹ Using NC/G-code parser")
                else:
                    # 默认使用SRC解析器
                    new_parser = KUKASrcParser(file_path)
                    print("  ℹ Using KUKA SRC parser")

                new_parser.parse()

                # Update current parser
                self.parser = new_parser
                self.original_parser = copy.deepcopy(new_parser)

                # Clear selections
                self.selected_drilling_names.clear()
                self.selected_contour_names.clear()

                # Reset zoom state for new file
                self.user_has_zoomed = False
                self.initial_xlim = None
                self.initial_ylim = None
                self.initial_zlim = None

                # Re-detect operations
                detector = OperationDetector(self.parser.motion_commands)
                self.drilling_operations, self.contouring_operations = detector.detect_all_operations()

                # Update display
                self.update_3d_plot()
                self.update_info()

                print(f"✓ File loaded successfully: {file_path}")
            except Exception as e:
                print(f"✗ Error loading file: {e}")
                import traceback
                traceback.print_exc()
        elif file_path:
            print(f"✗ File not found: {file_path}")

    def open_file(self, event):
        """Open file dialog to select a file / 打开文件对话框选择文件"""
        file_path = None

        if HAS_TKINTER:
            # Use tkinter file dialog (cross-platform GUI)
            root = tk.Tk()
            root.withdraw()  # Hide the main window
            root.attributes('-topmost', True)  # Make dialog appear on top

            # Open file dialog - 支持多种文件类型
            file_path = filedialog.askopenfilename(
                title='Select KUKA file (.src, .nc)',
                filetypes=[
                    ('All Supported', '*.src *.nc *.NC'),
                    ('KUKA Source Files', '*.src'),
                    ('NC/G-code Files', '*.nc *.NC'),
                    ('All Files', '*.*')
                ],
                initialdir='.'
            )

            root.destroy()  # Clean up
        else:
            # Use simple text-based file picker
            file_path = simple_file_picker(title="Select KUKA file (.src, .nc, .NC)")

        # Load the selected file
        if file_path:
            self.load_file_from_path(file_path)

    def save_file(self, event):
        """Save file / 保存文件"""
        if not self.parser:
            print("\n✗ No file loaded. Please open a file first.")
            return

        file_path = None

        # 检测原始文件类型
        original_ext = os.path.splitext(self.parser.filename)[1].lower()
        is_nc_file = original_ext in ['.nc', '.NC']

        if HAS_TKINTER:
            # Use tkinter save dialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)

            # 根据原始文件类型设置保存对话框
            if is_nc_file:
                default_ext = '.nc'
                filetypes = [
                    ('NC/G-code Files', '*.nc *.NC'),
                    ('KUKA Source Files', '*.src'),
                    ('All Files', '*.*')
                ]
                default_name = self.parser.filename.replace(original_ext, f'_modified{original_ext}')
            else:
                default_ext = '.src'
                filetypes = [
                    ('KUKA Source Files', '*.src'),
                    ('NC/G-code Files', '*.nc *.NC'),
                    ('All Files', '*.*')
                ]
                default_name = self.parser.filename.replace('.src', '_modified.src')

            # Open save dialog
            file_path = filedialog.asksaveasfilename(
                title='Save Modified File',
                defaultextension=default_ext,
                filetypes=filetypes,
                initialfile=os.path.basename(default_name)
            )

            root.destroy()
        else:
            # Simple text-based save dialog
            if is_nc_file:
                default_name = self.parser.filename.replace(original_ext, f'_modified{original_ext}')
            else:
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
                # 根据保存的文件扩展名选择导出方法
                save_ext = os.path.splitext(file_path)[1].lower()

                if save_ext in ['.nc', '.NC']:
                    # 导出为NC文件
                    if hasattr(self.parser, 'export_to_nc'):
                        self.parser.export_to_nc(file_path)
                    else:
                        print("✗ Current parser doesn't support NC export")
                        return
                else:
                    # 导出为SRC文件
                    if hasattr(self.parser, 'export_to_src'):
                        self.parser.export_to_src(file_path)
                    else:
                        print("✗ Current parser doesn't support SRC export")
                        return

                print(f"\n✓ File saved to: {file_path}")
            except Exception as e:
                print(f"✗ Error saving file: {e}")
                import traceback
                traceback.print_exc()

    def zoom_in(self, event):
        """Zoom in the 3D view / 放大视图"""
        if not self.parser:
            return

        # Get current limits
        xlim = self.ax_3d.get_xlim()
        ylim = self.ax_3d.get_ylim()
        zlim = self.ax_3d.get_zlim()

        # Calculate center
        x_center = (xlim[0] + xlim[1]) / 2
        y_center = (ylim[0] + ylim[1]) / 2
        z_center = (zlim[0] + zlim[1]) / 2

        # Zoom factor: 0.8 makes the view range smaller (zoom in)
        zoom_factor = 0.8
        x_range = (xlim[1] - xlim[0]) * zoom_factor / 2
        y_range = (ylim[1] - ylim[0]) * zoom_factor / 2
        z_range = (zlim[1] - zlim[0]) * zoom_factor / 2

        # Set new limits
        self.ax_3d.set_xlim(x_center - x_range, x_center + x_range)
        self.ax_3d.set_ylim(y_center - y_range, y_center + y_range)
        self.ax_3d.set_zlim(z_center - z_range, z_center + z_range)

        self.user_has_zoomed = True  # Mark that user has zoomed
        self.fig.canvas.draw_idle()

    def zoom_out(self, event):
        """Zoom out the 3D view / 缩小视图"""
        if not self.parser:
            return

        # Get current limits
        xlim = self.ax_3d.get_xlim()
        ylim = self.ax_3d.get_ylim()
        zlim = self.ax_3d.get_zlim()

        # Calculate center
        x_center = (xlim[0] + xlim[1]) / 2
        y_center = (ylim[0] + ylim[1]) / 2
        z_center = (zlim[0] + zlim[1]) / 2

        # Zoom factor: 1.25 makes the view range larger (zoom out)
        zoom_factor = 1.25
        x_range = (xlim[1] - xlim[0]) * zoom_factor / 2
        y_range = (ylim[1] - ylim[0]) * zoom_factor / 2
        z_range = (zlim[1] - zlim[0]) * zoom_factor / 2

        # Set new limits
        self.ax_3d.set_xlim(x_center - x_range, x_center + x_range)
        self.ax_3d.set_ylim(y_center - y_range, y_center + y_range)
        self.ax_3d.set_zlim(z_center - z_range, z_center + z_range)

        self.user_has_zoomed = True  # Mark that user has zoomed
        self.fig.canvas.draw_idle()

    def reset_view(self, event):
        """Reset view to initial state / 重置视图"""
        if not self.parser or self.initial_xlim is None:
            return

        self.ax_3d.set_xlim(self.initial_xlim)
        self.ax_3d.set_ylim(self.initial_ylim)
        self.ax_3d.set_zlim(self.initial_zlim)

        # Reset to default 3D view angle
        self.ax_3d.view_init(elev=30, azim=-60)

        self.user_has_zoomed = False  # Clear zoom state
        self.fig.canvas.draw_idle()
        print("✓ View reset to initial state")

    def set_view_angle(self, elev, azim):
        """Set view angle / 设置视角"""
        if not self.parser:
            return

        self.ax_3d.view_init(elev=elev, azim=azim)
        self.fig.canvas.draw_idle()

    def on_scroll(self, event):
        """Handle mouse scroll for zoom / 处理鼠标滚轮缩放"""
        # Only handle scroll in 3D axes
        if event.inaxes != self.ax_3d:
            return

        if not self.parser:
            return

        # Get current limits
        xlim = self.ax_3d.get_xlim()
        ylim = self.ax_3d.get_ylim()
        zlim = self.ax_3d.get_zlim()

        # Calculate center
        x_center = (xlim[0] + xlim[1]) / 2
        y_center = (ylim[0] + ylim[1]) / 2
        z_center = (zlim[0] + zlim[1]) / 2

        # Zoom factor based on scroll direction
        if event.button == 'up':
            zoom_factor = 0.9  # Zoom in
        else:
            zoom_factor = 1.1  # Zoom out

        x_range = (xlim[1] - xlim[0]) * zoom_factor / 2
        y_range = (ylim[1] - ylim[0]) * zoom_factor / 2
        z_range = (zlim[1] - zlim[0]) * zoom_factor / 2

        # Set new limits
        self.ax_3d.set_xlim(x_center - x_range, x_center + x_range)
        self.ax_3d.set_ylim(y_center - y_range, y_center + y_range)
        self.ax_3d.set_zlim(z_center - z_range, z_center + z_range)

        self.user_has_zoomed = True  # Mark that user has zoomed
        self.fig.canvas.draw_idle()

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
