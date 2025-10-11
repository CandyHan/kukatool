#!/usr/bin/env python3
"""
KUKA .src 文件3D可视化工具
使用matplotlib进行3D路径可视化
"""

import sys
from kuka_src_parser import KUKASrcParser, print_statistics
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import numpy as np


class KUKAVisualizer:
    """KUKA程序可视化器"""

    def __init__(self, parser: KUKASrcParser):
        self.parser = parser

    def plot_3d_path(self, show_points: bool = True, show_velocities: bool = True):
        """绘制3D路径"""
        fig = plt.figure(figsize=(15, 10))
        ax = fig.add_subplot(111, projection='3d')

        # 提取所有笛卡尔坐标点
        points = []
        velocities = []
        colors = []

        for cmd in self.parser.motion_commands:
            if cmd.position:
                points.append([cmd.position.x, cmd.position.y, cmd.position.z])
                velocities.append(cmd.velocity if cmd.velocity else 0)

                # 根据运动类型设置颜色
                if cmd.command_type == 'PTP':
                    colors.append('blue')
                elif cmd.command_type == 'LIN':
                    colors.append('green' if cmd.velocity and cmd.velocity > 0.05 else 'red')
                elif cmd.command_type == 'CIRC':
                    colors.append('orange')

        if not points:
            print("⚠️  没有找到笛卡尔坐标点")
            return

        points = np.array(points)

        # 绘制路径线
        ax.plot(points[:, 0], points[:, 1], points[:, 2],
                'gray', linewidth=0.5, alpha=0.6, label='运动路径')

        # 绘制点
        if show_points:
            ax.scatter(points[:, 0], points[:, 1], points[:, 2],
                      c=colors, s=20, alpha=0.6)

        # 标注速度变化点
        if show_velocities:
            # 找出速度变化的点
            for i in range(1, len(velocities)):
                if velocities[i] != velocities[i-1]:
                    ax.scatter(points[i, 0], points[i, 1], points[i, 2],
                             c='purple', s=100, marker='*', alpha=0.8)

        # 标注起点和终点
        ax.scatter(points[0, 0], points[0, 1], points[0, 2],
                  c='lime', s=200, marker='o', label='起点', edgecolors='black', linewidths=2)
        ax.scatter(points[-1, 0], points[-1, 1], points[-1, 2],
                  c='red', s=200, marker='X', label='终点', edgecolors='black', linewidths=2)

        # 标注BASE坐标系
        if self.parser.base_frame:
            bf = self.parser.base_frame
            ax.scatter(bf.x, bf.y, bf.z, c='blue', s=300, marker='^',
                      label='BASE坐标系', edgecolors='black', linewidths=2)

        # 设置标签
        ax.set_xlabel('X (mm)', fontsize=12, fontweight='bold')
        ax.set_ylabel('Y (mm)', fontsize=12, fontweight='bold')
        ax.set_zlabel('Z (mm)', fontsize=12, fontweight='bold')
        ax.set_title(f'KUKA程序3D路径可视化 - {self.parser.program_name}',
                    fontsize=14, fontweight='bold')

        # 设置相同的比例尺
        max_range = np.array([
            points[:, 0].max() - points[:, 0].min(),
            points[:, 1].max() - points[:, 1].min(),
            points[:, 2].max() - points[:, 2].min()
        ]).max() / 2.0

        mid_x = (points[:, 0].max() + points[:, 0].min()) * 0.5
        mid_y = (points[:, 1].max() + points[:, 1].min()) * 0.5
        mid_z = (points[:, 2].max() + points[:, 2].min()) * 0.5

        ax.set_xlim(mid_x - max_range, mid_x + max_range)
        ax.set_ylim(mid_y - max_range, mid_y + max_range)
        ax.set_zlim(mid_z - max_range, mid_z + max_range)

        # 添加图例
        ax.legend(loc='upper right')

        # 添加网格
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        return fig

    def plot_2d_projections(self):
        """绘制2D投影视图"""
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))

        # 提取点
        points = []
        colors = []
        for cmd in self.parser.motion_commands:
            if cmd.position:
                points.append([cmd.position.x, cmd.position.y, cmd.position.z])
                # 根据速度着色
                if cmd.velocity:
                    if cmd.velocity >= 0.1:
                        colors.append('green')
                    elif cmd.velocity >= 0.05:
                        colors.append('orange')
                    else:
                        colors.append('red')
                else:
                    colors.append('gray')

        if not points:
            print("⚠️  没有找到笛卡尔坐标点")
            return

        points = np.array(points)

        # XY平面 (俯视图)
        axes[0, 0].scatter(points[:, 0], points[:, 1], c=colors, s=10, alpha=0.6)
        axes[0, 0].plot(points[:, 0], points[:, 1], 'gray', linewidth=0.5, alpha=0.3)
        axes[0, 0].scatter(points[0, 0], points[0, 1], c='lime', s=100, marker='o', label='起点')
        axes[0, 0].scatter(points[-1, 0], points[-1, 1], c='red', s=100, marker='X', label='终点')
        axes[0, 0].set_xlabel('X (mm)')
        axes[0, 0].set_ylabel('Y (mm)')
        axes[0, 0].set_title('XY平面 (俯视图)')
        axes[0, 0].grid(True, alpha=0.3)
        axes[0, 0].legend()
        axes[0, 0].axis('equal')

        # XZ平面 (侧视图)
        axes[0, 1].scatter(points[:, 0], points[:, 2], c=colors, s=10, alpha=0.6)
        axes[0, 1].plot(points[:, 0], points[:, 2], 'gray', linewidth=0.5, alpha=0.3)
        axes[0, 1].scatter(points[0, 0], points[0, 2], c='lime', s=100, marker='o', label='起点')
        axes[0, 1].scatter(points[-1, 0], points[-1, 2], c='red', s=100, marker='X', label='终点')
        axes[0, 1].set_xlabel('X (mm)')
        axes[0, 1].set_ylabel('Z (mm)')
        axes[0, 1].set_title('XZ平面 (侧视图)')
        axes[0, 1].grid(True, alpha=0.3)
        axes[0, 1].legend()
        axes[0, 1].axis('equal')

        # YZ平面 (正视图)
        axes[1, 0].scatter(points[:, 1], points[:, 2], c=colors, s=10, alpha=0.6)
        axes[1, 0].plot(points[:, 1], points[:, 2], 'gray', linewidth=0.5, alpha=0.3)
        axes[1, 0].scatter(points[0, 1], points[0, 2], c='lime', s=100, marker='o', label='起点')
        axes[1, 0].scatter(points[-1, 1], points[-1, 2], c='red', s=100, marker='X', label='终点')
        axes[1, 0].set_xlabel('Y (mm)')
        axes[1, 0].set_ylabel('Z (mm)')
        axes[1, 0].set_title('YZ平面 (正视图)')
        axes[1, 0].grid(True, alpha=0.3)
        axes[1, 0].legend()
        axes[1, 0].axis('equal')

        # 速度分布图
        velocities = [cmd.velocity*1000 if cmd.velocity else 0
                     for cmd in self.parser.motion_commands if cmd.position]
        axes[1, 1].plot(range(len(velocities)), velocities, 'b-', linewidth=1)
        axes[1, 1].fill_between(range(len(velocities)), velocities, alpha=0.3)
        axes[1, 1].set_xlabel('指令序号')
        axes[1, 1].set_ylabel('速度 (mm/s)')
        axes[1, 1].set_title('速度分布图')
        axes[1, 1].grid(True, alpha=0.3)

        plt.tight_layout()
        return fig

    def plot_z_profile(self):
        """绘制Z轴深度变化图"""
        fig, ax = plt.subplots(figsize=(15, 6))

        z_values = []
        indices = []
        colors = []

        for i, cmd in enumerate(self.parser.motion_commands):
            if cmd.position:
                z_values.append(cmd.position.z)
                indices.append(i)
                # 根据速度着色
                if cmd.velocity and cmd.velocity < 0.05:
                    colors.append('red')  # 切削速度
                else:
                    colors.append('green')  # 快速移动

        ax.scatter(indices, z_values, c=colors, s=20, alpha=0.6)
        ax.plot(indices, z_values, 'gray', linewidth=0.5, alpha=0.3)

        ax.set_xlabel('指令序号', fontsize=12)
        ax.set_ylabel('Z坐标 (mm)', fontsize=12)
        ax.set_title(f'Z轴深度变化 - {self.parser.program_name}', fontsize=14, fontweight='bold')
        ax.grid(True, alpha=0.3)
        ax.axhline(y=0, color='black', linestyle='--', linewidth=1, alpha=0.5)

        # 添加图例
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor='red', alpha=0.6, label='切削速度 (<50mm/s)'),
            Patch(facecolor='green', alpha=0.6, label='快速移动 (≥50mm/s)')
        ]
        ax.legend(handles=legend_elements, loc='upper right')

        plt.tight_layout()
        return fig

    def analyze_machining_pattern(self):
        """分析加工模式"""
        print("\n" + "="*60)
        print("  加工模式分析")
        print("="*60)

        # 提取所有切削点（低速点）
        machining_points = []
        for cmd in self.parser.motion_commands:
            if cmd.position and cmd.velocity and cmd.velocity < 0.05:
                machining_points.append([cmd.position.x, cmd.position.y, cmd.position.z])

        if not machining_points:
            print("⚠️  未找到切削点")
            return

        machining_points = np.array(machining_points)

        # 分析X, Y坐标的唯一值（判断是否为矩阵式加工）
        unique_x = np.unique(np.round(machining_points[:, 0], 2))
        unique_y = np.unique(np.round(machining_points[:, 1], 2))
        unique_z = np.unique(np.round(machining_points[:, 2], 2))

        print(f"\n📍 切削点统计:")
        print(f"  总切削点数: {len(machining_points)}")
        print(f"\n  X方向:")
        print(f"    唯一位置数: {len(unique_x)}")
        if len(unique_x) > 1:
            x_spacing = np.diff(unique_x)
            print(f"    位置: {', '.join(f'{x:.2f}' for x in unique_x[:6])}{'...' if len(unique_x) > 6 else ''}")
            print(f"    平均间距: {np.mean(x_spacing):.2f} mm")

        print(f"\n  Y方向:")
        print(f"    唯一位置数: {len(unique_y)}")
        if len(unique_y) > 1:
            y_spacing = np.diff(unique_y)
            print(f"    位置: {', '.join(f'{y:.2f}' for y in unique_y[:6])}{'...' if len(unique_y) > 6 else ''}")
            print(f"    平均间距: {np.mean(y_spacing):.2f} mm")

        print(f"\n  Z方向:")
        print(f"    唯一深度数: {len(unique_z)}")
        print(f"    深度: {', '.join(f'{z:.2f}' for z in unique_z)}")

        # 判断加工类型
        print(f"\n🔍 加工类型判断:")
        if len(unique_x) > 2 and len(unique_y) > 2:
            print(f"  ✓ 矩阵式加工 ({len(unique_x)} x {len(unique_y)} 阵列)")
        elif len(unique_x) == 1 and len(unique_y) == 1:
            print(f"  ✓ 单点钻孔/铣削")
        else:
            print(f"  ✓ 线性加工模式")

        print("\n" + "="*60 + "\n")


def main():
    if len(sys.argv) < 2:
        print("使用方法: python kuka_visualizer.py <src文件路径>")
        print("\n示例:")
        print("  python kuka_visualizer.py B004XM.src")
        sys.exit(1)

    src_file = sys.argv[1]

    # 解析文件
    print(f"正在解析文件: {src_file}")
    parser = KUKASrcParser(src_file)
    parser.parse()

    # 显示统计信息
    stats = parser.get_statistics()
    print_statistics(stats)

    # 创建可视化器
    visualizer = KUKAVisualizer(parser)

    # 分析加工模式
    visualizer.analyze_machining_pattern()

    # 生成可视化
    print("正在生成3D可视化...")
    fig1 = visualizer.plot_3d_path()

    print("正在生成2D投影...")
    fig2 = visualizer.plot_2d_projections()

    print("正在生成Z轴剖面图...")
    fig3 = visualizer.plot_z_profile()

    print("\n✓ 可视化完成！关闭窗口以退出。")
    plt.show()


if __name__ == "__main__":
    main()
