import shutil
import subprocess
import threading
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QFileDialog, QCheckBox, QInputDialog, QComboBox,
                             QMessageBox, QProgressBar, QTextEdit, QProgressDialog, QLineEdit)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
import zipfile
import py7zr
import rarfile
import l4d2_vpk_lib as vpk
import sys
from datetime import datetime
import configparser
import re
import time
import psutil
import requests
from packaging import version
import traceback

CURRENT_VERSION = "1.0.6"
UPDATE_CHECK_URL = "https://api.github.com/repos/Mineralcr/l4d2_Map_Tools/releases/latest"
CONFIG_FILE = "map_tools_config.ini"


class UpdateChecker(QThread):
    update_available_signal = pyqtSignal(str)
    no_update_signal = pyqtSignal()

    def run(self):
        try:
            response = requests.get(UPDATE_CHECK_URL)
            if response.status_code == 200:
                latest_release = response.json()
                target_asset = None
                latest_version = None

                for asset in latest_release["assets"]:
                    name = asset["name"]
                    if name.startswith("l4d2_map_tools_") and name.endswith(".zip"):
                        version_part = name.split("_")[-1].replace(".zip", "")
                        try:
                            version.parse(version_part)
                            latest_version = version_part
                            target_asset = asset
                            break
                        except version.InvalidVersion:
                            continue

                if target_asset:
                    if version.parse(latest_version) > version.parse(CURRENT_VERSION):
                        download_url = target_asset["browser_download_url"]
                        self.update_available_signal.emit(download_url)
                    else:
                        self.no_update_signal.emit()
                else:
                    self.no_update_signal.emit()
            else:
                self.no_update_signal.emit()
        except Exception:
            self.no_update_signal.emit()


class UpdateDownloader(QThread):
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal()

    def __init__(self, download_url):
        super().__init__()
        self.download_url = download_url

    def run(self):
        try:
            response = requests.get(self.download_url, stream=True)
            total_size = int(response.headers.get('content-length', 0))
            block_size = 1024
            progress = 0
            with open("update.zip", 'wb') as f:
                for data in response.iter_content(block_size):
                    progress += len(data)
                    f.write(data)
                    percent = int((progress / total_size) * 100)
                    self.progress_signal.emit(percent)
            self.finished_signal.emit()
        except Exception:
            pass


class MapBuilder:
    def __init__(self, original_bsp_path, exe_path, dict_exist_signal):
        self.original_bsp_path = original_bsp_path
        self.file_name = os.path.basename(original_bsp_path)
        self.l4d2_exe_path = exe_path
        self.l4d2_maps_path = os.path.join(
        os.path.dirname(exe_path),
        "left4dead2",
        "maps"
        )
        self.dict_exist_signal = dict_exist_signal

    def _copy_map_file(self):
        if not self.l4d2_exe_path:
            raise ValueError("未选择left4dead2.exe 路径")
        
        target_path = os.path.join(self.l4d2_maps_path, self.file_name)
        shutil.copy2(self.original_bsp_path, target_path)
        map_name = self.file_name.replace(".bsp", "")
        return target_path, map_name

    def _run_process(self, command):
        try:
            process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW
            )
            process.communicate()

        except Exception as e:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.dict_exist_signal.emit(f"[{current_time}] 启动失败: {str(e)}")
            self.dict_exist_signal.emit(
            f"[{current_time}] 提示：如果路径正确但启动失败，建议通过Steam验证游戏文件完整性,并保证已连接steam")

    def _restore_map_file(self, target_path):
        current_time2 = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if os.path.getsize(target_path) != os.path.getsize(self.original_bsp_path):
            shutil.copy2(target_path, self.original_bsp_path)
            self.dict_exist_signal.emit(f"Progress:[{current_time2}] 反射和字典重建完成...")
            os.remove(target_path)
            return True
        else:
            self.dict_exist_signal.emit(f"Progress:[{current_time2}] 反射和字典重建失败!请尝试手动重建!")
            os.remove(target_path)
            return False

    def start_dictionary_process(self, launch_options):
        target_path, map_name = self._copy_map_file()
        command = [
            self.l4d2_exe_path,
            "-steam", "-novid",
            "-hidden", "-nosound", "-noborder",
            "-heapsize", "2097151",
            "+map", map_name, "-stringtabledictionary", "-buildcubemaps"
        ]
        command.extend(launch_options)

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.dict_exist_signal.emit(f"Progress:[{current_time}] 正在重建字典和反射...")
        self._run_process(command)
        return self._restore_map_file(target_path)

