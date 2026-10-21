# Clipboard V1

Windows 本地剪贴板历史管理工具，使用 Python、PySide6 和 SQLite。支持文字、图片、文件/文件夹、统一时间排序、搜索、分类、收藏、清理、双击恢复、个性化外观、Windows 全局快捷键和系统托盘。

## 运行

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

默认快捷键为 `Ctrl+Shift+V`。关闭主窗口会隐藏到托盘；请从托盘菜单选择“退出”来完全退出程序。

数据默认保存在 Windows 用户的本地应用数据目录，由 Qt 的 `AppLocalDataLocation` 决定。内容不会上传网络，图片副本位于数据目录的 `images` 子目录。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 打包 EXE

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean Clipboard.spec
```

产物位于 `dist\Clipboard\Clipboard.exe`。这是无控制台的 onedir 版本，请保留整个 `Clipboard` 文件夹一起使用。
