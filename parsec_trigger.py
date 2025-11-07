import sys
import cv2
import numpy as np
import mss
import win32gui
import win32con
import win32api
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QGroupBox, QCheckBox, QSpinBox,
    QComboBox, QFrame, QComboBox as QCombo
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QPoint
from PyQt5.QtGui import QFont, QColor, QPalette
import keyboard
import time
import ctypes
from ctypes import windll, c_long, c_ulong, Structure, Union, c_int, POINTER, sizeof
import pyautogui

# Disable PyAutoGUI fail-safe
pyautogui.FAILSAFE = False

# Mouse event constants
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

# Define mouse input structures
class MOUSEINPUT(Structure):
    _fields_ = [("dx", c_long),
                ("dy", c_long),
                ("mouseData", c_ulong),
                ("dwFlags", c_ulong),
                ("time", c_ulong),
                ("dwExtraInfo", POINTER(c_ulong))]

class _INPUTunion(Union):
    _fields_ = [("mi", MOUSEINPUT)]

class INPUT(Structure):
    _fields_ = [("type", c_ulong),
                ("union", _INPUTunion)]

class ParsecWindowDetector:
    """Parsec penceresini algılama ve koordinatlarını yönetme"""
    
    def __init__(self):
        self.hwnd = None
        self.window_rect = None
        self.window_title = None
    
    def find_parsec_window(self):
        """Parsec penceresini bul"""
        def callback(hwnd, windows):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if "parsec" in title.lower() or "playing on" in title.lower():
                    windows.append((hwnd, title))
            return True
        
        windows = []
        win32gui.EnumWindows(callback, windows)
        
        if windows:
            self.hwnd = windows[0][0]
            self.window_title = windows[0][1]
            self.update_window_rect()
            return True
        return False
    
    def update_window_rect(self):
        """Pencere koordinatlarını güncelle"""
        if self.hwnd:
            try:
                rect = win32gui.GetWindowRect(self.hwnd)
                self.window_rect = {
                    'left': rect[0],
                    'top': rect[1],
                    'width': rect[2] - rect[0],
                    'height': rect[3] - rect[1]
                }
                return True
            except:
                return False
        return False
    
    def get_center_region(self, fov_width=640, fov_height=640):
        """Parsec penceresinin merkez bölgesini döndür"""
        if not self.window_rect:
            return None
        
        center_x = self.window_rect['left'] + self.window_rect['width'] // 2
        center_y = self.window_rect['top'] + self.window_rect['height'] // 2
        
        return {
            'left': center_x - fov_width // 2,
            'top': center_y - fov_height // 2,
            'width': fov_width,
            'height': fov_height
        }


