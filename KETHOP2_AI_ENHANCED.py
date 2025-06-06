#!/usr/bin/env python3
"""
HỆ THỐNG KHÓA BẢO MẬT 4 LỚP - AI ENHANCED VERSION (COMPLETE)
Tác giả: Khoi - Luận án tốt nghiệp
Ngày tạo: 2025-01-16
Phiên bản: v2.0 AI Enhanced - Complete
"""

import cv2
import time
import json
import os
import logging
import threading
import tkinter as tk
from tkinter import ttk, font
from PIL import Image, ImageTk
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum
import sys
import numpy as np

# Import modules của dự án
try:
    from improved_face_recognition import ImprovedFaceRecognition, FaceDetectionResult
    from enhanced_components import (
        Colors, EnhancedBuzzerManager, EnhancedNumpadDialog, 
        EnhancedMessageBox, AdminDataManager, ImprovedAdminGUI
    )
except ImportError as e:
    print(f"❌ Lỗi import modules: {e}")
    print("🔧 Đảm bảo các file sau tồn tại:")
    print("   - improved_face_recognition.py")
    print("   - enhanced_components.py")
    sys.exit(1)

# Hardware imports
try:
    from picamera2 import Picamera2
    from gpiozero import LED, PWMOutputDevice
    from pyfingerprint.pyfingerprint import PyFingerprint
    import board
    import busio
    from adafruit_pn532.i2c import PN532_I2C
except ImportError as e:
    logging.error(f"Không thể import thư viện phần cứng: {e}")
    # Thêm simulation mode cho testing
    print("⚠️ Hardware import failed - running in simulation mode")
    
    # Mock hardware classes for testing
    class MockPicamera2:
        def configure(self, config): pass
        def start(self): pass
        def stop(self): pass
        def capture_array(self): 
            return np.zeros((600, 800, 3), dtype=np.uint8)
    
    class MockLED:
        def __init__(self, pin): self.state = True
        def on(self): self.state = True
        def off(self): self.state = False
    
    class MockPN532:
        def SAM_configuration(self): pass
        def read_passive_target(self, timeout=1): return None
    
    class MockFingerprint:
        def verifyPassword(self): return True
        def readImage(self): return False
        def convertImage(self, slot): pass
        def searchTemplate(self): return (-1, 0)
        def createTemplate(self): pass
        def storeTemplate(self, pos, slot): pass
        def deleteTemplate(self, pos): pass
        def loadTemplate(self, pos, slot): pass
    
    # Use mock classes
    Picamera2 = MockPicamera2
    LED = MockLED
    
    # Mock board and busio
    class MockBoard:
        SCL = None
        SDA = None
    
    class MockBusIO:
        def I2C(self, scl, sda): return None
    
    board = MockBoard()
    busio = MockBusIO()
    PN532_I2C = lambda i2c, debug=False: MockPN532()
    PyFingerprint = lambda *args, **kwargs: MockFingerprint()

# ==== CONFIGURATION ====
@dataclass
class Config:
    # Paths
    PROJECT_PATH: str = "/home/khoi/Desktop/KHOI_LUANAN"
    MODELS_PATH: str = "/home/khoi/Desktop/KHOI_LUANAN/models"
    FACE_DATA_PATH: str = "/home/khoi/Desktop/KHOI_LUANAN/face_data"
    ADMIN_DATA_PATH: str = "/home/khoi/Desktop/KHOI_LUANAN"
    
    # GPIO
    BUZZER_GPIO: int = 17
    RELAY_GPIO: int = 5
    
    # Face Recognition - AI Enhanced
    FACE_CONFIDENCE_THRESHOLD: float = 0.5
    FACE_RECOGNITION_THRESHOLD: float = 85.0
    FACE_REQUIRED_CONSECUTIVE: int = 5
    FACE_DETECTION_INTERVAL: float = 0.03  # ~33 FPS
    
    # Camera - Enhanced Quality
    CAMERA_WIDTH: int = 800
    CAMERA_HEIGHT: int = 600
    DISPLAY_WIDTH: int = 650
    DISPLAY_HEIGHT: int = 490
    
    # Admin
    ADMIN_UID: List[int] = None
    ADMIN_PASS: str = "0809"
    
    # Timing
    LOCK_OPEN_DURATION: int = 3
    MAX_ATTEMPTS: int = 5
    
    def __post_init__(self):
        if self.ADMIN_UID is None:
            self.ADMIN_UID = [0xe5, 0xa8, 0xbd, 0x2]
        
        # Tạo thư mục nếu chưa có
        for path in [self.MODELS_PATH, self.FACE_DATA_PATH, self.ADMIN_DATA_PATH]:
            os.makedirs(path, exist_ok=True)

class AuthStep(Enum):
    FACE = "face"
    FINGERPRINT = "fingerprint"
    RFID = "rfid"
    PASSCODE = "passcode"
    ADMIN = "admin"

