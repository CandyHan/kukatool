#!/usr/bin/env python3
"""
KUKA .src 文件解析和可视化工具
功能：
1. 解析KUKA .src文件中的运动指令
2. 3D可视化加工路径
3. 编辑和修改坐标点
4. 生成分析报告
5. 导出修改后的.src文件
"""

import re
import json
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, asdict
import copy


@dataclass
class Position:
    """位置数据结构"""
    x: float
    y: float
    z: float
    a: float  # Yaw
    b: float  # Pitch
    c: float  # Roll

    def to_dict(self):
        return asdict(self)

    def offset(self, dx: float = 0, dy: float = 0, dz: float = 0):
        """坐标偏移"""
        return Position(
            self.x + dx, self.y + dy, self.z + dz,
            self.a, self.b, self.c
        )


@dataclass
class JointPosition:
    """关节角度数据结构"""
    a1: float
    a2: float
    a3: float
    a4: float
    a5: float
    a6: float

    def to_dict(self):
        return asdict(self)


@dataclass
class MotionCommand:
    """运动指令数据结构"""
    line_number: int
    command_type: str  # PTP, LIN, CIRC
    position: Optional[Position] = None
    joint_position: Optional[JointPosition] = None
    velocity: Optional[float] = None
    velocity_comment: Optional[str] = None
    continuous: bool = False  # C_VEL标志
    auxiliary_point: Optional[Position] = None  # CIRC辅助点
    original_line: str = ""
    status: Optional[int] = None  # S参数：机器人配置状态
    turn: Optional[int] = None  # T参数：关节转数

    def to_dict(self):
        result = {
            'line_number': self.line_number,
            'command_type': self.command_type,
            'continuous': self.continuous,
            'original_line': self.original_line
        }
        if self.position:
            result['position'] = self.position.to_dict()
        if self.joint_position:
            result['joint_position'] = self.joint_position.to_dict()
        if self.velocity is not None:
            result['velocity'] = self.velocity
        if self.velocity_comment:
            result['velocity_comment'] = self.velocity_comment
        if self.auxiliary_point:
            result['auxiliary_point'] = self.auxiliary_point.to_dict()
        return result


