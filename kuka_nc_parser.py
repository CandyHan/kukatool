#!/usr/bin/env python3
"""
KUKA NC (G-code) 文件解析器
支持解析标准G代码文件，兼容KUKA格式
功能：
1. 解析NC/G代码文件中的运动指令
2. 提取笛卡尔坐标点
3. 支持与gui_editor集成
"""

import re
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class Position:
    """位置坐标"""
    x: float
    y: float
    z: float
    a: Optional[float] = None  # A轴旋转角度 (Yaw)
    b: Optional[float] = None  # B轴旋转角度 (Pitch) - NC文件通常不使用
    c: Optional[float] = None  # C轴旋转角度 (Roll) - NC文件通常不使用


@dataclass
class MotionCommand:
    """运动指令"""
    line_number: int        # 行号（N代码）
    command_type: str       # G00, G01, G02, G03等
    position: Optional[Position]
    velocity: Optional[float]  # 进给速度 F
    spindle_speed: Optional[int]  # 主轴转速 S
    tool_number: Optional[int]  # 刀具号 T
    auxiliary_point: Optional[Position] = None
    original_line: str = ""  # 原始行内容


class KukaNCParser:
    """KUKA NC/G-code文件解析器"""

    def __init__(self, filename: str):
        self.filename = filename
        self.lines = []
        self.motion_commands: List[MotionCommand] = []
        self.program_name = filename.split('/')[-1]
        self.base_frame = None

        # 当前状态
        self.current_position = Position(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        self.current_velocity = None
        self.current_spindle = None
        self.current_tool = None

    def parse(self):
        """解析NC文件"""
        with open(self.filename, 'r', encoding='utf-8') as f:
            self.lines = f.readlines()

        for line_idx, line in enumerate(self.lines):
            line = line.strip()
            if not line or line.startswith(';'):  # 跳过空行和注释
                continue

            # 解析G代码行
            cmd = self._parse_gcode_line(line, line_idx)
            if cmd and cmd.position:
                self.motion_commands.append(cmd)

        print(f"✓ 解析完成: {len(self.motion_commands)} 个运动指令")

    def _parse_gcode_line(self, line: str, line_idx: int) -> Optional[MotionCommand]:
        """解析单行G代码"""
        # 提取行号
        n_match = re.search(r'N(\d+)', line, re.IGNORECASE)
        line_number = int(n_match.group(1)) if n_match else line_idx

        # 提取G指令类型
        g_match = re.search(r'G(\d+)', line, re.IGNORECASE)

        # 先提取坐标 - 即使没有G代码也可能有坐标(模态指令)
        position = self._extract_coordinates(line)

        # 如果既没有G代码也没有坐标,返回None
        if not g_match and not position:
            return None

        # 确定指令类型
        if g_match:
            g_code = f"G{g_match.group(1).zfill(2)}"
            command_type = self._map_gcode_to_kuka(g_code)
        else:
            # 模态指令 - 继续使用上一个G代码的类型
            # 默认为LIN
            command_type = 'LIN'

        # 提取速度
        f_match = re.search(r'F([\d.]+)', line, re.IGNORECASE)
        if f_match:
            # 将mm/min转换为m/s (归一化速度)
            self.current_velocity = float(f_match.group(1)) / 60000.0

        # 提取主轴转速
        s_match = re.search(r'S(\d+)', line, re.IGNORECASE)
        if s_match:
            self.current_spindle = int(s_match.group(1))

        # 提取刀具号
        t_match = re.search(r'T(\d+)', line, re.IGNORECASE)
        if t_match:
            self.current_tool = int(t_match.group(1))

        # 只有有坐标信息时才创建运动指令
        if not position:
            return None

        return MotionCommand(
            line_number=line_number,
            command_type=command_type,
            position=position,
            velocity=self.current_velocity,
            spindle_speed=self.current_spindle,
            tool_number=self.current_tool,
            original_line=line
        )

    def _map_gcode_to_kuka(self, g_code: str) -> str:
        """将G代码映射到KUKA指令类型"""
        mapping = {
            'G00': 'PTP',   # 快速定位
            'G01': 'LIN',   # 直线插补
            'G02': 'CIRC',  # 顺时针圆弧
            'G03': 'CIRC',  # 逆时针圆弧
        }
        return mapping.get(g_code, 'LIN')

    def _extract_coordinates(self, line: str) -> Optional[Position]:
        """从G代码行中提取坐标"""
        x_match = re.search(r'X([-+]?[\d.]+)', line, re.IGNORECASE)
        y_match = re.search(r'Y([-+]?[\d.]+)', line, re.IGNORECASE)
        z_match = re.search(r'Z([-+]?[\d.]+)', line, re.IGNORECASE)
        a_match = re.search(r'A([-+]?[\d.]+)', line, re.IGNORECASE)

        # 如果没有坐标信息，返回None
        if not (x_match or y_match or z_match):
            return None

        # 更新当前位置（模态）
        if x_match:
            self.current_position.x = float(x_match.group(1))
        if y_match:
            self.current_position.y = float(y_match.group(1))
        if z_match:
            self.current_position.z = float(z_match.group(1))
        if a_match:
            self.current_position.a = float(a_match.group(1))

        return Position(
            x=self.current_position.x,
            y=self.current_position.y,
            z=self.current_position.z,
            a=self.current_position.a if self.current_position.a is not None else 0.0,
            b=0.0,  # NC文件通常不使用B轴
            c=0.0   # NC文件通常不使用C轴
        )

    def offset_all_points(self, dx: float, dy: float, dz: float):
        """偏移所有点"""
        for cmd in self.motion_commands:
            if cmd.position:
                cmd.position.x += dx
                cmd.position.y += dy
                cmd.position.z += dz

    def export_to_nc(self, output_filename: str):
        """导出为新的NC文件"""
        # 创建行号到指令的映射（只包含运动指令）
        line_to_cmd = {}
        all_motion_line_nums = set()
        for cmd in self.motion_commands:
            line_to_cmd[cmd.line_number] = cmd
            all_motion_line_nums.add(cmd.line_number)

        # 创建原始文件中所有运动指令行号的集合
        import re
        original_motion_lines = set()
        for line in self.lines:
            n_match = re.search(r'N(\d+)', line, re.IGNORECASE)
            if n_match:
                line_num = int(n_match.group(1))
                # 检查这一行是否包含运动指令特征（G00, G01, G02, G03或坐标）
                if any(pattern in line.upper() for pattern in ['G00', 'G01', 'G02', 'G03', ' X', ' Y', ' Z']):
                    original_motion_lines.add(line_num)

        new_lines = []

        for line in self.lines:
            original_line = line.rstrip()

            # 尝试从行中提取行号
            n_match = re.search(r'N(\d+)', original_line, re.IGNORECASE)

            if n_match:
                line_num = int(n_match.group(1))

                # 如果这是运动指令行
                if line_num in original_motion_lines:
                    # 检查是否还存在（未被删除）
                    if line_num in line_to_cmd:
                        cmd = line_to_cmd[line_num]
                        # 优先使用原始行（保留格式），除非坐标被修改
                        # 简单判断：如果original_line中的坐标值匹配，就用原始行
                        if self._line_matches_command(original_line, cmd):
                            new_lines.append(line)
                        else:
                            # 坐标被修改了，需要重建
                            rebuilt_line = self._rebuild_gcode_line(cmd)
                            new_lines.append(rebuilt_line + '\n')
                    # 否则跳过这一行（已被删除）
                else:
                    # 不是运动指令行（初始化命令等），保留原样
                    new_lines.append(line)
            else:
                # 没有行号的行，保留原样
                new_lines.append(line)

        # 写入文件
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

        print(f"✓ 已保存到: {output_filename}")

    def _line_matches_command(self, line: str, cmd: MotionCommand) -> bool:
        """检查行是否与命令匹配（坐标未被修改）"""
        import re

        if not cmd.position:
            return True

        # 提取行中的坐标
        x_match = re.search(r'X([-+]?[\d.]+)', line, re.IGNORECASE)
        y_match = re.search(r'Y([-+]?[\d.]+)', line, re.IGNORECASE)
        z_match = re.search(r'Z([-+]?[\d.]+)', line, re.IGNORECASE)

        # 比较坐标（允许0.001mm的误差）
        tolerance = 0.001

        if x_match:
            line_x = float(x_match.group(1))
            if abs(line_x - cmd.position.x) > tolerance:
                return False

        if y_match:
            line_y = float(y_match.group(1))
            if abs(line_y - cmd.position.y) > tolerance:
                return False

        if z_match:
            line_z = float(z_match.group(1))
            if abs(line_z - cmd.position.z) > tolerance:
                return False

        return True

    def _rebuild_gcode_line(self, cmd: MotionCommand) -> str:
        """重建G代码行（保留原始格式）"""
        import re

        # 如果有原始行，基于原始行进行修改以保留格式
        if cmd.original_line:
            line = cmd.original_line

            # 只更新坐标值，保留其他部分
            if cmd.position:
                # 检查原始行中是否有X坐标
                if re.search(r'X[-+]?[\d.]+', line, re.IGNORECASE):
                    line = re.sub(r'X[-+]?[\d.]+', f'X{cmd.position.x:.3f}', line, flags=re.IGNORECASE)

                # 检查原始行中是否有Y坐标
                if re.search(r'Y[-+]?[\d.]+', line, re.IGNORECASE):
                    line = re.sub(r'Y[-+]?[\d.]+', f'Y{cmd.position.y:.3f}', line, flags=re.IGNORECASE)

                # 检查原始行中是否有Z坐标
                if re.search(r'Z[-+]?[\d.]+', line, re.IGNORECASE):
                    line = re.sub(r'Z[-+]?[\d.]+', f'Z{cmd.position.z:.3f}', line, flags=re.IGNORECASE)

                # 只有当原始行中有A坐标时才更新
                if re.search(r'A[-+]?[\d.]+', line, re.IGNORECASE):
                    if cmd.position.a is not None:
                        line = re.sub(r'A[-+]?[\d.]+', f'A{cmd.position.a:.3f}', line, flags=re.IGNORECASE)

            return line

        # 如果没有原始行，构建新行（向后兼容）
        parts = []

        # 行号
        parts.append(f"N{cmd.line_number:04d}")

        # G代码
        g_code = self._kuka_to_gcode(cmd.command_type)
        parts.append(g_code)

        # 坐标
        if cmd.position:
            parts.append(f"X{cmd.position.x:.3f}")
            parts.append(f"Y{cmd.position.y:.3f}")
            parts.append(f"Z{cmd.position.z:.3f}")

        return ' '.join(parts)

    def _kuka_to_gcode(self, command_type: str) -> str:
        """KUKA指令类型转G代码"""
        mapping = {
            'PTP': 'G00',
            'LIN': 'G01',
            'CIRC': 'G02'
        }
        return mapping.get(command_type, 'G01')


# 为了兼容gui_editor，创建别名
KUKASrcParser = KukaNCParser


def main():
    import sys
    if len(sys.argv) < 2:
        print("使用方法: python kuka_nc_parser.py <nc文件路径>")
        print("\n示例:")
        print("  python kuka_nc_parser.py 404座板.NC.nc")
        sys.exit(1)

    nc_file = sys.argv[1]
    parser = KukaNCParser(nc_file)
    parser.parse()

    print(f"\n程序名称: {parser.program_name}")
    print(f"运动指令数: {len(parser.motion_commands)}")

    # 显示前10个点
    print("\n前10个运动点:")
    for i, cmd in enumerate(parser.motion_commands[:10]):
        if cmd.position:
            print(f"  {i+1}. {cmd.command_type} X={cmd.position.x:.2f} Y={cmd.position.y:.2f} Z={cmd.position.z:.2f}")


if __name__ == "__main__":
    main()
