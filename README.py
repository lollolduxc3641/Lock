#!/usr/bin/env python3
"""
Hệ thống khóa bảo mật 4 lớp - Phiên bản tối ưu đơn giản
"""

import cv2
import face_recognition
import pickle
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
    sys.exit(1)

# ==== CONFIGURATION ====
@dataclass
class Config:
    # GPIO
    BUZZER_GPIO: int = 17
    RELAY_GPIO: int = 5
    
    # Files
    ENCODINGS_FILE: str = "/home/khoi/Desktop/Centek/encodings.pickle"
    ADMIN_DATA_FILE: str = "/home/khoi/Desktop/Centek/admin_data.json"
    
    # Face Recognition
    FACE_TOLERANCE: float = 0.3
    FACE_REQUIRED_CONSECUTIVE: int = 3
    FACE_DETECTION_INTERVAL: float = 0.05
    
    # Camera
    CAMERA_WIDTH: int = 640
    CAMERA_HEIGHT: int = 480
    
    # Admin
    ADMIN_UID: List[int] = None
    ADMIN_PASS: str = "0809"
    
    # Timing
    LOCK_OPEN_DURATION: int = 3
    MAX_ATTEMPTS: int = 5
    
    def __post_init__(self):
        if self.ADMIN_UID is None:
            self.ADMIN_UID = [0xe5, 0xa8, 0xbd, 0x2]

class AuthStep(Enum):
    FACE = "face"
    FINGERPRINT = "fingerprint"
    RFID = "rfid"
    PASSCODE = "passcode"
    ADMIN = "admin"

# ==== CLEAN COLOR SCHEME ====
class Colors:
    PRIMARY = "#1E88E5"      # Blue
    SUCCESS = "#43A047"      # Green  
    ERROR = "#F4511E"        # Orange
    WARNING = "#FB8C00"      # Amber
    BACKGROUND = "#F8F9FA"   # Light Gray
    CARD_BG = "#FFFFFF"      # White
    TEXT_PRIMARY = "#212121" # Dark Gray
    TEXT_SECONDARY = "#757575" # Medium Gray
    ACCENT = "#7B1FA2"       # Purple
    BORDER = "#E0E0E0"       # Light Border

