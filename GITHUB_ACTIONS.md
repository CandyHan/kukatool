# GitHub Actions 自动构建说明

本项目配置了 GitHub Actions 自动构建 Windows 可执行文件，每次推送代码到 GitHub 后会自动生成 `KUKAEditor.exe`。

## 🚀 自动构建触发条件

GitHub Actions 会在以下情况自动构建：

1. **推送到 main 分支**：每次 `git push origin main`
2. **创建版本标签**：推送形如 `v1.0.0` 的标签
3. **Pull Request**：创建或更新 PR 到 main 分支
4. **手动触发**：在 GitHub 网页端手动运行

## 📥 如何下载自动构建的 EXE

### 方法 1：从 Actions 页面下载（开发版本）

1. 访问你的 GitHub 仓库
2. 点击顶部的 **"Actions"** 标签
3. 选择最新的 **"Build Windows Executable"** 工作流
4. 滚动到底部找到 **"Artifacts"** 部分
5. 下载 `KUKAEditor-Windows-dev-xxxxx.zip`
6. 解压得到 `KUKAEditor.exe`

**保留时间**：90天

### 方法 2：从 Releases 下载（正式版本）

当你推送版本标签时（如 `v1.0.0`），会自动创建 Release：

1. 访问你的 GitHub 仓库
2. 点击右侧的 **"Releases"**
3. 选择最新的版本
4. 下载 `KUKAEditor.exe`

## 🏷️ 创建版本发布

### 步骤 1: 创建并推送标签

```bash
# 创建版本标签
git tag -a v1.0.0 -m "Release version 1.0.0"

# 推送标签到 GitHub
git push origin v1.0.0
```

### 步骤 2: 等待构建完成

- GitHub Actions 会自动开始构建（约 5-10 分钟）
- 构建完成后自动创建 Release
- Release 中包含 `KUKAEditor.exe` 下载链接

### 步骤 3: 在 GitHub 上查看

访问 `https://github.com/CandyHan/kukatool/releases`

## 🔧 手动触发构建

如果你想手动触发构建（不推送代码）：

1. 访问 GitHub 仓库
2. 点击 **"Actions"** 标签
3. 选择 **"Build Windows Executable"** 工作流
4. 点击右上角 **"Run workflow"** 按钮
5. 选择分支（通常是 `main`）
6. 点击 **"Run workflow"** 确认

## 📊 查看构建状态

### 在 README 中显示构建状态徽章

在 `README.md` 顶部添加：

```markdown
![Build Status](https://github.com/CandyHan/kukatool/actions/workflows/build-windows.yml/badge.svg)
```

显示效果：
- ✅ 绿色：构建成功
- ❌ 红色：构建失败
- 🟡 黄色：正在构建

### 查看构建日志

1. 进入 **Actions** 页面
2. 点击某次工作流运行
3. 点击 **"build"** 查看详细日志
4. 可以看到每一步的执行结果

## 🛠️ 构建流程说明

GitHub Actions 执行以下步骤：

1. **Checkout code**：拉取最新代码
2. **Set up Python**：安装 Python 3.11
3. **Install dependencies**：安装 numpy, matplotlib, pyinstaller
4. **Build executable**：运行 `pyinstaller build_windows.spec`
5. **Check build output**：验证 exe 文件是否生成
6. **Upload artifact**：上传 exe 到 GitHub（保留90天）
7. **Create Release**（仅标签推送）：创建正式发布

## ❓ 常见问题

### Q: 为什么构建失败了？

**A**: 常见原因：
1. 依赖安装失败：检查 `requirements.txt`
2. 代码错误：本地测试代码是否能运行
3. PyInstaller 配置问题：检查 `build_windows.spec`

查看失败原因：
1. 进入 Actions 页面
2. 点击失败的工作流
3. 展开红色 ❌ 的步骤查看错误信息

### Q: 如何修改构建配置？

**A**: 编辑 `.github/workflows/build-windows.yml` 文件：

```yaml
# 修改 Python 版本
python-version: '3.11'  # 改为其他版本

# 添加额外依赖
pip install xxx

# 修改保留时间
retention-days: 90  # 改为其他天数
```

### Q: 构建的 exe 太大怎么办？

**A**: 在 `build_windows.spec` 中：

```python
# 排除不需要的包
excludes=['scipy', 'pandas', ...],

# 关闭 UPX 压缩（有时反而变大）
upx=False,
```

### Q: 能否同时构建 Linux 和 macOS 版本？

**A**: 可以！创建类似的工作流文件：
- `.github/workflows/build-linux.yml`
- `.github/workflows/build-macos.yml`

使用 `runs-on: ubuntu-latest` 或 `runs-on: macos-latest`

### Q: 如何给 exe 添加图标？

**A**:
1. 将 `icon.ico` 文件放到项目根目录
2. 在 `build_windows.spec` 中修改：
   ```python
   icon='icon.ico',
   ```
3. 提交并推送，GitHub Actions 会自动使用新图标

## 🎯 版本号建议

遵循语义化版本（Semantic Versioning）：

- `v1.0.0`：重大更新（不兼容的更改）
- `v1.1.0`：新功能添加（向后兼容）
- `v1.1.1`：Bug 修复（向后兼容）

## 📝 版本发布检查清单

发布新版本前：

- [ ] 在本地测试所有功能
- [ ] 更新 `README.md` 版本信息
- [ ] 更新 `CHANGELOG.md`（如果有）
- [ ] 创建版本标签：`git tag -a v1.x.x -m "..."`
- [ ] 推送标签：`git push origin v1.x.x`
- [ ] 等待 GitHub Actions 构建完成
- [ ] 检查 Release 页面
- [ ] 下载并测试自动构建的 exe
- [ ] 编辑 Release 说明添加更新内容

## 🔒 私有仓库注意事项

如果你的仓库是私有的：
- Artifacts 只有仓库成员可以下载
- Releases 同样受权限控制
- GitHub Actions 分钟数有限制（免费账户 2000 分钟/月）

## 📚 更多资源

- [GitHub Actions 文档](https://docs.github.com/actions)
- [PyInstaller 文档](https://pyinstaller.org/)
- [语义化版本规范](https://semver.org/lang/zh-CN/)

## 💡 提示

- 每次推送都会触发构建，频繁推送可能消耗 Actions 分钟数
- 可以在 commit 消息中添加 `[skip ci]` 跳过构建
- 建议在本地完成测试后再推送到 GitHub
