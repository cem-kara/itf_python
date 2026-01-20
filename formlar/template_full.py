# -*- coding: utf-8 -*-
import sys
import os
import logging

# PySide6 Kütüphaneleri
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QProgressBar, QSlider, QCheckBox, 
    QRadioButton, QTableWidget, QTableWidgetItem, 
    QHeaderView, QPushButton, QDateEdit, QComboBox
)
from PySide6.QtCore import Qt, QDate

# =============================================================================
# DİNAMİK YOL VE IMPORT AYARLARI (KRİTİK BÖLÜM)
# =============================================================================
# Bu dosya 'formlar' klasörü içindedir.
# Üst klasördeki (ana dizin) 'temalar' ve 'araclar' klasörlerine erişmek için:

current_dir = os.path.dirname(os.path.abspath(__file__)) # .../Proje/formlar
root_dir = os.path.dirname(current_dir)                # .../Proje (Ana Dizin)

if root_dir not in sys.path:
    sys.path.append(root_dir)

try:
    # Klasör yapısına göre importlar
    from temalar.tema import TemaYonetimi
    from araclar.ortak_araclar import (
        pencereyi_kapat, create_group_box, create_form_layout,
        add_line_edit, add_combo_box, add_date_edit, show_info,
        show_error, validate_required_fields
    )
    # Gerekirse google bağlantısı (Ana dizinde olduğu için direkt import)
    # import google_baglanti 
except ImportError as e:
    print(f"HATA: Modüller yüklenemedi! ({e})")
    print(f"Aranan Ana Dizin: {root_dir}")
    print("Lütfen 'temalar' ve 'araclar' klasörlerinin içinde ilgili dosyaların olduğundan emin olun.")
    sys.exit(1)

# Loglama
logger = logging.getLogger("TemplateForm")

class TemplateForm(QWidget):
    """
    Standart Form Şablonu
    Yapı: formlar/ klasörü altında çalışır.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Form Şablonu - Modüler Yapı")
        self.resize(900, 700)
        
        # UI Elemanlarını saklamak için sözlük
        self.ui = {}
        
        # Arayüzü Kur
        self._setup_ui()

    def _setup_ui(self):
        """Arayüz bileşenlerini oluşturur ve yerleştirir."""
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # --- BÖLÜM 1: KİŞİSEL BİLGİLER ---
        grp_kisisel = create_group_box("Personel Bilgileri")
        form_layout = create_form_layout()

        self.ui['ad'] = add_line_edit(form_layout, "Adı:", placeholder="Ad...")
        self.ui['soyad'] = add_line_edit(form_layout, "Soyadı:", placeholder="Soyad...")
        self.ui['tc'] = add_line_edit(form_layout, "TC Kimlik No:", max_length=11, only_int=True)
        
        roller = ["Seçiniz...", "Yönetici", "Personel", "Tekniker", "Doktor"]
        self.ui['rol'] = add_combo_box(form_layout, "Kullanıcı Rolü:", items=roller)
        self.ui['dogum_tarihi'] = add_date_edit(form_layout, "Doğum Tarihi:", default_date=QDate.currentDate())

        grp_kisisel.setLayout(form_layout)
        main_layout.addWidget(grp_kisisel)

        # --- BÖLÜM 2: TABLE ve DETAYLAR ---
        grp_liste = create_group_box("İşlem Geçmişi")
        v_liste = QVBoxLayout()
        
        table = QTableWidget(3, 3)
        table.setHorizontalHeaderLabels(["ID", "İşlem", "Durum"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        
        table.setItem(0, 0, QTableWidgetItem("1"))
        table.setItem(0, 1, QTableWidgetItem("Sisteme Giriş"))
        table.setItem(0, 2, QTableWidgetItem("Başarılı"))
        
        v_liste.addWidget(table)
        grp_liste.setLayout(v_liste)
        main_layout.addWidget(grp_liste)

        # --- BÖLÜM 3: BUTONLAR ---
        h_actions = QHBoxLayout()
        h_actions.addStretch()

        btn_iptal = QPushButton("İptal")
        btn_iptal.setFixedWidth(120)
        btn_iptal.setObjectName("btn_iptal")
        btn_iptal.clicked.connect(self._iptal)

        btn_kaydet = QPushButton("Kaydet")
        btn_kaydet.setFixedWidth(120)
        btn_kaydet.setObjectName("btn_kaydet")
        btn_kaydet.clicked.connect(self._kaydet)

        h_actions.addWidget(btn_iptal)
        h_actions.addWidget(btn_kaydet)
        
        main_layout.addLayout(h_actions)
        self.setLayout(main_layout)

    def _kaydet(self):
        """Kayıt işlemi simülasyonu."""
        required = [self.ui['ad'], self.ui['soyad'], self.ui['tc']]
        if not validate_required_fields(required):
            return

        show_info("Bilgi", "Kayıt işlemi başarılı (Simülasyon)")

    def _iptal(self):
        pencereyi_kapat(self)

# =============================================================================
# MAIN BLOĞU (TEST İÇİN)
# =============================================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Temayı Ana Klasörden Çekip Uyguluyoruz
    TemaYonetimi.uygula_fusion_dark(app)
    
    window = TemplateForm()
    window.show()
    
    sys.exit(app.exec())