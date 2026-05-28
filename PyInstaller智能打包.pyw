import os
import platform
import shutil
import sys
import tempfile
import traceback
import zipfile
import time
import subprocess
import urllib.request
import hashlib
import re
import logging
import ast
import json
from pathlib import Path
from typing import List, Optional, Dict, Set, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from PIL import Image
from PyInstaller import __version__ as pyinstaller_version
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSettings, QTimer
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QFileDialog,
    QRadioButton, QCheckBox, QGroupBox, QListWidget, QAbstractItemView,
    QMessageBox, QButtonGroup, QAction, QSpinBox, QComboBox, QProgressBar
)
VERSION = "2.4"
MIN_DISK_SPACE_MB = 500
TIMEOUT_NETWORK_TEST = 5  
TIMEOUT_MIRROR_SPEED = 3  
TIMEOUT_DOWNLOAD = 120    
TIMEOUT_COMMAND = 5       
TIMEOUT_INSTALL = 300     
AVAILABLE_PYTHON_VERSIONS = ["3.12.10", "3.11.9", "3.10.11", "3.9.13"]
DEFAULT_PYTHON_VERSION = "3.12.10"
PYTHON_VERSION = "3.12.10"
MIN_PYINSTALLER_VERSION = "5.0"
MAX_RETRIES = 3
RETRY_DELAY = 2
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
PYTHON_MIRRORS = [
    "https://mirrors.aliyun.com/python-ftp/python/{version}/python-{version}-embed-amd64.zip",
    "https://mirrors.huaweicloud.com/python/{version}/python-{version}-embed-amd64.zip",
    "https://www.python.org/ftp/python/{version}/python-{version}-embed-amd64.zip"
]
IMPORT_TO_PACKAGE_MAP = {
    'PIL': 'Pillow', 'cv2': 'opencv-python', 'sklearn': 'scikit-learn',
    'skimage': 'scikit-image', 'yaml': 'PyYAML', 'bs4': 'beautifulsoup4',
    'wx': 'wxPython', 'serial': 'pyserial', 'usb': 'pyusb',
    'Crypto': 'pycryptodome', 'OpenGL': 'PyOpenGL', 'git': 'GitPython',
    'dotenv': 'python-dotenv',
}
STDLIB_MODULES = {
    'os', 'sys', 'time', 'datetime', 'json', 'math', 'random', 'collections',
    'itertools', 'functools', 're', 'threading', 'multiprocessing', 'subprocess',
    'pathlib', 'typing', 'abc', 'io', 'tempfile', 'shutil', 'zipfile', 'tarfile',
    'gzip', 'hashlib', 'base64', 'urllib', 'http', 'email', 'html', 'xml',
    'sqlite3', 'pickle', 'copy', 'pprint', 'logging', 'unittest', 'doctest',
    'argparse', 'configparser', 'csv', 'socket', 'ssl', 'select', 'signal',
    'platform', 'ctypes', 'struct', 'array', 'queue', 'heapq', 'bisect',
    'weakref', 'types', 'traceback', 'inspect', 'dis', 'gc', 'warnings',
    'contextlib', 'decimal', 'fractions', 'numbers', 'cmath', 'statistics',
    'string', 'textwrap', 'unicodedata', 'codecs', 'locale', 'gettext',
    'calendar', 'enum', 'dataclasses', 'operator', 'keyword', 'ast', 'token',
    'tokenize', 'pdb', 'timeit', 'profile', 'cProfile', 'importlib', 'pkgutil',
    'venv', 'ensurepip', 'pip', 'setuptools', 'distutils', 'asyncio', 'concurrent',
    'mimetypes', 'webbrowser', 'uuid', 'secrets', 'hmac',
}
class LogManager:
    def __init__(self, log_dir: Optional[str] = None):
        self.log_dir = log_dir or os.path.join(os.path.expanduser("~"), "PyToExe_Logs")
        os.makedirs(self.log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(self.log_dir, f"packaging_{timestamp}.log")
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
    def info(self, msg: str): self.logger.info(msg)
    def error(self, msg: str): self.logger.error(msg)
    def warning(self, msg: str): self.logger.warning(msg)
    def debug(self, msg: str): self.logger.debug(msg)
log_manager = LogManager()
def sanitize_input(text: str) -> str:
    if not text:
        return ""
    for char in [';', '&', '|', '`', '$', '||', '&&']:
        text = text.replace(char, '')
    return text.strip()
def validate_module_name(name: str) -> bool:
    return bool(name and re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name))