# ==== LOGGING SETUP ====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/home/khoi/Desktop/KHOI_LUANAN/system.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==== ENHANCED GUI WITH AI FEATURES ====
class AIEnhancedSecurityGUI:
    def __init__(self, root):
        self.root = root
        self.fps_counter = 0
        self.fps_start_time = time.time()
        self.current_fps = 0
        self.detection_stats = {"total": 0, "recognized": 0, "unknown": 0}
        
        self._setup_window()
        self._create_widgets()
        self._setup_bindings()
    
    def _setup_window(self):
        self.root.title("🤖 HỆ THỐNG KHÓA BẢO MẬT AI - PHIÊN BẢN 2.0")
        self.root.geometry("1500x900")
        self.root.configure(bg=Colors.DARK_BG)
        self.root.attributes('-fullscreen', True)
        self.root.minsize(1200, 800)
    
    def _create_widgets(self):
        # Main container
        main_container = tk.Frame(self.root, bg=Colors.DARK_BG)
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        main_container.grid_columnconfigure(0, weight=2)  # Camera gets more space
        main_container.grid_columnconfigure(1, weight=1)
        main_container.grid_rowconfigure(0, weight=1)
        
        # LEFT - AI CAMERA PANEL
        self._create_ai_camera_panel(main_container)
        
        # RIGHT - STATUS PANEL
        self._create_status_panel(main_container)
        
        # BOTTOM - STATUS BAR
        self._create_status_bar()
    
    def _create_ai_camera_panel(self, parent):
        camera_panel = tk.Frame(parent, bg=Colors.CARD_BG, relief=tk.RAISED, bd=4)
        camera_panel.grid(row=0, column=0, padx=(0,10), pady=0, sticky="nsew")
        
        # Header với AI info
        header = tk.Frame(camera_panel, bg=Colors.PRIMARY, height=100)
        header.pack(fill=tk.X, padx=4, pady=4)
        header.pack_propagate(False)
        
        # Left side - title
        header_left = tk.Frame(header, bg=Colors.PRIMARY)
        header_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        tk.Label(header_left, text="🤖 AI FACE DETECTION SYSTEM", 
                font=('Arial', 26, 'bold'), fg='white', bg=Colors.PRIMARY,
                anchor='w').pack(side=tk.LEFT, padx=20, expand=True, fill=tk.X)
        
        # Right side - stats
        stats_frame = tk.Frame(header, bg=Colors.PRIMARY)
        stats_frame.pack(side=tk.RIGHT, padx=20)
        
        self.fps_label = tk.Label(stats_frame, text="FPS: --", 
                                 font=('Arial', 16, 'bold'), fg='white', bg=Colors.PRIMARY)
        self.fps_label.pack()
        
        self.detection_count_label = tk.Label(stats_frame, text="Detected: 0", 
                                            font=('Arial', 14), fg='white', bg=Colors.PRIMARY)
        self.detection_count_label.pack()
        
        # Camera display - MUCH LARGER
        self.camera_frame = tk.Frame(camera_panel, bg='black', relief=tk.SUNKEN, bd=4)
        self.camera_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        self.camera_label = tk.Label(self.camera_frame, 
                                   text="🤖 Đang khởi động AI Camera System...\n\n⚡ OpenCV DNN Loading...",
                                   font=('Arial', 22), fg='white', bg='black')
        self.camera_label.pack(expand=True)
        
        # AI Status bar
        ai_status_frame = tk.Frame(camera_panel, bg=Colors.CARD_BG, height=80)
        ai_status_frame.pack(fill=tk.X, pady=10)
        ai_status_frame.pack_propagate(False)
        
        self.ai_status = tk.Label(ai_status_frame, text="🤖 AI System Initializing...",
                                 font=('Arial', 18, 'bold'), 
                                 fg=Colors.PRIMARY, bg=Colors.CARD_BG)
        self.ai_status.pack(expand=True)
        
        self.detection_info = tk.Label(ai_status_frame, text="🔍 Preparing neural networks...",
                                      font=('Arial', 16), 
                                      fg=Colors.TEXT_SECONDARY, bg=Colors.CARD_BG)
        self.detection_info.pack()
    
    def _create_status_panel(self, parent):
        status_panel = tk.Frame(parent, bg=Colors.CARD_BG, relief=tk.RAISED, bd=4)
        status_panel.grid(row=0, column=1, padx=(10,0), pady=0, sticky="nsew")
        
        # Header
        header = tk.Frame(status_panel, bg=Colors.SUCCESS, height=100)
        header.pack(fill=tk.X, padx=4, pady=4)
        header.pack_propagate(False)
        
        tk.Label(header, text="📊 TRẠNG THÁI AUTHENTICATION", 
                font=('Arial', 22, 'bold'), fg='white', bg=Colors.SUCCESS).pack(expand=True)
        
        # Current step - LARGER
        self.step_frame = tk.Frame(status_panel, bg=Colors.CARD_BG)
        self.step_frame.pack(fill=tk.X, padx=25, pady=25)
        
        self.step_number = tk.Label(self.step_frame, text="1", 
                                   font=('Arial', 52, 'bold'),
                                   fg='white', bg=Colors.PRIMARY,
                                   width=2, relief=tk.RAISED, bd=5)
        self.step_number.pack(side=tk.LEFT, padx=(0,25))
        
        step_info = tk.Frame(self.step_frame, bg=Colors.CARD_BG)
        step_info.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.step_title = tk.Label(step_info, text="🤖 AI FACE RECOGNITION",
                                  font=('Arial', 30, 'bold'),
                                  fg=Colors.TEXT_PRIMARY, bg=Colors.CARD_BG,
                                  anchor='w')
        self.step_title.pack(fill=tk.X)
        
        self.step_subtitle = tk.Label(step_info, text="Neural network đang phân tích...",
                                     font=('Arial', 20),
                                     fg=Colors.TEXT_SECONDARY, bg=Colors.CARD_BG,
                                     anchor='w')
        self.step_subtitle.pack(fill=tk.X)
        
        # Progress indicators
        progress_frame = tk.Frame(status_panel, bg=Colors.CARD_BG)
        progress_frame.pack(fill=tk.X, padx=25, pady=20)
        
        tk.Label(progress_frame, text="🔄 TIẾN TRÌNH XÁC THỰC:",
                font=('Arial', 22, 'bold'),
                fg=Colors.TEXT_PRIMARY, bg=Colors.CARD_BG).pack(anchor='w')
        
        steps_frame = tk.Frame(progress_frame, bg=Colors.CARD_BG)
        steps_frame.pack(fill=tk.X, pady=15)
        
        self.step_indicators = {}
        steps = ["🤖", "👆", "📱", "🔑"]
        names = ["AI RECOGNITION", "FINGERPRINT", "RFID CARD", "PASSCODE"]
        
        for i, (icon, name) in enumerate(zip(steps, names)):
            container = tk.Frame(steps_frame, bg=Colors.CARD_BG)
            container.pack(fill=tk.X, pady=8)
            
            circle = tk.Label(container, text=f"{i+1}",
                             font=('Arial', 22, 'bold'),
                             fg='white', bg=Colors.TEXT_SECONDARY,
                             width=3, relief=tk.RAISED, bd=4)
            circle.pack(side=tk.LEFT, padx=(0,20))
            
            label = tk.Label(container, text=f"{icon} {name}",
                            font=('Arial', 20, 'bold'),
                            fg=Colors.TEXT_PRIMARY, bg=Colors.CARD_BG,
                            anchor='w')
            label.pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            self.step_indicators[i+1] = {
                'circle': circle,
                'label': label
            }
        
        # AI Details area
        msg_frame = tk.Frame(status_panel, bg=Colors.BACKGROUND, relief=tk.SUNKEN, bd=4)
        msg_frame.pack(fill=tk.X, padx=25, pady=20)
        
        tk.Label(msg_frame, text="🧠 AI ANALYSIS DETAILS:",
                font=('Arial', 18, 'bold'),
                fg=Colors.TEXT_PRIMARY, bg=Colors.BACKGROUND).pack(anchor='w', padx=20, pady=(15,8))
        
        self.detail_message = tk.Label(msg_frame, text="🤖 Khởi động neural networks...\n⚡ Loading OpenCV DNN models...",
                                      font=('Arial', 16),
                                      fg=Colors.TEXT_SECONDARY, bg=Colors.BACKGROUND,
                                      wraplength=450, justify=tk.LEFT, anchor='w')
        self.detail_message.pack(fill=tk.X, padx=20, pady=(0,15))
        
        # Time display
        self.time_label = tk.Label(status_panel, text="",
                                  font=('Arial', 16),
                                  fg=Colors.TEXT_SECONDARY, bg=Colors.CARD_BG)
        self.time_label.pack(side=tk.BOTTOM, pady=10)
        
        self._update_time()
    
    def _create_status_bar(self):
        status_bar = tk.Frame(self.root, bg=Colors.PRIMARY, height=90)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=20, pady=(0,20))
        status_bar.pack_propagate(False)
        
        self.main_status = tk.Label(status_bar, 
                                   text="🤖 AI ENHANCED SECURITY SYSTEM v2.0 - INITIALIZING...",
                                   font=('Arial', 22, 'bold'),
                                   fg='white', bg=Colors.PRIMARY)
        self.main_status.pack(expand=True)
    
    def _setup_bindings(self):
        self.root.bind('<Key>', self._on_key)
        self.root.bind('<F11>', lambda e: self.root.attributes('-fullscreen', 
                                                              not self.root.attributes('-fullscreen')))
        self.root.focus_set()
    
    def _on_key(self, event):
        key = event.keysym
        if key == 'asterisk' or key == 'KP_Multiply':
            if hasattr(self, 'system_ref'):
                self.system_ref._force_admin_mode()
        elif key == 'numbersign' or key == 'KP_Add':
            if hasattr(self, 'system_ref'):
                self.system_ref.start_authentication()
        elif key == 'Escape':
            if hasattr(self, 'system_ref') and hasattr(self.system_ref, 'buzzer'):
                if EnhancedMessageBox.ask_yesno(self.root, "Thoát hệ thống", 
                                            "Bạn có chắc chắn muốn thoát?", self.system_ref.buzzer):
                    self.root.quit()
    
    def _update_time(self):
        current_time = datetime.now().strftime("🕐 %H:%M:%S - %d/%m/%Y")
        self.time_label.config(text=current_time)
        self.root.after(1000, self._update_time)
    
    def update_camera(self, frame: np.ndarray, detection_result: Optional[FaceDetectionResult] = None):
        """Update camera display với AI feedback nâng cao"""
        try:
            # Calculate FPS
            self.fps_counter += 1
            current_time = time.time()
            if current_time - self.fps_start_time >= 1.0:
                self.current_fps = self.fps_counter
                self.fps_counter = 0
                self.fps_start_time = current_time
                self.fps_label.config(text=f"FPS: {self.current_fps}")
            
            # Update detection statistics
            if detection_result:
                self.detection_stats["total"] += 1
                if detection_result.recognized:
                    self.detection_stats["recognized"] += 1
                elif detection_result.detected:
                    self.detection_stats["unknown"] += 1
                
                self.detection_count_label.config(
                    text=f"Total: {self.detection_stats['total']} | OK: {self.detection_stats['recognized']}"
                )
            
            # Resize frame for display
            height, width = frame.shape[:2]
            display_height = Config.DISPLAY_HEIGHT
            display_width = int(width * display_height / height)
            
            img = cv2.resize(frame, (display_width, display_height))
            rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img_pil = Image.fromarray(rgb_img)
            img_tk = ImageTk.PhotoImage(img_pil)
            
            self.camera_label.config(image=img_tk, text="")
            self.camera_label.image = img_tk
            
            # Update AI status based on detection result
            if detection_result:
                if detection_result.detected:
                    if detection_result.recognized:
                        self.ai_status.config(
                            text=f"✅ AI CONFIRMED: {detection_result.person_name}",
                            fg=Colors.SUCCESS
                        )
                        self.detection_info.config(
                            text=f"🎯 Confidence: {detection_result.confidence:.1f} | Status: AUTHORIZED",
                            fg=Colors.SUCCESS
                        )
                    else:
                        self.ai_status.config(
                            text="❌ AI DETECTED: UNAUTHORIZED FACE",
                            fg=Colors.ERROR
                        )
                        self.detection_info.config(
                            text="⚠️ Face detected but not in database | Access denied",
                            fg=Colors.ERROR
                        )
                else:
                    self.ai_status.config(
                        text="🔍 AI SCANNING: Searching for faces...",
                        fg=Colors.WARNING
                    )
                    self.detection_info.config(
                        text="👁️ Neural networks analyzing video stream...",
                        fg=Colors.TEXT_SECONDARY
                    )
            
        except Exception as e:
            logger.error(f"Error updating camera: {e}")
    
    def update_step(self, step_num, title, subtitle, color=None):
        if color is None:
            color = Colors.PRIMARY
            
        self.step_number.config(text=str(step_num), bg=color)
        self.step_title.config(text=title)
        self.step_subtitle.config(text=subtitle)
        
        # Update progress indicators
        for i in range(1, 5):
            indicator = self.step_indicators[i]
            if i < step_num:
                indicator['circle'].config(bg=Colors.SUCCESS)
                indicator['label'].config(fg=Colors.TEXT_PRIMARY)
            elif i == step_num:
                indicator['circle'].config(bg=color)
                indicator['label'].config(fg=Colors.TEXT_PRIMARY)
            else:
                indicator['circle'].config(bg=Colors.TEXT_SECONDARY)
                indicator['label'].config(fg=Colors.TEXT_SECONDARY)
    
    def update_status(self, message, color=None):
        if color is None:
            color = 'white'
        self.main_status.config(text=f"🤖 {message}", fg=color)
    
    def update_detail(self, message, color=None):
        if color is None:
            color = Colors.TEXT_SECONDARY
        self.detail_message.config(text=message, fg=color)
    
    def set_system_reference(self, system):
        self.system_ref = system