def remove_directory_with_retries(file_path, max_retries=5):
    retries = 0
    while retries < max_retries:
        if os.path.exists(file_path):
            try:
                if os.path.isfile(file_path): 
                    os.remove(file_path)
                elif os.path.isdir(file_path): 
                    shutil.rmtree(file_path, ignore_errors=False)
                if not os.path.exists(file_path):
                    return True
            except Exception as e:
                print(f"Deletion attempt {retries + 1} failed:")
                print(f"Error type: {type(e).__name__}")
                print(f"Error details: {str(e)}")
                print("Traceback:")
                traceback.print_exc()
            
            retries += 1
            time.sleep(1) 
        else:
            return True
    return False

class FileProcessor(QThread):
    progress_signal = pyqtSignal(int)
    message_signal = pyqtSignal(str)
    dict_exist_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool)

    def __init__(self, input_path, rename_path, output_path, output_type, check_dictionary, bsp_path, auto_compress_dict,
                 main_window):
        super().__init__()
        self.input_path = input_path
        self.rename_path = rename_path
        self.output_path = output_path
        self.output_type = output_type
        self.check_dictionary = check_dictionary
        self.bsp_path = bsp_path
        self.temp_dir = os.path.join(self.output_path, "temp_vpk")
        self.temp_dir_file = os.path.join(self.output_path, "temp_vpk_file")
        self.temp_client_dir_file = os.path.join(self.output_path, "temp_vpk_client_file")
        self.auto_compress_dict = auto_compress_dict
        self.main_window = main_window
        self.launch_options = main_window.launch_options
        self.client_output_path = None

    def emit_same_message(self, message):
        self.message_signal.emit(message)
        self.dict_exist_signal.emit(message)

    def run(self):
        try:
            if self.input_path.lower().endswith(('.zip',  '.7z', '.rar')):
                current_time = datetime.now().strftime("%Y-%m-%d    %H:%M:%S")
                message = f"[{current_time}]正在解压文件..."
                self.emit_same_message(message) 
                self.extract_archive() 
                vpk_files = [
                    os.path.join(root,  f)
                    for root, dirs, files in os.walk(self.temp_dir) 
                    for f in files
                    if f.lower().endswith('.vpk') 
                ]
                if not vpk_files:
                    raise Exception("压缩包中没有找到VPK文件")

                if len(vpk_files) > 1:
                    if os.path.exists(self.temp_dir_file): 
                        if remove_directory_with_retries(self.temp_dir_file):
                            os.makedirs(self.temp_dir_file) 
                    else:
                        os.makedirs(self.temp_dir_file)
                    for vpk_file in vpk_files:
                        thread = threading.Thread(target=self.export_vpk_files,  args=(vpk_file,)) 
                        thread.start()  
                        thread.join()
                else:
                    self.input_path  = vpk_files[0]
            elif not self.input_path.lower().endswith('.vpk'): 
                raise Exception("输入文件不是VPK文件")

            if not os.path.exists(self.temp_dir_file): 
                if os.path.exists(self.temp_dir_file): 
                    if remove_directory_with_retries(self.temp_dir_file):
                        os.makedirs(self.temp_dir_file) 
                else:
                    os.makedirs(self.temp_dir_file) 

            if not os.listdir(self.temp_dir_file): 
                thread = threading.Thread(target=self.export_vpk_files,  args=(self.input_path,))  
                thread.start()  
                thread.join()

            current_time = datetime.now().strftime("%Y-%m-%d    %H:%M:%S")
            message = f"[{current_time}]正在处理VPK文件..."
            self.emit_same_message(message) 
            self.process_vpk() 
            remove_directory_with_retries(self.rename_path)

            if self.output_type != "vpk": 
                current_time = datetime.now().strftime("%Y-%m-%d    %H:%M:%S")
                message = f"[{current_time}]正在压缩文件..."
                self.emit_same_message(message) 
                self.compress_output() 

            current_time = datetime.now().strftime("%Y-%m-%d    %H:%M:%S")
            message = f"[{current_time}]处理完成！"
            self.emit_same_message(message) 
            self.finished_signal.emit(True) 

        except Exception as e: 
            current_time = datetime.now().strftime("%Y-%m-%d     %H:%M:%S") 
            message = f"[{current_time}]错误: {str(e)}" 
            self.emit_same_message(message)  
            self.finished_signal.emit(False)  
        finally: 
            remove_directory_with_retries(self.temp_dir)
            remove_directory_with_retries(self.rename_path)
            remove_directory_with_retries(self.temp_dir_file)
            remove_directory_with_retries(self.temp_client_dir_file)
    
    def export_vpk_files(self, vpk_file): 
        original_vpk = vpk.open(vpk_file)  
        for file_path in original_vpk: 
            file = original_vpk.get_file(file_path)  
            dest_path = os.path.join(self.temp_dir_file,  file_path) 
            os.makedirs(os.path.dirname(dest_path),  exist_ok=True) 
            with open(dest_path, 'wb') as f: 
                f.write(file.read()) 

    def extract_archive(self):
        if os.path.exists(self.temp_dir):
            if remove_directory_with_retries(self.temp_dir):
                os.makedirs(self.temp_dir)
        else:
            os.makedirs(self.temp_dir)

        if self.input_path.lower().endswith('.zip'):
            with zipfile.ZipFile(self.input_path, 'r') as zip_ref:
                zip_ref.extractall(self.temp_dir)
        elif self.input_path.lower().endswith('.7z'):
            with py7zr.SevenZipFile(self.input_path, mode='r') as z:
                z.extractall(path=self.temp_dir)
        elif self.input_path.lower().endswith('.rar'):
            with rarfile.RarFile(self.input_path, 'r') as rar_ref:
                rar_ref.extractall(self.temp_dir)

        self.progress_signal.emit(30)

    def process_vpk(self):
        self.progress_signal.emit(30)
        if os.path.exists(self.temp_dir):
            remove_directory_with_retries(self.temp_dir)
        if self.check_dictionary:
            bsp_files = []
            maps_dir = os.path.join(self.temp_dir_file, "maps")
            if os.path.exists(maps_dir):
                for root, dirs, files in os.walk(maps_dir):
                    for file in files:
                        if file.lower().endswith('.bsp'):
                            bsp_files.append(os.path.join(root, file))
            else:
                current_time = datetime.now().strftime("%Y-%m-%d    %H:%M:%S")
                message = f"[{current_time}]警告：未找到maps文件夹"
                self.emit_same_message(message)

            b = 0
            d = 0
            for bsp_file in bsp_files:
                with open(bsp_file, 'rb') as file:
                    content = file.read()
                    pattern = b"\x73\x74\x72\x69\x6E\x67\x74\x61\x62\x6C\x65\x5F\x64\x69\x63\x74\x69\x6F\x6E\x61\x72\x79\x2E\x64\x63\x74\x50\x4B"
                    offset = content.find(pattern)
                    dname = os.path.splitext(os.path.basename(bsp_file))[0]

                    if offset >= 0:
                        current_time = datetime.now().strftime("%Y-%m-%d    %H:%M:%S")
                        message = f"[{current_time}]地图名称: {dname}.bsp, 字典存在,安全!"
                        self.dict_exist_signal.emit(message)
                    else:
                        if self.auto_compress_dict:
                            exe_path = self.main_window.get_l4d2_exe_path(use_config=True)
                            if not exe_path:
                                raise Exception("用户取消选择exe路径")

                            current_time = datetime.now().strftime("%Y-%m-%d    %H:%M:%S")
                            message = f"[{current_time}]地图名称: {dname}.bsp, 字典缺失，正在进行处理!"
                            self.emit_same_message(message)
                            builder = MapBuilder(bsp_file, exe_path, self.dict_exist_signal)
                            # builder.start_cubemap_process()
                            if builder.start_dictionary_process(self.launch_options):
                                d += 1
                            b += 1
                        else:
                            reply = QMessageBox.question(self.main_window, "确认操作",
                                                         f"{bsp_file}  存在缺少字典的小图，是否继续处理？",
                                                         QMessageBox.Yes | QMessageBox.No)
                            if reply == QMessageBox.No:
                                raise Exception("用户取消处理")
                            else:
                                exe_path = self.main_window.get_l4d2_exe_path(use_config=True)
                                if not exe_path:
                                    raise Exception("用户取消选择exe路径")

                                self.auto_compress_dict = True
                                current_time = datetime.now().strftime("%Y-%m-%d    %H:%M:%S")
                                message = f"[{current_time}]地图名称: {dname}.bsp, 字典缺失，正在进行处理!"
                                self.emit_same_message(message)
                                builder = MapBuilder(bsp_file, exe_path, self.dict_exist_signal)
                                # builder.start_cubemap_process()
                                if builder.start_dictionary_process(self.launch_options):
                                    d += 1
                            b += 1

            if b == 0:
                current_time = datetime.now().strftime("%Y-%m-%d    %H:%M:%S")
                message = f"[{current_time}]字典检测完成,没有发现缺少字典的小图"
                self.emit_same_message(message)
            else:
                current_time = datetime.now().strftime("%Y-%m-%d    %H:%M:%S")
                if b == d:
                    message = f"[{current_time}]字典检测完成,发现 {b} 个缺少字典的小图,已进行处理"
                else:
                    message = f"[{current_time}]字典检测完成,发现 {b} 个缺少字典的小图,已处理{d}个，{b-d}个处理失败"
                self.emit_same_message(message)

                shutil.copytree(self.temp_dir_file, self.temp_client_dir_file)
                self.client_output_path = os.path.join(
                    self.output_path,
                    f"{os.path.splitext(os.path.basename(self.input_path))[0]}_client.vpk"
                )
                vpk.new(self.temp_client_dir_file).save(self.client_output_path)
                self.output_path = self.client_output_path
                self.compress_output()
                if os.path.exists(self.temp_client_dir_file):
                    remove_directory_with_retries(self.temp_client_dir_file)

        current_time = datetime.now().strftime("%Y-%m-%d    %H:%M:%S")
        message = f"[{current_time}]正在进行地图服务端无用资源清洗.."
        self.emit_same_message(message)
        for root, dirs, files in os.walk(self.temp_dir_file):
            for file in files:
                if '.' not in os.path.basename(file) or file.lower().endswith(('.vtf', '.mp3', '.wav', '.vmf', '.vmx')):
                    file_path = os.path.join(root, file)
                    os.remove(file_path)

        current_time = datetime.now().strftime("%Y-%m-%d    %H:%M:%S")
        message = f"[{current_time}]地图服务端无用资源清洗完毕.."
        self.emit_same_message(message)

        self.progress_signal.emit(50)

        base_name = os.path.splitext(os.path.basename(self.input_path))[0]
        if b == 0:
            output_vpk = os.path.join(self.output_path, f"{base_name}_server.vpk")
        else:
            output_vpk = os.path.join(os.path.dirname(self.output_path), f"{base_name}_server.vpk")

        new_pack = vpk.new(self.temp_dir_file)
        new_pack.save(output_vpk)

        self.output_path = output_vpk
        self.progress_signal.emit(100)

    def compress_output(self):
        base_name = os.path.splitext(os.path.basename(self.output_path))[0]
        output_file = ""

        if self.output_type == "zip":
            output_file = os.path.join(os.path.dirname(self.output_path), f"{base_name}.zip")
            with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(self.output_path, os.path.basename(self.output_path))
        elif self.output_type == "7z":
            output_file = os.path.join(os.path.dirname(self.output_path),  f"{base_name}.7z") 
            with py7zr.SevenZipFile(output_file, 'w') as z: 
                z.write(self.output_path,  os.path.basename(self.output_path))
        elif self.output_type == "rar":
            output_file = os.path.join(os.path.dirname(self.output_path),  f"{base_name}.rar") 
            with rarfile.RarFile(output_file, 'w') as rar_ref: 
                rar_ref.write(self.output_path,  os.path.basename(self.output_path))  

        os.remove(self.output_path)
        self.output_path = output_file


class DragAndDropButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setAcceptDrops(True) 
 
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): 
            event.acceptProposedAction() 
        else:
            event.ignore() 
 
    def dropEvent(self, event):
        for url in event.mimeData().urls(): 
            file_path = url.toLocalFile() 
            if file_path.lower().endswith(('.vpk',  '.zip', '.7z', '.rar')):

                main_window = self.parent().parent().window() 
                main_window.drop_input_file(file_path)
                if main_window.output_dir  == "":
                    main_window.output_dir  = os.path.dirname(file_path) 
             
            else:
                QMessageBox.warning(self,  "错误", "不支持的格式，仅支持.vpk/.zip/.7z/.rar")
 
 
class MainWindow(QMainWindow): 
    def __init__(self): 
        super().__init__() 
 
        self.setWindowIcon(self.style().standardIcon(42))  
        self.setWindowTitle("    洛琪地图简易工具") 
        self.setGeometry(100,  100, 400, 900) 
 
        self.central_widget  = QWidget() 
        self.setCentralWidget(self.central_widget)  
 
        self.layout  = QVBoxLayout() 
 
        self.layout.setSpacing(15)  
        self.layout.setContentsMargins(20,  20, 20, 20) 
        self.central_widget.setLayout(self.layout)  
 
        self.setStyleSheet("""  
            QWidget { 
                font-family: "宋体", "Times New Roman", sans-serif; 
                font-size: 14px; 
            } 
            QLabel { 
                color: #333; 
            } 
            QPushButton { 
                background-color: #FFB6C1; 
                color: white; 
                border: none; 
                padding: 8px 16px; 
                border-radius: 4px; 
            } 
            QPushButton:hover { 
                background-color: #FF69B4; 
            } 
            QCheckBox { 
                color: #333; 
            } 
            QProgressBar { 
                border: 1px solid #ccc; 
                border-radius: 5px; 
                text-align: center; 
                background: white; 
            } 
            QTextEdit { 
                border: 1px solid #ccc; 
                border-radius: 4px; 
            } 
        """) 
 
        self.title_label  = QLabel("洛琪地图简易工具") 
        self.title_label.setAlignment(Qt.AlignCenter)  
        self.title_label.setStyleSheet("""  
            font-family: "黑体"; 
            font-size: 24px; 
            font-weight: bold; 
            margin-bottom: 20px; 
            color: #007BFF; 
        """) 
        self.layout.addWidget(self.title_label)  
 
        self.select_file_btn  = DragAndDropButton("选择输入文件(.vpk .zip .7z .rar)") 
        self.select_file_btn.clicked.connect(self.select_input_file)  
        self.layout.addWidget(self.select_file_btn)  
 
        self.file_path_label  = QLabel("未选择文件") 
        self.file_path_label.setWordWrap(True)  
        self.layout.addWidget(self.file_path_label)  
 
        self.select_bsp_path_btn  = QPushButton("选择left4dead2.exe    路径[自动压字典功能才需要]") 
        self.select_bsp_path_btn.clicked.connect(self.get_l4d2_exe_path)  
        self.layout.addWidget(self.select_bsp_path_btn)  
 
        self.bsp_path_label  = QLabel("未选择left4dead2.exe    路径") 
        self.bsp_path_label.setWordWrap(True)  
        self.layout.addWidget(self.bsp_path_label)  
 
        self.select_output_dir_btn  = QPushButton("选择文件导出位置") 
        self.select_output_dir_btn.clicked.connect(self.select_output_dir)  
        self.layout.addWidget(self.select_output_dir_btn)  
 
        self.output_dir_label  = QLabel("未选择导出位置，将导出到当前文件夹下") 
        self.output_dir_label.setWordWrap(True)  
        self.layout.addWidget(self.output_dir_label)  
 
        checkbox_layout1 = QHBoxLayout() 
        checkbox_layout2 = QHBoxLayout()
 
        self.check_dictionary_checkbox  = QCheckBox("字典存在性检测") 
        self.check_dictionary_checkbox.setChecked(True)  
        checkbox_layout1.addWidget(self.check_dictionary_checkbox)  

        self.format_label  = QLabel("导出格式：") 
        self.format_combobox  = QComboBox() 
        self.format_combobox.addItems(["vpk",  "zip", "7z", "rar"]) 
        checkbox_layout1.addWidget(self.format_label,  stretch=1)
        checkbox_layout1.addWidget(self.format_combobox,  stretch=2)
        checkbox_layout1.insertStretch(1,  1) 
 
        self.auto_compress_dict_checkbox  = QCheckBox("开启自动压字典") 
        self.auto_compress_dict_checkbox.setChecked(True)  
        checkbox_layout2.addWidget(self.auto_compress_dict_checkbox)  
 
        self.auto_rename_vpk_checkbox  = QCheckBox("图名非法字符检测") 
        self.auto_rename_vpk_checkbox.setChecked(True)  
        checkbox_layout2.addWidget(self.auto_rename_vpk_checkbox)  
 
        self.layout.addLayout(checkbox_layout1)  
        self.layout.addLayout(checkbox_layout2)
 
        self.launch_options_label  = QLabel("额外启动参数（用空格分隔）：") 
        self.layout.addWidget(self.launch_options_label)  
 
        self.launch_options_input  = QLineEdit() 
        self.launch_options_input.setPlaceholderText(" 例如：-insecure") 
        self.launch_options_input.textChanged.connect(self.validate_launch_options)  
        self.layout.addWidget(self.launch_options_input)  
 
        self.command_preview_label  = QLabel("完整启动项命令预览：") 
        self.layout.addWidget(self.command_preview_label)  
 
        self.command_preview  = QTextEdit() 
        self.command_preview.setReadOnly(True)  
        self.command_preview.setMaximumHeight(80)  
        self.layout.addWidget(self.command_preview)  
 
        self.launch_options  = [] 
 
        self.process_btn  = QPushButton("开始处理") 
        self.process_btn.clicked.connect(self.process_file)  
        self.process_btn.setEnabled(False)  
        self.layout.addWidget(self.process_btn)  
 
        self.progress_bar  = QProgressBar() 
        self.progress_bar.setVisible(False)  
        self.layout.addWidget(self.progress_bar)  
 
        self.status_label  = QLabel("") 
        self.status_label.setWordWrap(True)  
        self.layout.addWidget(self.status_label)  
 
        self.log_text_edit  = QTextEdit() 
        self.log_text_edit.setReadOnly(True)  
        self.layout.addWidget(self.log_text_edit)  
 
        self.feature_description_label  = QLabel( 
            "本工具功能介绍：\n1. 自动检测地图字典缺失炸服并自动修复\n2. 自动删除服务器不需要的文件节约服务器空间") 
        self.feature_description_label.setWordWrap(True)  
        self.layout.addWidget(self.feature_description_label)  
 
        self.input_file  = "" 
        self.rename_path  = "" 
        self.output_file  = "" 
        self.bsp_path  = "" 
        self.output_dir  = "" 
        self.worker  = None 
 
        self.load_config()  
        self.check_for_updates()  
        self.update_command_preview()

    def validate_launch_options(self):
        input_text = self.launch_options_input.text()
        valid = True
        options = []

        for opt in input_text.split():
            if not opt.startswith(('-', '+')):
                QMessageBox.warning(self, "无效参数", f"参数 '{opt}' 必须以 '-' 或 '+' 开头")
                valid = False
                break
            options.append(opt)

        if valid:
            self.launch_options = options
            self.update_command_preview()
        else:
            self.launch_options_input.setStyleSheet("border: 1px solid red;")
            self.command_preview.setPlainText("包含无效参数！")
        return valid

    def update_command_preview(self):
        base_command = [
            "-steam", "-novid",
            "-hidden", "-nosound", "-noborder",
            "-heapsize", "2097151",
            "+map [MAPNAME]", "-stringtabledictionary", "-buildcubemaps"
        ]
        full_command = [self.bsp_path] + base_command + self.launch_options
        preview_text = " ".join(full_command)
        self.command_preview.setPlainText(preview_text)
        self.launch_options_input.setStyleSheet("")
 
    def load_config(self): 
        config = configparser.ConfigParser() 
        if os.path.exists(CONFIG_FILE):  
            config.read(CONFIG_FILE)  
            if 'Paths' in config: 
                last_input_folder = config.get('Paths',   'last_input_folder', fallback='') 
                last_exe_path = config.get('Paths',   'last_exe_path', fallback='') 
                last_output_dir = config.get('Paths',   'last_output_dir', fallback='') 
                if 'launch_options' in config['Paths']: 
                    opts = config.get('Paths',  'launch_options', fallback='') 
                    self.launch_options_input.setText(opts)  
                    self.validate_launch_options()  
                if last_input_folder: 
                    self.last_input_folder   = last_input_folder 
                if last_exe_path: 
                    self.bsp_path   = last_exe_path 
                    self.bsp_path_label.setText(last_exe_path)  
                if last_output_dir: 
                    self.output_dir   = last_output_dir 
                    self.output_dir_label.setText(last_output_dir)  
                last_format = config.get('Paths',  'last_export_format', fallback='zip') 
                index = self.format_combobox.findText(last_format)  
                if index != -1: 
                    self.format_combobox.setCurrentIndex(index)  
 
    def save_config(self): 
        config = configparser.ConfigParser() 
        config['Paths'] = { 
            'last_input_folder': os.path.dirname(self.input_file)  if self.input_file  else '', 
            'last_exe_path': self.bsp_path,  
            'last_output_dir': self.output_dir,  
            'launch_options': " ".join(self.launch_options),  
            'last_export_format': self.format_combobox.currentText()  
        } 
        with open(CONFIG_FILE, 'w') as configfile: 
            config.write(configfile)  
 
    def is_steam_no_running(self): 
        for proc in psutil.process_iter(['name']):  
            if proc.info['name'].lower()  in ['steam.exe',  'steam']: 
                return False 
        return True 
 
    def is_english_only(self, text):
        return bool(re.match(r'^[a-zA-Z0-9_\-\. ]+$', text))
    
    def drop_input_file(self, drop_path):
        self.process_input_file(drop_path)

    def select_input_file(self):
        initial_dir = getattr(self, 'last_input_folder', '') 
        file_filter = "支持的格式 (*.vpk *.zip *.7z *.rar)" 
        file_path, _ = QFileDialog.getOpenFileName(  
            self, "选择输入文件", initial_dir, file_filter)

        self.process_input_file(file_path)

    def process_input_file(self, file_path): 
        if self.is_steam_no_running():  
            QMessageBox.warning(self, "警告", "Steam未运行,可能无法自动压制字典") 
 
        if file_path: 
            if self.auto_rename_vpk_checkbox.isChecked():
                file_name = os.path.basename(file_path)
                base_name = os.path.splitext(file_name)[0]
                extension = os.path.splitext(file_name)[1]
                
                if not self.is_english_only(base_name):
                    new_name, ok = QInputDialog.getText(
                        self, 
                        "重命名文件", 
                        "检测到文件名含有特殊字符或中文，可能在Linux服务器上造成乱码。\n请输入英文文件名：",
                        QLineEdit.Normal
                    )
                    
                    if ok and new_name:
                        if not self.is_english_only(new_name):
                            QMessageBox.warning(self, "警告", "文件名仍包含非英文字符，请使用纯英文、数字和下划线")
                        else:
                            new_path = os.path.join(os.path.dirname(file_path), new_name + extension)
                            if os.path.exists(new_path):
                                reply = QMessageBox.question(
                                    self, 
                                    "文件已存在", 
                                    f"文件 {new_name + extension} 已存在，是否覆盖？",
                                    QMessageBox.Yes | QMessageBox.No
                                )
                                
                                if reply == QMessageBox.No:
                                    return
                            
                            try:
                                shutil.copy2(file_path, new_path)
                                QMessageBox.information(
                                    self, 
                                    "重命名成功", 
                                    f"已创建重命名后的文件副本：{new_name + extension}"
                                )
                                file_path = new_path
                                self.rename_path = new_path
                            except Exception as e:
                                QMessageBox.critical(self, "错误", f"重命名文件时出错: {str(e)}")
            
            self.input_file = file_path 
            self.file_path_label.setText(file_path)  
            self.save_config()  
            self.process_btn.setEnabled(True)  
            if self.output_dir == "": 
                self.output_dir = os.path.dirname(file_path)  
        else: 
            self.process_btn.setEnabled(False)  
 
    def select_output_dir(self): 
        output_dir = QFileDialog.getExistingDirectory(self,  "选择导出位置") 
        if output_dir: 
            self.output_dir  = output_dir 
            self.output_dir_label.setText(output_dir)  
            self.save_config()  
            self.load_config()  
 
    def get_l4d2_exe_path(self, use_config=False): 
        if use_config: 
            config = configparser.ConfigParser() 
            if os.path.exists(CONFIG_FILE):  
                config.read(CONFIG_FILE)  
                if 'Paths' in config: 
                    exe_path = config.get('Paths',  'last_exe_path', fallback='') 
                    if exe_path and os.path.exists(exe_path):  
                        return exe_path 
 
        file_path, _ = QFileDialog.getOpenFileName(  
            self, "选择 left4dead2.exe",  
            "", "Executable Files (*.exe)" 
        ) 
        if file_path: 
            self.bsp_path  = file_path 
            self.bsp_path_label.setText(file_path)  
            self.save_config()  
            self.load_config()  
            return file_path 
        return None 
 
    def process_file(self): 
        if not self.input_file:  
            QMessageBox.warning(self,  "警告", "请先选择输入文件") 
            return

        if not self.validate_launch_options():
            QMessageBox.warning(self, "警告", "启动项参数无效")
            return
 
        self.progress_bar.setVisible(True)  
        self.progress_bar.setValue(0)  
 
        self.worker  = FileProcessor( 
            self.input_file,  
            self.rename_path,
            self.output_dir,  
            self.format_combobox.currentText(),  
            self.check_dictionary_checkbox.isChecked(),  
            self.bsp_path,  
            self.auto_compress_dict_checkbox.isChecked(),  
            self 
        ) 
 
        self.worker.progress_signal.connect(self.progress_bar.setValue)  
        self.worker.message_signal.connect(self.status_label.setText)  
        self.worker.dict_exist_signal.connect(self.log_text_edit.append)  
        self.worker.finished_signal.connect(self.on_process_finished)  
        self.worker.start()  
        self.process_btn.setEnabled(False)
 
    def on_process_finished(self, success): 
        self.progress_bar.setVisible(False)  
        self.process_btn.setEnabled(True)  
 
        if success: 
            if self.worker.client_output_path  is None: 
                QMessageBox.information(  
                    self, "完成", 
                    f"处理完成！输出路径：{self.worker.output_path}\n"  
                    f"点击确定后将自动打开输出目录", 
                    QMessageBox.Ok 
                ) 
            else: 
                QMessageBox.information(  
                    self, 
                    "处理完成", 
                    f"已生成两份文件：\n{os.path.basename(self.worker.output_path)}\n{os.path.basename(self.worker.client_output_path)}\n"  
                    f"前者上传服务器，后者发送玩家使用\n" 
                    f"点击确定后将自动打开输出目录", 
                    QMessageBox.Ok 
                ) 
 
            output_dir = os.path.dirname(self.worker.output_path)  
            self.worker.client_output_path  = None 
            if sys.platform  == 'win32': 
                os.startfile(output_dir)  
            elif sys.platform  == 'darwin': 
                subprocess.Popen(['open', output_dir]) 
            else: 
                subprocess.Popen(['xdg-open', output_dir]) 
        else: 
            QMessageBox.critical(self,  "错误", "处理过程中出现错误") 
 
    def check_for_updates(self): 
        self.update_checker  = UpdateChecker() 
        self.update_checker.update_available_signal.connect(self.show_update_dialog)  
        self.update_checker.no_update_signal.connect(self.show_no_update_message)  
        self.update_checker.start()  
 
    def show_update_dialog(self, download_url): 
        reply = QMessageBox.question(self,  "发现新版本", 
                                     "检测到新版本可用，是否立即更新？", 
                                     QMessageBox.Yes | QMessageBox.No) 
        if reply == QMessageBox.Yes: 
            self.download_update(download_url)  
 
    def show_no_update_message(self): 
        QMessageBox.information(  
            self, 
            "更新检查", 
            f"当前已是最新版本 (v{CURRENT_VERSION})", 
            QMessageBox.Ok 
        ) 
 
    def download_update(self, download_url): 
        self.progress  = QProgressDialog("正在下载更新...", "取消", 0, 100, self) 
        self.progress.setWindowModality(Qt.WindowModal)  
 
        self.update_downloader  = UpdateDownloader(download_url) 
        self.update_downloader.progress_signal.connect(self.progress.setValue)  
        self.update_downloader.finished_signal.connect(self.apply_update)  
        self.update_downloader.start()  
 
    def apply_update(self): 
        try: 
            file_list = []
            with zipfile.ZipFile("update.zip",  'r') as zip_ref: 
                for filename in zip_ref.namelist():
                    zip_ref.extractall(os.getcwd())  
                    file_list.append(str(filename))
            os.remove("update.zip")  
            QMessageBox.information(self,  "更新完成", "程序将在重启后生效") 
            self.update_and_replace(file_list[0])  
        except Exception as e: 
            QMessageBox.critical(self,  "更新失败", f"错误信息: {str(e)}") 
    
    def update_and_replace(self, filename): 
        target_exe = "map_tools.exe"  

        bat_content = f""" 
        @echo off 
        ping 127.0.0.1 -n 2 > nul 
        del "{os.path.abspath(sys.argv[0])}"  
        ren "{os.path.join(os.getcwd(),  filename)}" "{target_exe}" 
        start "" "{os.path.join(os.getcwd(),  target_exe)}" 
        del "%~f0" 
        """ 
   
        bat_file = 'l4d_tool_update.bat'  
        with open(bat_file, 'w') as f: 
            f.write(bat_content)  

        subprocess.Popen(bat_file, shell=True) 
        sys.exit()  
 

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
