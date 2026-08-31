# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec cho M Auto Pilot (Qwen3.8-27B local agent).
# Build: .venv\Scripts\python.exe -m PyInstaller "M Auto Pilot.spec" --noconfirm

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

hiddenimports = [
    "uuid",
    # requests stack
    "requests",
    "urllib3",
    "certifi",
    "charset_normalizer",
    "idna",
    # system / tools
    "psutil",
    "PIL",
    "PIL.ImageGrab",
    "playwright",
    "playwright.sync_api",
    "pywinauto",
    "pywinauto.keyboard",
    "pywinauto.mouse",
    "rapidocr_onnxruntime",
    "cv2",
    "numpy",
    "onnxruntime",
    # MCP SDK (mcp 2.x, dynamic imports)
    "mcp",
    "mcp.types",
    "mcp.client",
    "mcp.client.stdio",
    "mcp.client.session",
    "mcp.server",
    "mcp.server.stdio",
    "mcp.server.session",
    "mcp.shared",
    "mcp.shared.session",
    "mcp.shared.context",
    "anyio",
    "anyio._backends",
    "httpx",
    "pydantic",
    "pydantic_core",
    "sse_starlette",
    "starlette",
]

# Các package có file dữ liệu động (model OCR, driver playwright...).
datas = [
    ("assets/M_Auto_Pilot_logo.png", "assets"),
    ("assets/M_Auto_Pilot.ico", "assets"),
    ("ui/styles.qss", "ui"),
]
datas += collect_data_files("rapidocr_onnxruntime")
datas += collect_data_files("mcp")
datas += collect_data_files("playwright", includes=["driver/**/*"])
datas += collect_data_files("pydantic")
datas += collect_data_files("pywinauto")

hiddenimports += collect_submodules("mcp")
hiddenimports += collect_submodules("anyio")
hiddenimports += collect_submodules("starlette")
hiddenimports += collect_submodules("sse_starlette")
hiddenimports += collect_submodules("pywinauto")

a = Analysis(
    ["scripts/run_auto_pilot_gui.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # torch/torchvision bị cuốn vào qua nhánh import tùy chọn của MCP/onnxruntime;
    # không module nào của ứng dụng dùng torch — loại bỏ để EXE gọn và khởi động nhanh.
    excludes=[
        "torch",
        "torchvision",
        "timm",
        "transformers",
        "ultralytics",
        "matplotlib",
        "scipy",
        "sympy",
        "networkx",
        "tensorboard",
        "pytest",
        "IPython",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="M Auto Pilot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/M_Auto_Pilot.ico",
)
