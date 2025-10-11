# KUKA Tool Suite

A comprehensive toolset for KUKA robot programming, featuring interactive visualization and editing capabilities for `.src` files.

## Features

### 🔧 KUKA Source Parser (`kuka_src_parser.py`)
- Parse KUKA `.src` robot program files
- Extract motion commands (LIN, PTP, CIRC)
- Analyze coordinate systems (BASE, TOOL)
- Export modified programs

### 🎨 Interactive GUI Editor (`kuka_gui_editor.py`)
- **3D Visualization**: Real-time 3D path visualization
- **Operation Detection**: Automatic identification of drilling and contouring operations
- **Interactive Selection**: Click to select drilling or contour operations
- **Batch Editing**: Move, modify, or delete selected operations
- **File Management**: Open, edit, and save `.src` files with GUI dialogs

### 📊 Visualizer (`kuka_visualizer.py`)
- Visualize robot paths in 3D
- Analyze workspace boundaries
- Export visualizations

### 🎬 Animator (`kuka_animator.py`)
- Animate robot motion paths
- Step-by-step playback
- Export animations

## Installation

### Prerequisites
- Python 3.12+ (3.11+ may work)
- pip package manager

### Setup

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/kukatool.git
cd kukatool
```

2. **Create virtual environment**
```bash
python3 -m venv venv
```

3. **Activate virtual environment**

- **macOS/Linux**:
  ```bash
  source venv/bin/activate
  ```

- **Windows**:
  ```cmd
  venv\Scripts\activate
  ```

4. **Install dependencies**
```bash
pip install -r requirements.txt
```

## Usage

### GUI Editor (Recommended)

**macOS/Linux**:
```bash
./run_editor.sh
```

**Windows**:
```cmd
run_editor.bat
```

Or run directly:
```bash
python kuka_gui_editor.py [optional_file.src]
```

#### GUI Features:
1. **Open File**: Click "Open" button to load a `.src` file
2. **Select Operations**:
   - Click blue triangles to select drilling operations
   - Click green lines to select contour paths
   - Selected items turn red/orange
3. **Edit Operations**:
   - Enter offset values (ΔX, ΔY, ΔZ)
   - Click "Move" to apply changes
   - Click "Delete Selected Drilling" to remove operations
4. **Save**: Click "Save File" to export modified program

### Command Line Tools

**Visualizer**:
```bash
python kuka_visualizer.py your_file.src
```

**Animator**:
```bash
python kuka_animator.py your_file.src
```

**Parser** (programmatic use):
```python
from kuka_src_parser import KUKASrcParser

parser = KUKASrcParser("robot_program.src")
parser.parse()

# Access parsed data
for cmd in parser.motion_commands:
    if cmd.position:
        print(f"{cmd.command_type}: X={cmd.position.x}, Y={cmd.position.y}, Z={cmd.position.z}")

# Modify and export
parser.offset_all_points(dx=10, dy=0, dz=5)
parser.export_to_src("modified_program.src")
```

## Building Windows Executable

To create a standalone Windows `.exe` file:

1. **Install PyInstaller**:
```bash
pip install pyinstaller
```

2. **Build executable**:
```bash
pyinstaller build_windows.spec
```

3. **Find executable**:
The `.exe` file will be in the `dist/` folder.

## Project Structure

```
kukatool/
├── kuka_src_parser.py      # Core parser module
├── kuka_gui_editor.py       # Interactive GUI editor
├── kuka_visualizer.py       # 3D visualization tool
├── kuka_animator.py         # Animation tool
├── requirements.txt         # Python dependencies
├── run_editor.sh           # macOS/Linux launcher
├── run_editor.bat          # Windows launcher
├── build_windows.spec      # PyInstaller configuration
└── README.md               # This file
```

## Requirements

- Python 3.12+
- numpy >= 1.24.0
- matplotlib >= 3.7.0
- tkinter (usually included with Python)

## Platform Support

- ✅ **macOS**: Full support
- ✅ **Linux**: Full support
- ✅ **Windows**: Full support (use `.bat` launcher or `.exe`)

## Troubleshooting

### tkinter not found
**macOS**:
```bash
brew install python-tk@3.12
```

**Ubuntu/Debian**:
```bash
sudo apt-get install python3-tk
```

**Windows**: tkinter is usually included with Python installer. If missing, reinstall Python and check "tcl/tk" option.

### Matplotlib backend issues
If GUI crashes, try setting a different backend:
```bash
export MPLBACKEND=TkAgg  # macOS/Linux
set MPLBACKEND=TkAgg     # Windows
```

## License

MIT License - Feel free to use and modify for your projects.

## Contributing

Contributions welcome! Please feel free to submit pull requests or open issues.

## Author

Created for KUKA robot programming and automation tasks.
