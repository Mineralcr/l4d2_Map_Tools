import smtplib 
from email.mime.multipart  import MIMEMultipart 
from email.mime.text  import MIMEText 
from email.mime.image  import MIMEImage 
from PyQt5.QtWidgets import QMessageBox, QDialog, QScrollArea, QVBoxLayout, QLabel, QPushButton, QTextEdit, QFileDialog 
from PyQt5.QtCore import Qt 
 
 
def show_help(parent=None): 
    content = """ 
    使用说明： 
    1. 一次只能处理一个文件，确保此文件内有且只有一张地图。 
    2. 如果地图由多个 vpk 组成，则先压缩为压缩包再输入处理。 
    3. 处理得到的 _server 后缀文件上传服务器使用。 
    4. 如果压制了字典，则会新生成 _client 后缀文件发放玩家使用。 
    5. 未压制字典则只生成 _server 后缀文件供服务器使用。 
    6. 遇到问题可点击顶部工具栏按钮提交错误报告。 
    """ 
    QMessageBox.information(parent,  "帮助文档", content.strip())  
 
 
def show_update_log(parent=None): 
    dialog = QDialog(parent) 
    dialog.setWindowTitle("  更新日志") 
    layout = QVBoxLayout() 
 
    log_content = QLabel(""" 
    v1.0.5 (2025 - 04 - 03) 
      - 公开版发布 
 
    v1.0.6 (2025 - 04 - 04) 
      - 修复编码读取异常问题 
      - 增加导出文件类型选择窗口 
 
    v1.0.7 (2025 - 04 - 05) 
      - 修复导出类型选择 vpk 类型时无法生成 client 文件的问题 
      - 修复自动更新系统更新开始后无法取消的问题 
      - 修复rar压缩报错的问题 
      - 增加帮助菜单、更新日志、错误报告等工具栏 
 
    v1.0.8 (2025 - 04 - 09) 
      - 修复额外启动项无法添加带有参数的启动项的问题 
      - 修复部分文件解码失败的问题 
      - 修复部分地图大于1.6G时将文件全部打包到一个vpk的问题 
      - 修复子窗口和主窗口不在同一进程的问题 
    """) 
    log_content.setAlignment(Qt.AlignLeft)  
 
    scroll_area = QScrollArea() 
    scroll_area.setWidget(log_content)  
    scroll_area.setWidgetResizable(True)  
    layout.addWidget(scroll_area)  
 
    dialog.setLayout(layout)  
    dialog.setFixedSize(400,  300) 
    dialog.exec_()   
 
 
def send_email(error_description, screenshot_path):  
    sender_email = '1291560497@qq.com'
    sender_password = 'yrlbfmtkwhkmgiaa' 
    receiver_email = '3841013254@qq.com'  
    smtps = 'smtp.qq.com'
 
    message = MIMEMultipart() 
    message["From"] = sender_email 
    message["To"] = receiver_email 
    message["Subject"] = "错误报告" 
 
    message.attach(MIMEText(error_description,  "plain")) 
 
    if screenshot_path: 
        with open(screenshot_path, "rb") as file: 
            img = MIMEImage(file.read())  
            img.add_header('Content-Disposition',  'attachment', filename="screenshot.png")  
            message.attach(img)  
 
    try: 
        server = smtplib.SMTP_SSL(smtps, 465)
        server.login(sender_email,  sender_password) 
        text = message.as_string()  
        server.sendmail(sender_email,  receiver_email, text) 
        server.quit()  
        QMessageBox.information(None,  "成功", "错误报告已成功发送！") 
    except Exception as e: 
        QMessageBox.critical(None,  "错误", f"发送邮件时出现错误：{str(e)}") 
 
 
def report_error(parent=None): 
    dialog = QDialog(parent) 
    dialog.setWindowTitle("  错误报告") 
    layout = QVBoxLayout() 
 
    error_label = QLabel("请输入详细的错误描述：") 
    error_label.setAlignment(Qt.AlignLeft)  
    layout.addWidget(error_label)  
 
    text_edit = QTextEdit() 
    layout.addWidget(text_edit)  
 
    select_button = QPushButton("选择截图") 
    screenshot_path = "" 
 
    def select_screenshot(): 
        nonlocal screenshot_path 
        file_dialog = QFileDialog() 
        screenshot_path, _ = file_dialog.getOpenFileName(dialog,  "选择截图文件", "", "图像文件 (*.png *.jpg *.jpeg)") 
 
    select_button.clicked.connect(select_screenshot)  
    layout.addWidget(select_button)  
 
    submit_button = QPushButton("提交") 
 
    def submit_report(): 
        error_description = text_edit.toPlainText()  
        send_email(error_description, screenshot_path) 
        dialog.close()  
 
    submit_button.clicked.connect(submit_report)  
    layout.addWidget(submit_button)  
 
    dialog.setLayout(layout)  
    dialog.setFixedSize(400,  300) 
    dialog.exec_()  
 
 
def about_this(parent=None): 
    dialog = QDialog(parent) 
    dialog.setWindowTitle("  关于本程序") 
    layout = QVBoxLayout() 
 
    about_label = QLabel(""" 
    本程序是一个地图处理工具，用于特定地图文件的处理。  
    项目链接： 
    https://github.com/Mineralcr/l4d2_Map_Tools  
    """) 
    about_label.setAlignment(Qt.AlignLeft)  
    layout.addWidget(about_label)  
 
    dialog.setLayout(layout)  
    dialog.setFixedSize(400,  200) 
    dialog.exec_()  