class KUKASrcParser:
    """KUKA .src文件解析器"""

    def __init__(self, filename: str):
        self.filename = filename
        self.lines = []
        self.motion_commands: List[MotionCommand] = []
        self.base_frame: Optional[Position] = None
        self.tool_frame: Optional[Position] = None
        self.program_name = ""
        self.current_velocity = None
        self.current_velocity_comment = None  # 保存速度注释

    def parse(self):
        """解析.src文件"""
        with open(self.filename, 'r', encoding='utf-8') as f:
            self.lines = f.readlines()

        for i, line in enumerate(self.lines, 1):
            line = line.strip()

            # 解析程序名
            if line.startswith('DEF '):
                match = re.match(r'DEF\s+(\w+)\s*\(', line)
                if match:
                    self.program_name = match.group(1)

            # 解析BASE坐标系
            elif '$BASE=' in line:
                self.base_frame = self._parse_position(line)

            # 解析TOOL坐标系
            elif '$TOOL=' in line:
                self.tool_frame = self._parse_position(line)

            # 解析速度设置
            elif '$VEL.CP=' in line:
                vel_match = re.search(r'\$VEL\.CP\s*=\s*([\d.]+)', line)
                if vel_match:
                    self.current_velocity = float(vel_match.group(1))
                    # 查找注释
                    comment_match = re.search(r';(.+)', line)
                    self.current_velocity_comment = comment_match.group(1).strip() if comment_match else None

            # 解析运动指令
            elif line.startswith(('PTP ', 'LIN ', 'CIRC ')):
                cmd = self._parse_motion_command(i, line)
                if cmd:
                    self.motion_commands.append(cmd)

        return self

    def _parse_position(self, line: str) -> Optional[Position]:
        """解析笛卡尔坐标"""
        # 匹配 {X ..., Y ..., Z ..., A ..., B ..., C ...}
        match = re.search(
            r'X\s*([-\d.]+).*?Y\s*([-\d.]+).*?Z\s*([-\d.]+).*?'
            r'A\s*([-\d.]+).*?B\s*([-\d.]+).*?C\s*([-\d.]+)',
            line
        )
        if match:
            return Position(
                float(match.group(1)),
                float(match.group(2)),
                float(match.group(3)),
                float(match.group(4)),
                float(match.group(5)),
                float(match.group(6))
            )
        return None

    def _parse_joint_position(self, line: str) -> Optional[JointPosition]:
        """解析关节角度"""
        match = re.search(
            r'A1\s*([-\d.]+).*?A2\s*([-\d.]+).*?A3\s*([-\d.]+).*?'
            r'A4\s*([-\d.]+).*?A5\s*([-\d.]+).*?A6\s*([-\d.]+)',
            line
        )
        if match:
            return JointPosition(
                float(match.group(1)),
                float(match.group(2)),
                float(match.group(3)),
                float(match.group(4)),
                float(match.group(5)),
                float(match.group(6))
            )
        return None

    def _parse_motion_command(self, line_num: int, line: str) -> Optional[MotionCommand]:
        """解析运动指令"""
        # 确定指令类型
        cmd_type = None
        if line.startswith('PTP '):
            cmd_type = 'PTP'
        elif line.startswith('LIN '):
            cmd_type = 'LIN'
        elif line.startswith('CIRC '):
            cmd_type = 'CIRC'
        else:
            return None

        # 检查是否连续运动
        continuous = 'C_VEL' in line

        # 创建指令对象
        cmd = MotionCommand(
            line_number=line_num,
            command_type=cmd_type,
            velocity=self.current_velocity,
            velocity_comment=self.current_velocity_comment,
            continuous=continuous,
            original_line=line
        )

        # 解析坐标（笛卡尔或关节）
        pos = self._parse_position(line)
        if pos:
            cmd.position = pos
        else:
            joint_pos = self._parse_joint_position(line)
            if joint_pos:
                cmd.joint_position = joint_pos

        # 解析CIRC的辅助点
        if cmd_type == 'CIRC':
            # CIRC有两个点：辅助点和终点
            parts = re.findall(r'\{[^}]+\}', line)
            if len(parts) >= 2:
                aux_str = parts[0]
                end_str = parts[1]
                cmd.auxiliary_point = self._parse_position(aux_str)
                cmd.position = self._parse_position(end_str)

        # 解析S和T参数（主要用于PTP指令）
        s_match = re.search(r',S\s*(\d+)', line)
        if s_match:
            cmd.status = int(s_match.group(1))

        t_match = re.search(r',T\s*(\d+)', line)
        if t_match:
            cmd.turn = int(t_match.group(1))

        return cmd

    def get_statistics(self) -> Dict:
        """获取统计信息"""
        stats = {
            'program_name': self.program_name,
            'total_commands': len(self.motion_commands),
            'ptp_commands': sum(1 for c in self.motion_commands if c.command_type == 'PTP'),
            'lin_commands': sum(1 for c in self.motion_commands if c.command_type == 'LIN'),
            'circ_commands': sum(1 for c in self.motion_commands if c.command_type == 'CIRC'),
            'base_frame': self.base_frame.to_dict() if self.base_frame else None,
            'tool_frame': self.tool_frame.to_dict() if self.tool_frame else None,
        }

        # 计算工作空间范围
        cartesian_cmds = [c for c in self.motion_commands if c.position]
        if cartesian_cmds:
            x_coords = [c.position.x for c in cartesian_cmds]
            y_coords = [c.position.y for c in cartesian_cmds]
            z_coords = [c.position.z for c in cartesian_cmds]

            stats['workspace'] = {
                'x_range': [min(x_coords), max(x_coords)],
                'y_range': [min(y_coords), max(y_coords)],
                'z_range': [min(z_coords), max(z_coords)],
                'x_span': max(x_coords) - min(x_coords),
                'y_span': max(y_coords) - min(y_coords),
                'z_span': max(z_coords) - min(z_coords),
            }

        # 速度统计
        velocities = [c.velocity for c in self.motion_commands if c.velocity is not None]
        if velocities:
            stats['velocity_stats'] = {
                'min': min(velocities),
                'max': max(velocities),
                'unique_values': sorted(set(velocities))
            }

        return stats

    def get_cartesian_points(self) -> List[Tuple[float, float, float]]:
        """获取所有笛卡尔坐标点"""
        points = []
        for cmd in self.motion_commands:
            if cmd.position:
                points.append((cmd.position.x, cmd.position.y, cmd.position.z))
        return points

    def filter_commands(self,
                       command_type: Optional[str] = None,
                       x_range: Optional[Tuple[float, float]] = None,
                       y_range: Optional[Tuple[float, float]] = None,
                       z_range: Optional[Tuple[float, float]] = None) -> List[MotionCommand]:
        """过滤运动指令"""
        filtered = self.motion_commands

        if command_type:
            filtered = [c for c in filtered if c.command_type == command_type]

        if x_range and any(c.position for c in filtered):
            filtered = [c for c in filtered if c.position and x_range[0] <= c.position.x <= x_range[1]]

        if y_range and any(c.position for c in filtered):
            filtered = [c for c in filtered if c.position and y_range[0] <= c.position.y <= y_range[1]]

        if z_range and any(c.position for c in filtered):
            filtered = [c for c in filtered if c.position and z_range[0] <= c.position.z <= z_range[1]]

        return filtered

    def offset_all_points(self, dx: float = 0, dy: float = 0, dz: float = 0):
        """对所有笛卡尔坐标进行偏移"""
        for cmd in self.motion_commands:
            if cmd.position:
                cmd.position = cmd.position.offset(dx, dy, dz)
            if cmd.auxiliary_point:
                cmd.auxiliary_point = cmd.auxiliary_point.offset(dx, dy, dz)

        # 同时偏移BASE坐标系
        if self.base_frame:
            self.base_frame = self.base_frame.offset(dx, dy, dz)

    def export_to_src(self, output_filename: str):
        """导出为新的.src文件"""
        # 重建文件内容
        new_lines = []
        cmd_index = 0
        current_velocity = None  # 跟踪当前速度

        # Build a set of line numbers that have motion commands
        motion_line_numbers = set(cmd.line_number for cmd in self.motion_commands)

        # 找到第一条运动指令的行号（在此之前的速度设置是初始化设置，应该保留）
        first_motion_line = min(motion_line_numbers) if motion_line_numbers else float('inf')

        # 找到下一条LIN/CIRC指令的行号（用于判断PTP之前的速度行是否保留）
        def get_next_lin_circ_line() -> int:
            """获取下一条LIN或CIRC指令的行号"""
            for cmd in self.motion_commands[cmd_index:]:
                if cmd.command_type in ('LIN', 'CIRC'):
                    return cmd.line_number
            return float('inf')

        # 统计清理的速度行数
        velocity_lines_removed = 0

        for i, line in enumerate(self.lines):
            line_num = i + 1
            original_line = line.rstrip()
            stripped_line = original_line.strip()

            # 检查是否是运动指令行（在原文件中）
            is_original_motion_line = stripped_line.startswith(('PTP ', 'LIN ', 'CIRC '))

            # 处理运动指令
            if is_original_motion_line:
                if line_num in motion_line_numbers:
                    # This line has a corresponding motion command, rebuild it
                    if cmd_index < len(self.motion_commands):
                        cmd = self.motion_commands[cmd_index]
                        if cmd.line_number == line_num:
                            # 只为LIN和CIRC指令重建速度控制行
                            if cmd.command_type in ('LIN', 'CIRC'):
                                if cmd.velocity is not None and cmd.velocity != current_velocity:
                                    # 查找原始的速度控制行以保留注释
                                    vel_comment = cmd.velocity_comment if cmd.velocity_comment else ''
                                    if vel_comment:
                                        vel_line = f'$VEL.CP={cmd.velocity}  ;{vel_comment}\n'
                                    else:
                                        vel_line = f'$VEL.CP={cmd.velocity}\n'
                                    new_lines.append(vel_line)
                                    current_velocity = cmd.velocity

                            # 输出运动指令
                            new_line = self._rebuild_motion_line(cmd)
                            new_lines.append(new_line + '\n')
                            cmd_index += 1
                        else:
                            # Line numbers don't match, skip this line (it was deleted)
                            continue
                else:
                    # This motion line was deleted, skip it
                    continue

            # 处理速度控制行
            elif stripped_line.startswith('$VEL.CP='):
                # 保留第一条运动指令之前的所有速度设置（初始化设置）
                if line_num < first_motion_line:
                    new_lines.append(line)
                    # 更新当前速度跟踪
                    vel_match = re.search(r'\$VEL\.CP\s*=\s*([\d.]+)', stripped_line)
                    if vel_match:
                        current_velocity = float(vel_match.group(1))
                else:
                    # 在运动指令区域内，需要判断是否保留
                    # 查找下一条非速度、非空白行
                    next_non_vel_line_num = line_num + 1
                    while next_non_vel_line_num <= len(self.lines):
                        next_line = self.lines[next_non_vel_line_num - 1].strip()
                        if next_line and not next_line.startswith('$VEL.CP='):
                            break
                        next_non_vel_line_num += 1

                    # 检查下一行是否是PTP指令
                    is_before_ptp = False
                    if next_non_vel_line_num <= len(self.lines):
                        next_line = self.lines[next_non_vel_line_num - 1].strip()
                        is_before_ptp = next_line.startswith('PTP ')

                    # 保留PTP之前的速度行
                    if is_before_ptp:
                        new_lines.append(line)
                        # 更新当前速度跟踪
                        vel_match = re.search(r'\$VEL\.CP\s*=\s*([\d.]+)', stripped_line)
                        if vel_match:
                            current_velocity = float(vel_match.group(1))
                    else:
                        # 跳过LIN/CIRC之前的速度行（我们会重建它们）
                        velocity_lines_removed += 1
                        continue

            # 检查是否是BASE或TOOL定义
            elif '$BASE=' in stripped_line and self.base_frame:
                new_line = self._rebuild_frame_line('$BASE', self.base_frame)
                new_lines.append(new_line + '\n')
            elif '$TOOL=' in stripped_line and self.tool_frame:
                new_line = self._rebuild_frame_line('$TOOL', self.tool_frame)
                new_lines.append(new_line + '\n')
            else:
                # Keep non-motion lines (comments, structure, etc.)
                new_lines.append(line)

        # 写入文件
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

        print(f"✓ 文件已导出到: {output_filename} (重建了LIN/CIRC速度控制行，移除了{velocity_lines_removed}条冗余速度行)")

    def _rebuild_motion_line(self, cmd: MotionCommand) -> str:
        """重建运动指令行"""
        parts = [cmd.command_type]

        if cmd.command_type == 'CIRC':
            # CIRC需要两个点
            if cmd.auxiliary_point and cmd.position:
                aux_str = self._position_to_string(cmd.auxiliary_point, cmd.status, cmd.turn)
                pos_str = self._position_to_string(cmd.position)
                parts.append(f' {aux_str},{pos_str}')
        elif cmd.position:
            # 笛卡尔坐标
            parts.append(f'  {self._position_to_string(cmd.position, cmd.status, cmd.turn)}')
        elif cmd.joint_position:
            # 关节坐标
            jp = cmd.joint_position
            joint_str = f'{{A1 {jp.a1:.4f},A2 {jp.a2:.4f},A3 {jp.a3:.4f},' \
                       f'A4 {jp.a4:.4f},A5 {jp.a5:.4f},A6 {jp.a6:.4f}'

            # Add S and T parameters for joint positions
            if cmd.status is not None:
                joint_str += f',S {cmd.status}'
            if cmd.turn is not None:
                joint_str += f',T {cmd.turn}'

            joint_str += '}'
            parts.append(f'  {joint_str}')

        # 添加C_VEL标志
        if cmd.continuous:
            parts.append(' C_VEL')

        return ''.join(parts)

    def _position_to_string(self, pos: Position, status: Optional[int] = None, turn: Optional[int] = None) -> str:
        """位置转换为字符串"""
        result = (f'{{X {pos.x:.4f},Y {pos.y:.4f},Z {pos.z:.4f},'
                  f'A {pos.a:.4f},B {pos.b:.4f},C {pos.c:.4f}')

        # Add S and T parameters if provided
        if status is not None:
            result += f',S {status}'
        if turn is not None:
            result += f',T {turn}'

        result += '}'
        return result

    def _rebuild_frame_line(self, frame_name: str, pos: Position) -> str:
        """重建坐标系定义行"""
        return f'{frame_name}={self._position_to_string(pos)}'

    def export_to_json(self, output_filename: str):
        """导出为JSON格式"""
        data = {
            'program_name': self.program_name,
            'base_frame': self.base_frame.to_dict() if self.base_frame else None,
            'tool_frame': self.tool_frame.to_dict() if self.tool_frame else None,
            'statistics': self.get_statistics(),
            'motion_commands': [cmd.to_dict() for cmd in self.motion_commands]
        }

        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"✓ JSON文件已导出到: {output_filename}")


