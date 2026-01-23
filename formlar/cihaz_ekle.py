# -*- coding: utf-8 -*-
import sys
import os
import uuid 
import logging
from datetime import datetime

# Gerekli Kütüphaneler
from PySide6.QtCore import Qt, QDate, QThread, Signal, QSize
from PySide6.QtGui import QPixmap, QCursor, QFont, QColor
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QLineEdit, QComboBox, QDateEdit, QPushButton, 
                               QScrollArea, QFrame, QFileDialog, QGridLayout, 
                               QProgressBar, QGraphicsDropShadowEffect, QSizePolicy)

# --- LOGLAMA ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CihazEkle")

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from araclar.yetki_yonetimi import YetkiYoneticisi

# --- İMPORTLAR ---
try:
    from google_baglanti import veritabani_getir, GoogleDriveService
    from araclar.ortak_araclar import show_info, show_error, pencereyi_kapat
except ImportError as e:
    print(f"Modül Hatası: {e}")
    def veritabani_getir(vt, sayfa): return None
    def show_info(t, m, p): print(m)
    def show_error(t, m, p): print(m)
    def pencereyi_kapat(w): w.close()
    class GoogleDriveService:
        def upload_file(self, a, b): return None

# Künye Motoru (Varsa)
try:
    from formlar.kunye_motoru import KunyeOlusturucu
except ImportError:
    KunyeOlusturucu = None

# --- AYARLAR ---
DRIVE_KLASORLERI = {
    "CIHAZ_RESIMLERI": "1-PznDkBqOHTbE3rWBlS8g2HjZXaK6Sdh", 
    "CIHAZ_BELGELERI": "1eOq_NfrjN_XwKirUuX_0uyOonk137HjF",
    "CIHAZ_KUNYE_PDF": "19kx3IHTg4XWrYrF-_LzT3BpY5gRy-CH5"
}

# =============================================================================
# 1. THREAD SINIFLARI (MANTIK)
# =============================================================================
class BaslangicYukleyici(QThread):
    # (Sabitler, Kısaltma Haritaları, Son Sıra No)
    veri_hazir = Signal(dict, dict, int)
    
    def run(self):
        sabitler = {}
        maps = {"AnaBilimDali": {}, "Cihaz_Tipi": {}, "Kaynak": {}}
        siradaki_no = 1

        try:
            # 1. Sabitleri Çek
            ws_sabit = veritabani_getir('sabit', 'Sabitler')
            if ws_sabit:
                kayitlar = ws_sabit.get_all_records()
                for satir in kayitlar:
                    kod = str(satir.get('Kod', '')).strip()
                    eleman = str(satir.get('MenuEleman', '')).strip()
                    kisaltma = str(satir.get('Aciklama', '')).strip()

                    if kod and eleman:
                        if kod not in sabitler: sabitler[kod] = []
                        sabitler[kod].append(eleman)
                        
                        if kisaltma:
                            if kod in maps: maps[kod][eleman] = kisaltma

            # 2. Son ID'yi Hesapla
            ws_cihaz = veritabani_getir('cihaz', 'Cihazlar')
            if ws_cihaz:
                data = ws_cihaz.get_all_values()
                if data and len(data) > 0:
                    headers = data[0]
                    id_idx = -1
                    for i, h in enumerate(headers):
                        if str(h).strip() in ["cihaz_id", "CihazID"]:
                            id_idx = i; break
                    
                    if id_idx != -1:
                        max_id = 0
                        for row in data[1:]:
                            if len(row) > id_idx:
                                val = str(row[id_idx]).strip()
                                # Sadece sayıları al (RAD-MR-001 -> 1)
                                try:
                                    num_str = ''.join(filter(str.isdigit, val))
                                    if num_str:
                                        num = int(num_str)
                                        if num > max_id and num < 900000: max_id = num
                                except: pass
                        siradaki_no = max_id + 1
        except Exception as e:
            logger.error(f"Başlangıç yükleme hatası: {e}")
        
        self.veri_hazir.emit(sabitler, maps, siradaki_no)

