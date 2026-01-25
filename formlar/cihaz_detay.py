# -*- coding: utf-8 -*-
import sys
import os
import urllib.request
import re 
import logging
from datetime import datetime

# Gerekli tüm kütüphaneler
from PySide6.QtCore import Qt, QDate, QThread, Signal, QSize, QUrl
from PySide6.QtGui import QPixmap, QCursor, QFont, QColor, QDesktopServices
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QLineEdit, QComboBox, QDateEdit, QPushButton, QMessageBox,
                               QScrollArea, QFrame, QFileDialog, QGridLayout, 
                               QProgressBar, QSizePolicy, QMdiSubWindow, QGraphicsDropShadowEffect,
                               QGroupBox)

# --- LOGLAMA ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CihazDetay")

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# --- İMPORTLAR ---
try:
    from araclar.yetki_yonetimi import YetkiYoneticisi
    from temalar.tema import TemaYonetimi
    
    from google_baglanti import veritabani_getir, GoogleDriveService
    from araclar.ortak_araclar import show_info, show_error, pencereyi_kapat
except ImportError as e:
    print(f"Modül Hatası: {e}")
    # Fallback
    def veritabani_getir(vt, sayfa): return None
    def show_info(t, m, p): print(m)
    def show_error(t, m, p): print(m)
    def pencereyi_kapat(w): w.close()
    class GoogleDriveService:
        def upload_file(self, a, b): return None
    class TemaYonetimi:
        @staticmethod
        def uygula_fusion_dark(app): pass

# Künye Motoru
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
# 1. THREAD SINIFLARI (MANTIK KORUNDU)
# =============================================================================
class VeriYukleyici(QThread):
    veri_hazir = Signal(dict, dict)
    hata_olustu = Signal(str)
    
    def __init__(self, cihaz_id):
        super().__init__()
        self.cihaz_id = str(cihaz_id).strip()

    def run(self):
        try:
            ws = veritabani_getir('cihaz', 'Cihazlar')
            if not ws: raise Exception("Veritabanına erişilemedi.")
            
            # Cihazı Bul
            hedef_satir = None
            tum_veriler = ws.get_all_records()
            
            for row in tum_veriler:
                row_id = str(row.get('cihaz_id') or row.get('CihazID') or "").strip()
                if row_id == self.cihaz_id:
                    hedef_satir = row
                    break
            
            if not hedef_satir:
                raise Exception("Cihaz bulunamadı.")

            # Sabitleri Çek
            sabitler = {}
            ws_sabit = veritabani_getir('sabit', 'Sabitler')
            if ws_sabit:
                for s in ws_sabit.get_all_records():
                    kod = str(s.get('Kod', '')).strip()
                    val = str(s.get('MenuEleman', '')).strip()
                    if kod and val:
                        if kod not in sabitler: sabitler[kod] = []
                        sabitler[kod].append(val)

            self.veri_hazir.emit(hedef_satir, sabitler)

        except Exception as e:
            self.hata_olustu.emit(str(e))