def print_statistics(stats: Dict):
    """打印统计信息"""
    print("\n" + "="*60)
    print(f"  KUKA程序分析报告 - {stats['program_name']}")
    print("="*60)

    print(f"\n📊 指令统计:")
    print(f"  总指令数: {stats['total_commands']}")
    print(f"  ├─ PTP (关节运动): {stats['ptp_commands']}")
    print(f"  ├─ LIN (直线运动): {stats['lin_commands']}")
    print(f"  └─ CIRC (圆弧运动): {stats['circ_commands']}")

    if stats.get('workspace'):
        ws = stats['workspace']
        print(f"\n📐 工作空间:")
        print(f"  X: [{ws['x_range'][0]:.2f}, {ws['x_range'][1]:.2f}] mm  (跨度: {ws['x_span']:.2f} mm)")
        print(f"  Y: [{ws['y_range'][0]:.2f}, {ws['y_range'][1]:.2f}] mm  (跨度: {ws['y_span']:.2f} mm)")
        print(f"  Z: [{ws['z_range'][0]:.2f}, {ws['z_range'][1]:.2f}] mm  (跨度: {ws['z_span']:.2f} mm)")

    if stats.get('velocity_stats'):
        vs = stats['velocity_stats']
        print(f"\n⚡ 速度统计:")
        print(f"  最小速度: {vs['min']*1000:.0f} mm/s")
        print(f"  最大速度: {vs['max']*1000:.0f} mm/s")
        print(f"  速度档位: {', '.join(f'{v*1000:.0f}' for v in vs['unique_values'])} mm/s")

    if stats.get('base_frame'):
        bf = stats['base_frame']
        print(f"\n🔧 BASE坐标系:")
        print(f"  位置: X={bf['x']:.2f}, Y={bf['y']:.2f}, Z={bf['z']:.2f} mm")

    if stats.get('tool_frame'):
        tf = stats['tool_frame']
        print(f"\n🛠️  TOOL坐标系:")
        print(f"  位置: X={tf['x']:.2f}, Y={tf['y']:.2f}, Z={tf['z']:.2f} mm")
        print(f"  姿态: A={tf['a']:.2f}, B={tf['b']:.2f}, C={tf['c']:.2f}°")

    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    import sys

    # 使用示例
    if len(sys.argv) < 2:
        print("使用方法: python kuka_src_parser.py <src文件路径>")
        print("\n示例:")
        print("  python kuka_src_parser.py B004XM.src")
        sys.exit(1)

    src_file = sys.argv[1]

    # 解析文件
    print(f"正在解析文件: {src_file}")
    parser = KUKASrcParser(src_file)
    parser.parse()

    # 显示统计信息
    stats = parser.get_statistics()
    print_statistics(stats)

    # 导出JSON
    json_file = src_file.replace('.src', '_analysis.json')
    parser.export_to_json(json_file)

    print("✓ 解析完成！")
    print("\n可用操作:")
    print("  1. 查看3D可视化: python kuka_visualizer.py " + src_file)
    print("  2. 编辑坐标: python kuka_editor.py " + src_file)