class ColorDetectionThread(QThread):
    """Renk algılama ve hedef bulma thread'i"""
    
    target_found = pyqtSignal(int, int)
    fps_updated = pyqtSignal(int)
    
    def __init__(self):
        super().__init__()
        self.running = False
        self.parsec_detector = ParsecWindowDetector()
        
        # Ayarlar
        self.enabled = False
        self.fov_size = 6  # Crosshair tarama alanı (piksel)
        self.target_fps = 200  # Daha yüksek FPS
        self.min_pixel_count = 2  # Minimum hedef piksel sayısı (false positive önleme)
        
        # HSV renk aralığı (Varsayılan: Mor/Purple)
        self.lower_hsv = np.array([130, 50, 50])
        self.upper_hsv = np.array([160, 255, 255])
        
        # Hedefleme modu
        self.aim_mode = "head"  # "head" veya "body"
        
        # Hold key ayarları
        self.holdkey_enabled = False
        self.holdkey = 'mouse5'  # Varsayılan hold key
        
        # Aimbot her zaman aktif (enabled ise)
        
        # MSS screen capture - thread içinde oluşturulacak
        self.sct = None
        
    def run(self):
        """Ana döngü"""
        self.running = True
        
        # MSS'i thread içinde oluştur (thread-safe)
        self.sct = mss.mss()
        
        frame_time = 1.0 / self.target_fps
        
        while self.running:
            try:
                start_time = time.time()
                
                if self.enabled:
                    # Hold key kontrolü
                    if self.holdkey_enabled:
                        if not keyboard.is_pressed(self.holdkey):
                            time.sleep(0.01)
                            continue
                    
                    # Parsec penceresini kontrol et
                    if not self.parsec_detector.hwnd or not self.parsec_detector.update_window_rect():
                        if not self.parsec_detector.find_parsec_window():
                            time.sleep(0.1)
                            continue
                    
                    # Hedef tarama
                    target = self.detect_target()
                    if target:
                        self.target_found.emit(target[0], target[1])
                
                # FPS hesaplama
                elapsed = time.time() - start_time
                if elapsed < frame_time:
                    time.sleep(frame_time - elapsed)
                
                actual_fps = int(1.0 / max(elapsed, 0.001))
                self.fps_updated.emit(actual_fps)
                
            except Exception as e:
                print(f"Detection thread error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(0.1)
    
    def detect_target(self):
        """Hedef algılama - Sadece crosshair bölgesi (trigger mantığı)"""
        # Parsec penceresini al
        if not self.parsec_detector.window_rect:
            return None
        
        # Ekranın tam ortasını hesapla (Parsec penceresi merkezi)
        window_rect = self.parsec_detector.window_rect
        center_x = window_rect['left'] + window_rect['width'] // 2
        center_y = window_rect['top'] + window_rect['height'] // 2
        
        # Küçük tarama alanı (crosshair etrafı) - varsayılan 6x6 piksel
        scan_area = self.fov_size if self.fov_size < 50 else 6
        
        region = {
            'left': center_x - scan_area // 2,
            'top': center_y - scan_area // 2,
            'width': scan_area,
            'height': scan_area
        }
        
        # Ekran görüntüsü al
        screenshot = self.sct.grab(region)
        img = np.array(screenshot)
        
        # BGRA'dan BGR'ye
        if img.shape[2] == 4:
            img_bgr = img[:, :, :3]
        else:
            img_bgr = img
        
        # HSV'ye çevir
        hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        
        # Renk maskesi
        mask = cv2.inRange(hsv, self.lower_hsv, self.upper_hsv)
        
        # Hedef piksel sayısını kontrol et (false positive önleme)
        target_pixel_count = np.count_nonzero(mask == 255)
        
        # Minimum piksel eşiğini kontrol et
        if target_pixel_count >= self.min_pixel_count:
            # Yeterli piksel var - hedef tespit edildi
            return (0, 0)  # Sadece tetikleme için
        
        return None
    
    def stop(self):
        self.running = False
        if self.sct:
            try:
                self.sct.close()
            except:
                pass
        self.wait()


class TriggerThread(QThread):
    """Hedef algılandığında tuşa basan thread"""
    
    def __init__(self, detection_thread):
        super().__init__()
        self.detection_thread = detection_thread
        self.running = False
        self.target_detected = False
        self.fire_key = 'k'  # Ateş etme tuşu
        self.last_fire_time = 0
        
        # Rastgele gecikme ayarları (humanization)
        self.fire_delay_min = 100  # ms
        self.fire_delay_max = 200  # ms
        
    def run(self):
        self.running = True
        
        while self.running:
            try:
                if self.target_detected:
                    current_time = time.time() * 1000  # Milisaniye
                    
                    # Minimum gecikme kontrolü
                    if current_time - self.last_fire_time < self.fire_delay_min:
                        self.target_detected = False
                        time.sleep(0.001)
                        continue
                    
                    # Rastgele gecikme hesapla (humanization)
                    import random
                    delay = random.randint(self.fire_delay_min, self.fire_delay_max)
                    
                    # Gecikme kontrolü
                    if current_time - self.last_fire_time >= delay:
                        # Keyboard ile tuşa bas
                        keyboard.press(self.fire_key)
                        time.sleep(0.05)  # Kısa basılı tutma
                        keyboard.release(self.fire_key)
                        
                        self.last_fire_time = current_time
                        print(f"➡️ Hedef! '{self.fire_key.upper()}' - Delay: {int(current_time - self.last_fire_time)}ms")
                    
                    self.target_detected = False
                
                time.sleep(0.001)
            except Exception as e:
                print(f"Trigger thread error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(0.01)
    
    def trigger(self):
        """Hedef algılandığını işaretle"""
        self.target_detected = True
    
    def stop(self):
        self.running = False
        self.wait()


class ParsecColorbotGUI(QMainWindow):
    """Ana GUI"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Parsec Triggerbot")
        self.setGeometry(100, 100, 600, 700)
        
        # Dark theme
        self.setup_dark_theme()
        
        # Thread'ler
        self.detection_thread = ColorDetectionThread()
        self.trigger_thread = TriggerThread(self.detection_thread)
        
        # UI
        self.setup_ui()
        
        # Bağlantılar
        self.detection_thread.target_found.connect(self.on_target_found)
        self.detection_thread.fps_updated.connect(self.update_fps_label)
        
        # Thread'leri başlat
        self.detection_thread.start()
        self.trigger_thread.start()
        
        # Parsec pencere kontrolü
        self.window_check_timer = QTimer()
        self.window_check_timer.timeout.connect(self.check_parsec_window)
        self.window_check_timer.start(2000)
    
    def setup_dark_theme(self):
        """Koyu tema ayarla"""
        dark_stylesheet = """
            QMainWindow {
                background-color: #1e1e2e;
            }
            QWidget {
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-family: 'Segoe UI', Arial;
                font-size: 10pt;
            }
            QGroupBox {
                border: 2px solid #45475a;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
                color: #a6e3a1;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QPushButton {
                background-color: #45475a;
                border: none;
                border-radius: 5px;
                padding: 8px;
                color: #cdd6f4;
            }
            QPushButton:hover {
                background-color: #585b70;
            }
            QPushButton:pressed {
                background-color: #313244;
            }
            QSlider::groove:horizontal {
                border: 1px solid #45475a;
                height: 8px;
                background: #313244;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #89b4fa;
                border: 1px solid #45475a;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }
            QLabel {
                background: transparent;
            }
            QSpinBox, QComboBox {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 5px;
                padding: 5px;
            }
            QCheckBox {
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 3px;
                border: 2px solid #45475a;
                background-color: #313244;
            }
            QCheckBox::indicator:checked {
                background-color: #a6e3a1;
                border-color: #a6e3a1;
            }
        """
        self.setStyleSheet(dark_stylesheet)
    
    def setup_ui(self):
        """UI oluştur"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Başlık
        title = QLabel("🎯 PARSEC TRIGGERBOT")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 24pt; font-weight: bold; color: #89b4fa; padding: 10px;")
        main_layout.addWidget(title)
        
        # Parsec durum
        self.parsec_status_label = QLabel("Parsec: Aranıyor...")
        self.parsec_status_label.setAlignment(Qt.AlignCenter)
        self.parsec_status_label.setStyleSheet("font-size: 12pt; color: #f9e2af; padding: 5px;")
        main_layout.addWidget(self.parsec_status_label)
        
        # FPS
        self.fps_label = QLabel("FPS: 0")
        self.fps_label.setAlignment(Qt.AlignCenter)
        self.fps_label.setStyleSheet("font-size: 11pt; color: #a6e3a1;")
        main_layout.addWidget(self.fps_label)
        
        # Ana kontrol
        main_control_group = QGroupBox("Ana Kontrol")
        main_control_layout = QVBoxLayout()
        
        self.enable_checkbox = QCheckBox("Aimbot Etkin (Otomatik Hedefleme)")
        self.enable_checkbox.stateChanged.connect(self.on_enable_changed)
        main_control_layout.addWidget(self.enable_checkbox)
        
        # Info label
        info = QLabel("✓ Hedef görüldüğünde otomatik ateş eder")
        info.setStyleSheet("color: #a6e3a1; font-size: 9pt; padding: 5px;")
        main_control_layout.addWidget(info)
        
        # Fire key selection
        fire_key_layout = QHBoxLayout()
        fire_key_layout.addWidget(QLabel("Ateş Tuşu:"))
        self.fire_key_button = QPushButton(self.trigger_thread.fire_key.upper())
        self.fire_key_button.clicked.connect(self.change_fire_key)
        fire_key_layout.addWidget(self.fire_key_button)
        main_control_layout.addLayout(fire_key_layout)
        
        # Hold key
        hold_layout = QHBoxLayout()
        self.holdkey_checkbox = QCheckBox("Hold Key Aktif")
        self.holdkey_checkbox.stateChanged.connect(self.on_holdkey_changed)
        hold_layout.addWidget(self.holdkey_checkbox)
        
        self.holdkey_button = QPushButton(self.detection_thread.holdkey.upper())
        self.holdkey_button.clicked.connect(self.change_hold_key)
        hold_layout.addWidget(self.holdkey_button)
        main_control_layout.addLayout(hold_layout)
        
        # Fire delay min
        delay_min_layout = QHBoxLayout()
        delay_min_layout.addWidget(QLabel("Min Ateş Gecikmesi:"))
        self.delay_min_spinbox = QSpinBox()
        self.delay_min_spinbox.setMinimum(50)
        self.delay_min_spinbox.setMaximum(1000)
        self.delay_min_spinbox.setSuffix(" ms")
        self.delay_min_spinbox.setValue(self.trigger_thread.fire_delay_min)
        self.delay_min_spinbox.valueChanged.connect(self.on_fire_delay_min_changed)
        delay_min_layout.addWidget(self.delay_min_spinbox)
        main_control_layout.addLayout(delay_min_layout)
        
        # Fire delay max
        delay_max_layout = QHBoxLayout()
        delay_max_layout.addWidget(QLabel("Max Ateş Gecikmesi:"))
        self.delay_max_spinbox = QSpinBox()
        self.delay_max_spinbox.setMinimum(50)
        self.delay_max_spinbox.setMaximum(1000)
        self.delay_max_spinbox.setSuffix(" ms")
        self.delay_max_spinbox.setValue(self.trigger_thread.fire_delay_max)
        self.delay_max_spinbox.valueChanged.connect(self.on_fire_delay_max_changed)
        delay_max_layout.addWidget(self.delay_max_spinbox)
        main_control_layout.addLayout(delay_max_layout)
        
        main_control_group.setLayout(main_control_layout)
        main_layout.addWidget(main_control_group)
        
        # Aimbot ayarları
        aim_settings_group = QGroupBox("Aimbot Ayarları")
        aim_settings_layout = QVBoxLayout()
        
        # Scan Area (Crosshair)
        scan_layout = QHBoxLayout()
        scan_layout.addWidget(QLabel("Scan Area (Crosshair):"))
        self.fov_slider = QSlider(Qt.Horizontal)
        self.fov_slider.setMinimum(1)
        self.fov_slider.setMaximum(50)
        self.fov_slider.setValue(6)
        self.fov_slider.valueChanged.connect(self.on_fov_changed)
        scan_layout.addWidget(self.fov_slider)
        self.fov_value_label = QLabel("6 px")
        scan_layout.addWidget(self.fov_value_label)
        aim_settings_layout.addLayout(scan_layout)
        
        # Minimum Pixel Threshold
        pixel_layout = QHBoxLayout()
        pixel_layout.addWidget(QLabel("Min Piksel Eşiği:"))
        self.min_pixel_spinbox = QSpinBox()
        self.min_pixel_spinbox.setMinimum(1)
        self.min_pixel_spinbox.setMaximum(20)
        self.min_pixel_spinbox.setValue(self.detection_thread.min_pixel_count)
        self.min_pixel_spinbox.setSuffix(" px")
        self.min_pixel_spinbox.valueChanged.connect(self.on_min_pixel_changed)
        pixel_layout.addWidget(self.min_pixel_spinbox)
        aim_settings_layout.addLayout(pixel_layout)
        
        
        # Target FPS
        fps_layout = QHBoxLayout()
        fps_layout.addWidget(QLabel("Target FPS:"))
        self.fps_spinbox = QSpinBox()
        self.fps_spinbox.setMinimum(30)
        self.fps_spinbox.setMaximum(200)
        self.fps_spinbox.setValue(120)
        self.fps_spinbox.valueChanged.connect(self.on_target_fps_changed)
        fps_layout.addWidget(self.fps_spinbox)
        aim_settings_layout.addLayout(fps_layout)
        
        # Aim mode
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Hedef:"))
        self.aim_mode_combo = QComboBox()
        self.aim_mode_combo.addItems(["Baş", "Gövde"])
        self.aim_mode_combo.currentTextChanged.connect(self.on_aim_mode_changed)
        mode_layout.addWidget(self.aim_mode_combo)
        aim_settings_layout.addLayout(mode_layout)
        
        aim_settings_group.setLayout(aim_settings_layout)
        main_layout.addWidget(aim_settings_group)
        
        # Renk ayarları
        color_settings_group = QGroupBox("Renk Ayarları (HSV)")
        color_settings_layout = QVBoxLayout()
        
        # Hue
        hue_layout = QHBoxLayout()
        hue_layout.addWidget(QLabel("Hue Min:"))
        self.hue_min_slider = QSlider(Qt.Horizontal)
        self.hue_min_slider.setMinimum(0)
        self.hue_min_slider.setMaximum(179)
        self.hue_min_slider.setValue(130)
        self.hue_min_slider.valueChanged.connect(self.on_color_changed)
        hue_layout.addWidget(self.hue_min_slider)
        self.hue_min_label = QLabel("130")
        hue_layout.addWidget(self.hue_min_label)
        
        hue_layout.addWidget(QLabel("Max:"))
        self.hue_max_slider = QSlider(Qt.Horizontal)
        self.hue_max_slider.setMinimum(0)
        self.hue_max_slider.setMaximum(179)
        self.hue_max_slider.setValue(160)
        self.hue_max_slider.valueChanged.connect(self.on_color_changed)
        hue_layout.addWidget(self.hue_max_slider)
        self.hue_max_label = QLabel("160")
        hue_layout.addWidget(self.hue_max_label)
        color_settings_layout.addLayout(hue_layout)
        
        # Saturation
        sat_layout = QHBoxLayout()
        sat_layout.addWidget(QLabel("Sat Min:"))
        self.sat_min_slider = QSlider(Qt.Horizontal)
        self.sat_min_slider.setMinimum(0)
        self.sat_min_slider.setMaximum(255)
        self.sat_min_slider.setValue(50)
        self.sat_min_slider.valueChanged.connect(self.on_color_changed)
        sat_layout.addWidget(self.sat_min_slider)
        self.sat_min_label = QLabel("50")
        sat_layout.addWidget(self.sat_min_label)
        
        sat_layout.addWidget(QLabel("Max:"))
        self.sat_max_slider = QSlider(Qt.Horizontal)
        self.sat_max_slider.setMinimum(0)
        self.sat_max_slider.setMaximum(255)
        self.sat_max_slider.setValue(255)
        self.sat_max_slider.valueChanged.connect(self.on_color_changed)
        sat_layout.addWidget(self.sat_max_slider)
        self.sat_max_label = QLabel("255")
        sat_layout.addWidget(self.sat_max_label)
        color_settings_layout.addLayout(sat_layout)
        
        # Value
        val_layout = QHBoxLayout()
        val_layout.addWidget(QLabel("Val Min:"))
        self.val_min_slider = QSlider(Qt.Horizontal)
        self.val_min_slider.setMinimum(0)
        self.val_min_slider.setMaximum(255)
        self.val_min_slider.setValue(50)
        self.val_min_slider.valueChanged.connect(self.on_color_changed)
        val_layout.addWidget(self.val_min_slider)
        self.val_min_label = QLabel("50")
        val_layout.addWidget(self.val_min_label)
        
        val_layout.addWidget(QLabel("Max:"))
        self.val_max_slider = QSlider(Qt.Horizontal)
        self.val_max_slider.setMinimum(0)
        self.val_max_slider.setMaximum(255)
        self.val_max_slider.setValue(255)
        self.val_max_slider.valueChanged.connect(self.on_color_changed)
        val_layout.addWidget(self.val_max_slider)
        self.val_max_label = QLabel("255")
        val_layout.addWidget(self.val_max_label)
        color_settings_layout.addLayout(val_layout)
        
        # Preset buttons
        preset_layout = QHBoxLayout()
        purple_btn = QPushButton("Mor (Purple)")
        purple_btn.clicked.connect(lambda: self.load_color_preset("purple"))
        preset_layout.addWidget(purple_btn)
        
        red_btn = QPushButton("Kırmızı (Red)")
        red_btn.clicked.connect(lambda: self.load_color_preset("red"))
        preset_layout.addWidget(red_btn)
        
        yellow_btn = QPushButton("Sarı (Yellow)")
        yellow_btn.clicked.connect(lambda: self.load_color_preset("yellow"))
        preset_layout.addWidget(yellow_btn)
        color_settings_layout.addLayout(preset_layout)
        
        color_settings_group.setLayout(color_settings_layout)
        main_layout.addWidget(color_settings_group)
        
        # Alt bilgi
        info_label = QLabel("Parsec Edition")
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setStyleSheet("color: #6c7086; font-size: 9pt; padding: 10px;")
        main_layout.addWidget(info_label)
    
    
    def check_parsec_window(self):
        """Parsec penceresini kontrol et"""
        if self.detection_thread.parsec_detector.find_parsec_window():
            title = self.detection_thread.parsec_detector.window_title
            self.parsec_status_label.setText(f"✅ Parsec: {title}")
            self.parsec_status_label.setStyleSheet("font-size: 12pt; color: #a6e3a1; padding: 5px;")
        else:
            self.parsec_status_label.setText("❌ Parsec: Bulunamadı")
            self.parsec_status_label.setStyleSheet("font-size: 12pt; color: #f38ba8; padding: 5px;")
    
    def on_target_found(self, x, y):
        """Hedef bulundu - triggerbot tetikle"""
        self.trigger_thread.trigger()
    
    def update_fps_label(self, fps):
        """FPS güncelle"""
        self.fps_label.setText(f"FPS: {fps}")
    
    def on_enable_changed(self, state):
        self.detection_thread.enabled = (state == Qt.Checked)
    
    def on_fov_changed(self, value):
        self.detection_thread.fov_size = value
        self.fov_value_label.setText(f"{value} px")
    
    def on_target_fps_changed(self, value):
        self.detection_thread.target_fps = value
    
    def on_aim_mode_changed(self, text):
        if text == "Baş":
            self.detection_thread.aim_mode = "head"
        else:
            self.detection_thread.aim_mode = "body"
    
    def on_holdkey_changed(self, state):
        self.detection_thread.holdkey_enabled = (state == Qt.Checked)
    
    def change_hold_key(self):
        """Hold tuşunu değiştir"""
        self.holdkey_button.setText("Tuşa bas...")
        self.holdkey_button.setEnabled(False)
        
        def on_key(e):
            self.detection_thread.holdkey = e.name
            self.holdkey_button.setText(e.name.upper())
            self.holdkey_button.setEnabled(True)
            keyboard.unhook_all()
        
        keyboard.on_press(on_key, suppress=False)
    
    def on_fire_delay_min_changed(self, value):
        self.trigger_thread.fire_delay_min = value
    
    def on_fire_delay_max_changed(self, value):
        self.trigger_thread.fire_delay_max = max(value, self.trigger_thread.fire_delay_min)
    
    def on_min_pixel_changed(self, value):
        self.detection_thread.min_pixel_count = value
    
    def change_fire_key(self):
        """Ateş tuşunu değiştir"""
        self.fire_key_button.setText("Tuşa bas...")
        self.fire_key_button.setEnabled(False)
        
        def on_key(e):
            self.trigger_thread.fire_key = e.name
            self.fire_key_button.setText(e.name.upper())
            self.fire_key_button.setEnabled(True)
            keyboard.unhook_all()
        
        keyboard.on_press(on_key, suppress=False)
    
    def on_color_changed(self):
        self.detection_thread.lower_hsv = np.array([
            self.hue_min_slider.value(),
            self.sat_min_slider.value(),
            self.val_min_slider.value()
        ])
        self.detection_thread.upper_hsv = np.array([
            self.hue_max_slider.value(),
            self.sat_max_slider.value(),
            self.val_max_slider.value()
        ])
        
        self.hue_min_label.setText(str(self.hue_min_slider.value()))
        self.hue_max_label.setText(str(self.hue_max_slider.value()))
        self.sat_min_label.setText(str(self.sat_min_slider.value()))
        self.sat_max_label.setText(str(self.sat_max_slider.value()))
        self.val_min_label.setText(str(self.val_min_slider.value()))
        self.val_max_label.setText(str(self.val_max_slider.value()))
    
    def load_color_preset(self, preset):
        """Renk preset yükle"""
        presets = {
            "purple": ([130, 50, 50], [160, 255, 255]),
            "red": ([0, 100, 100], [10, 255, 255]),
            "yellow": ([20, 100, 100], [30, 255, 255])
        }
        
        if preset in presets:
            lower, upper = presets[preset]
            self.hue_min_slider.setValue(lower[0])
            self.sat_min_slider.setValue(lower[1])
            self.val_min_slider.setValue(lower[2])
            self.hue_max_slider.setValue(upper[0])
            self.sat_max_slider.setValue(upper[1])
            self.val_max_slider.setValue(upper[2])
    
    
    def closeEvent(self, event):
        """Uygulama kapatılıyor"""
        self.detection_thread.stop()
        self.trigger_thread.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    
    # Yönetici izni kontrolü
    if not ctypes.windll.shell32.IsUserAnAdmin():
        print("UYARI: Yönetici olarak çalıştırmanız önerilir!")
    
    window = ParsecColorbotGUI()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