class GuncellemeIslemi(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)

    def __init__(self, cihaz_id, guncel_veri, dosya_yollari, mevcut_linkler):
        super().__init__()
        self.cihaz_id = cihaz_id
        self.veri = guncel_veri
        self.dosyalar = dosya_yollari
        self.linkler = mevcut_linkler

    def run(self):
        try:
            drive = GoogleDriveService()
            ws = veritabani_getir('cihaz', 'Cihazlar')
            
            # 1. Dosya Yükleme
            if self.dosyalar.get("Img"):
                link = drive.upload_file(self.dosyalar["Img"], DRIVE_KLASORLERI["CIHAZ_RESIMLERI"])
                if link: self.linkler["Resim"] = link
                
            if self.dosyalar.get("NDK_Lisans_Belgesi"):
                link = drive.upload_file(self.dosyalar["NDK_Lisans_Belgesi"], DRIVE_KLASORLERI["CIHAZ_BELGELERI"])
                if link: self.linkler["Belge"] = link

            # 2. Veri Güncelleme
            cell = ws.find(self.cihaz_id)
            if not cell: raise Exception("Cihaz satırı bulunamadı.")
            
            # Sütun başlıklarını al ve indexle
            headers = ws.row_values(1)
            header_map = {h.strip(): i+1 for i, h in enumerate(headers)}
            
            updates = []
            
            # Form verilerini eşle
            mapping = {
                "Marka": "marka", "Model": "model", "CihazTipi": "cihaz_tipi",
                "Kaynak": "kaynak", "SeriNo": "seri_no", "NDKSeriNo": "ndk_seri_no",
                "LisansDurum": "lisans_durum", "AnaBilimDali": "ana_bilim_dali",
                "BulunduguBina": "bulundugu_bina", "Sorumlusu": "sorumlu",
                "RKS": "rks", "Durum": "durum", "DemirbasNo": "demirbas_no",
                "Amaç": "kullanim_amaci", "Birim": "birim"
            }
            
            # Tarih alanları
            date_fields = ["HizmeteGirisTarihi", "BaslamaTarihi", "BitisTarihi", "GarantiBitisTarihi"]
            
            # Basit alanları güncelle
            for db_col, form_key in mapping.items():
                if db_col in header_map and form_key in self.veri:
                    updates.append({
                        'range': f"{chr(64+header_map[db_col])}{cell.row}",
                        'values': [[self.veri[form_key]]]
                    })

            # Tarihleri güncelle
            for f in date_fields:
                key = f.lower() # Form sözlüğündeki anahtar (örn: hizmetegiristarihi)
                if f in header_map and key in self.veri:
                     updates.append({
                        'range': f"{chr(64+header_map[f])}{cell.row}",
                        'values': [[self.veri[key]]]
                    })

            # Linkleri güncelle (Img, NDK_Lisans_Belgesi sütunları varsayılıyor)
            # Sütun adları tam eşleşmeli, yoksa atlar
            if "Img" in header_map and "Resim" in self.linkler:
                 updates.append({'range': f"{chr(64+header_map['Img'])}{cell.row}", 'values': [[self.linkler['Resim']]]})
            
            if "NDK_Lisans_Belgesi" in header_map and "Belge" in self.linkler:
                 updates.append({'range': f"{chr(64+header_map['NDK_Lisans_Belgesi'])}{cell.row}", 'values': [[self.linkler['Belge']]]})

            if updates:
                ws.batch_update(updates)

            # 3. Künye Yenileme (Opsiyonel)
            if KunyeOlusturucu:
                try:
                    # Künye için tüm veriyi birleştir
                    kunye_veri = self.veri.copy()
                    kunye_veri['cihaz_id'] = self.cihaz_id
                    
                    sablon_path = os.path.join(root_dir, "sablon", "cihaz_kunye.docx")
                    if os.path.exists(sablon_path):
                        motor = KunyeOlusturucu(sablon_path)
                        pdf_path = motor.belge_olustur(kunye_veri)
                        if pdf_path:
                            drive.upload_file(pdf_path, DRIVE_KLASORLERI["CIHAZ_KUNYE_PDF"])
                            os.remove(pdf_path)
                            motor.temizle()
                except: pass

            self.islem_tamam.emit()

        except Exception as e:
            self.hata_olustu.emit(str(e))

class ResimIndirici(QThread):
    resim_indi = Signal(QPixmap)
    
    def __init__(self, url):
        super().__init__()
        self.url = url
        
    def run(self):
        try:
            if not self.url: return
            # Drive ID ayıklama
            file_id = None
            if "id=" in self.url: file_id = self.url.split("id=")[1].split("&")[0]
            elif "/d/" in self.url: file_id = self.url.split("/d/")[1].split("/")[0]
            
            if file_id:
                dl_url = f"https://drive.google.com/uc?export=download&id={file_id}"
                data = urllib.request.urlopen(dl_url).read()
                pix = QPixmap()
                pix.loadFromData(data)
                self.resim_indi.emit(pix)
        except: pass

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
        
        # Manuel stiller kaldırıldı, tema.py yönetecek
        
        if widget: widget.setObjectName(f"inp_{label_text.replace(' ', '_')}")
            
        layout.addWidget(self.lbl)
        layout.addWidget(self.widget)

class InfoCard(QGroupBox):
    """
    Görsel gruplama sağlayan kart bileşeni.
    """
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        
        self.setStyleSheet("""
            QGroupBox {
                background-color: #2d2d2d;
                border: 1px solid #444;
                border-radius: 8px;
                margin-top: 20px; 
                font-weight: bold;
                color: #60cdff; 
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 10px;
                left: 10px;
            }
        """)
        
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 100))
        self.setGraphicsEffect(shadow)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 20, 15, 15)
        self.layout.setSpacing(15)

    def add_widget(self, widget):
        self.layout.addWidget(widget)

    def add_layout(self, layout):
        self.layout.addLayout(layout)