class KayitIslemi(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)

    def __init__(self, veri_listesi, resim_yolu, belge_yolu, form_verileri_dict):
        super().__init__()
        self.veri = veri_listesi
        self.resim_yolu = resim_yolu
        self.belge_yolu = belge_yolu
        self.sozluk_veri = form_verileri_dict

    def run(self):
        try:
            drive = GoogleDriveService()
            
            # 1. Dosyaları Yükle
            resim_link = ""
            if self.resim_yolu and os.path.exists(self.resim_yolu):
                resim_link = drive.upload_file(self.resim_yolu, DRIVE_KLASORLERI["CIHAZ_RESIMLERI"]) or ""
            
            belge_link = ""
            if self.belge_yolu and os.path.exists(self.belge_yolu):
                belge_link = drive.upload_file(self.belge_yolu, DRIVE_KLASORLERI["CIHAZ_BELGELERI"]) or ""

            self.veri.append(resim_link)
            self.veri.append(belge_link)

            # 2. PDF Künye (Opsiyonel)
            if KunyeOlusturucu:
                try:
                    sablon_path = os.path.join(root_dir, "sablon", "cihaz_kunye.docx")
                    if os.path.exists(sablon_path):
                        motor = KunyeOlusturucu(sablon_path)
                        gecici_pdf = motor.belge_olustur(self.sozluk_veri)
                        
                        if gecici_pdf and os.path.exists(gecici_pdf):
                            raw_id = self.sozluk_veri.get('cihaz_id', 'Yeni_Cihaz')
                            safe_id = str(raw_id).replace('/', '-').replace('\\', '-').strip()
                            yeni_isim = f"{safe_id}_kunye.pdf"
                            yeni_yol = os.path.join(os.path.dirname(gecici_pdf), yeni_isim)
                            
                            if os.path.exists(yeni_yol): os.remove(yeni_yol)
                            os.rename(gecici_pdf, yeni_yol)
                            
                            drive.upload_file(yeni_yol, DRIVE_KLASORLERI["CIHAZ_KUNYE_PDF"])
                            if os.path.exists(yeni_yol): os.remove(yeni_yol)
                            motor.temizle()
                except Exception as k_hata: logger.error(f"Künye hatası: {k_hata}")

            # 3. Sheets Kayıt
            ws = veritabani_getir('cihaz', 'Cihazlar')
            if not ws: raise Exception("Veritabanı bağlantısı yok.")
            ws.append_row(self.veri)
            self.islem_tamam.emit()

        except Exception as e:
            self.hata_olustu.emit(str(e))

# =============================================================================
# 2. UI: MODERN KONTROLLER
# =============================================================================
class ModernInputGroup(QWidget):
    def __init__(self, label_text, widget, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(4)
        
        self.lbl = QLabel(label_text)
        self.lbl.setStyleSheet("color: #b0b0b0; font-size: 11px; font-weight: bold; text-transform: uppercase;")
        
        self.widget = widget
        self.widget.setMinimumHeight(40)
        self.widget.setMinimumWidth(150)
        
        self.widget.setStyleSheet("""
            QLineEdit, QComboBox, QDateEdit {
                background-color: #2b2b2b;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                padding: 6px;
                color: #e0e0e0;
                font-size: 14px;
                min-height: 18px;
            }
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus {
                border: 1px solid #4dabf7;
                background-color: #333333;
            }
            QLineEdit:read-only {
                background-color: #202020;
                border: none;
                color: #999;
                font-style: italic;
            }
        """)
        layout.addWidget(self.lbl)
        layout.addWidget(self.widget)

class InfoCard(QFrame):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setStyleSheet("InfoCard { background-color: #1e1e1e; border-radius: 12px; border: 1px solid #333; }")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)
        
        if title:
            lbl_title = QLabel(title)
            lbl_title.setStyleSheet("color: #4dabf7; font-size: 14px; font-weight: bold; border-bottom: 1px solid #333; padding-bottom: 10px; margin-bottom: 5px;")
            self.layout.addWidget(lbl_title)

    def add_widget(self, widget):
        self.layout.addWidget(widget)

    def add_layout(self, layout):
        self.layout.addLayout(layout)

