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
                               QProgressBar, QSizePolicy, QMdiSubWindow, QGraphicsDropShadowEffect)

# --- LOGLAMA ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CihazDetay")

# --- ANA KLASÖR BAĞLANTISI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from araclar.yetki_yonetimi import YetkiYoneticisi

# --- İMPORTLAR ---
try:
    from google_baglanti import veritabani_getir, GoogleDriveService
    from araclar.ortak_araclar import show_info, show_error, pencereyi_kapat
except ImportError:
    def veritabani_getir(vt, sayfa): return None
    def show_info(t, m, p): print(m)
    def show_error(t, m, p): print(m)
    def pencereyi_kapat(w): w.close()
    class GoogleDriveService:
        def upload_file(self, a, b): return None

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
# 1. THREAD SINIFLARI
# =============================================================================
class ResimYukleyici(QThread):
    resim_indi = Signal(QPixmap)
    hata = Signal()
    def __init__(self, url):
        super().__init__()
        self.url = url
    def run(self):
        try:
            indirilebilir_url = self.url
            if "drive.google.com" in self.url and "/d/" in self.url:
                match = re.search(r'/d/([a-zA-Z0-9_-]+)', self.url)
                if match:
                    file_id = match.group(1)
                    indirilebilir_url = f"https://drive.google.com/uc?export=view&id={file_id}"
            req = urllib.request.Request(indirilebilir_url, headers={'User-Agent': 'Mozilla/5.0'})
            data = urllib.request.urlopen(req, timeout=10).read()
            pix = QPixmap()
            pix.loadFromData(data)
            if not pix.isNull(): self.resim_indi.emit(pix)
            else: self.hata.emit()
        except: self.hata.emit()

class VeriYukleyici(QThread):
    veri_hazir = Signal(dict)
    hata_olustu = Signal(str)
    def __init__(self, cihaz_id):
        super().__init__()
        self.cihaz_id = str(cihaz_id).strip()
    def run(self):
        paket = {"sabitler": {}, "cihaz_verisi": None, "satir_no": None}
        try:
            ws_sabit = veritabani_getir('sabit', 'Sabitler')
            if ws_sabit:
                kayitlar = ws_sabit.get_all_records()
                for row in kayitlar:
                    kod = str(row.get('Kod', '')).strip()
                    eleman = str(row.get('MenuEleman', '')).strip()
                    if kod and eleman:
                        if kod not in paket["sabitler"]: paket["sabitler"][kod] = []
                        paket["sabitler"][kod].append(eleman)
            ws_cihaz = veritabani_getir('cihaz', 'Cihazlar')
            if ws_cihaz:
                tum_satirlar = ws_cihaz.get_all_values()
                if tum_satirlar:
                    basliklar = [str(b).strip() for b in tum_satirlar[0]]
                    col_map = {name: idx for idx, name in enumerate(basliklar)}
                    id_col_idx = -1
                    for aday in ['cihaz_id', 'CihazID', 'kayit_no']:
                        if aday in col_map: id_col_idx = col_map[aday]; break
                    if id_col_idx != -1:
                        for i, satir in enumerate(tum_satirlar[1:], start=2):
                            if len(satir) > id_col_idx:
                                if str(satir[id_col_idx]).strip() == self.cihaz_id:
                                    hedef_veri = {}
                                    for col_name, col_idx in col_map.items():
                                        if col_idx < len(satir):
                                            hedef_veri[col_name] = satir[col_idx]
                                    paket["cihaz_verisi"] = hedef_veri
                                    paket["satir_no"] = i
                                    break
            self.veri_hazir.emit(paket)
        except Exception as e: self.hata_olustu.emit(str(e))