# =============================================================================
# 3. ANA PENCERE: CİHAZ DETAY
# =============================================================================
class CihazDetayPenceresi(QWidget):
    def __init__(self, cihaz_id, yetki='viewer', kullanici_adi=None, ana_pencere=None):
        super().__init__()
        self.cihaz_id = str(cihaz_id)
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        self.ana_pencere = ana_pencere
        
        self.setWindowTitle(f"Cihaz Detay: {self.cihaz_id}")
        self.resize(1200, 850)
        
        self.inputs = {}
        self.mevcut_veri = {}
        self.dosya_degisiklikleri = {} # {"Img": path, "NDK": path}
        self.linkler = {"Resim": "", "Belge": ""}
        
        self.duzenleme_modu = False
        
        self.setup_ui()
        
        # Yetki Uygulama
        YetkiYoneticisi.uygula(self, "cihaz_detay")
        
        self.verileri_yukle()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0,0,0,0)
        main_layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setFixedHeight(60)
        header.setObjectName("panel_frame")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(25, 0, 25, 0)
        
        self.lbl_baslik = QLabel(f"Cihaz: {self.cihaz_id}")
        self.lbl_baslik.setFont(QFont("Segoe UI", 16, QFont.Bold))
        
        self.progress = QProgressBar()
        self.progress.setFixedSize(150, 6)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("QProgressBar {background: #333; border-radius: 3px;} QProgressBar::chunk {background: #4dabf7; border-radius: 3px;}")
        
        h_lay.addWidget(self.lbl_baslik)
        h_lay.addStretch()
        h_lay.addWidget(self.progress)
        main_layout.addWidget(header)

        # Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        content = QWidget()
        
        grid = QGridLayout(content)
        grid.setContentsMargins(25, 25, 25, 25)
        grid.setSpacing(25)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 2)

        # --- SOL KOLON (Medya & Kimlik ID) ---
        card_media = InfoCard("Medya & Dosyalar")
        
        # 1. CİHAZ ID
        self.add_modern_input(card_media, "Cihaz ID", "CihazID")
        # Stil temizliği: QComboBox gibi bazı widget'lar setReadOnly desteklemez
        if "CihazID" in self.inputs:
            self.inputs["CihazID"].setStyleSheet("background-color: #202020; color: #4dabf7; font-weight: bold;")
        
        # 2. Resim Alanı
        self.lbl_resim = QLabel("Yükleniyor...")
        self.lbl_resim.setFixedSize(250, 250)
        self.lbl_resim.setStyleSheet("border: 2px dashed #444; border-radius: 8px; color: #666;")
        self.lbl_resim.setAlignment(Qt.AlignCenter)
        self.lbl_resim.setScaledContents(True)
        card_media.add_widget(self.lbl_resim)
        
        # 3. Dosya Butonları
        h_btn_img = QHBoxLayout()
        self.btn_resim_degis = QPushButton("📷 Değiştir")
        self.btn_resim_degis.setCursor(Qt.PointingHandCursor)
        self.btn_resim_degis.clicked.connect(self.resim_sec)
        self.btn_resim_degis.setVisible(False)
        h_btn_img.addWidget(self.btn_resim_degis)
        card_media.add_layout(h_btn_img)
        
        # Lisans Belgesi
        h_belge = QHBoxLayout()
        self.btn_belge_gor = QPushButton("📄 Belgeyi Aç")
        self.btn_belge_gor.setCursor(Qt.PointingHandCursor)
        self.btn_belge_gor.clicked.connect(lambda: self.link_ac("Belge"))
        
        self.btn_belge_yukle = QPushButton("📤 Yükle")
        self.btn_belge_yukle.setCursor(Qt.PointingHandCursor)
        self.btn_belge_yukle.clicked.connect(self.belge_sec)
        self.btn_belge_yukle.setVisible(False)
        
        h_belge.addWidget(self.btn_belge_gor)
        h_belge.addWidget(self.btn_belge_yukle)
        card_media.add_layout(h_belge)
        
        # 4. DEMİRBAŞ NO
        self.add_modern_input(card_media, "Demirbaş No", "DemirbasNo")
        
        card_media.layout.addStretch()
        grid.addWidget(card_media, 0, 0, 2, 1)

        # --- ORTA KOLON (Kimlik) ---
        card_kimlik = InfoCard("Kimlik Bilgileri")
        
        row1 = QHBoxLayout(); row1.setSpacing(15)
        self.add_modern_input(row1, "Marka", "Marka", "combo", db_kodu="Marka", stretch=1)
        self.add_modern_input(row1, "Model", "Model", stretch=1)
        card_kimlik.add_layout(row1)
        
        row2 = QHBoxLayout(); row2.setSpacing(15)
        self.add_modern_input(row2, "Cihaz Tipi", "CihazTipi", "combo", db_kodu="Cihaz_Tipi", stretch=1)
        self.add_modern_input(row2, "Seri No", "SeriNo", stretch=1)
        card_kimlik.add_layout(row2)
        
        # AMAÇ ve KAYNAK Yan Yana
        row_amac_kaynak = QHBoxLayout(); row_amac_kaynak.setSpacing(15)
        self.add_modern_input(row_amac_kaynak, "Kullanım Amacı", "Amaç", "combo", db_kodu="Amaç", stretch=1)
        self.add_modern_input(row_amac_kaynak, "Edinim Kaynağı", "Kaynak", "combo", db_kodu="Kaynak", stretch=1)
        card_kimlik.add_layout(row_amac_kaynak)
        
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

        # Demirbaş No buradan kaldırıldı
        
        card_teknik.add_layout(t_grid)
        grid.addWidget(card_teknik, 1, 1, 1, 2)

        scroll.setWidget(content)
        main_layout.addWidget(scroll)

        # Footer
        footer = QFrame()
        footer.setFixedHeight(80)
        footer.setObjectName("panel_frame")
        foot_lay = QHBoxLayout(footer)
        foot_lay.setContentsMargins(30, 15, 30, 15)
        foot_lay.setSpacing(15)
        
        self.btn_kapat = QPushButton("Kapat")
        self.btn_kapat.setObjectName("btn_iptal")
        self.btn_kapat.setFixedSize(120, 45)
        self.btn_kapat.setCursor(Qt.PointingHandCursor)
        self.btn_kapat.clicked.connect(self.pencereyi_kapat)
        
        self.btn_duzenle = QPushButton("✏️ Düzenle")
        self.btn_duzenle.setObjectName("btn_duzenle")
        self.btn_duzenle.setFixedSize(150, 45)
        self.btn_duzenle.setCursor(Qt.PointingHandCursor)
        self.btn_duzenle.clicked.connect(self.duzenle_modunu_ac)
        
        self.btn_kaydet = QPushButton("💾 Değişiklikleri Kaydet")
        self.btn_kaydet.setObjectName("btn_kaydet")
        self.btn_kaydet.setFixedSize(220, 45)
        self.btn_kaydet.setCursor(Qt.PointingHandCursor)
        self.btn_kaydet.setVisible(False)
        self.btn_kaydet.clicked.connect(self.kaydet_baslat)
        
        foot_lay.addWidget(self.btn_kapat)
        foot_lay.addStretch()
        foot_lay.addWidget(self.btn_duzenle)
        foot_lay.addWidget(self.btn_kaydet)
        
        main_layout.addWidget(footer)

    # --- UI FONKSİYONLARI ---
    def add_modern_input(self, parent, label, key, tip="text", db_kodu=None, stretch=0):
        widget = None
        if tip == "text": widget = QLineEdit()
        elif tip == "combo": widget = QComboBox(); widget.setProperty("db_kodu", db_kodu)
        elif tip == "date": 
            widget = QDateEdit(); widget.setCalendarPopup(True); widget.setDisplayFormat("dd.MM.yyyy")
        
        if widget:
            # FIX: setReadOnly kontrolü
            if hasattr(widget, "setReadOnly"):
                widget.setReadOnly(True)
            widget.setEnabled(False) 
            widget.setObjectName(f"inp_{key}")
            
        grp = ModernInputGroup(label, widget)
        
        if isinstance(parent, InfoCard): parent.add_widget(grp)
        elif hasattr(parent, "addWidget"): parent.addWidget(grp, stretch)
        elif hasattr(parent, "addLayout"): parent.addLayout(grp)
        self.inputs[key] = widget
        return widget

    def add_modern_input_grid(self, grid, row, col, label, key, tip="text", db_kodu=None, stretch=0):
        widget = None
        if tip == "text": widget = QLineEdit()
        elif tip == "combo": widget = QComboBox(); widget.setProperty("db_kodu", db_kodu)
        elif tip == "date": 
            widget = QDateEdit(); widget.setCalendarPopup(True); widget.setDisplayFormat("dd.MM.yyyy")
        
        if widget:
            # FIX: setReadOnly kontrolü
            if hasattr(widget, "setReadOnly"):
                widget.setReadOnly(True)
            widget.setEnabled(False)
            
        g = ModernInputGroup(label, widget)
        grid.addWidget(g, row, col)
        if stretch > 0: grid.setColumnStretch(col, stretch)
        self.inputs[key] = widget

    # --- MANTIK ---
    def verileri_yukle(self):
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.worker = VeriYukleyici(self.cihaz_id)
        self.worker.veri_hazir.connect(self.veriler_geldi)
        self.worker.hata_olustu.connect(self.hata_goster)
        self.worker.start()

    def veriler_geldi(self, veri, sabitler):
        self.progress.setRange(0, 100); self.progress.setValue(100)
        self.mevcut_veri = veri
        
        # 1. Sabitleri Doldur
        for w in self.inputs.values():
            if isinstance(w, QComboBox):
                kod = w.property("db_kodu")
                if kod and kod in sabitler:
                    w.clear(); w.addItems(sorted(sabitler[kod]))

        # 2. Değerleri Yaz
        try:
            self.inputs["CihazID"].setText(str(veri.get("cihaz_id") or veri.get("CihazID") or ""))
            self.inputs["Marka"].setCurrentText(str(veri.get("Marka", "")))
            self.inputs["Model"].setText(str(veri.get("Model", "")))
            self.inputs["CihazTipi"].setCurrentText(str(veri.get("Cihaz_Tipi", "")))
            self.inputs["SeriNo"].setText(str(veri.get("SeriNo", "")))
            self.inputs["Birim"].setCurrentText(str(veri.get("Birim", "")))
            self.inputs["BulunduguBina"].setText(str(veri.get("BulunduguBina", "")))
            self.inputs["AnaBilimDali"].setCurrentText(str(veri.get("AnaBilimDali", "")))
            self.inputs["Sorumlusu"].setText(str(veri.get("Sorumlusu", "")))
            self.inputs["RKS"].setText(str(veri.get("RKS", "")))
            self.inputs["NDKLisansNo"].setText(str(veri.get("NDKLisansNo", "")))
            self.inputs["LisansDurum"].setCurrentText(str(veri.get("LisansDurum", "")))
            self.inputs["GarantiDurumu"].setCurrentText(str(veri.get("GarantiDurumu", "")))
            self.inputs["BakimDurum"].setCurrentText(str(veri.get("BakimDurum", "")))
            self.inputs["KalibrasyonGereklimi"].setCurrentText(str(veri.get("KalibrasyonGereklimi", "")))
            self.inputs["Durum"].setCurrentText(str(veri.get("Durum", "")))
            self.inputs["DemirbasNo"].setText(str(veri.get("DemirbasNo", "")))
            self.inputs["Amaç"].setCurrentText(str(veri.get("KullanimAmaci", "")))
            self.inputs["Kaynak"].setCurrentText(str(veri.get("Kaynak", "")))

            # Tarihler
            for key in ["HizmeteGirisTarihi", "BitisTarihi", "GarantiBitisTarihi"]:
                if key in self.inputs:
                    val = str(veri.get(key, ""))
                    if val:
                        try:
                            d = datetime.strptime(val, "%d.%m.%Y")
                            self.inputs[key].setDate(d)
                        except: pass
            
            # 3. Dosyalar
            self.linkler["Resim"] = str(veri.get("Img", ""))
            self.linkler["Belge"] = str(veri.get("NDK_Lisans_Belgesi", ""))
            
            if self.linkler["Resim"]:
                self.resim_loader = ResimIndirici(self.linkler["Resim"])
                self.resim_loader.resim_indi.connect(lambda p: self.lbl_resim.setPixmap(p.scaled(250, 250, Qt.KeepAspectRatio)))
                self.resim_loader.start()
            else:
                self.lbl_resim.setText("Resim Yok")

        except Exception as e:
            logger.error(f"Veri doldurma hatası: {e}")

    def duzenle_modunu_ac(self):
        self.duzenleme_modu = True
        self.btn_duzenle.setVisible(False)
        self.btn_kaydet.setVisible(True)
        self.btn_resim_degis.setVisible(True)
        self.btn_belge_yukle.setVisible(True)
        
        for k, w in self.inputs.items():
            if k == "CihazID": continue # ID değişmez
            # FIX: setReadOnly
            if hasattr(w, "setReadOnly"): w.setReadOnly(False)
            w.setEnabled(True)

    def resim_sec(self):
        yol, _ = QFileDialog.getOpenFileName(self, "Resim Seç", "", "Resimler (*.jpg *.png)")
        if yol:
            self.dosya_degisiklikleri["Img"] = yol
            self.lbl_resim.setPixmap(QPixmap(yol).scaled(250, 250, Qt.KeepAspectRatio))

    def belge_sec(self):
        yol, _ = QFileDialog.getOpenFileName(self, "Belge Seç", "", "PDF Dosyası (*.pdf)")
        if yol:
            self.dosya_degisiklikleri["NDK_Lisans_Belgesi"] = yol
            self.btn_belge_gor.setText("📄 Yeni Belge Seçildi")

    def link_ac(self, key):
        link = self.linkler.get(key)
        if link: QDesktopServices.openUrl(QUrl(link))
        else: show_info("Bilgi", "Dosya bulunamadı.", self)

    def kaydet_baslat(self):
        if not self.duzenleme_modu: return
        
        self.btn_kaydet.setEnabled(False)
        self.btn_kaydet.setText("Kaydediliyor...")
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        
        # Verileri topla
        guncel = {}
        for k, w in self.inputs.items():
            val = ""
            if isinstance(w, QLineEdit): val = w.text().strip()
            elif isinstance(w, QComboBox): val = w.currentText()
            elif isinstance(w, QDateEdit): val = w.date().toString("dd.MM.yyyy")
            
            guncel[k.lower()] = val
            # Özel mappingler
            if k == "CihazTipi": guncel["cihaz_tipi"] = val
            if k == "SeriNo": guncel["seri_no"] = val
            if k == "NDKSeriNo": guncel["ndk_seri_no"] = val
            if k == "AnaBilimDali": guncel["ana_bilim_dali"] = val
            if k == "BulunduguBina": guncel["bulundugu_bina"] = val
            if k == "NDKLisansNo": guncel["ndk_lisans_no"] = val
            if k == "LisansDurum": guncel["lisans_durum"] = val
            if k == "DemirbasNo": guncel["demirbas_no"] = val
            if k == "Amaç": guncel["kullanim_amaci"] = val

        self.updater = GuncellemeIslemi(self.cihaz_id, guncel, self.dosya_degisiklikleri, self.linkler)
        self.updater.islem_tamam.connect(self.guncelleme_basarili)
        self.updater.hata_olustu.connect(self.guncelleme_hatali)
        self.updater.start()

    def guncelleme_basarili(self):
        QApplication.restoreOverrideCursor()
        self.progress.setRange(0, 100); self.progress.setValue(100)
        show_info("Başarılı", "Kayıt güncellendi ve PDF künye yenilendi.", self)
        if self.ana_pencere and hasattr(self.ana_pencere, 'verileri_yenile'):
            self.ana_pencere.verileri_yenile()
        self.pencereyi_kapat()

    def guncelleme_hatali(self, hata):
        QApplication.restoreOverrideCursor()
        self.progress.setRange(0, 100); self.progress.setValue(0)
        show_error("Hata", f"Güncelleme hatası: {hata}", self)
        self.btn_kaydet.setEnabled(True)
        self.btn_kaydet.setText("Değişiklikleri Kaydet")
        self.btn_kapat.setEnabled(True)

    def pencereyi_kapat(self):
        pencereyi_kapat(self)

    def hata_goster(self, m):
        show_error("Hata", m, self)
        self.progress.setVisible(False)

    def closeEvent(self, event):
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(500)
        if hasattr(self, 'updater') and self.updater.isRunning():
            self.updater.quit()
            self.updater.wait(500)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    try:
        TemaYonetimi.uygula_fusion_dark(app)
    except Exception as e:
        print(f"Tema uygulanamadı: {e}")
        app.setStyle("Fusion")
        
    win = CihazDetayPenceresi("GEN-CHZ-D-001") # Test ID
    win.show()
    sys.exit(app.exec())