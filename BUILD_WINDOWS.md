# Building Windows Executable

This guide explains how to build a **standalone Windows executable** (`KUKAEditor.exe`) that requires **no Python installation** to run.

## Prerequisites

You need a **Windows machine** (or Windows VM) with:
- Python 3.11+ installed
- Internet connection for downloading dependencies

## Step-by-Step Build Instructions

### 1. Clone the Repository

```cmd
git clone https://github.com/yourusername/kukatool.git
cd kukatool
```

### 2. Create Virtual Environment

```cmd
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies

```cmd
pip install -r requirements.txt
pip install pyinstaller
```

### 4. Build the Executable

```cmd
pyinstaller build_windows.spec
```

**Build time**: 2-5 minutes (depending on your machine)

### 5. Find Your Executable

The standalone executable will be created at:
```
dist/KUKAEditor.exe
```

**File size**: Approximately 150-250 MB (includes all dependencies)

## Distribution

The `KUKAEditor.exe` file is **completely standalone**. You can:

1. **Copy** `dist/KUKAEditor.exe` to any Windows machine
2. **Double-click** to run (no installation needed)
3. **Distribute** via USB drive, network share, or download

**No Python or dependencies required on target machines!**

## Testing the Executable

### On the Build Machine

```cmd
cd dist
KUKAEditor.exe
```

### On a Clean Windows Machine

1. Copy `KUKAEditor.exe` to the test machine
2. Double-click the file
3. The GUI should launch directly

## Troubleshooting

### Issue: "Windows protected your PC" warning

This is normal for unsigned executables. Click **"More info"** → **"Run anyway"**

To avoid this warning, you need to:
- Code sign the executable with a valid certificate ($$$)
- Users can add an exception for your app

### Issue: Antivirus flags the executable

**Why**: PyInstaller executables are sometimes flagged as false positives.

**Solutions**:
1. Submit the `.exe` to antivirus vendors as a false positive
2. Code sign the executable (reduces false positives)
3. Ask users to add an exception

### Issue: Build fails with "ImportError"

**Solution**: Make sure all dependencies are installed:
```cmd
pip install numpy matplotlib pyinstaller
```

### Issue: Executable crashes on startup

**Debug mode**: Edit `build_windows.spec` and change:
```python
console=False,  # Change to True
```

Then rebuild:
```cmd
pyinstaller build_windows.spec
```

This will show console output for debugging.

### Issue: Missing DLLs on target machine

The executable should be self-contained, but if you encounter DLL issues:

1. Install **Visual C++ Redistributable** on the target machine:
   - [Download from Microsoft](https://aka.ms/vs/17/release/vc_redist.x64.exe)

## Build Optimization

### Reduce File Size

1. **Remove UPX compression** (paradoxically sometimes reduces size):
   ```python
   upx=False,  # In build_windows.spec
   ```

2. **Exclude unused backends**:
   ```python
   excludes=['matplotlib.backends.backend_qt5agg', ...],
   ```

### Include Custom Icon

1. Create or download an `.ico` file (e.g., `icon.ico`)
2. Edit `build_windows.spec`:
   ```python
   icon='icon.ico',
   ```

## Automated Build (Optional)

Create a `build.bat` script:

```batch
@echo off
echo Building KUKA Editor for Windows...
call venv\Scripts\activate
pip install -q pyinstaller
pyinstaller --clean build_windows.spec
echo.
echo Done! Executable: dist\KUKAEditor.exe
pause
```

Then just run: `build.bat`

## Release Checklist

Before distributing your executable:

- [ ] Test on build machine
- [ ] Test on clean Windows 10 machine
- [ ] Test on clean Windows 11 machine
- [ ] Test file open/save dialogs
- [ ] Test 3D visualization
- [ ] Test editing operations
- [ ] Verify no console window appears (unless debug mode)
- [ ] Check file size is reasonable (<300MB)
- [ ] Create README for end users

## Alternative: One-File vs One-Folder

Current config creates a **one-file** executable (everything in one `.exe`).

For **one-folder** (faster startup, easier to debug):

Edit `build_windows.spec`:

```python
# Replace EXE(...) section with:
exe = EXE(
    pyz,
    a.scripts,
    [],  # Empty - don't bundle everything
    exclude_binaries=True,  # Add this
    name='KUKAEditor',
    ...
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='KUKAEditor'
)
```

This creates `dist/KUKAEditor/` folder with `.exe` + DLLs.

## Cross-Compilation Note

**You cannot build Windows .exe on macOS/Linux directly.**

Options for non-Windows developers:
1. Use a Windows VM (VirtualBox, Parallels, VMware)
2. Use Wine + PyInstaller (complicated, not recommended)
3. Use GitHub Actions / AppVeyor for CI/CD builds
4. Borrow a Windows machine temporarily

## GitHub Actions Build (Advanced)

Create `.github/workflows/build.yml`:

```yaml
name: Build Windows Executable

on: [push, workflow_dispatch]

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt pyinstaller
      - run: pyinstaller build_windows.spec
      - uses: actions/upload-artifact@v3
        with:
          name: KUKAEditor-Windows
          path: dist/KUKAEditor.exe
```

Now every git push automatically builds your `.exe`!

## Support

If you encounter issues:
1. Check this guide's Troubleshooting section
2. Open an issue on GitHub
3. Include the full error message and your Python version