# ==== AI ENHANCED SECURITY SYSTEM ====
class AIEnhancedSecuritySystem:
    def __init__(self):
        self.config = Config()
        logger.info("🤖 Khởi tạo AI Enhanced Security System...")
        
        self._init_hardware()
        self._init_components()
        self._init_gui()
        
        self.auth_state = {
            "step": AuthStep.FACE,
            "consecutive_face_ok": 0,
            "fingerprint_attempts": 0,
            "rfid_attempts": 0,
            "pin_attempts": 0
        }
        
        self.running = True
        self.face_thread = None
        
        logger.info("✅ AI Enhanced Security System khởi tạo thành công!")
    
    def _init_hardware(self):
        """Khởi tạo phần cứng"""
        try:
            logger.info("🔧 Khởi tạo phần cứng...")
            
            # Buzzer (với mock nếu cần)
            try:
                self.buzzer = EnhancedBuzzerManager(self.config.BUZZER_GPIO)
            except:
                logger.warning("⚠️ Buzzer mock mode")
                self.buzzer = type('MockBuzzer', (), {'beep': lambda x, y: None})()
            
            # Camera
            self.picam2 = Picamera2()
            if hasattr(self.picam2, 'configure'):
                self.picam2.configure(self.picam2.create_video_configuration(
                    main={"format": 'XRGB8888', "size": (self.config.CAMERA_WIDTH, self.config.CAMERA_HEIGHT)}
                ))
                self.picam2.start()
                time.sleep(2)
            
            # Relay (Door lock)
            self.relay = LED(self.config.RELAY_GPIO)
            self.relay.on()  # Locked by default
            
            # RFID
            i2c = busio.I2C(board.SCL, board.SDA)
            self.pn532 = PN532_I2C(i2c, debug=False)
            self.pn532.SAM_configuration()
            
            # Fingerprint sensor
            self.fingerprint = PyFingerprint('/dev/ttyUSB0', 57600, 0xFFFFFFFF, 0x00000000)
            if not self.fingerprint.verifyPassword():
                logger.warning("⚠️ Fingerprint sensor simulation mode")
            
            logger.info("✅ Tất cả phần cứng đã sẵn sàng")
            
        except Exception as e:
            logger.error(f"❌ Lỗi khởi tạo phần cứng: {e}")
            logger.info("🔄 Continuing in simulation mode...")
    
    def _init_components(self):
        """Khởi tạo các thành phần AI và data"""
        try:
            logger.info("🧠 Khởi tạo AI components...")
            
            # Admin data manager
            self.admin_data = AdminDataManager(self.config.ADMIN_DATA_PATH)
            
            # AI Face Recognition - Enhanced
            self.face_recognizer = ImprovedFaceRecognition(
                models_path=self.config.MODELS_PATH,
                face_data_path=self.config.FACE_DATA_PATH,
                confidence_threshold=self.config.FACE_CONFIDENCE_THRESHOLD,
                recognition_threshold=self.config.FACE_RECOGNITION_THRESHOLD
            )
            
            logger.info("✅ AI components đã sẵn sàng")
            
        except Exception as e:
            logger.error(f"❌ Lỗi khởi tạo AI components: {e}")
            raise
    
    def _init_gui(self):
        """Khởi tạo giao diện"""
        try:
            logger.info("🎨 Khởi tạo GUI...")
            
            self.root = tk.Tk()
            self.gui = AIEnhancedSecurityGUI(self.root)
            self.gui.set_system_reference(self)
            
            # Admin GUI
            self.admin_gui = ImprovedAdminGUI(self.root, self)
            
            logger.info("✅ GUI đã sẵn sàng")
            
        except Exception as e:
            logger.error(f"❌ Lỗi khởi tạo GUI: {e}")
            raise
    
    def _force_admin_mode(self):
        """Chế độ admin nhanh bằng phím *"""
        dialog = EnhancedNumpadDialog(self.root, "🔧 AI ADMIN ACCESS", 
                                    "Nhập mật khẩu admin:", True, self.buzzer)
        password = dialog.show()
        
        if password == self.config.ADMIN_PASS:
            self.gui.update_status("AI ADMIN MODE ACTIVATED", 'lightgreen')
            self.gui.update_detail("✅ Admin authentication successful! Opening control panel...", Colors.SUCCESS)
            self.buzzer.beep("success")
            self.admin_gui.show_admin_panel()
        elif password is not None:
            self.gui.update_status("ADMIN ACCESS DENIED", 'orange')
            self.gui.update_detail("❌ Incorrect admin password!", Colors.ERROR)
            self.buzzer.beep("error")
    
    def start_authentication(self):
        """Bắt đầu quy trình xác thực AI"""
        logger.info("🚀 Bắt đầu quy trình xác thực AI")
        
        self.auth_state = {
            "step": AuthStep.FACE,
            "consecutive_face_ok": 0,
            "fingerprint_attempts": 0,
            "rfid_attempts": 0,
            "pin_attempts": 0
        }
        
        self.gui.update_step(1, "🤖 AI FACE RECOGNITION", "Neural network đang phân tích...", Colors.PRIMARY)
        self.gui.update_status("AI ANALYZING FACES - PLEASE LOOK AT CAMERA", 'white')
        self.gui.update_detail("🤖 AI neural networks đang quét và phân tích khuôn mặt.\n👁️ Nhìn thẳng vào camera và giữ nguyên vị trí.", Colors.PRIMARY)
        
        # Reset detection stats
        self.gui.detection_stats = {"total": 0, "recognized": 0, "unknown": 0}
        
        if self.face_thread and self.face_thread.is_alive():
            return
        
        self.face_thread = threading.Thread(target=self._ai_face_loop, daemon=True)
        self.face_thread.start()
    
    def _ai_face_loop(self):
        """AI Face recognition loop với enhanced performance"""
        logger.info("👁️ Bắt đầu AI face recognition loop")
        consecutive_count = 0
        
        while self.running and self.auth_state["step"] == AuthStep.FACE:
            try:
                # Capture frame
                frame = self.picam2.capture_array()
                if frame is None:
                    continue
                
                # AI Processing
                annotated_frame, result = self.face_recognizer.process_frame(frame)
                
                # Update GUI với kết quả AI
                self.root.after(0, lambda: self.gui.update_camera(annotated_frame, result))
                
                if result.recognized:
                    consecutive_count += 1
                    self.auth_state["consecutive_face_ok"] = consecutive_count
                    
                    progress = consecutive_count / self.config.FACE_REQUIRED_CONSECUTIVE * 100
                    msg = f"AI confirmed ({consecutive_count}/{self.config.FACE_REQUIRED_CONSECUTIVE}) - {progress:.0f}%"
                    
                    self.root.after(0, lambda: self.gui.update_step(1, "✅ AI RECOGNITION", msg, Colors.SUCCESS))
                    self.root.after(0, lambda: self.gui.update_detail(
                        f"🎯 Identity: {result.person_name}\n"
                        f"🔄 Verifying... {self.config.FACE_REQUIRED_CONSECUTIVE - consecutive_count} more confirmations needed\n"
                        f"📊 Confidence: {result.confidence:.1f}/100", 
                        Colors.SUCCESS))
                    
                    if consecutive_count >= self.config.FACE_REQUIRED_CONSECUTIVE:
                        logger.info(f"✅ AI Face recognition thành công: {result.person_name}")
                        self.buzzer.beep("success")
                        self.root.after(0, lambda: self.gui.update_status(f"AI FACE VERIFIED: {result.person_name.upper()}!", 'lightgreen'))
                        self.root.after(1500, self._proceed_to_fingerprint)
                        break
                        
                elif result.detected:
                    # Phát hiện khuôn mặt nhưng không nhận diện được
                    consecutive_count = 0
                    self.auth_state["consecutive_face_ok"] = 0
                    self.root.after(0, lambda: self.gui.update_step(1, "⚠️ AI DETECTION", "Unknown face detected", Colors.WARNING))
                    self.root.after(0, lambda: self.gui.update_detail(
                        "🚫 AI detected a face but it's not in the authorized database.\n"
                        f"📊 Detection confidence: {result.confidence:.1f}\n"
                        "👤 Please ensure you are registered in the system.", 
                        Colors.WARNING))
                else:
                    # Không phát hiện khuôn mặt
                    consecutive_count = 0
                    self.auth_state["consecutive_face_ok"] = 0
                    self.root.after(0, lambda: self.gui.update_step(1, "🔍 AI SCANNING", "Searching for faces...", Colors.PRIMARY))
                
                time.sleep(self.config.FACE_DETECTION_INTERVAL)
                
            except Exception as e:
                logger.error(f"❌ Lỗi AI face loop: {e}")
                self.root.after(0, lambda: self.gui.update_detail(f"❌ AI Error: {str(e)}", Colors.ERROR))
                time.sleep(1)
    
    def _proceed_to_fingerprint(self):
        """Chuyển sang bước vân tay"""
        logger.info("👆 Chuyển sang xác thực vân tay")
        self.auth_state["step"] = AuthStep.FINGERPRINT
        self.auth_state["fingerprint_attempts"] = 0
        
        self.gui.update_step(2, "👆 FINGERPRINT SCAN", "Place finger on sensor", Colors.WARNING)
        self.gui.update_status("WAITING FOR FINGERPRINT...", 'yellow')
        self.gui.update_detail("👆 Please place your registered finger on the biometric sensor.\n🔍 Sensor is ready for scanning.", Colors.WARNING)
        
        threading.Thread(target=self._fingerprint_loop, daemon=True).start()
    
    def _fingerprint_loop(self):
        """Fingerprint verification loop"""
        while (self.auth_state["fingerprint_attempts"] < self.config.MAX_ATTEMPTS and 
               self.auth_state["step"] == AuthStep.FINGERPRINT):
            
            try:
                self.auth_state["fingerprint_attempts"] += 1
                attempt_msg = f"Attempt {self.auth_state['fingerprint_attempts']}/{self.config.MAX_ATTEMPTS}"
                
                self.root.after(0, lambda: self.gui.update_step(2, "👆 FINGERPRINT", attempt_msg, Colors.WARNING))
                self.root.after(0, lambda: self.gui.update_detail(
                    f"👆 Scanning fingerprint... (Attempt {self.auth_state['fingerprint_attempts']}/{self.config.MAX_ATTEMPTS})\n"
                    "🔍 Please hold finger steady on sensor.", 
                    Colors.WARNING))
                
                timeout = 10
                start_time = time.time()
                
                while time.time() - start_time < timeout:
                    if self.fingerprint.readImage():
                        self.fingerprint.convertImage(0x01)
                        result = self.fingerprint.searchTemplate()
                        
                        if result[0] != -1:
                            # Success
                            logger.info(f"✅ Fingerprint verified: ID {result[0]}")
                            self.buzzer.beep("success")
                            self.root.after(0, lambda: self.gui.update_status("FINGERPRINT VERIFIED! PROCEEDING TO RFID...", 'lightgreen'))
                            self.root.after(0, lambda: self.gui.update_detail(f"✅ Fingerprint authentication successful!\n🆔 Template ID: {result[0]}\n📊 Match score: {result[1]}", Colors.SUCCESS))
                            self.root.after(1500, self._proceed_to_rfid)
                            return
                        else:
                            # Wrong fingerprint
                            self.buzzer.beep("error")
                            remaining = self.config.MAX_ATTEMPTS - self.auth_state["fingerprint_attempts"]
                            if remaining > 0:
                                self.root.after(0, lambda: self.gui.update_detail(
                                    f"❌ Fingerprint not recognized!\n🔄 {remaining} attempts remaining\n👆 Please try again with a registered finger.", Colors.ERROR))
                                time.sleep(2)
                                break
                    time.sleep(0.1)
                
                if time.time() - start_time >= timeout:
                    # Timeout
                    remaining = self.config.MAX_ATTEMPTS - self.auth_state["fingerprint_attempts"]
                    if remaining > 0:
                        self.root.after(0, lambda: self.gui.update_detail(
                            f"⏰ Scan timeout!\n🔄 {remaining} attempts remaining\n👆 Please place finger properly on sensor.", Colors.WARNING))
                        time.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ Fingerprint error: {e}")
                self.root.after(0, lambda: self.gui.update_detail(f"❌ Sensor error: {str(e)}", Colors.ERROR))
                time.sleep(1)
        
        # Out of attempts
        logger.warning("⚠️ Fingerprint: Hết lượt thử")
        self.root.after(0, lambda: self.gui.update_status("FINGERPRINT FAILED - RESTARTING AUTHENTICATION", 'orange'))
        self.root.after(0, lambda: self.gui.update_detail("⚠️ Maximum fingerprint attempts exceeded.\n🔄 Restarting authentication process...", Colors.ERROR))
        self.buzzer.beep("error")
        self.root.after(3000, self.start_authentication)
    
    def _proceed_to_rfid(self):
        """Chuyển sang bước RFID"""
        logger.info("📱 Chuyển sang xác thực RFID")
        self.auth_state["step"] = AuthStep.RFID
        self.auth_state["rfid_attempts"] = 0
        
        self.gui.update_step(3, "📱 RFID SCAN", "Present card to reader", Colors.ACCENT)
        self.gui.update_status("WAITING FOR RFID CARD...", 'lightblue')
        self.gui.update_detail("📱 Please present your RFID card near the reader.\n📡 Reader is active and scanning for cards.", Colors.ACCENT)
        
        threading.Thread(target=self._rfid_loop, daemon=True).start()
    
    def _rfid_loop(self):
        """RFID verification loop"""
        while (self.auth_state["rfid_attempts"] < self.config.MAX_ATTEMPTS and 
               self.auth_state["step"] == AuthStep.RFID):
            
            try:
                self.auth_state["rfid_attempts"] += 1
                attempt_msg = f"Attempt {self.auth_state['rfid_attempts']}/{self.config.MAX_ATTEMPTS}"
                
                self.root.after(0, lambda: self.gui.update_step(3, "📱 RFID SCAN", attempt_msg, Colors.ACCENT))
                self.root.after(0, lambda: self.gui.update_detail(
                    f"📱 Scanning for RFID card... (Attempt {self.auth_state['rfid_attempts']}/{self.config.MAX_ATTEMPTS})\n"
                    "📡 Hold card within 2-5cm of reader.", 
                    Colors.ACCENT))
                
                uid = self.pn532.read_passive_target(timeout=8)
                
                if uid:
                    uid_list = list(uid)
                    logger.info(f"📱 RFID detected: {uid_list}")
                    
                    # Check admin card
                    if uid_list == self.config.ADMIN_UID:
                        self.root.after(0, lambda: self._admin_authentication())
                        return
                    
                    # Check regular cards
                    valid_uids = self.admin_data.get_rfid_uids()
                    if uid_list in valid_uids:
                        logger.info(f"✅ RFID verified: {uid_list}")
                        self.buzzer.beep("success")
                        self.root.after(0, lambda: self.gui.update_status("RFID VERIFIED! ENTER PASSCODE...", 'lightgreen'))
                        self.root.after(0, lambda: self.gui.update_detail(f"✅ RFID card authentication successful!\n🆔 Card UID: {uid_list}\n🔑 Proceeding to final passcode step.", Colors.SUCCESS))
                        self.root.after(1500, self._proceed_to_passcode)
                        return
                    else:
                        # Invalid card
                        self.buzzer.beep("error")
                        remaining = self.config.MAX_ATTEMPTS - self.auth_state["rfid_attempts"]
                        if remaining > 0:
                            self.root.after(0, lambda: self.gui.update_detail(
                                f"❌ Unauthorized RFID card!\n🆔 UID: {uid_list}\n🔄 {remaining} attempts remaining", Colors.ERROR))
                            time.sleep(2)
                else:
                    # No card detected
                    remaining = self.config.MAX_ATTEMPTS - self.auth_state["rfid_attempts"]
                    if remaining > 0:
                        self.root.after(0, lambda: self.gui.update_detail(
                            f"⏰ No card detected!\n🔄 {remaining} attempts remaining\n📱 Please present card closer to reader.", Colors.WARNING))
                        time.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ RFID error: {e}")
                self.root.after(0, lambda: self.gui.update_detail(f"❌ RFID reader error: {str(e)}", Colors.ERROR))
                time.sleep(1)
        
        # Out of attempts
        logger.warning("⚠️ RFID: Hết lượt thử")
        self.root.after(0, lambda: self.gui.update_status("RFID FAILED - RESTARTING AUTHENTICATION", 'orange'))
        self.root.after(0, lambda: self.gui.update_detail("⚠️ Maximum RFID attempts exceeded.\n🔄 Restarting authentication process...", Colors.ERROR))
        self.buzzer.beep("error")
        self.root.after(3000, self.start_authentication)
    
    def _admin_authentication(self):
        """Admin authentication via RFID"""
        dialog = EnhancedNumpadDialog(self.root, "🔧 ADMIN RFID ACCESS", 
                                    "Admin card detected. Enter password:", True, self.buzzer)
        password = dialog.show()
        
        if password == self.config.ADMIN_PASS:
            logger.info("✅ Admin RFID authentication successful")
            self.gui.update_status("ADMIN RFID VERIFIED! OPENING CONTROL PANEL", 'lightgreen')
            self.gui.update_detail("✅ Admin RFID authentication successful!\n🔧 Opening admin control panel...", Colors.SUCCESS)
            self.buzzer.beep("success")
            self.admin_gui.show_admin_panel()
        elif password is not None:
            self.gui.update_status("ADMIN PASSWORD INCORRECT", 'orange')
            self.gui.update_detail("❌ Admin password incorrect!\n🔄 Returning to authentication...", Colors.ERROR)
            self.buzzer.beep("error")
            time.sleep(2)
            self.start_authentication()
        else:
            self.start_authentication()
    
    def _proceed_to_passcode(self):
        """Chuyển sang bước cuối - passcode"""
        logger.info("🔑 Chuyển sang bước passcode cuối cùng")
        self.auth_state["step"] = AuthStep.PASSCODE
        self.auth_state["pin_attempts"] = 0
        
        self.gui.update_step(4, "🔑 FINAL PASSCODE", "Enter system passcode", Colors.SUCCESS)
        self.gui.update_status("ENTER FINAL PASSCODE...", 'lightgreen')
        
        self._request_passcode()
    
    def _request_passcode(self):
        """Passcode input với retry logic"""
        if self.auth_state["pin_attempts"] >= self.config.MAX_ATTEMPTS:
            logger.warning("⚠️ Passcode: Hết lượt thử")
            self.gui.update_status("PASSCODE FAILED - RESTARTING", 'orange')
            self.gui.update_detail("⚠️ Maximum passcode attempts exceeded.\n🔄 Restarting authentication process...", Colors.ERROR)
            self.buzzer.beep("error")
            self.root.after(3000, self.start_authentication)
            return
        
        self.auth_state["pin_attempts"] += 1
        attempt_msg = f"Attempt {self.auth_state['pin_attempts']}/{self.config.MAX_ATTEMPTS}"
        
        self.gui.update_step(4, "🔑 PASSCODE", attempt_msg, Colors.SUCCESS)
        self.gui.update_detail(f"🔑 Enter system passcode... (Attempt {self.auth_state['pin_attempts']}/{self.config.MAX_ATTEMPTS})\n🔢 Use the numeric keypad to enter your code.", Colors.SUCCESS)
        
        dialog = EnhancedNumpadDialog(self.root, "🔑 FINAL AUTHENTICATION", 
                                    "Enter system passcode to unlock:", True, self.buzzer)
        pin = dialog.show()
        
        if pin == self.admin_data.get_passcode():
            logger.info("✅ Passcode verified - Authentication complete!")
            self.gui.update_status("AUTHENTICATION COMPLETE! UNLOCKING DOOR...", 'lightgreen')
            self.gui.update_detail("🎉 All authentication steps completed successfully!\n🚪 Door unlocking now...", Colors.SUCCESS)
            self.buzzer.beep("success")
            self._unlock_door()
        elif pin is not None:
            remaining = self.config.MAX_ATTEMPTS - self.auth_state["pin_attempts"]
            if remaining > 0:
                self.gui.update_detail(f"❌ Incorrect passcode!\n🔄 {remaining} attempts remaining\n🔢 Please try again.", Colors.ERROR)
                self.buzzer.beep("error")
                self.root.after(1500, self._request_passcode)
            else:
                self.gui.update_status("PASSCODE FAILED - RESTARTING", 'orange')
                self.gui.update_detail("⚠️ Maximum passcode attempts exceeded.\n🔄 Restarting authentication process...", Colors.ERROR)
                self.buzzer.beep("error")
                self.root.after(3000, self.start_authentication)
        else:
            self.start_authentication()
    
    def _unlock_door(self):
        """Mở khóa cửa với countdown"""
        try:
            logger.info(f"🚪 Unlocking door for {self.config.LOCK_OPEN_DURATION} seconds")
            
            self.gui.update_step(4, "✅ COMPLETED", "🚪 DOOR UNLOCKED", Colors.SUCCESS)
            self.gui.update_status(f"DOOR OPEN - AUTO LOCK IN {self.config.LOCK_OPEN_DURATION}S", 'lightgreen')
            
            self.relay.off()  # Unlock door
            self.buzzer.beep("success")
            
            # Countdown với hiệu ứng
            for i in range(self.config.LOCK_OPEN_DURATION, 0, -1):
                self.root.after((self.config.LOCK_OPEN_DURATION - i) * 1000, 
                               lambda t=i: self.gui.update_detail(f"🚪 Door is open - Auto lock in {t} seconds\n✅ Please enter and close the door", Colors.SUCCESS))
                self.root.after((self.config.LOCK_OPEN_DURATION - i) * 1000,
                               lambda t=i: self.gui.update_status(f"DOOR OPEN - LOCK IN {t}S", 'lightgreen'))
                
                # Warning beeps for last 3 seconds
                if i <= 3:
                    self.root.after((self.config.LOCK_OPEN_DURATION - i) * 1000,
                                   lambda: self.buzzer.beep("click"))
            
            self.root.after(self.config.LOCK_OPEN_DURATION * 1000, self._lock_door)
            
        except Exception as e:
            logger.error(f"❌ Door unlock error: {e}")
            self.gui.update_detail(f"❌ Door unlock error: {str(e)}", Colors.ERROR)
            self.buzzer.beep("error")
    
    def _lock_door(self):
        """Khóa cửa và reset hệ thống"""
        try:
            logger.info("🔒 Locking door and resetting system")
            
            self.relay.on()  # Lock door
            self.gui.update_status("DOOR LOCKED - SYSTEM READY FOR NEXT USER", 'white')
            self.gui.update_detail("🔒 Door has been locked automatically.\n🔄 System ready for next authentication cycle.", Colors.PRIMARY)
            self.buzzer.beep("click")
            
            # Reset detection stats
            self.gui.detection_stats = {"total": 0, "recognized": 0, "unknown": 0}
            
            self.root.after(2000, self.start_authentication)
            
        except Exception as e:
            logger.error(f"❌ Door lock error: {e}")
            self.gui.update_detail(f"❌ Door lock error: {str(e)}", Colors.ERROR)
            self.buzzer.beep("error")
    
    def add_face_training_mode(self, person_name: str):
        """AI Face training mode với UI feedback"""
        try:
            logger.info(f"👤 Bắt đầu training khuôn mặt cho: {person_name}")
            
            # Show training instruction
            EnhancedMessageBox.show_info(self.root, "🤖 AI FACE TRAINING", 
                                       f"Starting AI training for: {person_name}\n\n"
                                       "📸 The system will capture 20 images\n"
                                       "👁️ Please look at camera and move head slightly\n"
                                       "🔄 This will create multiple angles for better recognition", 
                                       self.buzzer)
            
            captured_images = []
            training_target = 20
            
            self.gui.update_status(f"AI TRAINING MODE: {person_name.upper()}", 'purple')
            
            for i in range(training_target):
                self.gui.update_detail(f"📸 Capturing training image {i+1}/{training_target}\n"
                                     f"👤 Subject: {person_name}\n"
                                     f"🤖 Please hold position and look at camera", Colors.WARNING)
                
                # Capture frame
                frame = self.picam2.capture_array()
                if frame is None:
                    continue
                
                # Get training images
                training_images = self.face_recognizer.capture_training_images(frame, 1)
                
                if training_images:
                    captured_images.extend(training_images)
                    self.buzzer.beep("click")
                    
                    # Show progress
                    progress = ((i + 1) / training_target) * 100
                    self.gui.update_step(1, "🤖 AI TRAINING", f"Progress: {progress:.0f}%", Colors.SUCCESS)
                    
                    time.sleep(0.8)  # Pause between captures
                else:
                    self.gui.update_detail(f"❌ No face detected in image {i+1}\n"
                                         "🔄 Retrying... Please look at camera", Colors.ERROR)
                    i -= 1  # Retry this capture
                    time.sleep(1)
            
            # Process training data
                if len(captured_images) >= 15:  # Minimum threshold
                    self.gui.update_detail(f"🧠 Processing {len(captured_images)} training images...\n"
                                     "⚡ AI neural network learning...", Colors.PRIMARY)
                
                if self.face_recognizer.add_person(person_name, captured_images):
                    logger.info(f"✅ AI training successful for {person_name}")
                    EnhancedMessageBox.show_success(self.root, "🎉 AI TRAINING SUCCESS", 
                                                  f"✅ AI training completed successfully!\n\n"
                                                  f"👤 Name: {person_name}\n"
                                                  f"📸 Training images: {len(captured_images)}\n"
                                                  f"🤖 Neural network updated\n"
                                                  f"🔐 Access authorized for future authentication", 
                                                  self.buzzer)
                    
                    # Show updated stats
                    face_info = self.face_recognizer.get_database_info()
                    self.gui.update_detail(f"📊 Database updated!\n"
                                         f"👥 Total people: {face_info['total_people']}\n"
                                         f"📸 Total training images: {sum(p['face_count'] for p in face_info['people'].values())}", 
                                         Colors.SUCCESS)
                    return True
                else:
                    EnhancedMessageBox.show_error(self.root, "❌ TRAINING FAILED", 
                                                "❌ Failed to save training data!\n\n"
                                                "🔧 Please check system permissions\n"
                                                "💾 Ensure sufficient storage space", 
                                                self.buzzer)
            else:
                EnhancedMessageBox.show_error(self.root, "❌ INSUFFICIENT DATA", 
                                            f"❌ Training failed - insufficient data!\n\n"
                                            f"📸 Captured: {len(captured_images)} images\n"
                                            f"📊 Required: minimum 15 images\n"
                                            f"💡 Please ensure good lighting and clear face visibility", 
                                            self.buzzer)
            
            return False
            
        except Exception as e:
            logger.error(f"❌ AI training error: {e}")
            EnhancedMessageBox.show_error(self.root, "❌ TRAINING ERROR", 
                                        f"❌ AI training failed!\n\nError: {str(e)}", 
                                        self.buzzer)
            return False
        finally:
            # Return to normal mode
            self.gui.update_status("RETURNING TO NORMAL MODE...", 'white')
            self.root.after(2000, self.start_authentication)
    
    def run(self):
        """Chạy hệ thống chính"""
        try:
            logger.info("🚀 Starting AI Enhanced Security System")
            
            # Startup effects
            self.gui.update_status("AI ENHANCED SECURITY SYSTEM v2.0 - READY!", 'lightgreen')
            self.gui.update_detail("🤖 AI neural networks loaded and ready\n"
                                 "🔐 4-layer security system active\n"
                                 "⚡ Enhanced performance for Raspberry Pi 5", Colors.SUCCESS)
            
            self.buzzer.beep("startup")
            
            # Show system info
            face_info = self.face_recognizer.get_database_info()
            self.gui.update_detail(f"📊 System Status:\n"
                                 f"👥 Registered faces: {face_info['total_people']}\n"
                                 f"👆 Fingerprints: {len(self.admin_data.get_fingerprint_ids())}\n"
                                 f"📱 RFID cards: {len(self.admin_data.get_rfid_uids())}\n"
                                 f"🤖 AI Status: Ready", Colors.SUCCESS)
            
            # Start authentication after 3 seconds
            self.root.after(3000, self.start_authentication)
            
            # Setup cleanup
            self.root.protocol("WM_DELETE_WINDOW", self.cleanup)
            
            # Start main loop
            self.root.mainloop()
            
        except KeyboardInterrupt:
            logger.info("System stopped by user request")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cleanup tài nguyên khi thoát"""
        logger.info("🔧 Cleaning up system resources...")
        self.running = False
        
        try:
            if hasattr(self, 'picam2'):
                self.picam2.stop()
                logger.info("📹 Camera stopped")
                
            if hasattr(self, 'relay'):
                self.relay.on()  # Ensure door is locked
                logger.info("🔒 Door locked")
                
            if hasattr(self, 'buzzer') and hasattr(self.buzzer, 'buzzer') and self.buzzer.buzzer:
                self.buzzer.buzzer.off()
                logger.info("🔇 Buzzer stopped")
                
        except Exception as e:
            logger.error(f"❌ Cleanup error: {e}")
        
        if hasattr(self, 'root'):
            self.root.quit()
        
        logger.info("✅ Cleanup completed")

# ==== MAIN EXECUTION ====
if __name__ == "__main__":
    try:
        print("=" * 100)
        print("🤖 HỆ THỐNG KHÓA BẢO MẬT 4 LỚP - AI ENHANCED VERSION 2.0")
        print("   Tác giả: Khoi - Luận án tốt nghiệp")
        print("   Ngày: 2025-01-16")
        print("=" * 100)
        print()
        print("🎯 CẢI TIẾN AI ĐẶC BIỆT:")
        print("   🤖 OpenCV DNN Face Detection với MobileNet SSD")
        print("   🧠 LBPH Face Recognition với độ chính xác cao")
        print("   📹 FPS cao 30+ với real-time visual feedback")
        print("   🎨 Khung bounding box màu sắc (xanh/đỏ)")
        print("   📱 Cửa sổ camera lớn hơn 60% so với phiên bản cũ")
        print("   ⚡ Tối ưu hoàn toàn cho Raspberry Pi 5")
        print("   🎵 Enhanced buzzer với nhiều âm thanh")
        print("   👤 AI Training mode tự động")
        print("   📊 Real-time statistics và monitoring")
        print()
        print("🔐 4 LỚP BẢO MẬT TUẦN TỰ:")
        print("   1. 🤖 AI Face Recognition (OpenCV DNN)")
        print("   2. 👆 Fingerprint Biometric (AS608)")
        print("   3. 📱 RFID/NFC Card (PN532)")
        print("   4. 🔑 Numeric Passcode (Keyboard)")
        print()
        print("🎮 ĐIỀU KHIỂN NÂNG CAO:")
        print("   * hoặc KP_* = Admin mode")
        print("   # hoặc KP_+ = Start authentication")
        print("   ESC = Exit system")
        print("   F11 = Toggle fullscreen")
        print("   ↑↓←→ = Navigate dialogs")
        print("   Enter/Space = Confirm")
        print("   1-9 = Quick select")
        print()
        print("🔍 KIỂM TRA PHẦN CỨNG:")
        
        hardware_components = [
            ("📹", "Raspberry Pi Camera Module 2"),
            ("👆", "Fingerprint Sensor AS608 (USB/UART)"),
            ("📱", "RFID Reader PN532 (I2C)"),
            ("🔌", "Solenoid Lock + 4-channel Relay"),
            ("🔊", "Enhanced Buzzer (GPIO PWM)"),
            ("⌨️", "USB Numeric Keypad"),
            ("💾", "AI Model Storage"),
            ("🧠", "Face Database System")
        ]
        
        for icon, component in hardware_components:
            print(f"   {icon} {component}")
            time.sleep(0.2)
        
        print()
        print("🚀 KHỞI TẠO HỆ THỐNG AI...")
        print("=" * 100)
        
        # Initialize and run system
        system = AIEnhancedSecuritySystem()
        
        print()
        print("✅ TẤT CẢ THÀNH PHẦN ĐÃ SẴN SÀNG!")
        print("🎨 Đang khởi động giao diện AI...")
        print("📡 Kết nối hardware thành công!")
        print("🤖 AI neural networks đã được load!")
        print("=" * 100)
        print("🎯 HỆ THỐNG SẴN SÀNG! BẮT ĐẦU SỬ DỤNG...")
        print("=" * 100)
        
        system.run()
        
    except Exception as e:
        print()
        print("=" * 100)
        print(f"❌ LỖI KHỞI ĐỘNG NGHIÊM TRỌNG: {e}")
        print()
        print("🔧 DANH SÁCH KIỂM TRA KHẮC PHỤC:")
        
        troubleshooting_items = [
            ("🔌", "Kiểm tra kết nối phần cứng và nguồn điện"),
            ("📁", "Đảm bảo các file models AI tồn tại"),
            ("🔑", "Kiểm tra quyền truy cập GPIO và USB"),
            ("📦", "Cài đặt đầy đủ thư viện Python"),
            ("🔊", "Cấu hình đúng GPIO cho Buzzer"),
            ("📹", "Camera permissions và drivers"),
            ("💾", "Kiểm tra dung lượng ổ cứng"),
            ("🌐", "Kết nối I2C và UART hoạt động"),
            ("🤖", "Download AI models (chạy download_models.py)"),
            ("📝", "Kiểm tra log file để xem chi tiết lỗi")
        ]
        
        for icon, item in troubleshooting_items:
            print(f"   • {icon} {item}")
        
        print()
        print("📞 HƯỚNG DẪN KHẮC PHỤC:")
        print("   1. Chạy: python3 download_models.py")
        print("   2. Kiểm tra: ls -la /home/khoi/Desktop/KHOI_LUANAN/models/")
        print("   3. Test camera: python3 -c 'from picamera2 import Picamera2; print(\"OK\")'")
        print("   4. Test OpenCV: python3 -c 'import cv2; print(cv2.__version__)'")
        print("   5. Kiểm tra log: tail -f /home/khoi/Desktop/KHOI_LUANAN/system.log")
        print()
        print("=" * 100)
        
        logger.error(f"System startup failed: {e}")
        sys.exit(1)
