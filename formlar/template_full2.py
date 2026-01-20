# -*- coding: utf-8 -*-
import sys
import os
import logging
from datetime import datetime

# PySide6 Kütüphaneleri (Mevcut kontroller korundu)
from PySide6.QtCore import Qt, QDate, QSize
from PySide6.QtGui import QAction, QIcon, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, 
    QComboBox, QDateEdit, QPushButton, QTableWidget, QTableWidgetItem, 
    QHeaderView, QListWidget, QProgressBar, QSlider, QCheckBox, 
    QRadioButton, QTabWidget, QGroupBox, QMenuBar, QMenu, QSplitter,
    QFrame, QScrollArea
)

# =============================================================================
# DİNAMİK YOL AYARLARI (GÜNCELLENDİ)
# =============================================================================
# Bu dosya 'formlar' klasöründedir.
# Üst dizindeki 'temalar' ve 'araclar' klasörlerine erişmek için path ayarı:

current_dir = os.path.dirname(os.path.abspath(__file__))  # .../formlar
root_dir = os.path.dirname(current_dir)                 # .../ (Ana Proje Dizini)

if root_dir not in sys.path:
    sys.path.append(root_dir)

try:
    # 1. TEMA MODÜLÜ (temalar/tema.py)
    from temalar.tema import TemaYonetimi
    
    # 2. ORTAK ARAÇLAR MODÜLÜ (araclar/ortak_araclar.py)
    from araclar.ortak_araclar import (
        pencereyi_kapat, create_group_box, create_form_layout,
        add_line_edit, add_combo_box, add_date_edit, show_info,
        show_error, validate_required_fields
    )
except ImportError as e:
    print(f"KRİTİK HATA: Modüller yüklenemedi! ({e})")
    print(f"Aranan Ana Dizin: {root_dir}")
    print("Lütfen 'temalar' ve 'araclar' klasörlerinin doğru yerde olduğundan emin olun.")
    sys.exit(1)

# Loglama
logger = logging.getLogger("TemplateFull2")

class TemplateForm(QWidget):
    """
    Genişletilmiş Form Şablonu (Full Kontroller)
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gelişmiş Form Şablonu")
        self.resize(1000, 800)
        
        # UI Elemanlarını saklamak için sözlük
        self.ui = {}
        
        # Arayüzü Kur
        self._setup_ui()

    def _setup_ui(self):
        """Arayüz bileşenlerini oluşturur."""
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # --- ÜST KISIM: Splitter ile Bölünmüş Alan (Örnek) ---
        splitter = QSplitter(Qt.Horizontal)
        
        # SOL PANEL (ListWidget)
        left_frame = QFrame()
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(0,0,0,0)
        
        list_widget = QListWidget()
        list_widget.addItems(["Menü 1", "Menü 2", "Ayarlar", "Raporlar"])
        left_layout.addWidget(create_group_box("Hızlı Menü"))
        left_layout.addWidget(list_widget)
        
        # SAĞ PANEL (ScrollArea İçinde Form)
        right_frame = QFrame()
        right_layout = QVBoxLayout(right_frame)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        # 1. PERSONEL BİLGİLERİ (Form Layout)
        grp_kisisel = create_group_box("Personel Bilgileri")
        form_layout = create_form_layout()
        
        self.ui['ad'] = add_line_edit(form_layout, "Adı:", placeholder="Ad giriniz...")
        self.ui['soyad'] = add_line_edit(form_layout, "Soyadı:", placeholder="Soyad giriniz...")
        self.ui['tc'] = add_line_edit(form_layout, "TC No:", max_length=11, only_int=True)
        self.ui['dogum'] = add_date_edit(form_layout, "Doğum Tarihi:")
        
        grp_kisisel.setLayout(form_layout)
        scroll_layout.addWidget(grp_kisisel)

        # 2. DETAYLI AYARLAR (Grid / Karma)
        grp_detay = create_group_box("Sistem Ayarları")
        v_detay = QVBoxLayout()
        
        # Checkboxlar
        self.ui['chk_aktif'] = QCheckBox("Kullanıcı Aktif")
        self.ui['chk_aktif'].setChecked(True)
        self.ui['chk_admin'] = QCheckBox("Yönetici Yetkisi")
        
        # Radio Butonlar
        h_radio = QHBoxLayout()
        self.ui['rb_mod1'] = QRadioButton("Mod A")
        self.ui['rb_mod2'] = QRadioButton("Mod B")
        self.ui['rb_mod1'].setChecked(True)
        h_radio.addWidget(QLabel("Çalışma Modu:"))
        h_radio.addWidget(self.ui['rb_mod1'])
        h_radio.addWidget(self.ui['rb_mod2'])
        h_radio.addStretch()

        # Slider ve Progress
        h_slider = QHBoxLayout()
        slider = QSlider(Qt.Horizontal)
        pbar = QProgressBar()
        pbar.setValue(45)
        h_slider.addWidget(QLabel("Hassasiyet:"))
        h_slider.addWidget(slider)
        h_slider.addWidget(pbar)

        v_detay.addWidget(self.ui['chk_aktif'])
        v_detay.addWidget(self.ui['chk_admin'])
        v_detay.addLayout(h_radio)
        v_detay.addLayout(h_slider)
        grp_detay.setLayout(v_detay)
        scroll_layout.addWidget(grp_detay)
        
        # Scroll Kapanış
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        right_layout.addWidget(scroll)

        # Splitter'a ekle
        splitter.addWidget(left_frame)
        splitter.addWidget(right_frame)
        splitter.setStretchFactor(1, 4) # Sağ taraf daha geniş
        
        main_layout.addWidget(splitter)

        # --- ALT KISIM: BUTONLAR ---
        h_actions = QHBoxLayout()
        h_actions.addStretch()
        
        btn_iptal = QPushButton("İptal")
        btn_iptal.setObjectName("btn_iptal") # Kırmızı stil
        btn_iptal.setFixedWidth(120)
        btn_iptal.clicked.connect(self._iptal)
        
        btn_kaydet = QPushButton("Kaydet")
        btn_kaydet.setObjectName("btn_kaydet") # Mavi stil
        btn_kaydet.setFixedWidth(120)
        btn_kaydet.clicked.connect(self._kaydet)
        
        h_actions.addWidget(btn_iptal)
        h_actions.addWidget(btn_kaydet)
        main_layout.addLayout(h_actions)

        self.setLayout(main_layout)

    def _kaydet(self):
        """Kaydetme işlemi."""
        # Validasyon
        if not validate_required_fields([self.ui['ad'], self.ui['soyad'], self.ui['tc']]):
            return
            
        show_info("Bilgi", "Kayıt başarılı (Simülasyon)")

    def _iptal(self):
        pencereyi_kapat(self)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # --- TEMA UYGULAMA ---
    TemaYonetimi.uygula_fusion_dark(app)
    
    window = TemplateForm()
    window.show()
    
    sys.exit(app.exec())