# ==== LOGGING ====
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ==== SIMPLIFIED NUMPAD DIALOG ====
class CleanNumpadDialog:
    def __init__(self, parent, title, prompt, is_password=False):
        self.parent = parent
        self.title = title
        self.prompt = prompt
        self.is_password = is_password
        self.result = None
        self.input_text = ""
        self.selected_btn = None
        self.buttons = []
        
    def show(self) -> Optional[str]:
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title(self.title)
        self.dialog.geometry("480x600")
        self.dialog.configure(bg=Colors.BACKGROUND)
        self.dialog.resizable(False, False)
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        # Center dialog
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (240)
        y = (self.dialog.winfo_screenheight() // 2) - (300)
        self.dialog.geometry(f'480x600+{x}+{y}')
        
        self._create_widgets()
        self._setup_bindings()
        self._select_button(1, 1)
        
        self.dialog.wait_window()
        return self.result
    
    def _create_widgets(self):
        # Header - simplified
        header_frame = tk.Frame(self.dialog, bg=Colors.CARD_BG, relief=tk.RAISED, bd=2)
        header_frame.pack(fill=tk.X, padx=20, pady=20)
        
        tk.Label(header_frame, text=self.title, 
                font=('Arial', 26, 'bold'), fg=Colors.PRIMARY, bg=Colors.CARD_BG).pack(pady=20)
        
        if self.prompt:
            tk.Label(header_frame, text=self.prompt,
                    font=('Arial', 16), fg=Colors.TEXT_PRIMARY, bg=Colors.CARD_BG).pack(pady=(0,20))
        
        # Display
        display_frame = tk.Frame(self.dialog, bg=Colors.CARD_BG, relief=tk.RAISED, bd=2)
        display_frame.pack(fill=tk.X, padx=20, pady=(0,20))
        
        self.display_var = tk.StringVar()
        self.display_label = tk.Label(display_frame, textvariable=self.display_var,
                font=('Courier New', 32, 'bold'), fg=Colors.SUCCESS, bg=Colors.CARD_BG,
                height=2, width=12, relief=tk.SUNKEN, bd=2)
        self.display_label.pack(pady=20)
        
        # Numpad - clean design
        numpad_frame = tk.Frame(self.dialog, bg=Colors.CARD_BG, relief=tk.RAISED, bd=2)
        numpad_frame.pack(padx=20, pady=(0,20))
        
        grid_frame = tk.Frame(numpad_frame, bg=Colors.CARD_BG)
        grid_frame.pack(pady=20)
        
        buttons_config = [
            [('7', Colors.PRIMARY), ('8', Colors.PRIMARY), ('9', Colors.PRIMARY)],
            [('4', Colors.PRIMARY), ('5', Colors.PRIMARY), ('6', Colors.PRIMARY)],
            [('1', Colors.PRIMARY), ('2', Colors.PRIMARY), ('3', Colors.PRIMARY)],
            [('XÓA', Colors.ERROR), ('0', Colors.PRIMARY), ('CLR', Colors.WARNING)]
        ]
        
        self.button_widgets = {}
        
        for i, row in enumerate(buttons_config):
            for j, (text, color) in enumerate(row):
                btn = tk.Button(grid_frame, text=text, font=('Arial', 20, 'bold'),
                              bg=color, fg='white', width=5, height=2,
                              relief=tk.RAISED, bd=3,
                              command=lambda t=text: self._on_key_click(t))
                btn.grid(row=i, column=j, padx=6, pady=6)
                self.buttons.append(btn)
                self.button_widgets[(i, j)] = btn
        
        # Control buttons
        control_frame = tk.Frame(self.dialog, bg=Colors.BACKGROUND)
        control_frame.pack(pady=20)
        
        ok_btn = tk.Button(control_frame, text="XÁC NHẬN", font=('Arial', 18, 'bold'),
                 bg=Colors.SUCCESS, fg='white', width=12, height=2,
                 relief=tk.RAISED, bd=3,
                 command=self._on_ok)
        ok_btn.pack(side=tk.LEFT, padx=15)
        
        cancel_btn = tk.Button(control_frame, text="HỦY BỎ", font=('Arial', 18, 'bold'),
                 bg=Colors.ACCENT, fg='white', width=12, height=2,
                 relief=tk.RAISED, bd=3,
                 command=self._on_cancel)
        cancel_btn.pack(side=tk.RIGHT, padx=15)
        
        self.buttons.extend([ok_btn, cancel_btn])
        
        self._update_display()
    
    def _setup_bindings(self):
        # Number keys
        for i in range(10):
            self.dialog.bind(str(i), lambda e, key=str(i): self._on_key_click(key))
        
        # Special keys
        self.dialog.bind('<Return>', lambda e: self._on_ok())
        self.dialog.bind('<KP_Enter>', lambda e: self._on_ok())
        self.dialog.bind('<Escape>', lambda e: self._on_cancel())
        self.dialog.bind('<BackSpace>', lambda e: self._on_key_click('XÓA'))
        self.dialog.bind('<Delete>', lambda e: self._on_key_click('CLR'))
        
        # Navigation
        self.dialog.bind('<Up>', lambda e: self._navigate(-1, 0))
        self.dialog.bind('<Down>', lambda e: self._navigate(1, 0))
        self.dialog.bind('<Left>', lambda e: self._navigate(0, -1))
        self.dialog.bind('<Right>', lambda e: self._navigate(0, 1))
        self.dialog.bind('<space>', lambda e: self._activate_selected())
        
        self.dialog.focus_set()
    
    def _navigate(self, row_delta, col_delta):
        if not hasattr(self, 'current_row'):
            self.current_row, self.current_col = 1, 1
        
        new_row = max(0, min(3, self.current_row + row_delta))
        new_col = max(0, min(2, self.current_col + col_delta))
        
        self._select_button(new_row, new_col)
    
    def _select_button(self, row, col):
        # Clear previous selection
        for btn in self.buttons[:12]:
            btn.config(relief=tk.RAISED, bd=3)
        
        # Highlight new selection
        if (row, col) in self.button_widgets:
            btn = self.button_widgets[(row, col)]
            btn.config(relief=tk.SUNKEN, bd=5)
            self.current_row, self.current_col = row, col
    
    def _activate_selected(self):
        if hasattr(self, 'current_row') and hasattr(self, 'current_col'):
            if (self.current_row, self.current_col) in self.button_widgets:
                btn = self.button_widgets[(self.current_row, self.current_col)]
                btn.invoke()
    
    def _on_key_click(self, key):
        if key.isdigit():
            self.input_text += key
        elif key == 'XÓA' and self.input_text:
            self.input_text = self.input_text[:-1]
        elif key == 'CLR':
            self.input_text = ""
        self._update_display()
    
    def _update_display(self):
        if self.is_password:
            display = '●' * len(self.input_text)
        else:
            display = self.input_text
        
        if len(display) == 0:
            display = "___"
        
        self.display_var.set(display)
        
        # Color feedback
        if len(self.input_text) >= 4:
            self.display_label.config(fg=Colors.SUCCESS)
        elif len(self.input_text) > 0:
            self.display_label.config(fg=Colors.WARNING)
        else:
            self.display_label.config(fg=Colors.TEXT_SECONDARY)
    
    def _on_ok(self):
        if len(self.input_text) >= 1:
            self.result = self.input_text
            self.dialog.destroy()
    
    def _on_cancel(self):
        self.result = None
        self.dialog.destroy()

# ==== SIMPLIFIED MESSAGE BOX ====
class CleanMessageBox:
    @staticmethod
    def show_info(parent, title, message):
        return CleanMessageBox._show(parent, title, message, "info", ["OK"])
    
    @staticmethod
    def show_error(parent, title, message):
        return CleanMessageBox._show(parent, title, message, "error", ["OK"])
    
    @staticmethod
    def show_success(parent, title, message):
        return CleanMessageBox._show(parent, title, message, "success", ["OK"])
    
    @staticmethod
    def ask_yesno(parent, title, message):
        return CleanMessageBox._show(parent, title, message, "question", ["CÓ", "KHÔNG"]) == "CÓ"
    
    @staticmethod
    def _show(parent, title, message, msg_type, buttons):
        dialog = tk.Toplevel(parent)
        dialog.title(title)
        dialog.geometry("500x350")
        dialog.configure(bg=Colors.BACKGROUND)
        dialog.transient(parent)
        dialog.grab_set()
        
        # Center
        x = (dialog.winfo_screenwidth() // 2) - (250)
        y = (dialog.winfo_screenheight() // 2) - (175)
        dialog.geometry(f'500x350+{x}+{y}')
        
        result = [None]
        selected = [0]
        
        # Main card
        card = tk.Frame(dialog, bg=Colors.CARD_BG, relief=tk.RAISED, bd=3)
        card.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Colors for different types
        colors = {
            "info": Colors.PRIMARY,
            "error": Colors.ERROR, 
            "success": Colors.SUCCESS,
            "question": Colors.WARNING
        }
        color = colors.get(msg_type, Colors.PRIMARY)
        
        # Header
        header_frame = tk.Frame(card, bg=Colors.CARD_BG)
        header_frame.pack(fill=tk.X, pady=25)
        
        tk.Label(header_frame, text=title, font=('Arial', 22, 'bold'),
                fg=color, bg=Colors.CARD_BG).pack()
        
        # Message
        tk.Label(card, text=message, font=('Arial', 16),
                fg=Colors.TEXT_PRIMARY, bg=Colors.CARD_BG, 
                wraplength=420, justify=tk.CENTER).pack(pady=30)
        
        # Buttons
        btn_frame = tk.Frame(card, bg=Colors.CARD_BG)
        btn_frame.pack(pady=25)
        
        btn_widgets = []
        btn_colors = [Colors.SUCCESS, Colors.ERROR]
        
        for i, btn_text in enumerate(buttons):
            bg_color = btn_colors[i] if i < len(btn_colors) else Colors.PRIMARY
            btn = tk.Button(btn_frame, text=btn_text, font=('Arial', 16, 'bold'),
                          bg=bg_color, fg='white', width=10, height=2,
                          relief=tk.RAISED, bd=3,
                          command=lambda t=btn_text, idx=i: [result.__setitem__(0, t), dialog.destroy()])
            btn.pack(side=tk.LEFT, padx=15)
            btn_widgets.append(btn)
            
            # Number key bindings
            dialog.bind(str(i+1), lambda e, t=btn_text: [result.__setitem__(0, t), dialog.destroy()])
        
        # Navigation
        def select_button(idx):
            for j, btn in enumerate(btn_widgets):
                if j == idx:
                    btn.config(relief=tk.SUNKEN, bd=5)
                else:
                    btn.config(relief=tk.RAISED, bd=3)
            selected[0] = idx
        
        def navigate_buttons(direction):
            new_idx = (selected[0] + direction) % len(btn_widgets)
            select_button(new_idx)
        
        select_button(0)
        
        dialog.bind('<Left>', lambda e: navigate_buttons(-1))
        dialog.bind('<Right>', lambda e: navigate_buttons(1))
        dialog.bind('<Return>', lambda e: btn_widgets[selected[0]].invoke())
        dialog.bind('<KP_Enter>', lambda e: btn_widgets[selected[0]].invoke())
        dialog.bind('<Escape>', lambda e: dialog.destroy())
        dialog.bind('<space>', lambda e: btn_widgets[selected[0]].invoke())
        
        dialog.focus_set()
        dialog.wait_window()
        return result[0]

# ==== ADMIN DATA MANAGER (UNCHANGED) ====
class AdminDataManager:
    def __init__(self, config: Config):
        self.config = config
        self.data = self._load_data()
    
    def _load_data(self):
        default_data = {
            "system_passcode": "1234",
            "valid_rfid_uids": [[0x1b, 0x93, 0xf2, 0x3c]],
            "fingerprint_ids": [1, 2, 3]
        }
        
        try:
            if os.path.exists(self.config.ADMIN_DATA_FILE):
                with open(self.config.ADMIN_DATA_FILE, 'r') as f:
                    data = json.load(f)
                    for key, value in default_data.items():
                        if key not in data:
                            data[key] = value
                    return data
            else:
                self._save_data(default_data)
                return default_data
        except:
            return default_data
    
    def _save_data(self, data=None):
        try:
            if data is None:
                data = self.data
            with open(self.config.ADMIN_DATA_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except:
            return False
    
    def get_passcode(self):
        return self.data["system_passcode"]
    
    def set_passcode(self, new_passcode):
        self.data["system_passcode"] = new_passcode
        return self._save_data()
    
    def get_rfid_uids(self):
        return self.data["valid_rfid_uids"].copy()
    
    def add_rfid(self, uid_list):
        if uid_list not in self.data["valid_rfid_uids"]:
            self.data["valid_rfid_uids"].append(uid_list)
            return self._save_data()
        return False
    
    def remove_rfid(self, uid_list):
        if uid_list in self.data["valid_rfid_uids"]:
            self.data["valid_rfid_uids"].remove(uid_list)
            return self._save_data()
        return False
    
    def get_fingerprint_ids(self):
        return self.data["fingerprint_ids"].copy()
    
    def add_fingerprint_id(self, fp_id):
        if fp_id not in self.data["fingerprint_ids"]:
            self.data["fingerprint_ids"].append(fp_id)
            return self._save_data()
        return False
    
    def remove_fingerprint_id(self, fp_id):
        if fp_id in self.data["fingerprint_ids"]:
            self.data["fingerprint_ids"].remove(fp_id)
            return self._save_data()
        return False

# ==== HARDWARE MANAGERS (UNCHANGED) ====
class BuzzerManager:
    def __init__(self, gpio_pin: int):
        self.buzzer = PWMOutputDevice(gpio_pin)
        self.buzzer.off()
    
    def beep(self, pattern: str):
        patterns = {
            "success": [(2000, 0.5, 0.2)] * 2,
            "error": [(200, 0.8, 0.5)],
            "click": [(1000, 0.3, 0.1)]
        }
        
        if pattern in patterns:
            try:
                for freq, volume, duration in patterns[pattern]:
                    self.buzzer.frequency = freq
                    self.buzzer.value = volume
                    time.sleep(duration)
                    self.buzzer.off()
                    time.sleep(0.1)
            except:
                pass

class FaceRecognition:
    def __init__(self, encodings_file: str, tolerance: float = 0.3):
        self.encodings_file = encodings_file
        self.tolerance = tolerance
        self.face_data = None
        self._load_encodings()
    
    def _load_encodings(self):
        try:
            with open(self.encodings_file, "rb") as f:
                self.face_data = pickle.load(f)
        except Exception as e:
            logger.error(f"Lỗi load encodings: {e}")
            raise
    
    def recognize(self, frame):
        try:
            small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
            rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
            
            face_locations = face_recognition.face_locations(rgb_small)
            if len(face_locations) == 0:
                return {"recognized": False, "message": "Không phát hiện khuôn mặt"}
            
            face_encodings = face_recognition.face_encodings(rgb_small, face_locations)
            
            for face_encoding in face_encodings:
                matches = face_recognition.compare_faces(
                    self.face_data["encodings"], face_encoding, tolerance=self.tolerance)
                
                if True in matches:
                    return {"recognized": True, "message": "Nhận diện thành công"}
            
            return {"recognized": False, "message": "Khuôn mặt không khớp"}
            
        except Exception as e:
            return {"recognized": False, "message": f"Lỗi: {str(e)}"}

# ==== CLEAN 2-COLUMN GUI ====
class CleanSecurityGUI:
    def __init__(self, root):
        self.root = root
        self._setup_window()
        self._create_widgets()
        self._setup_bindings()
    
    def _setup_window(self):
        self.root.title("HỆ THỐNG KHÓA BẢO MẬT 4 LỚP")
        self.root.geometry("1024x600")
        self.root.configure(bg=Colors.BACKGROUND)
        self.root.attributes('-fullscreen', False)  # Change to True for deployment
        self.root.minsize(800, 480)
    
    def _create_widgets(self):
        # Main container
        main_container = tk.Frame(self.root, bg=Colors.BACKGROUND)
        main_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # Configure grid
        main_container.grid_columnconfigure(0, weight=1)  # Camera
        main_container.grid_columnconfigure(1, weight=1)  # Status  
        main_container.grid_rowconfigure(0, weight=1)
        
        # LEFT COLUMN - CAMERA
        self._create_camera_panel(main_container)
        
        # RIGHT COLUMN - STATUS
        self._create_status_panel(main_container)
        
        # BOTTOM - MAIN STATUS
        self._create_bottom_status()
    
    def _create_camera_panel(self, parent):
        # Camera panel
        camera_panel = tk.Frame(parent, bg=Colors.CARD_BG, relief=tk.RAISED, bd=3)
        camera_panel.grid(row=0, column=0, padx=(0,8), pady=0, sticky="nsew")
        
        # Camera header
        cam_header = tk.Frame(camera_panel, bg=Colors.PRIMARY, height=70)
        cam_header.pack(fill=tk.X, padx=4, pady=4)
        cam_header.pack_propagate(False)
        
        tk.Label(cam_header, text="CAMERA NHẬN DIỆN", 
                font=('Arial', 22, 'bold'), fg='white', bg=Colors.PRIMARY).pack(expand=True)
        
        # Camera display
        self.camera_frame = tk.Frame(camera_panel, bg='black', relief=tk.SUNKEN, bd=2)
        self.camera_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        
        self.camera_label = tk.Label(self.camera_frame, 
                                    text="Đang khởi động camera...",
                                    font=('Arial', 18), fg='white', bg='black')
        self.camera_label.pack(expand=True)
        
        # Camera status
        self.camera_status = tk.Label(camera_panel, text="Camera sẵn sàng",
                                     font=('Arial', 16, 'bold'), 
                                     fg=Colors.SUCCESS, bg=Colors.CARD_BG)
        self.camera_status.pack(pady=8)
    
    def _create_status_panel(self, parent):
        # Status panel
        status_panel = tk.Frame(parent, bg=Colors.CARD_BG, relief=tk.RAISED, bd=3)
        status_panel.grid(row=0, column=1, padx=(8,0), pady=0, sticky="nsew")
        
        # Status header
        status_header = tk.Frame(status_panel, bg=Colors.SUCCESS, height=70)
        status_header.pack(fill=tk.X, padx=4, pady=4)
        status_header.pack_propagate(False)
        
        tk.Label(status_header, text="TRẠNG THÁI HỆ THỐNG", 
                font=('Arial', 22, 'bold'), fg='white', bg=Colors.SUCCESS).pack(expand=True)
        
        # Current step display - LARGER TEXT
        self.step_frame = tk.Frame(status_panel, bg=Colors.CARD_BG)
        self.step_frame.pack(fill=tk.X, padx=20, pady=20)
        
        self.step_number = tk.Label(self.step_frame, text="1", 
                                   font=('Arial', 48, 'bold'),  # Much larger
                                   fg='white', bg=Colors.PRIMARY,
                                   width=2, height=1, relief=tk.RAISED, bd=3)
        self.step_number.pack(side=tk.LEFT, padx=(0,20))
        
        step_info_frame = tk.Frame(self.step_frame, bg=Colors.CARD_BG)
        step_info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.step_title = tk.Label(step_info_frame, text="NHẬN DIỆN KHUÔN MẶT",
                                  font=('Arial', 24, 'bold'),  # Larger font
                                  fg=Colors.TEXT_PRIMARY, bg=Colors.CARD_BG,
                                  anchor='w')
        self.step_title.pack(fill=tk.X)
        
        self.step_subtitle = tk.Label(step_info_frame, text="Nhìn vào camera để xác thực",
                                     font=('Arial', 16),  # Larger font
                                     fg=Colors.TEXT_SECONDARY, bg=Colors.CARD_BG,
                                     anchor='w')
        self.step_subtitle.pack(fill=tk.X)
        
        # Progress indicators - SIMPLIFIED & LARGER
        self._create_progress_indicators(status_panel)
        
        # Status message
        self._create_status_message(status_panel)
        
        # Time display
        self._create_time_display(status_panel)
    
    def _create_progress_indicators(self, parent):
        # Progress section - cleaner design
        progress_frame = tk.Frame(parent, bg=Colors.CARD_BG)
        progress_frame.pack(fill=tk.X, padx=20, pady=15)
        
        tk.Label(progress_frame, text="TIẾN TRÌNH XÁC THỰC",
                font=('Arial', 18, 'bold'),  # Larger font
                fg=Colors.TEXT_PRIMARY, bg=Colors.CARD_BG).pack(anchor='w')
        
        # Step indicators - LARGER TEXT, NO ICONS
        steps_frame = tk.Frame(progress_frame, bg=Colors.CARD_BG)
        steps_frame.pack(fill=tk.X, pady=15)
        
        self.step_indicators = {}
        steps = [
            ("1", "KHUÔN MẶT"),
            ("2", "VÂN TAY"), 
            ("3", "THẺ RFID"),
            ("4", "MẬT KHẨU")
        ]
        
        for i, (num, name) in enumerate(steps):
            step_container = tk.Frame(steps_frame, bg=Colors.CARD_BG)
            step_container.pack(fill=tk.X, pady=4)
            
            # Step circle - larger
            circle = tk.Label(step_container, text=num,
                             font=('Arial', 18, 'bold'),  # Larger font
                             fg='white', bg=Colors.TEXT_SECONDARY,
                             width=3, height=1, relief=tk.RAISED, bd=2)
            circle.pack(side=tk.LEFT, padx=(0,15))
            
            # Step name - larger, no icons
            step_label = tk.Label(step_container, text=name,
                                 font=('Arial', 16, 'bold'),  # Larger font
                                 fg=Colors.TEXT_PRIMARY, bg=Colors.CARD_BG,
                                 anchor='w')
            step_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            self.step_indicators[i+1] = {
                'circle': circle,
                'label': step_label,
                'container': step_container
            }
    
    def _create_status_message(self, parent):
        # Status message - simplified
        msg_frame = tk.Frame(parent, bg=Colors.BACKGROUND, relief=tk.SUNKEN, bd=2)
        msg_frame.pack(fill=tk.X, padx=20, pady=15)
        
        tk.Label(msg_frame, text="CHI TIẾT",
                font=('Arial', 14, 'bold'),
                fg=Colors.TEXT_PRIMARY, bg=Colors.BACKGROUND).pack(anchor='w', padx=15, pady=(15,5))
        
        self.detail_message = tk.Label(msg_frame, text="Hệ thống đang sẵn sàng...",
                                      font=('Arial', 14),  # Larger font
                                      fg=Colors.TEXT_SECONDARY, bg=Colors.BACKGROUND,
                                      wraplength=350, justify=tk.LEFT, anchor='w')
        self.detail_message.pack(fill=tk.X, padx=15, pady=(0,15))
    
    def _create_time_display(self, parent):
        # Time display at bottom
        time_frame = tk.Frame(parent, bg=Colors.CARD_BG)
        time_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=20, pady=15)
        
        self.time_label = tk.Label(time_frame, text="",
                                  font=('Arial', 14),
                                  fg=Colors.TEXT_SECONDARY, bg=Colors.CARD_BG)
        self.time_label.pack()
        
        self._update_time()
    
    def _create_bottom_status(self):
        # Bottom status bar - simplified
        status_bar = tk.Frame(self.root, bg=Colors.PRIMARY, height=80)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=15, pady=(0,15))
        status_bar.pack_propagate(False)
        
        self.main_status = tk.Label(status_bar, 
                                   text="HỆ THỐNG SẴN SÀNG - ĐỢI XÁC THỰC",
                                   font=('Arial', 18, 'bold'),  # Larger font
                                   fg='white', bg=Colors.PRIMARY)
        self.main_status.pack(expand=True)
    
    def _setup_bindings(self):
        self.root.bind('<Key>', self._on_key)
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
            if CleanMessageBox.ask_yesno(self.root, "Thoát hệ thống", 
                                        "Bạn có chắc chắn muốn thoát khỏi hệ thống không?"):
                self.root.quit()
    
    def _update_time(self):
        current_time = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
        self.time_label.config(text=current_time)
        self.root.after(1000, self._update_time)
    
    def update_step(self, step_num, title, subtitle, color=None):
        """Update current step display"""
        if color is None:
            color = Colors.PRIMARY
            
        # Update main step display
        self.step_number.config(text=str(step_num), bg=color)
        self.step_title.config(text=title)
        self.step_subtitle.config(text=subtitle)
        
        # Update progress indicators
        for i in range(1, 5):
            indicator = self.step_indicators[i]
            if i < step_num:
                # Completed step
                indicator['circle'].config(bg=Colors.SUCCESS, fg='white')
                indicator['label'].config(fg=Colors.TEXT_PRIMARY, font=('Arial', 16, 'bold'))
            elif i == step_num:
                # Current step
                indicator['circle'].config(bg=color, fg='white')
                indicator['label'].config(fg=Colors.TEXT_PRIMARY, font=('Arial', 16, 'bold'))
            else:
                # Future step
                indicator['circle'].config(bg=Colors.TEXT_SECONDARY, fg='white')
                indicator['label'].config(fg=Colors.TEXT_SECONDARY, font=('Arial', 16))
    
    def update_status(self, message, color=None):
        """Update main status bar"""
        if color is None:
            color = 'white'
        self.main_status.config(text=message, fg=color)
    
    def update_detail(self, message, color=None):
        """Update detailed message"""
        if color is None:
            color = Colors.TEXT_SECONDARY
        self.detail_message.config(text=message, fg=color)
    
    def update_camera_status(self, status, color=None):
        """Update camera status"""
        if color is None:
            color = Colors.SUCCESS
        self.camera_status.config(text=status, fg=color)
    
    def update_camera(self, frame):
        """Update camera display"""
        try:
            # Resize for display
            height, width = frame.shape[:2]
            display_height = 320
            display_width = int(width * display_height / height)
            
            img = cv2.resize(frame, (display_width, display_height))
            rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img_pil = Image.fromarray(rgb_img)
            img_tk = ImageTk.PhotoImage(img_pil)
            
            self.camera_label.config(image=img_tk, text="")
            self.camera_label.image = img_tk
        except Exception as e:
            logger.error(f"Error updating camera: {e}")
    
    def set_system_reference(self, system):
        self.system_ref = system

# ==== CLEAN ADMIN GUI ====
class CleanAdminGUI:
    def __init__(self, parent, system):
        self.parent = parent
        self.system = system
        self.admin_window = None
        self.selected = 0
        self.options = [
            ("Đổi mật khẩu hệ thống"),
            ("Thêm thẻ RFID mới"), 
            ("Xóa thẻ RFID"),
            ("Đăng ký vân tay"),
            ("Xóa vân tay"),
            ("Thoát chế độ admin")
        ]
    
    def show_admin_panel(self):
        if self.admin_window:
            return
            
        self.admin_window = tk.Toplevel(self.parent)
        self.admin_window.title("QUẢN TRỊ HỆ THỐNG")
        self.admin_window.geometry("650x550")
        self.admin_window.configure(bg=Colors.BACKGROUND)
        self.admin_window.transient(self.parent)
        self.admin_window.grab_set()
        
        # Center
        x = (self.admin_window.winfo_screenwidth() // 2) - (325)
        y = (self.admin_window.winfo_screenheight() // 2) - (275)
        self.admin_window.geometry(f'650x550+{x}+{y}')
        
        self._create_widgets()
        self._setup_bindings()
        self._update_selection()
    
    def _create_widgets(self):
        # Header
        header_card = tk.Frame(self.admin_window, bg=Colors.CARD_BG, relief=tk.RAISED, bd=3)
        header_card.pack(fill=tk.X, padx=20, pady=20)
        
        tk.Label(header_card, text="BẢNG ĐIỀU KHIỂN ADMIN",
                font=('Arial', 26, 'bold'), fg=Colors.PRIMARY, bg=Colors.CARD_BG).pack(pady=25)
        
        # Menu
        menu_card = tk.Frame(self.admin_window, bg=Colors.CARD_BG, relief=tk.RAISED, bd=3)
        menu_card.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0,20))
        
        self.menu_frame = tk.Frame(menu_card, bg=Colors.CARD_BG)
        self.menu_frame.pack(expand=True, pady=30)
        
        self.buttons = []
        colors = [Colors.WARNING, Colors.SUCCESS, Colors.ERROR, Colors.PRIMARY, Colors.ACCENT, Colors.TEXT_SECONDARY]
        
        for i, option in enumerate(self.options):
            btn_frame = tk.Frame(self.menu_frame, bg=Colors.CARD_BG)
            btn_frame.pack(fill=tk.X, pady=6, padx=25)
            
            btn = tk.Button(btn_frame, text=f"{i+1}. {option}",
                           font=('Arial', 18, 'bold'), width=30, height=2,  # Larger font
                           bg=colors[i], fg='white', relief=tk.RAISED, bd=3,
                           anchor='w',
                           command=lambda idx=i: self._select_option(idx))
            btn.pack(fill=tk.X)
            self.buttons.append(btn)
    
    def _setup_bindings(self):
        for i in range(6):
            self.admin_window.bind(str(i+1), lambda e, idx=i: self._select_option(idx))
        
        self.admin_window.bind('<Return>', lambda e: self._confirm())
        self.admin_window.bind('<KP_Enter>', lambda e: self._confirm())
        self.admin_window.bind('<Escape>', lambda e: self._close())
        self.admin_window.bind('<Up>', lambda e: self._navigate(-1))
        self.admin_window.bind('<Down>', lambda e: self._navigate(1))
        self.admin_window.bind('<space>', lambda e: self._confirm())
        self.admin_window.focus_set()
    
    def _navigate(self, direction):
        self.selected = (self.selected + direction) % len(self.options)
        self._update_selection()
    
    def _select_option(self, idx):
        self.selected = idx
        self._update_selection()
        self.admin_window.after(200, self._confirm)
    
    def _update_selection(self):
        for i, btn in enumerate(self.buttons):
            if i == self.selected:
                btn.config(relief=tk.SUNKEN, bd=5)
            else:
                btn.config(relief=tk.RAISED, bd=3)
    
    def _confirm(self):
        actions = [
            self._change_passcode,
            self._add_rfid,
            self._remove_rfid, 
            self._add_fingerprint,
            self._remove_fingerprint,
            self._close
        ]
        
        if 0 <= self.selected < len(actions):
            actions[self.selected]()
    
    def _change_passcode(self):
        dialog = CleanNumpadDialog(self.admin_window, "Đổi mật khẩu", 
                                   "Nhập mật khẩu mới (4-8 số):", True)
        new_pass = dialog.show()
        if new_pass and 4 <= len(new_pass) <= 8:
            if self.system.admin_data.set_passcode(new_pass):
                CleanMessageBox.show_success(self.admin_window, "Thành công", 
                                            f"Đã cập nhật mật khẩu hệ thống!\nMật khẩu mới: {new_pass}")
            else:
                CleanMessageBox.show_error(self.admin_window, "Lỗi", 
                                          "Không thể lưu mật khẩu! Vui lòng thử lại.")
        elif new_pass:
            CleanMessageBox.show_error(self.admin_window, "Lỗi", 
                                      "Mật khẩu phải có từ 4-8 chữ số!")
    
    def _add_rfid(self):
        CleanMessageBox.show_info(self.admin_window, "Thêm thẻ RFID", 
                                 "Vui lòng đặt thẻ RFID lên đầu đọc trong 10 giây...")
        
        def scan():
            try:
                uid = self.system.pn532.read_passive_target(timeout=10)
                if uid:
                    uid_list = list(uid)
                    if self.system.admin_data.add_rfid(uid_list):
                        self.admin_window.after(0, lambda: CleanMessageBox.show_success(
                            self.admin_window, "Thành công", 
                            f"Đã thêm thẻ RFID thành công!\nUID: {uid_list}"))
                    else:
                        self.admin_window.after(0, lambda: CleanMessageBox.show_error(
                            self.admin_window, "Lỗi", 
                            f"Thẻ đã tồn tại trong hệ thống!\nUID: {uid_list}"))
                else:
                    self.admin_window.after(0, lambda: CleanMessageBox.show_error(
                        self.admin_window, "Lỗi", 
                        "Không phát hiện thẻ RFID!\nVui lòng thử lại."))
            except Exception as e:
                self.admin_window.after(0, lambda: CleanMessageBox.show_error(
                    self.admin_window, "Lỗi", f"Lỗi đọc thẻ: {str(e)}"))
        
        threading.Thread(target=scan, daemon=True).start()
    
    def _remove_rfid(self):
        uids = self.system.admin_data.get_rfid_uids()
        if not uids:
            CleanMessageBox.show_info(self.admin_window, "Thông báo", 
                                     "Không có thẻ RFID nào trong hệ thống!")
            return
        
        self._show_rfid_selection(uids)
    
    def _show_rfid_selection(self, uids):
        sel_window = tk.Toplevel(self.admin_window)
        sel_window.title("Chọn thẻ cần xóa")
        sel_window.geometry("450x400")
        sel_window.configure(bg=Colors.BACKGROUND)
        sel_window.transient(self.admin_window)
        sel_window.grab_set()
        
        # Center
        x = (sel_window.winfo_screenwidth() // 2) - (225)
        y = (sel_window.winfo_screenheight() // 2) - (200)
        sel_window.geometry(f'450x400+{x}+{y}')
        
        # Header
        header = tk.Frame(sel_window, bg=Colors.CARD_BG, relief=tk.RAISED, bd=2)
        header.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(header, text="Chọn thẻ RFID cần xóa",
                font=('Arial', 20, 'bold'), fg=Colors.ERROR, bg=Colors.CARD_BG).pack(pady=20)
        
        # List
        list_frame = tk.Frame(sel_window, bg=Colors.CARD_BG, relief=tk.RAISED, bd=2)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,10))
        
        for i, uid in enumerate(uids):
            btn = tk.Button(list_frame, text=f"{i+1}. {uid}",
                           font=('Arial', 16), width=35, height=2,  # Larger font
                           bg=Colors.ERROR, fg='white', relief=tk.RAISED, bd=2,
                           command=lambda u=uid: self._do_remove_rfid(u, sel_window))
            btn.pack(pady=8, padx=20)
            
            sel_window.bind(str(i+1), lambda e, u=uid: self._do_remove_rfid(u, sel_window))
        
        # Cancel button
        tk.Button(sel_window, text="Hủy bỏ", font=('Arial', 16, 'bold'),
                 bg=Colors.TEXT_SECONDARY, fg='white', width=15,
                 command=sel_window.destroy).pack(pady=15)
        
        sel_window.focus_set()
    
    def _do_remove_rfid(self, uid, window):
        if CleanMessageBox.ask_yesno(window, "Xác nhận xóa", 
                                    f"Bạn có chắc chắn muốn xóa thẻ này?\nUID: {uid}"):
            if self.system.admin_data.remove_rfid(uid):
                CleanMessageBox.show_success(self.admin_window, "Thành công", 
                                            f"Đã xóa thẻ RFID!\nUID: {uid}")
            else:
                CleanMessageBox.show_error(self.admin_window, "Lỗi", 
                                          "Không thể xóa thẻ! Vui lòng thử lại.")
        window.destroy()
    
    def _add_fingerprint(self):
        CleanMessageBox.show_info(self.admin_window, "Đăng ký vân tay", 
                                 "Chuẩn bị đăng ký vân tay mới...\nVui lòng làm theo hướng dẫn.")
        
        def enroll():
            try:
                # Find empty position
                pos = None
                for i in range(1, 200):
                    try:
                        self.system.fingerprint.loadTemplate(i, 0x01)
                    except:
                        pos = i
                        break
                
                if pos is None:
                    self.admin_window.after(0, lambda: CleanMessageBox.show_error(
                        self.admin_window, "Lỗi", "Bộ nhớ vân tay đã đầy!"))
                    return
                
                # Step 1
                self.admin_window.after(0, lambda: CleanMessageBox.show_info(
                    self.admin_window, "Bước 1/2", "Đặt ngón tay lần đầu tiên..."))
                
                while not self.system.fingerprint.readImage():
                    time.sleep(0.1)
                self.system.fingerprint.convertImage(0x01)
                
                # Step 2
                self.admin_window.after(0, lambda: CleanMessageBox.show_info(
                    self.admin_window, "Bước 2/2", "Nhấc tay rồi đặt lại ngón tay..."))
                
                while self.system.fingerprint.readImage():
                    time.sleep(0.1)
                while not self.system.fingerprint.readImage():
                    time.sleep(0.1)
                self.system.fingerprint.convertImage(0x02)
                
                # Create and store
                self.system.fingerprint.createTemplate()
                self.system.fingerprint.storeTemplate(pos, 0x01)
                
                self.system.admin_data.add_fingerprint_id(pos)
                
                self.admin_window.after(0, lambda: CleanMessageBox.show_success(
                    self.admin_window, "Thành công", 
                    f"Đã đăng ký vân tay thành công!\nVị trí lưu: {pos}"))
                
            except Exception as e:
                self.admin_window.after(0, lambda: CleanMessageBox.show_error(
                    self.admin_window, "Lỗi", f"Lỗi đăng ký vân tay: {str(e)}"))
        
        threading.Thread(target=enroll, daemon=True).start()
    
    def _remove_fingerprint(self):
        fp_ids = self.system.admin_data.get_fingerprint_ids()
        if not fp_ids:
            CleanMessageBox.show_info(self.admin_window, "Thông báo", 
                                     "Không có vân tay nào trong hệ thống!")
            return
        
        self._show_fingerprint_selection(fp_ids)
    
    def _show_fingerprint_selection(self, fp_ids):
        sel_window = tk.Toplevel(self.admin_window)
        sel_window.title("Chọn vân tay cần xóa")
        sel_window.geometry("400x450")
        sel_window.configure(bg=Colors.BACKGROUND)
        sel_window.transient(self.admin_window)
        sel_window.grab_set()
        
        # Center
        x = (sel_window.winfo_screenwidth() // 2) - (200)
        y = (sel_window.winfo_screenheight() // 2) - (225)
        sel_window.geometry(f'400x450+{x}+{y}')
        
        # Header
        header = tk.Frame(sel_window, bg=Colors.CARD_BG, relief=tk.RAISED, bd=2)
        header.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(header, text="Chọn vân tay cần xóa",
                font=('Arial', 20, 'bold'), fg=Colors.ERROR, bg=Colors.CARD_BG).pack(pady=20)
        
        # List
        list_frame = tk.Frame(sel_window, bg=Colors.CARD_BG, relief=tk.RAISED, bd=2)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,10))
        
        for i, fp_id in enumerate(fp_ids):
            btn = tk.Button(list_frame, text=f"{i+1}. Vân tay ID: {fp_id}",
                           font=('Arial', 16), width=20, height=2,  # Larger font
                           bg=Colors.ERROR, fg='white',
                           command=lambda fid=fp_id: self._do_remove_fingerprint(fid, sel_window))
            btn.pack(pady=8, padx=20)
            
            sel_window.bind(str(i+1), lambda e, fid=fp_id: self._do_remove_fingerprint(fid, sel_window))
        
        # Cancel button
        tk.Button(sel_window, text="Hủy bỏ", font=('Arial', 16, 'bold'),
                 bg=Colors.TEXT_SECONDARY, fg='white', width=15,
                 command=sel_window.destroy).pack(pady=15)
        
        sel_window.focus_set()
    
    def _do_remove_fingerprint(self, fp_id, window):
        if CleanMessageBox.ask_yesno(window, "Xác nhận xóa", 
                                    f"Bạn có chắc chắn muốn xóa vân tay này?\nID: {fp_id}"):
            try:
                self.system.fingerprint.deleteTemplate(fp_id)
                self.system.admin_data.remove_fingerprint_id(fp_id)
                CleanMessageBox.show_success(self.admin_window, "Thành công", 
                                            f"Đã xóa vân tay!\nID: {fp_id}")
            except Exception as e:
                CleanMessageBox.show_error(self.admin_window, "Lỗi", 
                                          f"Không thể xóa: {str(e)}")
        window.destroy()
    
    def _close(self):
        if CleanMessageBox.ask_yesno(self.admin_window, "Thoát Admin", 
                                    "Bạn có muốn thoát chế độ quản trị?"):
            self.admin_window.destroy()
            self.admin_window = None
            self.system.start_authentication()

# Continue with SecuritySystem class (giữ nguyên phần logic, chỉ thay đổi tên class GUI)
class SecuritySystem:
    def __init__(self):
        self.config = Config()
        self._init_hardware()
        
        self.admin_data = AdminDataManager(self.config)
        self.face_recognizer = FaceRecognition(self.config.ENCODINGS_FILE, self.config.FACE_TOLERANCE)
        
        self.auth_state = {
            "step": AuthStep.FACE,
            "consecutive_face_ok": 0,
            "fingerprint_attempts": 0,
            "rfid_attempts": 0,
            "pin_attempts": 0
        }
        
        # GUI - sử dụng CleanSecurityGUI và CleanAdminGUI
        self.root = tk.Tk()
        self.gui = CleanSecurityGUI(self.root)
        self.gui.set_system_reference(self)
        self.admin_gui = CleanAdminGUI(self.root, self)
        
        self.running = True
        self.face_thread = None
        
        logger.info("✅ Hệ thống khởi tạo thành công")
    
    # [Phần còn lại của SecuritySystem class giữ nguyên, chỉ thay đổi ModernNumpadDialog -> CleanNumpadDialog và ModernMessageBox -> CleanMessageBox]
    
    def _init_hardware(self):
        try:
            self.buzzer = BuzzerManager(self.config.BUZZER_GPIO)
            
            self.picam2 = Picamera2()
            self.picam2.configure(self.picam2.create_video_configuration(
                main={"format": 'XRGB8888', "size": (self.config.CAMERA_WIDTH, self.config.CAMERA_HEIGHT)}
            ))
            self.picam2.start()
            time.sleep(2)
            
            self.relay = LED(self.config.RELAY_GPIO)
            self.relay.on()  # Locked
            
            i2c = busio.I2C(board.SCL, board.SDA)
            self.pn532 = PN532_I2C(i2c, debug=False)
            self.pn532.SAM_configuration()
            
            self.fingerprint = PyFingerprint('/dev/ttyUSB0', 57600, 0xFFFFFFFF, 0x00000000)
            if not self.fingerprint.verifyPassword():
                raise ValueError('Cảm biến vân tay không phản hồi')
            
            logger.info("✅ Hardware khởi tạo thành công")
            
        except Exception as e:
            logger.error(f"❌ Lỗi khởi tạo hardware: {e}")
            raise
    
    def _force_admin_mode(self):
        """Chế độ admin nhanh bằng phím *"""
        dialog = CleanNumpadDialog(self.root, "Quản trị viên", "Nhập mật khẩu admin:", True)
        password = dialog.show()
        
        if password == self.config.ADMIN_PASS:
            self.gui.update_status("ĐÃ VÀO CHẾ ĐỘ QUẢN TRỊ", 'lightgreen')
            self.gui.update_detail("Xác thực admin thành công! Đang mở bảng điều khiển...", Colors.SUCCESS)
            self.buzzer.beep("success")
            self.admin_gui.show_admin_panel()
        elif password is not None:
            self.gui.update_status("SAI MẬT KHẨU ADMIN", 'orange')
            self.gui.update_detail("Mật khẩu admin không chính xác! Vui lòng thử lại.", Colors.ERROR)
            self.buzzer.beep("error")
    
    def start_authentication(self):
        """Bắt đầu xác thực từ đầu"""
        self.auth_state = {
            "step": AuthStep.FACE,
            "consecutive_face_ok": 0,
            "fingerprint_attempts": 0,
            "rfid_attempts": 0,
            "pin_attempts": 0
        }
        
        self.gui.update_step(1, "NHẬN DIỆN KHUÔN MẶT", "Nhìn thẳng vào camera để bắt đầu xác thực", Colors.PRIMARY)
        self.gui.update_status("ĐANG NHẬN DIỆN KHUÔN MẶT...", 'white')
        self.gui.update_detail("Hãy nhìn thẳng vào camera và giữ nguyên tư thế trong vài giây", Colors.PRIMARY)
        self.gui.update_camera_status("Đang phân tích...", Colors.WARNING)
        
        if self.face_thread and self.face_thread.is_alive():
            return
        
        self.face_thread = threading.Thread(target=self._face_loop, daemon=True)
        self.face_thread.start()
    
    def _face_loop(self):
        """Face recognition loop"""
        consecutive_count = 0
        
        while self.running and self.auth_state["step"] == AuthStep.FACE:
            try:
                frame = self.picam2.capture_array()
                if frame is None:
                    continue
                
                self.root.after(0, lambda: self.gui.update_camera(frame))
                
                result = self.face_recognizer.recognize(frame)
                
                if result["recognized"]:
                    consecutive_count += 1
                    self.auth_state["consecutive_face_ok"] = consecutive_count
                    
                    progress = consecutive_count / self.config.FACE_REQUIRED_CONSECUTIVE * 100
                    msg = f"Nhận diện OK ({consecutive_count}/{self.config.FACE_REQUIRED_CONSECUTIVE}) - {progress:.0f}%"
                    
                    self.root.after(0, lambda: self.gui.update_step(1, "NHẬN DIỆN KHUÔN MẶT", msg, Colors.SUCCESS))
                    self.root.after(0, lambda: self.gui.update_detail(
                        f"Tiếp tục giữ nguyên tư thế... Còn {self.config.FACE_REQUIRED_CONSECUTIVE - consecutive_count} lần", 
                        Colors.SUCCESS))
                    
                    if consecutive_count >= self.config.FACE_REQUIRED_CONSECUTIVE:
                        self.buzzer.beep("success")
                        self.root.after(0, lambda: self.gui.update_status("KHUÔN MẶT OK! CHUYỂN SANG VÂN TAY", 'lightgreen'))
                        self.root.after(0, lambda: self.gui.update_camera_status("Nhận diện thành công", Colors.SUCCESS))
                        self.root.after(1000, self._proceed_to_fingerprint)
                        break
                else:
                    consecutive_count = 0
                    self.auth_state["consecutive_face_ok"] = 0
                    self.root.after(0, lambda: self.gui.update_step(1, "NHẬN DIỆN KHUÔN MẶT", result["message"], Colors.PRIMARY))
                    self.root.after(0, lambda: self.gui.update_detail(
                        "Đang tìm kiếm khuôn mặt... Hãy đảm bảo ánh sáng đủ và nhìn thẳng vào camera", 
                        Colors.TEXT_SECONDARY))
                
                time.sleep(self.config.FACE_DETECTION_INTERVAL)
                
            except Exception as e:
                logger.error(f"Lỗi face loop: {e}")
                self.root.after(0, lambda: self.gui.update_detail(f"Lỗi camera: {str(e)}", Colors.ERROR))
                time.sleep(1)
    
    def _proceed_to_fingerprint(self):
        """Chuyển sang bước vân tay"""
        self.auth_state["step"] = AuthStep.FINGERPRINT
        self.auth_state["fingerprint_attempts"] = 0
        
        self.gui.update_step(2, "QUÉT VÂN TAY", "Đặt ngón tay lên cảm biến vân tay", Colors.WARNING)
        self.gui.update_status("ĐANG ĐỢI VÂN TAY...", 'yellow')
        self.gui.update_detail("Đặt ngón tay đã đăng ký lên cảm biến và giữ nguyên cho đến khi có tín hiệu", Colors.WARNING)
        
        threading.Thread(target=self._fingerprint_loop, daemon=True).start()
    
    def _fingerprint_loop(self):
        """Fingerprint loop với retry logic"""
        while (self.auth_state["fingerprint_attempts"] < self.config.MAX_ATTEMPTS and 
               self.auth_state["step"] == AuthStep.FINGERPRINT):
            
            try:
                self.auth_state["fingerprint_attempts"] += 1
                attempt_msg = f"Lần thử {self.auth_state['fingerprint_attempts']}/{self.config.MAX_ATTEMPTS}"
                
                self.root.after(0, lambda: self.gui.update_step(2, "QUÉT VÂN TAY", attempt_msg, Colors.WARNING))
                self.root.after(0, lambda: self.gui.update_detail(
                    f"Đặt ngón tay lên cảm biến... (Lần thử {self.auth_state['fingerprint_attempts']}/{self.config.MAX_ATTEMPTS})", 
                    Colors.WARNING))
                
                timeout = 10
                start_time = time.time()
                
                while time.time() - start_time < timeout:
                    if self.fingerprint.readImage():
                        self.fingerprint.convertImage(0x01)
                        result = self.fingerprint.searchTemplate()
                        
                        if result[0] != -1:
                            # Thành công
                            self.buzzer.beep("success")
                            self.root.after(0, lambda: self.gui.update_status("VÂN TAY OK! CHUYỂN SANG RFID", 'lightgreen'))
                            self.root.after(0, lambda: self.gui.update_detail(f"Xác thực vân tay thành công! ID: {result[0]}", Colors.SUCCESS))
                            self.root.after(1000, self._proceed_to_rfid)
                            return
                        else:
                            # Sai vân tay
                            self.buzzer.beep("error")
                            remaining = self.config.MAX_ATTEMPTS - self.auth_state["fingerprint_attempts"]
                            if remaining > 0:
                                self.root.after(0, lambda: self.gui.update_detail(
                                    f"Vân tay không khớp! Còn {remaining} lần thử. Vui lòng thử lại.", Colors.ERROR))
                                time.sleep(2)
                                break
                    time.sleep(0.1)
                
                if time.time() - start_time >= timeout:
                    # Timeout
                    remaining = self.config.MAX_ATTEMPTS - self.auth_state["fingerprint_attempts"]
                    if remaining > 0:
                        self.root.after(0, lambda: self.gui.update_detail(
                            f"Hết thời gian chờ! Còn {remaining} lần thử. Vui lòng đặt ngón tay lên cảm biến.", Colors.WARNING))
                        time.sleep(1)
                
            except Exception as e:
                logger.error(f"Lỗi fingerprint: {e}")
                self.root.after(0, lambda: self.gui.update_detail(f"Lỗi cảm biến vân tay: {str(e)}", Colors.ERROR))
                time.sleep(1)
        
        # Hết lần thử - quay về face
        self.root.after(0, lambda: self.gui.update_status("HẾT LƯỢT THỬ VÂN TAY - RESET HỆ THỐNG", 'orange'))
        self.root.after(0, lambda: self.gui.update_detail("Đã hết số lần thử cho vân tay. Hệ thống sẽ khởi động lại từ đầu...", Colors.ERROR))
        self.buzzer.beep("error")
        self.root.after(3000, self.start_authentication)
    
    def _proceed_to_rfid(self):
        """Chuyển sang bước RFID"""
        self.auth_state["step"] = AuthStep.RFID
        self.auth_state["rfid_attempts"] = 0
        
        self.gui.update_step(3, "QUÉT THẺ RFID", "Đặt thẻ RFID gần đầu đọc", Colors.ACCENT)
        self.gui.update_status("ĐANG ĐỢI THẺ RFID...", 'lightblue')
        self.gui.update_detail("Đặt thẻ RFID hoặc NFC gần đầu đọc trong phạm vi 2-5cm", Colors.ACCENT)
        
        threading.Thread(target=self._rfid_loop, daemon=True).start()
    
    def _rfid_loop(self):
        """RFID loop với retry logic"""
        while (self.auth_state["rfid_attempts"] < self.config.MAX_ATTEMPTS and 
               self.auth_state["step"] == AuthStep.RFID):
            
            try:
                self.auth_state["rfid_attempts"] += 1
                attempt_msg = f"Lần thử {self.auth_state['rfid_attempts']}/{self.config.MAX_ATTEMPTS}"
                
                self.root.after(0, lambda: self.gui.update_step(3, "QUÉT THẺ RFID", attempt_msg, Colors.ACCENT))
                self.root.after(0, lambda: self.gui.update_detail(
                    f"Đặt thẻ gần đầu đọc... (Lần thử {self.auth_state['rfid_attempts']}/{self.config.MAX_ATTEMPTS})", 
                    Colors.ACCENT))
                
                uid = self.pn532.read_passive_target(timeout=8)
                
                if uid:
                    uid_list = list(uid)
                    
                    # Check admin card
                    if uid_list == self.config.ADMIN_UID:
                        self.root.after(0, lambda: self._admin_authentication())
                        return
                    
                    # Check regular cards
                    valid_uids = self.admin_data.get_rfid_uids()
                    if uid_list in valid_uids:
                        self.buzzer.beep("success")
                        self.root.after(0, lambda: self.gui.update_status("THẺ RFID OK! NHẬP MẬT KHẨU", 'lightgreen'))
                        self.root.after(0, lambda: self.gui.update_detail(f"Thẻ RFID hợp lệ! UID: {uid_list}", Colors.SUCCESS))
                        self.root.after(1000, self._proceed_to_passcode)
                        return
                    else:
                        # Thẻ không hợp lệ
                        self.buzzer.beep("error")
                        remaining = self.config.MAX_ATTEMPTS - self.auth_state["rfid_attempts"]
                        if remaining > 0:
                            self.root.after(0, lambda: self.gui.update_detail(
                                f"Thẻ không hợp lệ! UID: {uid_list}. Còn {remaining} lần thử.", Colors.ERROR))
                            time.sleep(2)
                else:
                    # Timeout
                    remaining = self.config.MAX_ATTEMPTS - self.auth_state["rfid_attempts"]
                    if remaining > 0:
                        self.root.after(0, lambda: self.gui.update_detail(
                            f"Không phát hiện thẻ! Còn {remaining} lần thử. Vui lòng đặt thẻ gần hơn.", Colors.WARNING))
                        time.sleep(1)
                
            except Exception as e:
                logger.error(f"Lỗi RFID: {e}")
                self.root.after(0, lambda: self.gui.update_detail(f"Lỗi đầu đọc RFID: {str(e)}", Colors.ERROR))
                time.sleep(1)
        
        # Hết lần thử - quay về face
        self.root.after(0, lambda: self.gui.update_status("HẾT LƯỢT THỬ RFID - RESET HỆ THỐNG", 'orange'))
        self.root.after(0, lambda: self.gui.update_detail("Đã hết số lần thử cho RFID. Hệ thống sẽ khởi động lại từ đầu...", Colors.ERROR))
        self.buzzer.beep("error")
        self.root.after(3000, self.start_authentication)
    
    def _admin_authentication(self):
        """Xác thực admin qua thẻ RFID"""
        dialog = CleanNumpadDialog(self.root, "Admin RFID", "Nhập mật khẩu admin để tiếp tục:", True)
        password = dialog.show()
        
        if password == self.config.ADMIN_PASS:
            self.gui.update_status("ADMIN RFID OK! VÀO BẢNG ĐIỀU KHIỂN", 'lightgreen')
            self.gui.update_detail("Xác thực admin qua RFID thành công! Đang mở bảng điều khiển...", Colors.SUCCESS)
            self.buzzer.beep("success")
            self.admin_gui.show_admin_panel()
        elif password is not None:
            self.gui.update_status("SAI MẬT KHẨU ADMIN", 'orange')
            self.gui.update_detail("Mật khẩu admin không chính xác! Quay lại quá trình xác thực...", Colors.ERROR)
            self.buzzer.beep("error")
            time.sleep(2)
            self.start_authentication()
        else:
            self.start_authentication()
    
    def _proceed_to_passcode(self):
        """Chuyển sang bước cuối - nhập mật khẩu"""
        self.auth_state["step"] = AuthStep.PASSCODE
        self.auth_state["pin_attempts"] = 0
        
        self.gui.update_step(4, "NHẬP MẬT KHẨU", "Nhập mật khẩu hệ thống để hoàn tất", Colors.SUCCESS)
        self.gui.update_status("NHẬP MẬT KHẨU CUỐI CÙNG...", 'lightgreen')
        
        self._request_passcode()
    
    def _request_passcode(self):
        """PIN input với retry logic"""
        if self.auth_state["pin_attempts"] >= self.config.MAX_ATTEMPTS:
            self.gui.update_status("HẾT LƯỢT THỬ MẬT KHẨU - RESET HỆ THỐNG", 'orange')
            self.gui.update_detail("Đã hết số lần thử cho mật khẩu. Hệ thống sẽ khởi động lại từ đầu...", Colors.ERROR)
            self.buzzer.beep("error")
            self.root.after(3000, self.start_authentication)
            return
        
        self.auth_state["pin_attempts"] += 1
        attempt_msg = f"Lần thử {self.auth_state['pin_attempts']}/{self.config.MAX_ATTEMPTS}"
        
        self.gui.update_step(4, "NHẬP MẬT KHẨU", attempt_msg, Colors.SUCCESS)
        self.gui.update_detail(f"Nhập mật khẩu hệ thống... (Lần thử {self.auth_state['pin_attempts']}/{self.config.MAX_ATTEMPTS})", Colors.SUCCESS)
        
        dialog = CleanNumpadDialog(self.root, "Mật khẩu cuối cùng", "Nhập mật khẩu hệ thống để mở khóa:", True)
        pin = dialog.show()
        
        if pin == self.admin_data.get_passcode():
            self.gui.update_status("XÁC THỰC HOÀN TẤT! ĐANG MỞ KHÓA...", 'lightgreen')
            self.gui.update_detail("Tất cả các bước xác thực đã hoàn tất! Đang mở khóa cửa...", Colors.SUCCESS)
            self.buzzer.beep("success")
            self._unlock_door()
        elif pin is not None:
            remaining = self.config.MAX_ATTEMPTS - self.auth_state["pin_attempts"]
            if remaining > 0:
                self.gui.update_detail(f"Mật khẩu sai! Còn {remaining} lần thử. Vui lòng nhập lại.", Colors.ERROR)
                self.buzzer.beep("error")
                self.root.after(1500, self._request_passcode)
            else:
                self.gui.update_status("HẾT LƯỢT THỬ MẬT KHẨU - RESET HỆ THỐNG", 'orange')
                self.gui.update_detail("Đã hết số lần thử cho mật khẩu. Hệ thống sẽ khởi động lại từ đầu...", Colors.ERROR)
                self.buzzer.beep("error")
                self.root.after(3000, self.start_authentication)
        else:
            self.start_authentication()
    
    def _unlock_door(self):
        """Mở khóa cửa với countdown timer"""
        try:
            self.gui.update_step(4, "HOÀN THÀNH", "CỬA ĐÃ ĐƯỢC MỞ KHÓA", Colors.SUCCESS)
            self.gui.update_status(f"CỬA ĐÃ MỞ - TỰ ĐỘNG KHÓA SAU {self.config.LOCK_OPEN_DURATION}S", 'lightgreen')
            
            self.relay.off()  # Unlock
            self.buzzer.beep("success")
            
            # Countdown timer
            for i in range(self.config.LOCK_OPEN_DURATION, 0, -1):
                self.root.after((self.config.LOCK_OPEN_DURATION - i) * 1000, 
                               lambda t=i: self.gui.update_detail(f"Cửa đang mở - Tự động khóa sau {t} giây", Colors.SUCCESS))
                self.root.after((self.config.LOCK_OPEN_DURATION - i) * 1000,
                               lambda t=i: self.gui.update_status(f"CỬA MỞ - KHÓA SAU {t}S", 'lightgreen'))
            
            self.root.after(self.config.LOCK_OPEN_DURATION * 1000, self._lock_door)
            
        except Exception as e:
            logger.error(f"Lỗi mở khóa: {e}")
            self.gui.update_detail(f"Lỗi mở khóa: {str(e)}", Colors.ERROR)
    
    def _lock_door(self):
        """Khóa cửa và reset hệ thống"""
        try:
            self.relay.on()  # Lock
            self.gui.update_status("CỬA ĐÃ KHÓA LẠI - HỆ THỐNG SẴN SÀNG", 'white')
            self.gui.update_detail("Cửa đã được khóa lại. Hệ thống sẵn sàng cho lượt xác thực tiếp theo.", Colors.PRIMARY)
            self.buzzer.beep("click")
            self.root.after(2000, self.start_authentication)
        except Exception as e:
            logger.error(f"Lỗi khóa cửa: {e}")
            self.gui.update_detail(f"Lỗi khóa cửa: {str(e)}", Colors.ERROR)
    
    def run(self):
        """Chạy hệ thống chính"""
        try:
            self.gui.update_status("HỆ THỐNG KHỞI ĐỘNG THÀNH CÔNG!", 'lightgreen')
            self.gui.update_detail("Hệ thống khóa bảo mật 4 lớp đã sẵn sàng. Bắt đầu quá trình xác thực...", Colors.SUCCESS)
            
            # Khởi động camera status
            self.gui.update_camera_status("Camera sẵn sàng", Colors.SUCCESS)
            
            self.start_authentication()
            
            self.root.protocol("WM_DELETE_WINDOW", self.cleanup)
            self.root.mainloop()
            
        except KeyboardInterrupt:
            logger.info("Dừng hệ thống theo yêu cầu người dùng")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Dọn dẹp tài nguyên khi thoát"""
        logger.info("Đang dọn dẹp tài nguyên...")
        self.running = False
        
        try:
            if hasattr(self, 'picam2'):
                self.picam2.stop()
                logger.info("Camera đã dừng")
                
            if hasattr(self, 'relay'):
                self.relay.on()  # Ensure locked
                logger.info("Cửa đã được khóa")
                
            if hasattr(self, 'buzzer'):
                self.buzzer.buzzer.off()
                logger.info("Buzzer đã tắt")
                
        except Exception as e:
            logger.error(f"Lỗi khi dọn dẹp: {e}")
        
        self.root.quit()
        logger.info("Dọn dẹp hoàn tất")

# ==== MAIN EXECUTION ====
if __name__ == "__main__":
    try:
        print("=" * 50)
        print("HỆ THỐNG KHÓA BẢO MẬT 4 LỚP")
        print("=" * 50)
        print("Tối ưu cho màn hình cảm ứng 7-10 inch")
        print("Hỗ trợ đầy đủ điều khiển bằng bàn phím số")
        print("Giao diện đơn giản, rõ ràng")
        print("4 lớp bảo mật: Khuôn mặt + Vân tay + RFID + Mật khẩu")
        print("=" * 50)
        
        # Hardware check
        print("Đang kiểm tra phần cứng...")
        print("   Camera Module 2")
        print("   Cảm biến vân tay AS608") 
        print("   RFID PN532")
        print("   Khóa Solenoid + Relay")
        print("   Buzzer")
        print("=" * 50)
        
        system = SecuritySystem()
        print("Tất cả phần cứng đã sẵn sàng!")
        print("Đang khởi động giao diện...")
        
        system.run()
        
    except Exception as e:
        print("=" * 50)
        print(f"LỖI KHỞI ĐỘNG: {e}")
        print("Vui lòng kiểm tra:")
        print("   • Kết nối phần cứng")
        print("   • File encodings.pickle")
        print("   • Quyền truy cập GPIO")
        print("   • Thư viện Python")
        print("=" * 50)
        logger.error(f"Lỗi khởi động hệ thống: {e}")
        sys.exit(1)