class GuncellemeIslemi(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)
    def __init__(self, satir_no, db_internal_id, form_inputlari, secilen_resim, secilen_belge, mevcut_resim_link, mevcut_belge_link, sozluk_veri):
        super().__init__()
        self.satir_no = satir_no
        self.db_internal_id = db_internal_id
        self.inputs = form_inputlari
        self.secilen_resim = secilen_resim
        self.secilen_belge = secilen_belge
        self.mevcut_resim_link = mevcut_resim_link
        self.mevcut_belge_link = mevcut_belge_link
        self.sozluk_veri = sozluk_veri

    def run(self):
        try:
            drive = GoogleDriveService()
            yeni_resim_link = self.mevcut_resim_link
            if self.secilen_resim and os.path.exists(self.secilen_resim):
                link = drive.upload_file(self.secilen_resim, DRIVE_KLASORLERI["CIHAZ_RESIMLERI"])
                if link: yeni_resim_link = link
            yeni_belge_link = self.mevcut_belge_link
            if self.secilen_belge and os.path.exists(self.secilen_belge):
                link = drive.upload_file(self.secilen_belge, DRIVE_KLASORLERI["CIHAZ_BELGELERI"])
                if link: yeni_belge_link = link
            
            if KunyeOlusturucu:
                try:
                    sablon_path = os.path.join(root_dir, "sablon", "cihaz_kunye.docx")
                    if os.path.exists(sablon_path):
                        motor = KunyeOlusturucu(sablon_path)
                        gecici_pdf = motor.belge_olustur(self.sozluk_veri)
                        if gecici_pdf and os.path.exists(gecici_pdf):
                            raw_id = self.sozluk_veri.get('cihaz_id', 'Isimsiz')
                            safe_id = str(raw_id).replace('/', '-').replace('\\', '-').strip()
                            yeni_isim = f"{safe_id}_kunye.pdf"
                            yeni_yol = os.path.join(os.path.dirname(gecici_pdf), yeni_isim)
                            if os.path.exists(yeni_yol): os.remove(yeni_yol)
                            os.rename(gecici_pdf, yeni_yol)
                            drive.upload_file(yeni_yol, DRIVE_KLASORLERI["CIHAZ_KUNYE_PDF"])
                            if os.path.exists(yeni_yol): os.remove(yeni_yol)
                            motor.temizle()
                except Exception as k_hata: logger.error(f"Künye hatası: {k_hata}")

            v = self.inputs
            guncel_veri = [
                self.db_internal_id, 
                v.get("CihazID"), v.get("CihazTipi"), v.get("Marka"), v.get("Model"), v.get("Amaç"), 
                v.get("Kaynak"), v.get("SeriNo"), v.get("NDKSeriNo"), v.get("HizmeteGirisTarihi"),
                v.get("RKS"), v.get("Sorumlusu"), v.get("Gorevi"), v.get("NDKLisansNo"),
                v.get("BaslamaTarihi"), v.get("BitisTarihi"), v.get("LisansDurum"), v.get("AnaBilimDali"),
                v.get("Birim"), v.get("BulunduguBina"), v.get("GarantiDurumu"), v.get("GarantiBitisTarihi"),
                v.get("DemirbasNo"), v.get("KalibrasyonGereklimi"), v.get("BakimDurum"), v.get("Durum"),
                yeni_resim_link, yeni_belge_link
            ]
            ws = veritabani_getir('cihaz', 'Cihazlar')
            range_str = f"A{self.satir_no}:AB{self.satir_no}"
            ws.update(range_str, [guncel_veri])
            self.islem_tamam.emit()
        except Exception as e: self.hata_olustu.emit(str(e))