# =============================================================================
# 3. ANA PENCERE: CİHAZ EKLE
# =============================================================================
class CihazEklePenceresi(QWidget):
    # 🟢 DEĞİŞİKLİK 1: Parametreler
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.setWindowTitle("Yeni Cihaz Ekleme Kartı")
        self.resize(1200, 850)
        self.setStyleSheet("background-color: #121212;")

        self.inputs = {}
        self.control_buttons = {} 
        self.secilen_resim_yolu = None
        self.secilen_belge_yolu = None
        
        self.map_anabilim = {}
        self.map_cihaz_tipi = {}
        self.map_kaynak = {}
        self.siradaki_no = 1
        
        self.setup_ui()
        
        # 🟢 DEĞİŞİKLİK 2: Yetki Uygulama
        YetkiYoneticisi.uygula(self, "cihaz_ekle")
        
        self.baslangic_yukle()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0,0,0,0)
        main_layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setFixedHeight(60)
        header.setStyleSheet("background-color: #1e1e1e; border-bottom: 1px solid #333;")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(25, 0, 25, 0)
        
        lbl_baslik = QLabel("Yeni Cihaz Kaydı")
        lbl_baslik.setFont(QFont("Segoe UI", 16, QFont.Bold))
        lbl_baslik.setStyleSheet("color: #ffffff;")
        
        self.progress = QProgressBar()
        self.progress.setFixedSize(150, 6)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("QProgressBar {background: #333; border-radius: 3px;} QProgressBar::chunk {background: #4dabf7; border-radius: 3px;}")
        
        h_lay.addWidget(lbl_baslik)
        h_lay.addStretch()
        h_lay.addWidget(self.progress)
        main_layout.addWidget(header)

        # Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        
        grid = QGridLayout(content)
        grid.setContentsMargins(25, 25, 25, 25)
        grid.setSpacing(25)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 2)

        # --- SOL KOLON (Medya) ---
        card_media = InfoCard("Medya & Dosyalar")
        
        self.lbl_resim = QLabel("Görsel Seçilmedi")
        self.lbl_resim.setFixedSize(250, 250)
        self.lbl_resim.setStyleSheet("background-color: #000; border-radius: 8px; border: 1px solid #333; color: #666;")
        self.lbl_resim.setAlignment(Qt.AlignCenter)
        self.lbl_resim.setScaledContents(True)
        card_media.add_widget(self.lbl_resim)
        
        self.create_file_manager(card_media, "Cihaz Görseli Seç", "Img", is_image=True)
        self.create_file_manager(card_media, "Lisans Belgesi Seç", "NDK_Lisans_Belgesi", is_image=False)
        
        card_media.layout.addStretch()
        grid.addWidget(card_media, 0, 0, 2, 1)

        # --- ORTA KOLON (Kimlik) ---
        card_kimlik = InfoCard("Kimlik Bilgileri")
        self.add_modern_input(card_kimlik, "Cihaz ID (Otomatik)", "CihazID")
        self.inputs["CihazID"].setReadOnly(True)
        self.inputs["CihazID"].setStyleSheet("background-color: #202020; color: #4dabf7; font-weight: bold; border: none;")
        
        row1 = QHBoxLayout(); row1.setSpacing(15)
        self.add_modern_input(row1, "Marka", "Marka", "combo", db_kodu="Marka", stretch=1)
        self.add_modern_input(row1, "Model", "Model", stretch=1)
        card_kimlik.add_layout(row1)
        
        row2 = QHBoxLayout(); row2.setSpacing(15)
        self.add_modern_input(row2, "Cihaz Tipi", "CihazTipi", "combo", db_kodu="Cihaz_Tipi", stretch=1)
        self.add_modern_input(row2, "Seri No", "SeriNo", stretch=1)
        card_kimlik.add_layout(row2)
        
        self.add_modern_input(card_kimlik, "Kullanım Amacı", "Amaç", "combo", db_kodu="Amaç")
        self.add_modern_input(card_kimlik, "Edinim Kaynağı", "Kaynak", "combo", db_kodu="Kaynak")
        grid.addWidget(card_kimlik, 0, 1)

        # --- SAĞ KOLON (Lokasyon) ---
        card_lokasyon = InfoCard("Lokasyon ve Sorumluluk")
        row3 = QHBoxLayout(); row3.setSpacing(15)
        self.add_modern_input(row3, "Birim", "Birim", "combo", db_kodu="Birim")
        self.add_modern_input(row3, "Bulunduğu Bina", "BulunduguBina")
        card_lokasyon.add_layout(row3)
        self.add_modern_input(card_lokasyon, "Ana Bilim Dalı", "AnaBilimDali", "combo", db_kodu="AnaBilimDali")
        row4 = QHBoxLayout(); row4.setSpacing(15)
        self.add_modern_input(row4, "Sorumlu Kişi", "Sorumlusu")
        self.add_modern_input(row4, "Radyasyon Sor. (RKS)", "RKS")
        card_lokasyon.add_layout(row4)
        grid.addWidget(card_lokasyon, 0, 2)

        # --- ALT SATIR (Teknik & Lisans) ---
        card_teknik = InfoCard("Lisans ve Teknik Durum")
        t_grid = QGridLayout()
        t_grid.setSpacing(15)
        
        self.add_modern_input_grid(t_grid, 0, 0, "NDK Lisans No", "NDKLisansNo", stretch=1)
        self.add_modern_input_grid(t_grid, 0, 1, "Lisans Durumu", "LisansDurum", "combo", db_kodu="Lisans_Durum", stretch=1)
        self.add_modern_input_grid(t_grid, 0, 2, "Lisans Bitiş", "BitisTarihi", "date", stretch=1)

        self.add_modern_input_grid(t_grid, 1, 0, "Hizmete Giriş", "HizmeteGirisTarihi", "date", stretch=1)
        self.add_modern_input_grid(t_grid, 1, 1, "Garanti Durumu", "GarantiDurumu", "combo", db_kodu="Garanti_Durum", stretch=1)
        self.add_modern_input_grid(t_grid, 1, 2, "Garanti Bitiş", "GarantiBitisTarihi", "date", stretch=1)

        self.add_modern_input_grid(t_grid, 2, 0, "Bakım Durumu", "BakimDurum", "combo", db_kodu="Bakim_Durum", stretch=1)
        self.add_modern_input_grid(t_grid, 2, 1, "Kalibrasyon Gerekli mi?", "KalibrasyonGereklimi", "combo", db_kodu="Kalibrasyon_Durum", stretch=1)
        self.add_modern_input_grid(t_grid, 2, 2, "Genel Durum", "Durum", "combo", db_kodu="Cihaz_Durum", stretch=1)

        self.add_modern_input_grid(t_grid, 3, 0, "Demirbaş No", "DemirbasNo")
        
        card_teknik.add_layout(t_grid)
        grid.addWidget(card_teknik, 1, 1, 1, 2)

        scroll.setWidget(content)
        main_layout.addWidget(scroll)

        # Footer
        footer = QFrame()
        footer.setFixedHeight(80)
        footer.setStyleSheet("background-color: #1e1e1e; border-top: 1px solid #333;")
        foot_lay = QHBoxLayout(footer)
        foot_lay.setContentsMargins(30, 15, 30, 15)
        foot_lay.setSpacing(15)
        
        self.btn_temizle = QPushButton("🗑️ Formu Temizle")
        self.btn_temizle.setObjectName("btn_temizle") # 🟢 DEĞİŞİKLİK 3: ObjectName
        self.btn_temizle.setFixedSize(160, 45)
        self.btn_temizle.setCursor(Qt.PointingHandCursor)
        self.btn_temizle.setStyleSheet("""
            QPushButton { background: transparent; border: 1px solid #555; color: #aaa; border-radius: 8px; font-weight: bold; }
            QPushButton:hover { background: #333; color: white; }
        """)
        self.btn_temizle.clicked.connect(self.formu_temizle)
        
        self.btn_kaydet = QPushButton("✅ Sisteme Kaydet")
        self.btn_kaydet.setObjectName("btn_kaydet") # 🟢 DEĞİŞİKLİK 3: ObjectName
        self.btn_kaydet.setFixedSize(200, 45)
        self.btn_kaydet.setCursor(Qt.PointingHandCursor)
        self.btn_kaydet.setStyleSheet("""
            QPushButton { background-color: #16a34a; color: white; border: none; border-radius: 8px; font-weight: bold; font-size: 14px; }
            QPushButton:hover { background-color: #15803d; }
            QPushButton:disabled { background-color: #333; color: #555; }
        """)
        self.btn_kaydet.clicked.connect(self.kaydet_baslat)
        
        foot_lay.addWidget(self.btn_temizle)
        foot_lay.addStretch()
        foot_lay.addWidget(self.btn_kaydet)
        
        main_layout.addWidget(footer)

    # --- UI FONKSİYONLARI ---
    def add_modern_input(self, parent, label, key, tip="text", db_kodu=None, stretch=0):
        widget = None
        if tip == "text": widget = QLineEdit()
        elif tip == "combo": widget = QComboBox(); widget.setProperty("db_kodu", db_kodu)
        elif tip == "date": 
            widget = QDateEdit(); widget.setCalendarPopup(True); widget.setDisplayFormat("dd.MM.yyyy")
            widget.setDate(QDate.currentDate())
        
        # Objeye erişim için ismi set et (Yetki için opsiyonel ama iyi pratik)
        if widget: widget.setObjectName(f"inp_{key}")
            
        grp = ModernInputGroup(label, widget)
        
        if isinstance(parent, InfoCard): parent.add_widget(grp)
        elif hasattr(parent, "addWidget"): parent.addWidget(grp, stretch)
        self.inputs[key] = widget
        return widget

    def add_modern_input_grid(self, grid, row, col, label, key, tip="text", db_kodu=None, stretch=0):
        widget = None
        if tip == "text": widget = QLineEdit()
        elif tip == "combo": widget = QComboBox(); widget.setProperty("db_kodu", db_kodu)
        elif tip == "date": 
            widget = QDateEdit(); widget.setCalendarPopup(True); widget.setDisplayFormat("dd.MM.yyyy")
            widget.setDate(QDate.currentDate())
        g = ModernInputGroup(label, widget)
        grid.addWidget(g, row, col)
        if stretch > 0: grid.setColumnStretch(col, stretch)
        self.inputs[key] = widget

    def create_file_manager(self, card, label, key, is_image=False):
        container = QWidget()
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0,0,0,0)
        lay.setSpacing(5)
        
        edt = QLineEdit()
        edt.setVisible(False)
        
        lbl_status = QLabel("Seçim Bekleniyor...")
        lbl_status.setStyleSheet("color: #666; font-style: italic;")
        
        btn_select = QPushButton("📂 Seç" if not is_image else "📷 Görsel Seç")
        btn_select.setCursor(Qt.PointingHandCursor)
        btn_select.setStyleSheet("background: #333; color: white; border: 1px solid #444; border-radius: 4px; padding: 5px 15px;")
        btn_select.clicked.connect(lambda: self.dosya_sec(key, edt, lbl_status))
        
        lay.addWidget(lbl_status)
        lay.addStretch()
        lay.addWidget(btn_select)
        
        self.inputs[key] = edt
        self.control_buttons[key] = {"status": lbl_status}
        
        grp = ModernInputGroup(label, container)
        container.setStyleSheet("background: transparent;")
        card.add_widget(grp)

    # --- MANTIK ---
    def baslangic_yukle(self):
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.loader = BaslangicYukleyici()
        self.loader.veri_hazir.connect(self.veriler_yuklendi)
        self.loader.start()

    def veriler_yuklendi(self, sabitler, maps, siradaki_no):
        self.progress.setRange(0, 100); self.progress.setValue(100)
        self.map_anabilim = maps["AnaBilimDali"]
        self.map_cihaz_tipi = maps["Cihaz_Tipi"]
        self.map_kaynak = maps["Kaynak"]
        self.siradaki_no = siradaki_no
        
        for widget in self.inputs.values():
            if isinstance(widget, QComboBox):
                db_kodu = widget.property("db_kodu")
                if db_kodu and db_kodu in sabitler:
                    widget.clear()
                    widget.addItem("")
                    widget.addItems(sorted(sabitler[db_kodu]))
        
        self.inputs["AnaBilimDali"].currentTextChanged.connect(self.id_guncelle)
        self.inputs["CihazTipi"].currentTextChanged.connect(self.id_guncelle)
        self.inputs["Kaynak"].currentTextChanged.connect(self.id_guncelle)
        self.id_guncelle()

    def id_guncelle(self):
        abd = self.inputs["AnaBilimDali"].currentText()
        tip = self.inputs["CihazTipi"].currentText()
        kaynak = self.inputs["Kaynak"].currentText()
        
        kisa_abd = self.map_anabilim.get(abd, "GEN") 
        kisa_tip = self.map_cihaz_tipi.get(tip, "CHZ")
        kisa_kaynak = self.map_kaynak.get(kaynak, "D")
        sira_str = str(self.siradaki_no).zfill(3)
        
        final_id = f"{kisa_abd}-{kisa_tip}-{kisa_kaynak}-{sira_str}"
        self.inputs["CihazID"].setText(final_id)

    def dosya_sec(self, key, line_edit, status_label):
        yol, _ = QFileDialog.getOpenFileName(self, "Dosya Seç", "", "Tüm Dosyalar (*.*)")
        if yol:
            line_edit.setText(yol)
            dosya_adi = os.path.basename(yol)
            status_label.setText(f"✅ {dosya_adi}")
            status_label.setStyleSheet("color: #4CAF50;")
            
            if key == "Img":
                self.secilen_resim_yolu = yol
                self.lbl_resim.setPixmap(QPixmap(yol).scaled(250, 250, Qt.KeepAspectRatio))
            elif key == "NDK_Lisans_Belgesi":
                self.secilen_belge_yolu = yol

    def formu_temizle(self):
        for w in self.inputs.values():
            if isinstance(w, QLineEdit): w.clear()
            elif isinstance(w, QComboBox): w.setCurrentIndex(0)
            elif isinstance(w, QDateEdit): w.setDate(QDate.currentDate())
        
        self.secilen_resim_yolu = None
        self.secilen_belge_yolu = None
        self.lbl_resim.setText("Görsel Seçilmedi")
        self.lbl_resim.setPixmap(QPixmap())
        
        for key in ["Img", "NDK_Lisans_Belgesi"]:
            self.control_buttons[key]["status"].setText("Seçim Bekleniyor...")
            self.control_buttons[key]["status"].setStyleSheet("color: #666;")

        self.baslangic_yukle()

    def kaydet_baslat(self):
        cihaz_id = self.inputs["CihazID"].text().strip()
        marka = self.inputs["Marka"].currentText()
        
        if not cihaz_id or not marka:
            show_error("Eksik", "Lütfen en azından Marka ve Birim bilgilerini girin.", self)
            return

        self.btn_kaydet.setText("Kaydediliyor...")
        self.btn_kaydet.setEnabled(False)
        self.progress.setRange(0, 0)
        QApplication.setOverrideCursor(Qt.WaitCursor)

        def v(k):
            w = self.inputs.get(k)
            if not w: return ""
            if isinstance(w, QLineEdit): return w.text().strip()
            if isinstance(w, QComboBox): return w.currentText()
            if isinstance(w, QDateEdit): return w.date().toString("yyyy-MM-dd")
            return ""

        yeni_uuid = str(uuid.uuid4())
        # Google Sheets Cihazlar Sayfası Sırasına Göre
        veri_listesi = [
            yeni_uuid, v("CihazID"), v("CihazTipi"), v("Marka"), v("Model"), v("Amaç"), v("Kaynak"),
            v("SeriNo"), v("NDKSeriNo"), v("HizmeteGirisTarihi"), v("RKS"), v("Sorumlusu"), v("Gorevi"),
            v("NDKLisansNo"), v("BaslamaTarihi"), v("BitisTarihi"), v("LisansDurum"),
            v("AnaBilimDali"), v("Birim"), v("BulunduguBina"), v("GarantiDurumu"),
            v("GarantiBitisTarihi"), v("DemirbasNo"), v("KalibrasyonGereklimi"),
            v("BakimDurum"), v("Durum")
        ]

        form_sozlugu = {
            "cihaz_id": v("CihazID"), "marka": v("Marka"), "model": v("Model"),
            "seri_no": v("SeriNo"), "cihaz_tipi": v("CihazTipi"), "birim": v("Birim"),
            "sorumlu": v("Sorumlusu"), "rks": v("RKS"), "bulundugu_bina": v("BulunduguBina"),
            "hizmete_giris": v("HizmeteGirisTarihi"), "uretim_tarihi": "Bilinmiyor"
        }

        self.saver = KayitIslemi(veri_listesi, self.secilen_resim_yolu, self.secilen_belge_yolu, form_sozlugu)
        self.saver.islem_tamam.connect(self.kayit_basarili)
        self.saver.hata_olustu.connect(self.kayit_hatali)
        self.saver.start()

    def kayit_basarili(self):
        QApplication.restoreOverrideCursor()
        self.progress.setRange(0, 100); self.progress.setValue(100)
        self.btn_kaydet.setText("✅ Sisteme Kaydet")
        self.btn_kaydet.setEnabled(True)
        show_info("Başarılı", "Cihaz kaydedildi ve künye oluşturuldu.", self)
        self.formu_temizle()

    def kayit_hatali(self, hata):
        QApplication.restoreOverrideCursor()
        self.progress.setRange(0, 100); self.progress.setValue(0)
        self.btn_kaydet.setText("✅ Sisteme Kaydet")
        self.btn_kaydet.setEnabled(True)
        show_error("Hata", f"Kayıt Hatası: {hata}", self)

    # 🟢 DEĞİŞİKLİK 4: Thread Güvenliği
    def closeEvent(self, event):
        if hasattr(self, 'loader') and self.loader.isRunning():
            self.loader.quit()
            self.loader.wait(500)
        if hasattr(self, 'saver') and self.saver.isRunning():
            self.saver.quit()
            self.saver.wait(500)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = CihazEklePenceresi()
    win.show()
    sys.exit(app.exec())