def calculate_file_hash(filepath: str, algorithm: str = 'sha256') -> str:
    hash_obj = hashlib.new(algorithm)
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()
class DragDropLineEdit(QLineEdit):
    def __init__(self, file_filter: str = "", parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.file_filter = [ext.strip().lower() for ext in file_filter.split() if ext.strip()]
    def dragEnterEvent(self, event):
        event.acceptProposedAction() if event.mimeData().hasUrls() else event.ignore()
    def dragMoveEvent(self, event):
        event.acceptProposedAction() if event.mimeData().hasUrls() else event.ignore()
    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
        file_path = urls[0].toLocalFile()
        if not self.file_filter or any(file_path.lower().endswith(ext) for ext in self.file_filter):
            self.setText(file_path)
class DragDropListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.viewport().setAcceptDrops(True)
    def dragEnterEvent(self, event):
        event.acceptProposedAction() if event.mimeData().hasUrls() else event.ignore()
    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path and not self.findItems(file_path, Qt.MatchExactly):
                self.addItem(file_path)
class PreparationThread(QThread):
    """环境准备线程：检查Python、安装PyInstaller、扫描依赖等"""
    output_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str, object)  # success, message, python_exe
    
    def __init__(self, parent_window, script_path: str):
        super().__init__()
        self.parent = parent_window
        self.script_path = script_path
        self._is_cancelled = False
        self._cached_python_exe = None  # 缓存Python路径
    
    def cancel(self):
        self._is_cancelled = True
    
    def log(self, msg: str):
        """线程安全的日志输出 - 立即刷新"""
        self.output_signal.emit(msg)
        # 强制立即处理事件，避免日志堆积
        time.sleep(0.01)  # 给主线程时间处理信号
    
    def run(self):
        try:
            # 1. 快速检查Python环境（优先使用系统Python）
            if self._is_cancelled:
                self.finished_signal.emit(False, "用户取消", None)
                return
            
            self.log("🔍 检查Python环境...")
            python_exe = self._find_system_python()
            
            if not python_exe:
                self.log("  ⚠ 未找到系统Python，准备部署便携版...")
                python_exe = self._ensure_python_ready()
            if not python_exe:
                self.finished_signal.emit(False, "无法准备Python环境", None)
                return
            else:
                self.log(f"  ✓ 检测到系统Python: {python_exe}")
            
            self._cached_python_exe = python_exe
            
            # 2. 检查PyInstaller（快速检查，不输出过多信息）
            if self._is_cancelled:
                self.finished_signal.emit(False, "用户取消", None)
                return
            
            self.log("🔍 检查PyInstaller...")
            if not self._ensure_pyinstaller_installed(python_exe):
                self.finished_signal.emit(False, "无法安装PyInstaller", None)
                return
            
            # 3. 扫描并安装依赖（仅在使用便携版Python时）
            if self._is_cancelled:
                self.finished_signal.emit(False, "用户取消", None)
                return
            
            if self.parent.portable_python_dir:
                self.log("🔍 扫描脚本依赖...")
                detected_imports = self._scan_script_imports(self.script_path)
                if detected_imports and not self._is_cancelled:
                    self._install_dependencies_in_portable(python_exe, detected_imports)
            
            if self._is_cancelled:
                self.finished_signal.emit(False, "用户取消", None)
                return
            
            # 准备完成
            self.finished_signal.emit(True, "环境准备完成", python_exe)
            
        except Exception as e:
            error_msg = f"环境准备失败: {str(e)}"
            log_manager.error(error_msg)
            log_manager.error(traceback.format_exc())
            self.finished_signal.emit(False, error_msg, None)
    
    def _is_temp_python(self, path: str) -> bool:
        """检查是否为临时Python"""
        if not path:
            return True
        exclude_patterns = ['onefile_', 'AppData\\Local\\Temp', 'AppData/Local/Temp', 
                          '\\Temp\\', '/tmp/', '_MEI']
        path_lower = path.lower()
        return any(pattern.lower() in path_lower for pattern in exclude_patterns)
    
    def _get_executable_path(self, cmd: str) -> Optional[str]:
        """获取可执行文件路径"""
        try:
            if sys.platform == 'win32':
                result = subprocess.run(['where', cmd], capture_output=True, text=True, 
                                      timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                result = subprocess.run(['which', cmd], capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                return None
            for line in result.stdout.strip().split('\n'):
                path = line.strip()
                if os.path.exists(path):
                    return path
        except Exception as e:
            log_manager.debug(f"获取可执行路径时出错: {e}")
        return None
    
    def _check_disk_space(self, path: str, required_mb: int = MIN_DISK_SPACE_MB) -> Tuple[bool, float]:
        """检查磁盘空间"""
        try:
            if not path or not os.path.exists(os.path.dirname(path) or path):
                return True, 0
            if sys.platform == 'win32':
                import ctypes
                free_bytes = ctypes.c_ulonglong(0)
                ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                    ctypes.c_wchar_p(os.path.dirname(path) or path), 
                    None, None, ctypes.pointer(free_bytes)
                )
                free_mb = free_bytes.value / (1024 * 1024)
            else:
                st = os.statvfs(path)
                free_mb = (st.f_bavail * st.f_frsize) / (1024 * 1024)
            return free_mb >= required_mb, free_mb
        except Exception as e:
            log_manager.warning(f"检查磁盘空间时出错: {e}")
            return True, 0
    
    def _check_network(self, timeout: int = 5) -> bool:
        """检查网络连接"""
        test_urls = ['https://www.baidu.com', 'https://pypi.tuna.tsinghua.edu.cn', 'https://pypi.org']
        for url in test_urls:
            try:
                req = urllib.request.Request(url, method='HEAD')
                req.add_header('User-Agent', 'Mozilla/5.0')
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    if response.status == 200:
                        return True
            except Exception:
                continue
        return False
    
    def _ensure_python_ready(self) -> Optional[str]:
        """在子线程中检查Python环境"""
        system_python = self._find_system_python()
        if system_python:
            self.log(f"  ✓ 检测到系统Python: {system_python}")
            return system_python
        
        self.log("  ⚠ 未在系统中找到Python，尝试自动部署...")
        
        base_dir = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
        has_space, free_mb = self._check_disk_space(base_dir)
        if not has_space:
            self.log(f"  ✗ 磁盘空间不足！当前可用: {free_mb:.0f}MB，需要至少: {MIN_DISK_SPACE_MB}MB")
            return None
        
        python_exe = self._install_portable_python()
        if python_exe and os.path.exists(python_exe):
            return python_exe
        return None
    
    def _find_system_python(self) -> Optional[str]:
        """查找系统Python"""
        is_frozen = getattr(sys, 'frozen', False)
        is_nuitka = '__compiled__' in dir() or '__nuitka__' in dir()
        is_temp_exe = self._is_temp_python(sys.executable)
        
        if not is_frozen and not is_nuitka and not is_temp_exe:
            return sys.executable
        
        for cmd in ['py', 'python', 'python3']:
            try:
                result = subprocess.run(
                    [cmd, '--version'],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                )
                if result.returncode != 0 or 'Python' not in result.stdout:
                    continue
                python_path = self._get_executable_path(cmd)
                if python_path and os.path.exists(python_path) and not self._is_temp_python(python_path):
                    return python_path
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
            except Exception as e:
                log_manager.debug(f"查找Python时出错 ({cmd}): {e}")
        return None
    
    def _install_portable_python(self) -> Optional[str]:
        """安装便携版Python"""
        if platform.system() != "Windows":
            self.log("❌ 自动部署Python暂仅支持Windows系统")
            return None
        
        base_dir = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
        portable_dir = os.path.join(base_dir, '_internal_python')
        self.parent.portable_python_dir = portable_dir
        
        # 检查是否已存在
        python_exe_path = os.path.join(portable_dir, 'python.exe')
        pip_exe_path = os.path.join(portable_dir, 'Scripts', 'pip.exe')
        
        if os.path.exists(python_exe_path) and os.path.exists(pip_exe_path):
            self.log(f"  ✓ 发现已部署的便携版Python: {python_exe_path}")
            return python_exe_path
        
        os.makedirs(portable_dir, exist_ok=True)
        
        if os.path.exists(python_exe_path):
            self.log("  ⚠ 检测到Python但缺少pip，将尝试修复...")
            if not self._install_pip(python_exe_path, portable_dir):
                return None
            return python_exe_path
        
        self.log("  🔧 开始部署便携版Python...")
        
        # 检查网络
        if not self._check_network():
            self.log("  ✗ 无网络连接，无法下载Python。")
            return None
        
        # 下载Python
        python_mirrors = [url.format(version=PYTHON_VERSION) for url in PYTHON_MIRRORS]
        best_url = self._test_mirror_speed(python_mirrors)
        
        zip_filename = os.path.basename(best_url)
        zip_filepath = os.path.join(portable_dir, zip_filename)
        
        if not self._download_file_with_retry(best_url, zip_filepath):
            return None
        
        # 解压
        if not self._unzip_file(zip_filepath, portable_dir):
            return None
        
        # 清理zip
        if os.path.exists(zip_filepath):
            try:
                os.remove(zip_filepath)
            except OSError:
                pass
        
        # 配置.pth文件
        self._configure_python_pth_file(portable_dir)
        
        # 安装pip
        if not self._install_pip(python_exe_path, portable_dir):
            return None
        
        # 验证
        if os.path.exists(python_exe_path) and os.path.exists(pip_exe_path):
            self.log(f"  ✓ 便携版Python部署成功: {python_exe_path}")
            return python_exe_path
        else:
            self.log("  ✗ 便携版Python部署失败。")
            return None
    
    def _test_mirror_speed(self, mirrors: List[str]) -> str:
        """测试镜像速度"""
        self.log("🔍 正在对比多个镜像源(阿里云/华为云/官方)速度...")
        
        def test_single_mirror(mirror: str) -> Tuple[str, float]:
            try:
                start_time = time.time()
                response = requests.get(mirror, stream=True, timeout=TIMEOUT_MIRROR_SPEED)
                if response.status_code == 200:
                    elapsed_time = time.time() - start_time
                    response.close()
                    return mirror, elapsed_time
            except Exception:
                pass
            return mirror, float('inf')
        
        fastest_mirror = None
        min_time = float('inf')
        
        with ThreadPoolExecutor(max_workers=len(mirrors)) as executor:
            future_to_mirror = {executor.submit(test_single_mirror, m): m for m in mirrors}
            for future in as_completed(future_to_mirror):
                mirror, elapsed = future.result()
                if elapsed < min_time:
                    min_time = elapsed
                    fastest_mirror = mirror
        
        result = fastest_mirror if fastest_mirror else mirrors[0]
        if min_time != float('inf'):
            self.log(f"✅ 测速完成，已优选最佳镜像 (响应时间: {min_time:.2f}秒)")
        else:
            self.log(f"⚠️ 所有镜像测速失败，使用默认镜像")
        return result
    
    def _download_file_with_retry(self, url: str, dest_path: str, max_retries: int = MAX_RETRIES) -> bool:
        """带重试的下载"""
        for attempt in range(max_retries):
            try:
                if self._download_file(url, dest_path):
                    return True
            except Exception as e:
                log_manager.warning(f"下载尝试 {attempt + 1}/{max_retries} 失败: {e}")
                if attempt < max_retries - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
        return False
    
    def _download_file(self, url: str, dest_path: str) -> bool:
        """下载文件"""
        filename = os.path.basename(dest_path)
        self.log(f"  📥 下载中: {filename}")
        self.parent.download_progress_signal.emit(0, filename)
        
        temp_path = dest_path + '.tmp'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=TIMEOUT_DOWNLOAD) as response:
                total_size = int(response.getheader('Content-Length', 0))
                block_size = 8192
                downloaded_size = 0
                last_percent = 0
                
                with open(temp_path, 'wb') as f:
                    while True:
                        if self._is_cancelled:
                            raise Exception("用户取消下载")
                        chunk = response.read(block_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        
                        if total_size > 0:
                            progress_percent = int(downloaded_size * 100 / total_size)
                            if progress_percent - last_percent >= 5 or progress_percent == 100:
                                self.parent.download_progress_signal.emit(progress_percent, filename)
                                last_percent = progress_percent
                            QApplication.processEvents()
            
            if total_size > 0 and downloaded_size != total_size:
                raise ValueError(f"下载不完整: {downloaded_size}/{total_size}")
            
            if os.path.exists(dest_path):
                os.remove(dest_path)
            os.rename(temp_path, dest_path)
            
            self.parent.download_progress_signal.emit(100, filename)
            self.log("  ✓ 下载完成。")
            return True
        except Exception as e:
            self.log(f"  ✗ 下载失败: {e}")
            log_manager.error(f"下载失败 ({url}): {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            self.parent.download_progress_signal.emit(100, filename)
            return False
    
    def _unzip_file(self, zip_path: str, extract_to: str) -> bool:
        """解压文件"""
        self.log(f"📦 解压中: {os.path.basename(zip_path)}")
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to)
            self.log("✓ 解压完成")
            return True
        except Exception as e:
            self.log(f"✗ 解压失败: {e}")
            log_manager.error(f"解压失败: {e}")
            return False
    
    def _configure_python_pth_file(self, portable_dir: str) -> bool:
        """配置.pth文件"""
        pth_file = None
        for item in os.listdir(portable_dir):
            if item.endswith('._pth'):
                pth_file = os.path.join(portable_dir, item)
                break
        
        if not pth_file or not os.path.exists(pth_file):
            return True
        
        self.log("  ⚙️ 配置便携版Python的模块搜索路径...")
        try:
            with open(pth_file, 'r+') as f:
                lines = f.readlines()
                lines = [line for line in lines if 'site-packages' not in line.strip() and 'import site' not in line.strip()]
                content_to_add = ['Lib/site-packages\n', 'import site\n']
                lines.extend(content_to_add)
                f.seek(0)
                f.truncate()
                f.writelines(lines)
            self.log("  ✓ 已为便携版Python启用site-packages。")
            return True
        except Exception as e:
            self.log(f"  ⚠ 修改pth文件失败: {e}")
            return True
    
    def _install_pip(self, python_exe: str, portable_dir: str = None) -> bool:
        """安装pip"""
        if portable_dir is None:
            portable_dir = self.parent.portable_python_dir
        self.log("  🔧 为便携版Python安装pip...")
        get_pip_script_path = os.path.join(portable_dir, 'get-pip.py')
        
        try:
            self.log("    📥 下载pip安装脚本...")
            req = urllib.request.Request(GET_PIP_URL, headers={'User-Agent': 'Python-Packager'})
            with urllib.request.urlopen(req, timeout=60) as response, open(get_pip_script_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
            self.log("    ✓ 下载成功。")
            
            self.log("    ⚙️ 执行pip安装脚本...")
            pip_install_cmd = [python_exe, get_pip_script_path, '--quiet', '--no-warn-script-location']
            creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            result = subprocess.run(
                pip_install_cmd,
                cwd=portable_dir,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_INSTALL,
                creationflags=creationflags
            )
            
            if result.returncode != 0:
                self.log(f"  ✗ pip安装失败: {result.stderr}")
                return False
            
            self.log("  ✓ pip安装成功。")
            return True
            
        except Exception as e:
            self.log(f"  ✗ pip安装流程出错: {e}")
            return False
        finally:
            if os.path.exists(get_pip_script_path):
                try:
                    os.remove(get_pip_script_path)
                except OSError:
                    pass
    
    def _ensure_pyinstaller_installed(self, python_exe: str) -> bool:
        """检查并安装PyInstaller - 快速静默检查"""
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            result = subprocess.run(
                [python_exe, "-m", "PyInstaller", "--version"],
                capture_output=True, text=True, timeout=10, creationflags=creationflags
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                self.log(f"  ✓ PyInstaller已安装: v{version}")
                return True
        except Exception:
            pass
        
        self.log("  ⚠ PyInstaller未安装，正在安装...")
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            result = subprocess.run(
                [python_exe, "-m", "pip", "install", "--no-cache-dir", "pyinstaller"],
                capture_output=True, text=True, timeout=300, creationflags=creationflags
            )
            if result.returncode == 0:
                self.log("  ✓ PyInstaller安装成功")
                return True
            else:
                self.log(f"  ✗ PyInstaller安装失败: {result.stderr}")
                return False
        except Exception as e:
            self.log(f"  ✗ PyInstaller安装出错: {e}")
            return False
    
    def _scan_script_imports(self, script_path: str) -> List[str]:
        """扫描脚本导入"""
        imports = set()
        try:
            with open(script_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            module = alias.name.split('.')[0]
                            if module not in STDLIB_MODULES:
                                imports.add(module)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            module = node.module.split('.')[0]
                            if module not in STDLIB_MODULES:
                                imports.add(module)
            except SyntaxError:
                import_pattern = r'^\s*(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
                matches = re.findall(import_pattern, content, re.MULTILINE)
                for module in matches:
                    if module not in STDLIB_MODULES:
                        imports.add(module)
        except Exception as e:
            self.log(f"⚠ 扫描import时出错: {e}")
            log_manager.warning(f"扫描导入失败: {e}")
        return list(imports)
    
    def _install_dependencies_in_portable(self, python_exe: str, modules: List[str]) -> bool:
        """安装依赖"""
        if not modules:
            return True
        valid_modules = [m for m in modules if validate_module_name(m)]
        if not valid_modules:
            return True
        packages = list(set([IMPORT_TO_PACKAGE_MAP.get(m, m) for m in valid_modules]))
        self.log(f"🔧 检测到脚本依赖，正在安装: {', '.join(packages)}")
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            cmd = [python_exe, "-m", "pip", "install", "--no-cache-dir"] + packages
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, creationflags=creationflags)
            if result.returncode == 0:
                self.log("  ✓ 依赖安装成功")
                return True
            else:
                self.log(f"  ⚠ 部分依赖可能安装失败，继续尝试打包...")
                return True
        except Exception as e:
            self.log(f"  ✗ 依赖安装出错: {e}")
            return False

class PackagingThread(QThread):
    output_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)
    progress_signal = pyqtSignal(int)
    def __init__(self, command: List[str], output_dir: str, 
                 cleanup_files: Optional[List[str]] = None, 
                 env: Optional[Dict[str, str]] = None):
        super().__init__()
        self.command = command
        self.output_dir = output_dir
        self.cleanup_files = cleanup_files or []
        self.env = env or {}
        self._is_cancelled = False
        self.process: Optional[subprocess.Popen] = None
        self._total_steps = 0
        self._current_step = 0
    def cancel(self):
        self._is_cancelled = True
        if not self.process or self.process.poll() is not None:
            return
        try:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        except Exception as e:
            log_manager.error(f"终止进程时出错: {e}")
    def run(self):
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            process_env = os.environ.copy()
            process_env.update(self.env)
            log_manager.info(f"执行命令: {' '.join(self.command)}")
            self.process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                shell=False,
                creationflags=creationflags,
                env=process_env
            )
            while True:
                if self._is_cancelled:
                    self.finished_signal.emit(False, "用户取消了打包")
                    return
                line = self.process.stdout.readline()
                if line:
                    self.output_signal.emit(line.strip())
                    if "Analyzing" in line:
                        self.progress_signal.emit(10)
                    elif "Building" in line:
                        self.progress_signal.emit(30)
                    elif "Collecting" in line:
                        self.progress_signal.emit(50)
                    elif "Creating" in line:
                        self.progress_signal.emit(70)
                    elif "Appending" in line or "Copying" in line:
                        self.progress_signal.emit(85)
                elif self.process.poll() is not None:
                    break
            remaining = self.process.stdout.read()
            if remaining:
                self.output_signal.emit(remaining.strip())
            success = self.process.returncode == 0
            if success:
                self.progress_signal.emit(100)
                self.finished_signal.emit(True, self.output_dir)
            else:
                self.finished_signal.emit(False, f"打包失败，返回码: {self.process.returncode}")
        except FileNotFoundError as e:
            error_msg = f"错误: 'pyinstaller' 命令未找到。\n请确保PyInstaller已安装并在系统的PATH中。\n详情: {e}"
            log_manager.error(error_msg)
            self.finished_signal.emit(False, error_msg)
        except subprocess.SubprocessError as e:
            error_msg = f"子进程错误: {e}"
            log_manager.error(error_msg)
            self.finished_signal.emit(False, error_msg)
        except Exception as e:
            error_msg = f"打包过程异常: {str(e)}"
            log_manager.error(error_msg)
            log_manager.error(traceback.format_exc())
            self.finished_signal.emit(False, error_msg)
        finally:
            self._cleanup()
    def _cleanup(self):
        for f in self.cleanup_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
                    log_manager.debug(f"清理临时文件: {f}")
            except OSError as e:
                error_msg = f"无法清理临时文件 {f}: {e}"
                log_manager.warning(error_msg)
                self.output_signal.emit(error_msg)
@dataclass
class PackageConfig:
    script_path: str = ""
    icon_path: str = ""
    data_files: List[str] = None
    hidden_imports: str = ""
    exclude_modules: str = ""
    onefile: bool = True
    noconsole: bool = True
    clean_build: bool = True
    no_confirm: bool = True
    increase_recursion: bool = False
    uac_admin: bool = True
    output_name: str = ""
    output_dir: str = ""
    def __post_init__(self):
        if self.data_files is None:
            self.data_files = []
        if not self.output_dir:
            self.output_dir = os.path.join(os.path.expanduser("~"), "Desktop")
    def to_dict(self) -> dict:
        return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> 'PackageConfig':
        return cls(**data)
class MainWindow(QMainWindow):
    download_progress_signal = pyqtSignal(int, str)  # 进度百分比, 文件名
    
    def __init__(self):
        super().__init__()
        self.packaging_thread: Optional[PackagingThread] = None
        self.preparation_thread: Optional[PreparationThread] = None
        self.current_script_path = ""
        self.current_exe_name = ""
        self.is_packaging = False
        self.is_preparing = False
        self.portable_python_dir: Optional[str] = None
        self.system_python: Optional[str] = None
        self.config = PackageConfig()
        self.settings = QSettings("PyToExe", "Config")
        self.init_ui()
        self.load_settings()
        
        # 连接下载进度信号
        self.download_progress_signal.connect(self._update_download_progress)
    def init_ui(self):
        self.setWindowTitle(f"Py转Exe_v{VERSION} by Fish")
        self.setMinimumSize(800, 1200)
        self.resize(600, 900)
        self.setStyleSheet(self._get_stylesheet())
        self._create_menu_bar()
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        self._create_script_section(main_layout)
        self._create_icon_section(main_layout)
        self._create_data_section(main_layout)
        self._create_dependency_section(main_layout)
        self._create_output_type_section(main_layout)
        self._create_advanced_options_section(main_layout)
        self._create_output_section(main_layout)
        self._create_action_buttons(main_layout)
        self._create_log_section(main_layout)
    def _create_menu_bar(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("文件")
        save_config_action = QAction("保存配置", self)
        save_config_action.triggered.connect(self.save_config)
        file_menu.addAction(save_config_action)
        load_config_action = QAction("加载配置", self)
        load_config_action.triggered.connect(self.load_config)
        file_menu.addAction(load_config_action)
        file_menu.addSeparator()
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        help_menu = menubar.addMenu("帮助")
        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    def _create_script_section(self, layout):
        script_group = QGroupBox("脚本选择")
        script_layout = QHBoxLayout(script_group)
        script_layout.addWidget(QLabel("脚本路径:"))
        self.script_entry = DragDropLineEdit(".py .pyw")
        script_layout.addWidget(self.script_entry, 1)
        self.browse_script_btn = QPushButton("浏览")
        self.browse_script_btn.setStyleSheet("background-color: #0078D4;")
        self.browse_script_btn.clicked.connect(self.browse_script)
        script_layout.addWidget(self.browse_script_btn)
        layout.addWidget(script_group)
    def _create_icon_section(self, layout):
        icon_group = QGroupBox("图标设置")
        icon_layout = QHBoxLayout(icon_group)
        icon_layout.addWidget(QLabel("图标路径:"))
        self.icon_entry = DragDropLineEdit(".ico .png .jpg .jpeg .bmp")
        icon_layout.addWidget(self.icon_entry, 1)
        self.browse_icon_btn = QPushButton("浏览")
        self.browse_icon_btn.setStyleSheet("background-color: #107C10;")
        self.browse_icon_btn.clicked.connect(self.browse_icon)
        icon_layout.addWidget(self.browse_icon_btn)
        layout.addWidget(icon_group)
    def _create_data_section(self, layout):
        adddata_group = QGroupBox("附加数据")
        adddata_group.setFixedHeight(180)
        adddata_layout = QVBoxLayout(adddata_group)
        adddata_btn_layout = QHBoxLayout()
        self.add_file_btn = QPushButton("添加文件")
        self.add_file_btn.setStyleSheet("background-color: #8764B8;")
        self.add_file_btn.clicked.connect(self.add_data_file)
        adddata_btn_layout.addWidget(self.add_file_btn)
        self.add_folder_btn = QPushButton("添加目录")
        self.add_folder_btn.setStyleSheet("background-color: #00B7C3;")
        self.add_folder_btn.clicked.connect(self.add_data_folder)
        adddata_btn_layout.addWidget(self.add_folder_btn)
        self.remove_data_btn = QPushButton("移除选中")
        self.remove_data_btn.setStyleSheet("background-color: #D83B01;")
        self.remove_data_btn.clicked.connect(self.remove_data_item)
        adddata_btn_layout.addWidget(self.remove_data_btn)
        adddata_btn_layout.addStretch()
        adddata_layout.addLayout(adddata_btn_layout)
        self.adddata_list = DragDropListWidget()
        self.adddata_list.setFixedHeight(88)
        self.adddata_list.setSelectionMode(QAbstractItemView.SingleSelection)
        adddata_layout.addWidget(self.adddata_list)
        layout.addWidget(adddata_group)
    def _create_dependency_section(self, layout):
        dep_group = QGroupBox("依赖管理")
        dep_layout = QVBoxLayout(dep_group)
        hidden_import_layout = QHBoxLayout()
        hidden_import_layout.addWidget(QLabel("隐藏导入:"))
        self.hidden_import_entry = QLineEdit()
        self.hidden_import_entry.setPlaceholderText("逗号分隔,例如: my_module, other_module")
        hidden_import_layout.addWidget(self.hidden_import_entry, 1)
        dep_layout.addLayout(hidden_import_layout)
        exclude_module_layout = QHBoxLayout()
        exclude_module_layout.addWidget(QLabel("排除模块:"))
        self.exclude_module_entry = QLineEdit()
        self.exclude_module_entry.setPlaceholderText("逗号分隔,例如: tkinter, unittest")
        exclude_module_layout.addWidget(self.exclude_module_entry, 1)
        dep_layout.addLayout(exclude_module_layout)
        layout.addWidget(dep_group)
    def _create_output_type_section(self, layout):
        type_console_group = QGroupBox("输出类型 / 控制台窗口")
        type_console_layout = QHBoxLayout(type_console_group)
        self.onefile_radio = QRadioButton("单个文件")
        self.onedir_radio = QRadioButton("单个目录")
        self.onefile_radio.setChecked(True)
        self.type_group = QButtonGroup()
        self.type_group.addButton(self.onefile_radio)
        self.type_group.addButton(self.onedir_radio)
        self.console_radio = QRadioButton("显示控制台")
        self.noconsole_radio = QRadioButton("隐藏控制台")
        self.noconsole_radio.setChecked(True)
        self.console_group = QButtonGroup()
        self.console_group.addButton(self.console_radio)
        self.console_group.addButton(self.noconsole_radio)
        type_console_layout.addWidget(self.onefile_radio)
        type_console_layout.addStretch(1)
        type_console_layout.addWidget(self.onedir_radio)
        type_console_layout.addStretch(1)
        type_console_layout.addWidget(self.noconsole_radio)
        type_console_layout.addStretch(1)
        type_console_layout.addWidget(self.console_radio)
        layout.addWidget(type_console_group)
    def _create_advanced_options_section(self, layout):
        options_group = QGroupBox("高级选项")
        options_layout = QHBoxLayout(options_group)
        self.clean_build_check = QCheckBox("清理构建文件")
        self.clean_build_check.setChecked(True)
        self.no_confirm_check = QCheckBox("覆盖输出目录")
        self.no_confirm_check.setChecked(True)
        self.increase_recursion_check = QCheckBox("增加递归限制")
        self.uac_admin_check = QCheckBox("请求管理员权限")
        self.uac_admin_check.setChecked(True)
        options_layout.addWidget(self.clean_build_check)
        options_layout.addStretch(1)
        options_layout.addWidget(self.uac_admin_check)
        options_layout.addStretch(1)
        options_layout.addWidget(self.increase_recursion_check)
        options_layout.addStretch(1)
        options_layout.addWidget(self.no_confirm_check)
        layout.addWidget(options_group)
    def _create_output_section(self, layout):
        output_group = QGroupBox("输出设置")
        output_layout = QVBoxLayout(output_group)
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("程序名称:"))
        self.name_entry = QLineEdit()
        self.name_entry.setPlaceholderText("留空则使用脚本名称")
        name_layout.addWidget(self.name_entry, 1)
        output_layout.addLayout(name_layout)
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("输出目录:"))
        self.output_entry = QLineEdit()
        self.output_entry.setText(self.config.output_dir)
        dir_layout.addWidget(self.output_entry, 1)
        self.browse_output_btn = QPushButton("浏览")
        self.browse_output_btn.setStyleSheet("background-color: #CA5010;")
        self.browse_output_btn.clicked.connect(self.browse_output)
        dir_layout.addWidget(self.browse_output_btn)
        output_layout.addLayout(dir_layout)
        layout.addWidget(output_group)
    def _create_action_buttons(self, layout):
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.convert_btn = QPushButton("开始打包")
        self.convert_btn.setStyleSheet("background-color: #00BFFF; padding: 10px 30px;")
        self.convert_btn.clicked.connect(self.on_convert_btn_clicked)
        button_layout.addWidget(self.convert_btn)
        self.open_output_btn = QPushButton("打开目录")
        self.open_output_btn.setStyleSheet("background-color: #68217A; padding: 10px 30px;")
        self.open_output_btn.clicked.connect(self.open_output_directory)
        button_layout.addWidget(self.open_output_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
    def _create_log_section(self, layout):
        log_group = QGroupBox("输出日志")
        log_layout = QVBoxLayout(log_group)
        
        # 添加下载进度条
        progress_layout = QHBoxLayout()
        self.download_progress_label = QLabel("下载进度:")
        self.download_progress_label.setVisible(False)
        progress_layout.addWidget(self.download_progress_label)
        
        self.download_progress_bar = QProgressBar()
        self.download_progress_bar.setVisible(False)
        self.download_progress_bar.setMaximum(100)
        self.download_progress_bar.setTextVisible(True)
        self.download_progress_bar.setFormat("%p% - %v/%m")
        progress_layout.addWidget(self.download_progress_bar)
        log_layout.addLayout(progress_layout)
        
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMinimumHeight(150)
        log_layout.addWidget(self.output_text)
        layout.addWidget(log_group)
    def _get_stylesheet(self) -> str:
        return """
QMainWindow, QWidget {background-color: #ffffff; color: #333333; font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; font-size: 18px;}
QGroupBox {border: 1px solid #888888; border-radius: 4px; margin-top: 12px; padding-top: 10px;}
QGroupBox::title {subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #00BFFF; font-size: 18px; font-weight: bold !important;}
QLineEdit, QTextEdit, QListWidget {background-color: #ffffff; border: 1px solid #cccccc; border-radius: 4px; padding: 5px; color: #333333;}
QLineEdit:focus, QTextEdit:focus {border-color: #007acc;}
QPushButton {border: none; border-radius: 4px; padding: 8px 16px; color: white;}
QPushButton:hover {opacity: 0.9;}
QPushButton:pressed {opacity: 0.7;}
QRadioButton, QCheckBox {spacing: 8px;}
QRadioButton::indicator, QCheckBox::indicator {width: 16px; height: 16px;}
QTextEdit {font-family: 'Consolas', 'Courier New', monospace;}
QMenuBar {background-color: #f0f0f0; font-size: 18px;}
QMenuBar::item:selected {background-color: #0078D4; color: white;}
        """
    def save_settings(self):
        self.settings.setValue("icon_path", self.icon_entry.text())
        self.settings.setValue("output_dir", self.output_entry.text())
        self.settings.setValue("onefile", self.onefile_radio.isChecked())
        self.settings.setValue("noconsole", self.noconsole_radio.isChecked())
        self.settings.setValue("clean_build", self.clean_build_check.isChecked())
        self.settings.setValue("uac_admin", self.uac_admin_check.isChecked())
    def load_settings(self):
        self.icon_entry.setText(self.settings.value("icon_path", ""))
        self.output_entry.setText(self.settings.value("output_dir", self.config.output_dir))
        onefile = self.settings.value("onefile", True, type=bool)
        self.onefile_radio.setChecked(onefile)
        self.onedir_radio.setChecked(not onefile)
        noconsole = self.settings.value("noconsole", True, type=bool)
        self.noconsole_radio.setChecked(noconsole)
        self.console_radio.setChecked(not noconsole)
        self.clean_build_check.setChecked(self.settings.value("clean_build", True, type=bool))
        self.uac_admin_check.setChecked(self.settings.value("uac_admin", True, type=bool))
    def save_config(self):
        config = self._get_current_config()
        file_path, _ = QFileDialog.getSaveFileName(self, "保存配置", "", "JSON Files (*.json)")
        if not file_path:
            return
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config.to_dict(), f, ensure_ascii=False, indent=2)
            self.append_output(f"✅ 配置已保存: {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存配置失败: {e}")
    def load_config(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "加载配置", "", "JSON Files (*.json)")
        if not file_path:
            return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                config = PackageConfig.from_dict(data)
                self._apply_config(config)
            self.append_output(f"✅ 配置已加载: {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载配置失败: {e}")
    def _get_current_config(self) -> PackageConfig:
        data_files = [self.adddata_list.item(i).text() for i in range(self.adddata_list.count())]
        return PackageConfig(
            script_path=self.script_entry.text(),
            icon_path=self.icon_entry.text(),
            data_files=data_files,
            hidden_imports=self.hidden_import_entry.text(),
            exclude_modules=self.exclude_module_entry.text(),
            onefile=self.onefile_radio.isChecked(),
            noconsole=self.noconsole_radio.isChecked(),
            clean_build=self.clean_build_check.isChecked(),
            no_confirm=self.no_confirm_check.isChecked(),
            increase_recursion=self.increase_recursion_check.isChecked(),
            uac_admin=self.uac_admin_check.isChecked(),
            output_name=self.name_entry.text(),
            output_dir=self.output_entry.text()
        )
    def _apply_config(self, config: PackageConfig):
        self.script_entry.setText(config.script_path)
        self.icon_entry.setText(config.icon_path)
        self.adddata_list.clear()
        for f in config.data_files:
            self.adddata_list.addItem(f)
        self.hidden_import_entry.setText(config.hidden_imports)
        self.exclude_module_entry.setText(config.exclude_modules)
        self.onefile_radio.setChecked(config.onefile)
        self.onedir_radio.setChecked(not config.onefile)
        self.noconsole_radio.setChecked(config.noconsole)
        self.console_radio.setChecked(not config.noconsole)
        self.clean_build_check.setChecked(config.clean_build)
        self.no_confirm_check.setChecked(config.no_confirm)
        self.increase_recursion_check.setChecked(config.increase_recursion)
        self.uac_admin_check.setChecked(config.uac_admin)
        self.name_entry.setText(config.output_name)
        self.output_entry.setText(config.output_dir)
    def append_output(self, text: str):
        """立即输出日志，不缓冲"""
        self.output_text.append(text)
        self.output_text.moveCursor(QTextCursor.End)
        QApplication.processEvents()  # 强制立即刷新UI
    def _flush_log_buffer(self):
        """保留此方法以兼容性，但不再使用缓冲"""
        pass
    
    def _update_download_progress(self, percent: int, filename: str):
        """更新下载进度条"""
        if percent == 0:
            # 开始下载
            self.download_progress_label.setText(f"下载进度: {filename}")
            self.download_progress_label.setVisible(True)
            self.download_progress_bar.setVisible(True)
            self.download_progress_bar.setValue(0)
        elif percent == 100:
            # 下载完成
            self.download_progress_bar.setValue(100)
            QTimer.singleShot(1000, lambda: self.download_progress_label.setVisible(False))
            QTimer.singleShot(1000, lambda: self.download_progress_bar.setVisible(False))
        else:
            # 更新进度
            self.download_progress_bar.setValue(percent)
    def _is_temp_python(self, path: str) -> bool:
        if not path:
            return True
        exclude_patterns = ['onefile_', 'AppData\\Local\\Temp', 'AppData/Local/Temp', 
                          '\\Temp\\', '/tmp/', '_MEI']
        path_lower = path.lower()
        return any(pattern.lower() in path_lower for pattern in exclude_patterns)
    def _find_system_python(self) -> Optional[str]:
        is_frozen = getattr(sys, 'frozen', False)
        is_nuitka = '__compiled__' in dir() or '__nuitka__' in dir()
        is_temp_exe = self._is_temp_python(sys.executable)
        if not is_frozen and not is_nuitka and not is_temp_exe:
            return sys.executable
        for cmd in ['py', 'python', 'python3']:
            try:
                result = subprocess.run(
                    [cmd, '--version'],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                )
                if result.returncode != 0 or 'Python' not in result.stdout:
                    continue
                python_path = self._get_executable_path(cmd)
                if python_path and os.path.exists(python_path) and not self._is_temp_python(python_path):
                    return python_path
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
            except Exception as e:
                log_manager.debug(f"查找Python时出错 ({cmd}): {e}")
        return None
    def _get_executable_path(self, cmd: str) -> Optional[str]:
        try:
            if sys.platform == 'win32':
                result = subprocess.run(['where', cmd], capture_output=True, text=True, 
                                      timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                result = subprocess.run(['which', cmd], capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                return None
            for line in result.stdout.strip().split('\n'):
                path = line.strip()
                if os.path.exists(path):
                    return path
        except Exception as e:
            log_manager.debug(f"获取可执行路径时出错: {e}")
        return None

    def _check_disk_space(self, path: str, required_mb: int = MIN_DISK_SPACE_MB) -> Tuple[bool, float]:
        try:
            if not path or not os.path.exists(os.path.dirname(path) or path):
                return True, 0
            if sys.platform == 'win32':
                import ctypes
                free_bytes = ctypes.c_ulonglong(0)
                ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                    ctypes.c_wchar_p(os.path.dirname(path) or path), 
                    None, None, ctypes.pointer(free_bytes)
                )
                free_mb = free_bytes.value / (1024 * 1024)
            else:
                st = os.statvfs(path)
                free_mb = (st.f_bavail * st.f_frsize) / (1024 * 1024)
            return free_mb >= required_mb, free_mb
        except Exception as e:
            log_manager.warning(f"检查磁盘空间时出错: {e}")
            return True, 0
    def _check_network(self, timeout: int = 5) -> bool:
        test_urls = ['https://www.baidu.com', 'https://pypi.tuna.tsinghua.edu.cn', 'https://pypi.org']
        for url in test_urls:
            try:
                req = urllib.request.Request(url, method='HEAD')
                req.add_header('User-Agent', 'Mozilla/5.0')
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    if response.status == 200:
                        return True
            except Exception:
                continue
        return False



        
    

    

    

    

    

    







    def _check_upx_valid(self) -> bool:
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            subprocess.run(
                ["upx", "--version"], 
                capture_output=True, 
                text=True, 
                check=True, 
                timeout=TIMEOUT_COMMAND,
                creationflags=creationflags
            )
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
            return False
    
    def _download_upx(self) -> bool:
        if platform.system() != "Windows":
            self.append_output("❌ 自动下载UPX暂仅支持Windows")
            return False
        
        upx_version = "4.2.4"
        upx_arch = "win64" if platform.architecture()[0] == "64bit" else "win32"
        upx_filename = f"upx-{upx_version}-{upx_arch}.zip"
        upx_inner_folder = f"upx-{upx_version}-{upx_arch}"
        
        # 多个镜像源（优先国内镜像）
        mirrors = [
            (f"https://github.com/upx/upx/releases/download/v{upx_version}/{upx_filename}", "zip", "GitHub官方"),
            (f"https://mirror.ghproxy.com/https://github.com/upx/upx/releases/download/v{upx_version}/{upx_filename}", "zip", "GitHub代理"),
            (f"https://objects.githubusercontent.com/github-production-release-asset-2e65be/67031040/{upx_filename}", "zip", "GitHub直连"),
        ]
        
        final_upx_dir = Path(tempfile.gettempdir()) / "autopytoexe_upx"
        final_upx_dir.mkdir(exist_ok=True)
        final_upx_exe = final_upx_dir / "upx.exe"
        
        download_success = False
        self.append_output("  📥 尝试从多个镜像下载UPX...")
        
        for i, (mirror_url, file_type, mirror_name) in enumerate(mirrors, 1):
            try:
                self.append_output(f"    [{i}/{len(mirrors)}] {mirror_name}")
                
                response = requests.get(mirror_url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
                response.raise_for_status()
                
                if file_type == "exe":
                    with open(final_upx_exe, 'wb') as f:
                        f.write(response.content)
                    self.append_output(f"    ✓ 下载成功")
                    download_success = True
                    break
                else:
                    upx_save_path = Path(tempfile.gettempdir()) / upx_filename
                    with open(upx_save_path, 'wb') as f:
                        f.write(response.content)
                    
                    upx_extract_dir = Path(tempfile.gettempdir()) / "upx_extract_temp"
                    if upx_extract_dir.exists():
                        shutil.rmtree(upx_extract_dir)
                    
                    with zipfile.ZipFile(upx_save_path, 'r') as zip_ref:
                        zip_ref.extractall(upx_extract_dir)
                    
                    upx_exe_in_zip = upx_extract_dir / upx_inner_folder / "upx.exe"
                    if upx_exe_in_zip.exists():
                        if final_upx_exe.exists():
                            final_upx_exe.unlink()
                        shutil.move(str(upx_exe_in_zip), str(final_upx_exe))
                        shutil.rmtree(upx_extract_dir)
                        upx_save_path.unlink()
                        self.append_output(f"    ✓ 下载并解压成功")
                        download_success = True
                        break
                    else:
                        self.append_output(f"    ✗ 解压失败")
                        continue
                        
            except Exception as e:
                self.append_output(f"    ✗ 失败: {type(e).__name__}")
                continue
        
        if not download_success:
            self.append_output("  ❌ 所有镜像下载均失败")
            return False
        
        if not final_upx_exe.exists():
            return False
            
        os.environ['PATH'] = f"{str(final_upx_dir)}{os.pathsep}{os.environ.get('PATH', '')}"
        return True
    
    def _ensure_upx_ready(self) -> Tuple[bool, str]:
        self.append_output("🔍 检查UPX压缩工具...")
        if self._check_upx_valid():
            self.append_output("  ✓ UPX已就绪")
            return True, ""
        self.append_output("  ⚠ UPX未安装，尝试自动下载...")
        if self._download_upx() and shutil.which("upx"):
            self.append_output("  ✓ UPX配置成功")
            return True, ""
        self.append_output("  ⚠ UPX配置失败，将跳过压缩")
        return False, ""
    def show_version_info(self):
        python_version = sys.version.split()[0]
        info = f"工具版本 {VERSION} | Python {python_version} | PyInstaller v{pyinstaller_version}"
        self.output_text.append(info)
        self.output_text.append("=" * 60)
    def show_about(self):
        QMessageBox.about(self, "关于", 
            f"<h2>Py转Exe工具 v{VERSION}</h2>"
            f"<p>基于PyInstaller的Python打包工具</p>"
            f"<p>优化版 - 增强稳定性与健壮性</p>"
            f"<p>支持自动部署Python环境和UPX压缩</p>"
        )
    def browse_script(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择Python脚本", "", "Python Files (*.py *.pyw)")
        if not file_path:
            return
        self.script_entry.setText(file_path)
        if not self.name_entry.text():
            self.name_entry.setText(Path(file_path).stem)
    def browse_icon(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择图标", "", "Icon Files (*.ico *.png *.jpg *.jpeg *.bmp)")
        if file_path:
            self.icon_entry.setText(file_path)
    def browse_output(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if dir_path:
            self.output_entry.setText(dir_path)
    def add_data_file(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择文件")
        for f in files:
            if not self.adddata_list.findItems(f, Qt.MatchExactly):
                self.adddata_list.addItem(f)
    def add_data_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择目录")
        if folder and not self.adddata_list.findItems(folder, Qt.MatchExactly):
            self.adddata_list.addItem(folder)
    def remove_data_item(self):
        current_item = self.adddata_list.currentItem()
        if current_item:
            self.adddata_list.takeItem(self.adddata_list.row(current_item))
    def open_output_directory(self):
        output_dir = self.output_entry.text()
        if not output_dir or not os.path.exists(output_dir):
            QMessageBox.warning(self, "警告", "输出目录不存在！")
            return
        try:
            if platform.system() == "Windows":
                os.startfile(output_dir)
            elif platform.system() == "Darwin":
                subprocess.run(['open', output_dir], check=True)
            else:
                subprocess.run(['xdg-open', output_dir], check=True)
        except Exception as e:
            QMessageBox.warning(self, "警告", f"无法打开目录: {e}")
    def on_convert_btn_clicked(self):
        if self.is_packaging or self.is_preparing:
            self.cancel_packaging()
        else:
            self.start_conversion()
    
    def start_conversion(self):
        script_path = self.script_entry.text().strip()
        if not script_path or not os.path.exists(script_path):
            QMessageBox.warning(self, "警告", "请选择一个有效的Python脚本文件！")
            return
        
        self.output_text.clear()
        self.show_version_info()
        self.append_output("▶️ 开始打包...")
        
        # 标记为准备中
        self.is_preparing = True
        self.convert_btn.setText("取消准备")
        self.convert_btn.setStyleSheet("background-color: #FFA500; padding: 10px 30px;")
        
        # 创建准备线程
        self.preparation_thread = PreparationThread(self, script_path)
        self.preparation_thread.output_signal.connect(self.append_output)
        self.preparation_thread.finished_signal.connect(self.on_preparation_finished)
        self.preparation_thread.start()
    
    def on_preparation_finished(self, success: bool, message: str, python_exe):
        """环境准备完成的回调"""
        self.is_preparing = False
        
        if not success:
            self.append_output(f"❌ {message}")
            self.convert_btn.setText("开始打包")
            self.convert_btn.setStyleSheet("background-color: #00BFFF; padding: 10px 30px;")
            if "用户取消" not in message:
                QMessageBox.critical(self, "错误", message)
            return
        
        # 准备成功，直接开始打包（不输出额外消息）
        self._start_packaging_with_python(python_exe)
    
    def _start_packaging_with_python(self, python_exe: str):
        """使用准备好的Python环境开始打包"""
        script_path = self.script_entry.text().strip()
        
        self.append_output("=" * 60)
        self.append_output("📦 开始构建打包命令...")
        
        cmd_parts: List[str] = ["pyinstaller"]
        temp_files: List[str] = []
        env_vars = {}
        
        if self.portable_python_dir:
            scripts_path = os.path.join(self.portable_python_dir, 'Scripts')
            new_path = f"{self.portable_python_dir}{os.pathsep}{scripts_path}{os.pathsep}{os.environ.get('PATH', '')}"
            env_vars['PATH'] = new_path
        
        try:
            cmd_parts.append("--onefile" if self.onefile_radio.isChecked() else "--onedir")
            cmd_parts.append("--noconsole" if self.noconsole_radio.isChecked() else "--console")
            
            icon_path = self.icon_entry.text().strip()
            if icon_path and os.path.exists(icon_path):
                if not icon_path.lower().endswith('.ico'):
                    converted_ico_path = self._convert_icon_to_ico(icon_path)
                    if converted_ico_path:
                        temp_files.append(converted_ico_path)
                        cmd_parts.extend(["--icon", converted_ico_path])
                else:
                    cmd_parts.extend(["--icon", icon_path])
            
            name = sanitize_input(self.name_entry.text().strip())
            if name:
                cmd_parts.extend(['--name', name])
            self.current_exe_name = name if name else Path(script_path).stem
            self.current_script_path = script_path
            
            output_dir = self.output_entry.text().strip()
            if output_dir:
                cmd_parts.extend(['--distpath', output_dir])
            
            for i in range(self.adddata_list.count()):
                item_path = self.adddata_list.item(i).text()
                if os.path.exists(item_path):
                    dest_folder = "." if os.path.isfile(item_path) else os.path.basename(item_path)
                    data_arg = f"{item_path}{os.pathsep}{dest_folder}"
                    cmd_parts.extend(['--add-data', data_arg])
            
            hidden_imports = sanitize_input(self.hidden_import_entry.text().strip())
            if hidden_imports:
                for module in [m.strip() for m in hidden_imports.split(',') if m.strip()]:
                    if validate_module_name(module):
                        cmd_parts.extend(['--hidden-import', module])
            
            exclude_modules = sanitize_input(self.exclude_module_entry.text().strip())
            if exclude_modules:
                for module in [m.strip() for m in exclude_modules.split(',') if m.strip()]:
                    if validate_module_name(module):
                        cmd_parts.extend(['--exclude-module', module])
            
            if self.clean_build_check.isChecked():
                cmd_parts.append("--clean")
            if self.no_confirm_check.isChecked():
                cmd_parts.append("--noconfirm")
            if self.uac_admin_check.isChecked() and platform.system() == "Windows":
                cmd_parts.append("--uac-admin")
            if self.increase_recursion_check.isChecked():
                cmd_parts.extend(['--recursion-limit', '5000'])
            
            upx_ready, _ = self._ensure_upx_ready()
            if upx_ready:
                upx_path = shutil.which("upx")
                if upx_path:
                    upx_dir = os.path.dirname(upx_path)
                    cmd_parts.extend(['--upx-dir', upx_dir])
            
            cmd_parts.append(script_path)
            
            self.append_output("=" * 60)
            self.append_output("🚀 执行PyInstaller打包命令")
            self.append_output(f"命令: {' '.join(cmd_parts)}")
            self.append_output("=" * 60)
            
            self.is_packaging = True
            self.convert_btn.setText("取消打包")
            self.convert_btn.setStyleSheet("background-color: #A1260D; padding: 10px 30px;")
            
            self.packaging_thread = PackagingThread(cmd_parts, output_dir, temp_files, env_vars if env_vars else None)
            self.packaging_thread.output_signal.connect(self.append_output)
            self.packaging_thread.finished_signal.connect(self.on_packaging_finished)
            self.packaging_thread.start()
            
        except Exception as e:
            self.append_output(f"❌ 启动打包失败: {e}")
            log_manager.error(f"启动打包失败: {e}")
            log_manager.error(traceback.format_exc())
            self.on_packaging_finished(False, str(e))
            for f in temp_files:
                if f and os.path.exists(f):
                    try:
                        os.remove(f)
                    except OSError as e:
                        log_manager.warning(f"清理临时文件失败 {f}: {e}")
    def _convert_icon_to_ico(self, icon_path: str) -> Optional[str]:
        try:
            with Image.open(icon_path) as img:
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                with tempfile.NamedTemporaryFile(suffix=".ico", delete=False) as tmp:
                    converted_ico_path = tmp.name
                icon_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
                img.save(converted_ico_path, format='ICO', sizes=icon_sizes)
            if os.path.exists(converted_ico_path) and os.path.getsize(converted_ico_path) > 0:
                self.append_output(f"✅ 图标已转换: {converted_ico_path}")
                return converted_ico_path
            else:
                raise ValueError("转换后的ICO文件无效")
        except Exception as e:
            self.append_output(f"❌ 图标转换失败: {e}")
            log_manager.error(f"图标转换失败: {e}")
            return None
    def cancel_packaging(self):
        """取消打包或准备"""
        if self.preparation_thread and self.preparation_thread.isRunning():
            self.append_output("⚠️ 正在取消准备...")
            self.preparation_thread.cancel()
            self.preparation_thread.wait(2000)
            self.is_preparing = False
            self.convert_btn.setText("开始打包")
            self.convert_btn.setStyleSheet("background-color: #00BFFF; padding: 10px 30px;")
        
        if self.packaging_thread and self.packaging_thread.isRunning():
            self.append_output("⚠️ 正在取消打包...")
            self.packaging_thread.cancel()
    def on_packaging_finished(self, success: bool, message: str):
        self.is_packaging = False
        self.convert_btn.setText("开始打包")
        self.convert_btn.setStyleSheet("background-color: #00BFFF; padding: 10px 30px;")
        self._flush_log_buffer()
        self.append_output("\n" + "=" * 60)
        if success:
            if self.clean_build_check.isChecked() and self.current_exe_name:
                try:
                    build_dir = Path.cwd() / "build"
                    if build_dir.exists():
                        shutil.rmtree(build_dir)
                        self.append_output("✅ 已清理 build 文件夹")
                    spec_file = Path.cwd() / f"{self.current_exe_name}.spec"
                    if spec_file.exists():
                        spec_file.unlink()
                        self.append_output(f"✅ 已清理 {spec_file.name}")
                except Exception as e:
                    self.append_output(f"⚠️ 清理构建文件时出错: {e}")
            exe_size_str = self._get_exe_size()
            if exe_size_str:
                self.append_output(f"✅ 打包成功，体积为：{exe_size_str}")
            else:
                self.append_output("✅ 打包成功完成！")
            self.append_output(f"📂 输出目录: {message}")
            self.save_settings()
            QApplication.beep()
        else:
            self.append_output(f"❌ 打包失败: {message}")
            if "用户取消" not in message:
                QMessageBox.critical(self, "打包失败", message)
        self.append_output("=" * 60)
        self.packaging_thread = None
    def _get_exe_size(self) -> Optional[str]:
        try:
            output_dir = self.output_entry.text().strip()
            if not output_dir or not os.path.exists(output_dir):
                return None
            if self.onefile_radio.isChecked():
                exe_path = os.path.join(output_dir, f"{self.current_exe_name}.exe")
                if os.path.exists(exe_path):
                    size_bytes = os.path.getsize(exe_path)
                    return self._format_size(size_bytes)
            else:
                dist_folder = os.path.join(output_dir, self.current_exe_name)
                if os.path.exists(dist_folder):
                    total_size = 0
                    for dirpath, dirnames, filenames in os.walk(dist_folder):
                        for filename in filenames:
                            filepath = os.path.join(dirpath, filename)
                            total_size += os.path.getsize(filepath)
                    return self._format_size(total_size)
            return None
        except Exception as e:
            log_manager.warning(f"获取文件大小失败: {e}")
            return None
    def _format_size(self, size_bytes: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f}{unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f}TB"
    def showEvent(self, event):
        super().showEvent(event)
        if not hasattr(self, '_version_info_shown'):
            self._version_info_shown = True
            self.show_version_info()
    def closeEvent(self, event):
        if (self.packaging_thread and self.packaging_thread.isRunning()) or \
           (self.preparation_thread and self.preparation_thread.isRunning()):
            reply = QMessageBox.question(
                self, "确认退出", "打包正在进行中，确定要退出吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                if self.preparation_thread and self.preparation_thread.isRunning():
                    self.preparation_thread.cancel()
                    self.preparation_thread.wait(2000)
                if self.packaging_thread and self.packaging_thread.isRunning():
                    self.packaging_thread.cancel()
                    if not self.packaging_thread.wait(5000):
                        self.packaging_thread.terminate()
                event.accept()
            else:
                event.ignore()
        else:
            self.save_settings()
            event.accept()
def run():
    try:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        app.setApplicationName("Py转Exe工具")
        app.setApplicationVersion(VERSION)
        window = MainWindow()
        window.show()
        sys.exit(app.exec_())
    except Exception:
        error_log = os.path.join(os.path.expanduser("~"), "py_to_exe_error.log")
        with open(error_log, 'w', encoding='utf-8') as f:
            f.write(traceback.format_exc())
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setText("应用程序遇到致命错误")
        msg.setInformativeText(f"错误日志已保存到:\n{error_log}")
        msg.setWindowTitle("错误")
        msg.exec_()
        raise
if __name__ == "__main__":
    run()