# =============================================================================
# 2. UI: MODERN KONTROLLER (cihaz_ekle.py ile EŞİTLENDİ)
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
# 3. ANA PENCERE
# =============================================================================
class CihazDetayPenceresi(QWidget):
    def __init__(self, cihaz_id, yetki='viewer', kullanici_adi=None, ana_pencere=None):
        super().__init__()
        self.target_id = str(cihaz_id).strip()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        self.ana_pencere = ana_pencere
        
        self.setWindowTitle(f"Cihaz Detay Kartı | {self.target_id}")
        self.resize(1200, 850)
        self.setStyleSheet("background-color: #121212;")

        # --- Değişkenler ---
        self.inputs = {}
        self.sabit_veriler = {}
        self.control_buttons = {}
        self.satir_numarasi = None
        self.mevcut_resim_url = "" 
        self.mevcut_lisans_url = "" 
        self.secilen_yeni_resim = None
        self.secilen_yeni_belge = None
        self.db_internal_id = "" 
        self.son_gelen_paket = None

        self.setup_ui()
        YetkiYoneticisi.uygula(self, "cihaz_detay")
        self.verileri_yukle_baslat()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0,0,0,0)
        main_layout.setSpacing(0)

        # HEADER (cihaz_ekle ile aynı stil)
        header = QFrame()
        header.setFixedHeight(60)
        header.setStyleSheet("background-color: #1e1e1e; border-bottom: 1px solid #333;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(25, 0, 25, 0)
        
        lbl_baslik = QLabel(f"Cihaz Yönetimi: {self.target_id}")
        lbl_baslik.setFont(QFont("Segoe UI", 16, QFont.Bold))
        lbl_baslik.setStyleSheet("color: #ffffff;")
        
        self.progress = QProgressBar()
        self.progress.setFixedSize(150, 6)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("QProgressBar {background: #333; border-radius: 3px;} QProgressBar::chunk {background: #4dabf7; border-radius: 3px;}")
        
        h_layout.addWidget(lbl_baslik)
        h_layout.addStretch()
        h_layout.addWidget(self.progress)
        main_layout.addWidget(header)

        # SCROLL AREA
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        
        # GRID LAYOUT (3 Kolonlu Yapı)
        grid = QGridLayout(content)
        grid.setContentsMargins(25, 25, 25, 25)
        grid.setSpacing(25)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 2)

        # --- SOL KOLON (Medya) ---
        card_media = InfoCard("Medya & Dosyalar")
        self.lbl_resim = QLabel("Yükleniyor...")
        self.lbl_resim.setFixedSize(250, 250)
        self.lbl_resim.setStyleSheet("background-color: #000; border-radius: 8px; border: 1px solid #333; color: #666;")
        self.lbl_resim.setScaledContents(True)
        self.lbl_resim.setAlignment(Qt.AlignCenter)
        card_media.add_widget(self.lbl_resim)
        
        self.create_file_manager(card_media, "Görsel İşlemleri", "Img", is_image=True)
        self.create_file_manager(card_media, "NDK Lisans Belgesi", "NDK_Lisans_Belgesi", is_image=False)
        
        card_media.layout.addStretch()
        grid.addWidget(card_media, 0, 0, 2, 1)

        # --- ORTA KOLON (Kimlik) ---
        card_kimlik = InfoCard("Kimlik Bilgileri")
        self.add_modern_input(card_kimlik, "Cihaz ID", "CihazID")
        
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
        self.add_modern_input(row3, "Birim", "Birim", "combo", db_kodu="Birim", stretch=1)
        self.add_modern_input(row3, "Bulunduğu Bina", "BulunduguBina", stretch=1)
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

        # FOOTER
        action_bar = QFrame()
        action_bar.setFixedHeight(80)
        action_bar.setStyleSheet("background-color: #1e1e1e; border-top: 1px solid #333;")
        act_lay = QHBoxLayout(action_bar)
        act_lay.setContentsMargins(30, 15, 30, 15)
        act_lay.setSpacing(15)
        
        self.btn_kapat = QPushButton("Vazgeç / Kapat")
        self.btn_kapat.setObjectName("btn_kapat")
        self.btn_kapat.setFixedSize(140, 45)
        self.btn_kapat.setCursor(Qt.PointingHandCursor)
        self.btn_kapat.setStyleSheet("""
            QPushButton { background: transparent; border: 1px solid #555; color: #aaa; border-radius: 8px; font-weight: bold; }
            QPushButton:hover { background: #333; color: white; border-color: #777; }
        """)
        self.btn_kapat.clicked.connect(self.kapat_veya_iptal)
        
        self.btn_duzenle = QPushButton("Bilgileri Düzenle")
        self.btn_duzenle.setObjectName("btn_duzenle")
        self.btn_duzenle.setFixedSize(160, 45)
        self.btn_duzenle.setCursor(Qt.PointingHandCursor)
        self.btn_duzenle.setEnabled(False)
        self.btn_duzenle.setStyleSheet("""
            QPushButton { background-color: #2563eb; color: white; border: none; border-radius: 8px; font-weight: bold; font-size: 14px; }
            QPushButton:hover { background-color: #1d4ed8; }
            QPushButton:disabled { background-color: #333; color: #555; }
        """)
        self.btn_duzenle.clicked.connect(self.duzenleme_modunu_ac)
        
        self.btn_kaydet = QPushButton("Değişiklikleri Kaydet")
        self.btn_kaydet.setObjectName("btn_kaydet")
        self.btn_kaydet.setFixedSize(200, 45)
        self.btn_kaydet.setCursor(Qt.PointingHandCursor)
        self.btn_kaydet.setVisible(False)
        self.btn_kaydet.setStyleSheet("""
            QPushButton { background-color: #16a34a; color: white; border: none; border-radius: 8px; font-weight: bold; font-size: 14px; }
            QPushButton:hover { background-color: #15803d; }
        """)
        self.btn_kaydet.clicked.connect(self.guncelleme_baslat)
        
        act_lay.addWidget(self.btn_kapat)
        act_lay.addStretch()
        act_lay.addWidget(self.btn_duzenle)
        act_lay.addWidget(self.btn_kaydet)
        main_layout.addWidget(action_bar)

    # --- UI YARDIMCILARI ---
    def add_modern_input(self, parent, label, key, tip="text", db_kodu=None, stretch=0):
        widget = None
        if tip == "text": widget = QLineEdit()
        elif tip == "combo": widget = QComboBox(); widget.setProperty("db_kodu", db_kodu)
        elif tip == "date": 
            widget = QDateEdit(); widget.setCalendarPopup(True); widget.setDisplayFormat("dd.MM.yyyy")
            widget.setDate(QDate.currentDate())
            
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
        
        lbl_status = QLabel("Yükleniyor...")
        lbl_status.setStyleSheet("color: #666; font-style: italic; font-size: 12px;")
        
        btn_view = QPushButton("📄 Belgeyi Aç")
        btn_view.setCursor(Qt.PointingHandCursor)
        btn_view.setStyleSheet("background: #333; color: #4dabf7; border: 1px solid #444; border-radius: 4px; padding: 5px;")
        btn_view.clicked.connect(lambda: self.dosyayi_ac(edt.text()))
        btn_view.setVisible(False)
        
        btn_change = QPushButton("📷 Değiştir" if is_image else "📂 Belge Yükle")
        btn_change.setCursor(Qt.PointingHandCursor)
        btn_change.setStyleSheet("background: #444; color: white; border-radius: 4px; border:none; padding: 5px 10px;")
        btn_change.setVisible(False)
        btn_change.clicked.connect(lambda: self.dosya_sec(key, edt, lbl_status))
        
        lay.addWidget(lbl_status)
        lay.addStretch()
        if not is_image: lay.addWidget(btn_view)
        lay.addWidget(btn_change)
        
        self.inputs[key] = edt
        self.control_buttons[key] = {
            "view": btn_view, 
            "status": lbl_status, 
            "change": btn_change
        }
        
        grp = ModernInputGroup(label, container)
        container.setStyleSheet("background: transparent; border: none;")
        card.add_widget(grp)

    def dosyayi_ac(self, url):
        if url and ("http" in url or os.path.exists(url)):
            QDesktopServices.openUrl(QUrl(url))
        else:
            show_error("Hata", "Geçerli bir dosya bağlantısı yok.", self)

    def dosya_sec(self, key, line_edit, status_label):
        yol, _ = QFileDialog.getOpenFileName(self, "Dosya Seç", "", "Tüm Dosyalar (*.*)")
        if yol:
            line_edit.setText(yol)
            status_label.setText("Seçildi: " + os.path.basename(yol))
            status_label.setStyleSheet("color: #FF9800; font-weight: bold;")
            
            if key == "Img":
                self.secilen_yeni_resim = yol
                self.lbl_resim.setPixmap(QPixmap(yol).scaled(250, 250, Qt.KeepAspectRatio))
            elif key == "NDK_Lisans_Belgesi":
                self.secilen_yeni_belge = yol

    def verileri_yukle_baslat(self):
        self.progress.setRange(0, 0)
        self.formu_kilitle(True)
        self.worker = VeriYukleyici(self.target_id)
        self.worker.veri_hazir.connect(self.verileri_ekrana_bas)
        self.worker.hata_olustu.connect(self.hata_goster)
        self.worker.start()

    def verileri_ekrana_bas(self, paket):
        self.progress.setRange(0, 100); self.progress.setValue(100)
        self.btn_duzenle.setEnabled(True)
        self.son_gelen_paket = paket
        
        sabitler = paket["sabitler"]
        veri = paket["cihaz_verisi"]
        self.satir_numarasi = paket["satir_no"]
        
        if not veri:
            show_info("Uyarı", "Kayıt bulunamadı.", self)
            return

        for key, widget in self.inputs.items():
            if isinstance(widget, QComboBox):
                db_kodu = widget.property("db_kodu")
                if db_kodu and db_kodu in sabitler:
                    widget.clear(); widget.addItems(sorted(sabitler[db_kodu]))

        mapping = {
            "CihazID": "cihaz_id", "CihazTipi": "CihazTipi", "Marka": "Marka", "Model": "Model", 
            "SeriNo": "SeriNo", "NDKSeriNo": "NDKSeriNo", "RKS": "RKS", "Sorumlusu": "Sorumlusu", 
            "Gorevi": "Gorevi", "NDKLisansNo": "NDKLisansNo", "LisansDurum": "LisansDurum", 
            "AnaBilimDali": "AnaBilimDali", "Birim": "Birim", "BulunduguBina": "BulunduguBina", 
            "GarantiDurumu": "GarantiDurumu", "DemirbasNo": "DemirbasNo", 
            "KalibrasyonGereklimi": "KalibrasyonGereklimi", "BakimDurum": "BakimDurum", 
            "Durum": "Durum", "Amaç": "Amac", "Kaynak": "Kaynak"
        }
        self.db_internal_id = veri.get('kayit_no', '')

        for ui_key, widget in self.inputs.items():
            if isinstance(widget, QLineEdit) and widget.isVisible() == False: continue
            
            db_key = mapping.get(ui_key, ui_key)
            val = ""
            if db_key in veri: val = str(veri[db_key]).strip()
            elif db_key.lower() in [k.lower() for k in veri.keys()]:
                 for k in veri.keys():
                     if k.lower() == db_key.lower(): val = str(veri[k]).strip(); break
            
            if isinstance(widget, QLineEdit): widget.setText(val)
            elif isinstance(widget, QComboBox): widget.setCurrentText(val)
            elif isinstance(widget, QDateEdit): widget.setDate(self.tarih_parse(val))

        self.mevcut_resim_url = veri.get('Img', '')
        if "Img" in self.control_buttons:
            if self.mevcut_resim_url and "http" in self.mevcut_resim_url:
                self.resmi_indir(self.mevcut_resim_url)
                self.inputs["Img"].setText(self.mevcut_resim_url)
                self.control_buttons["Img"]["status"].setText("Görsel Yüklü")
                self.control_buttons["Img"]["status"].setStyleSheet("color: #4CAF50;")
            else:
                self.lbl_resim.setText("Görsel Yok")
                self.lbl_resim.setStyleSheet("background-color: #202020; color: #555; border: 1px dashed #444; border-radius: 8px;")
                self.control_buttons["Img"]["status"].setText("Görsel Yok")
                self.control_buttons["Img"]["status"].setStyleSheet("color: #666;")

        self.mevcut_lisans_url = veri.get('NDK_Lisans_Belgesi', '')
        if "NDK_Lisans_Belgesi" in self.control_buttons:
            if self.mevcut_lisans_url and "http" in self.mevcut_lisans_url:
                self.inputs["NDK_Lisans_Belgesi"].setText(self.mevcut_lisans_url)
                self.control_buttons["NDK_Lisans_Belgesi"]["status"].setText("Belge Mevcut")
                self.control_buttons["NDK_Lisans_Belgesi"]["status"].setStyleSheet("color: #4CAF50;")
                self.control_buttons["NDK_Lisans_Belgesi"]["view"].setVisible(True)
            else:
                self.inputs["NDK_Lisans_Belgesi"].clear()
                self.control_buttons["NDK_Lisans_Belgesi"]["status"].setText("Belge Yüklenmemiş")
                self.control_buttons["NDK_Lisans_Belgesi"]["status"].setStyleSheet("color: #666;")
                self.control_buttons["NDK_Lisans_Belgesi"]["view"].setVisible(False)

    def resmi_indir(self, url):
        self.lbl_resim.setText("Yükleniyor...")
        self.resim_worker = ResimYukleyici(url)
        self.resim_worker.resim_indi.connect(self.resim_goster)
        self.resim_worker.hata.connect(lambda: self.lbl_resim.setText("Hata"))
        self.resim_worker.start()

    def resim_goster(self, pixmap):
        scaled_pix = pixmap.scaled(250, 250, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.lbl_resim.setPixmap(scaled_pix)
        self.lbl_resim.setStyleSheet("border: 2px solid #333; border-radius: 8px;")

    def hata_goster(self, mesaj):
        self.progress.setRange(0, 100); self.progress.setValue(0)
        show_error("Hata", mesaj, self)

    def tarih_parse(self, t_str):
        if not t_str: return QDate.currentDate()
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(t_str, fmt)
                return QDate(dt.year, dt.month, dt.day)
            except: continue
        return QDate.currentDate()

    def formu_kilitle(self, kilitli):
        for key, widget in self.inputs.items():
            if isinstance(widget, QLineEdit) and not widget.isVisible(): continue
            if isinstance(widget, QLineEdit): widget.setReadOnly(kilitli)
            elif isinstance(widget, (QComboBox, QDateEdit)): widget.setEnabled(not kilitli)
            if kilitli: widget.setStyleSheet("background-color: #202020; border: none; color: #aaa; font-style: italic; padding: 8px; border-radius: 6px;")
            else: widget.setStyleSheet("QLineEdit, QComboBox, QDateEdit { background-color: #333333; border: 1px solid #555; color: white; padding: 8px; border-radius: 6px; } QLineEdit:focus, QComboBox:focus { border: 1px solid #4dabf7; }")
        
        if "CihazID" in self.inputs: 
            self.inputs["CihazID"].setReadOnly(True)
            self.inputs["CihazID"].setStyleSheet("background-color: #202020; color: #4dabf7; font-weight: bold; border: none;")

        for key, btns in self.control_buttons.items():
            btns["change"].setVisible(not kilitli)

    def duzenleme_modunu_ac(self):
        self.formu_kilitle(False)
        self.btn_duzenle.setVisible(False)
        self.btn_kaydet.setVisible(True)
        self.btn_kapat.setText("İptal Et") 
        self.btn_kapat.setStyleSheet("color: #ff5252; border: 1px solid #ff5252;")

    def kapat_veya_iptal(self):
        if self.btn_kaydet.isVisible():
            if self.son_gelen_paket: self.verileri_ekrana_bas(self.son_gelen_paket)
            self.formu_kilitle(True)
            self.btn_kaydet.setVisible(False)
            self.btn_duzenle.setVisible(True)
            self.btn_kapat.setText("Vazgeç / Kapat")
            self.btn_kapat.setStyleSheet("color: #aaa; border: 1px solid #555;")
        else:
            self.pencereyi_kapat()

    def pencereyi_kapat(self):
        pencereyi_kapat(self)

    def guncelleme_baslat(self):
        if not self.satir_numarasi: return
        self.btn_kaydet.setText("Kaydediliyor...")
        self.btn_kaydet.setEnabled(False)
        self.btn_kapat.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.progress.setRange(0, 0)

        def v(k): 
            w = self.inputs.get(k)
            if not w: return ""
            if isinstance(w, QLineEdit): return w.text().strip()
            if isinstance(w, QComboBox): return w.currentText()
            if isinstance(w, QDateEdit): return w.date().toString("yyyy-MM-dd")
            return ""
        
        input_degerleri = {}
        for k in self.inputs.keys():
            if k not in ["Img", "NDK_Lisans_Belgesi"]:
                input_degerleri[k] = v(k)

        sozluk_veri = {
            "cihaz_id": v("CihazID"), "marka": v("Marka"), "model": v("Model"),
            "seri_no": v("SeriNo"), "cihaz_tipi": v("CihazTipi"), "birim": v("Birim"),
            "sorumlu": v("Sorumlusu"), "rks": v("RKS"), "bulundugu_bina": v("BulunduguBina"),
            "hizmete_giris": v("HizmeteGirisTarihi"), "uretim_tarihi": "Bilinmiyor"
        }

        self.updater = GuncellemeIslemi(
            self.satir_numarasi, self.db_internal_id, input_degerleri,
            self.secilen_yeni_resim, self.secilen_yeni_belge,
            self.mevcut_resim_url, self.mevcut_lisans_url, sozluk_veri
        )
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

    # 🟢 DEĞİŞİKLİK 4: Thread Güvenliği
    def closeEvent(self, event):
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(500)
        if hasattr(self, 'updater') and self.updater.isRunning():
            self.updater.quit()
            self.updater.wait(500)
        if hasattr(self, 'resim_worker') and self.resim_worker.isRunning():
            self.resim_worker.quit()
            self.resim_worker.wait(500)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = CihazDetayPenceresi("TEST-123")
    win.show()
    sys.exit(app.exec())