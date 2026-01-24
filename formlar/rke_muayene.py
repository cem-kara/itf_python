# -*- coding: utf-8 -*-
import sys
import os
import time
import datetime
import logging
from datetime import datetime as dt

from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                               QTableWidget, QTableWidgetItem, QHeaderView, 
                               QLineEdit, QPushButton, QLabel, QMessageBox, 
                               QComboBox, QDateEdit, QTextEdit, QFileDialog, 
                               QProgressBar, QFrame, QGraphicsDropShadowEffect, QSplitter, QScrollArea,QCompleter
                               )
from PySide6.QtCore import Qt, QDate, QThread, Signal, QSize, QUrl
from PySide6.QtGui import QColor, QBrush, QIcon, QDesktopServices, QFont

# --- LOGLAMA ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RKEMuayene")

# --- AYARLAR ---
DRIVE_KLASOR_ID = "1KIYRhomNGppMZCXbqyngT2kH0X8c-GEK" 

# --- BAĞLANTILAR ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

try:
    from google_baglanti import veritabani_getir, GoogleDriveYoneticisi
except ImportError:
    def veritabani_getir(vt_tipi, sayfa_adi): return None
    class GoogleDriveYoneticisi:
        def dosya_yukle(self, a, b): return None

# =============================================================================
# 1. WORKER THREADS (ARKA PLAN İŞLEMLERİ)
# =============================================================================

class VeriYukleyici(QThread):
    """
    RKE Listesini (Seçim için) ve Muayene Geçmişini çeker.
    """
    veri_hazir = Signal(list, dict, list, list) # RKE_Combo_List, RKE_Dict, Muayene_List, Headers
    hata_olustu = Signal(str)

    def run(self):
        try:
            rke_combo = []
            rke_dict = {} 
            muayene_listesi = []
            headers = []

            # 1. RKE LİSTESİNİ ÇEK
            ws_rke = veritabani_getir('rke', 'rke_list')
            if ws_rke:
                raw_rke = ws_rke.get_all_records()
                for row in raw_rke:
                    ekipman_no = str(row.get('EkipmanNo', '')).strip()
                    cins = str(row.get('KoruyucuCinsi', '')).strip()
                    
                    if ekipman_no:
                        # Görünen: EkipmanNo | Cins
                        display = f"{ekipman_no} | {cins}"
                        rke_combo.append(display)
                        rke_dict[display] = ekipman_no # Arkada: EkipmanNo

            # 2. MUAYENE GEÇMİŞİNİ ÇEK
            ws_muayene = veritabani_getir('rke', 'rke_muayene')
            if ws_muayene:
                raw_muayene = ws_muayene.get_all_values()
                if len(raw_muayene) > 0:
                    headers = raw_muayene[0]
                    muayene_listesi = raw_muayene[1:]

            self.veri_hazir.emit(sorted(rke_combo), rke_dict, muayene_listesi, headers)

        except Exception as e:
            self.hata_olustu.emit(str(e))

class KayitWorker(QThread):
    finished = Signal(str)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, veri_dict, dosya_yolu):
        super().__init__()
        self.veri = veri_dict
        self.dosya_yolu = dosya_yolu

    def run(self):
        try:
            drive_link = "-"
            
            if self.dosya_yolu and os.path.exists(self.dosya_yolu):
                self.progress.emit("Dosya yükleniyor...")
                drive = GoogleDriveYoneticisi()
                link = drive.dosya_yukle(self.dosya_yolu, DRIVE_KLASOR_ID)
                if link: drive_link = link

            self.progress.emit("Veritabanına kaydediliyor...")
            ws = veritabani_getir('rke', 'rke_muayene')
            if not ws: raise Exception("Veritabanı bağlantısı yok.")

            satir = [
                self.veri['KayitNo'],
                self.veri['EkipmanNo'],
                self.veri['F_MuayeneTarihi'],
                self.veri['FizikselDurum'],
                self.veri['S_MuayeneTarihi'],
                self.veri['SkopiDurum'],
                self.veri['Aciklamalar'],
                self.veri['KontrolEden'],
                self.veri['BirimSorumlusu'],
                self.veri['Not'],
                drive_link
            ]
            
            ws.append_row(satir)
            self.finished.emit("Muayene kaydı başarıyla oluşturuldu.")

        except Exception as e:
            self.error.emit(str(e))

# =============================================================================
# 2. UI BİLEŞENLERİ
# =============================================================================

class ModernInputGroup(QWidget):
    def __init__(self, label_text, widget, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 10)
        layout.setSpacing(6)
        
        self.lbl = QLabel(label_text)
        self.lbl.setStyleSheet("color: #cfcfcf; font-size: 12px; font-weight: 600; font-family: 'Segoe UI';")
        
        self.widget = widget
        self.widget.setMinimumHeight(40)
        
        base_style = "border: 1px solid #454545; border-radius: 6px; padding: 0 10px; background-color: #2d2d2d; color: #ffffff; font-size: 13px;"
        focus_style = "border: 1px solid #42a5f5; background-color: #323232;"
        
        if isinstance(widget, QTextEdit):
            self.widget.setMinimumHeight(60)
            self.widget.setStyleSheet(f"QTextEdit {{ {base_style} }} QTextEdit:focus {{ {focus_style} }}")
        else:
            self.widget.setStyleSheet(f"""
                QLineEdit, QComboBox, QDateEdit {{ {base_style} }}
                QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{ {focus_style} }}
                QComboBox::drop-down {{ width: 25px; border: none; }}
            """)
        
        layout.addWidget(self.lbl)
        layout.addWidget(self.widget)

class InfoCard(QFrame):
    def __init__(self, title, parent=None, color="#42a5f5"):
        super().__init__(parent)
        self.setStyleSheet("InfoCard { background-color: #1e1e1e; border: 1px solid #333; border-radius: 12px; }")
        
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20); shadow.setColor(QColor(0, 0, 0, 60))
        self.setGraphicsEffect(shadow)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(10)
        
        if title:
            h_lay = QHBoxLayout()
            indicator = QFrame()
            indicator.setFixedSize(4, 18)
            indicator.setStyleSheet(f"background-color: {color}; border-radius: 2px;")
            
            lbl = QLabel(title)
            lbl.setStyleSheet(f"color: {color}; font-size: 15px; font-weight: bold; font-family: 'Segoe UI';")
            
            h_lay.addWidget(indicator)
            h_lay.addWidget(lbl)
            h_lay.addStretch()
            
            self.layout.addLayout(h_lay)
            
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setStyleSheet("background-color: #333; margin-bottom: 5px;")
            self.layout.addWidget(line)

    def add_widget(self, widget): self.layout.addWidget(widget)
    def add_layout(self, layout): self.layout.addLayout(layout)

# =============================================================================
# 3. ANA PENCERE
# =============================================================================

class RKEMuayenePenceresi(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RKE Muayene Girişi")
        self.resize(1400, 850)
        self.setStyleSheet("background-color: #121212; color: #e0e0e0; font-family: 'Segoe UI';")
        
        self.rke_dict = {} 
        self.tum_muayeneler = []
        self.secilen_dosya = None
        self.header_map = {}
        
        self.inputs = {}
        self.setup_ui()
        self.verileri_yukle()

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle { background-color: #2b2b2b; }")

        # ==========================================
        # --- SOL PANEL (FORM) ---
        # ==========================================
        sol_widget = QWidget()
        sol_layout = QVBoxLayout(sol_widget)
        sol_layout.setContentsMargins(0, 0, 15, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        form_inner = QWidget()
        form_inner.setStyleSheet("background: transparent;")
        form_layout = QVBoxLayout(form_inner)
        form_layout.setSpacing(20)
        form_layout.setContentsMargins(5, 5, 5, 20)

        # ------------------------------------------
        # 1. KART: EKİPMAN NO (TEK BAŞINA)
        # ------------------------------------------
        card_ekipman = InfoCard("Ekipman Seçimi", color="#ab47bc")
        
        self.cmb_rke = QComboBox()
        self.cmb_rke.setEditable(True)
        self.cmb_rke.setPlaceholderText("Ekipman No Ara...")
        self.cmb_rke.completer().setCompletionMode(QCompleter.PopupCompletion)
        # Seçim değiştiğinde geçmiş tablosunu güncelle
        self.cmb_rke.currentIndexChanged.connect(self.ekipman_secildi)
        
        self.add_input(card_ekipman, "Ekipman No", self.cmb_rke, "ekipman")
        form_layout.addWidget(card_ekipman)

        # ------------------------------------------
        # 2. KART: MUAYENE DETAYLARI
        # ------------------------------------------
        card_detay = InfoCard("Muayene Detayları", color="#29b6f6")
        
        # A) Fiziksel Muayene Satırı
        row_fiz = QHBoxLayout()
        row_fiz.setSpacing(15)
        self.dt_fiziksel = QDateEdit()
        self.dt_fiziksel.setCalendarPopup(True)
        self.dt_fiziksel.setDate(QDate.currentDate())
        self.dt_fiziksel.setDisplayFormat("yyyy-MM-dd")
        
        self.cmb_fiziksel = QComboBox()
        self.cmb_fiziksel.setEditable(True)
        self.cmb_fiziksel.addItems(["Sağlam", "Yırtık Var", "Deforme", "Kirli", "Askı Kopuk"])
        
        self.add_input_to_layout(row_fiz, "Fiziksel Muayene Tarihi", self.dt_fiziksel, "tarih_f")
        self.add_input_to_layout(row_fiz, "Fiziksel Muayene Durumu", self.cmb_fiziksel, "durum_f")
        card_detay.add_layout(row_fiz)
        
        # B) Skopi Muayene Satırı
        row_sko = QHBoxLayout()
        row_sko.setSpacing(15)
        self.dt_skopi = QDateEdit()
        self.dt_skopi.setCalendarPopup(True)
        self.dt_skopi.setDate(QDate.currentDate())
        self.dt_skopi.setDisplayFormat("yyyy-MM-dd")
        
        self.cmb_skopi = QComboBox()
        self.cmb_skopi.setEditable(True)
        self.cmb_skopi.addItems(["Uygun", "Uygun Değil", "Yapılmadı"])
        
        self.add_input_to_layout(row_sko, "Skopi Muayene Tarihi", self.dt_skopi, "tarih_s")
        self.add_input_to_layout(row_sko, "Skopi Muayene Durumu", self.cmb_skopi, "durum_s")
        card_detay.add_layout(row_sko)
        
        form_layout.addWidget(card_detay)

        # ------------------------------------------
        # 3. KART: SONUÇ VE RAPORLAMA
        # ------------------------------------------
        card_sonuc = InfoCard("Sonuç ve Raporlama", color="#ffa726")
        
        # A) Personel Satırı
        row_pers = QHBoxLayout()
        row_pers.setSpacing(15)
        self.txt_kontrol = QLineEdit()
        self.txt_kontrol.setPlaceholderText("Kontrol Eden Kişi")
        
        self.txt_sorumlu = QLineEdit()
        self.txt_sorumlu.setPlaceholderText("Birim Sorumlusu")
        
        self.add_input_to_layout(row_pers, "Kontrol Eden", self.txt_kontrol, "kontrol_eden")
        self.add_input_to_layout(row_pers, "Birim Sorumlusu", self.txt_sorumlu, "birim_sorumlu")
        card_sonuc.add_layout(row_pers)
        
        # B) Teknik Açıklama
        self.txt_aciklama = QTextEdit()
        self.txt_aciklama.setPlaceholderText("Teknik değerlendirme ve sonuç...")
        self.txt_aciklama.setMaximumHeight(70)
        self.add_input(card_sonuc, "Teknik Açıklama", self.txt_aciklama, "aciklama")
        
        # C) Dosya Yükleme
        file_container = QWidget()
        file_layout = QHBoxLayout(file_container)
        file_layout.setContentsMargins(0,0,0,0)
        self.lbl_dosya = QLabel("Rapor Yok")
        self.lbl_dosya.setStyleSheet("color: #777; font-style: italic;")
        btn_dosya = QPushButton("📂 Rapor Yükle")
        btn_dosya.setFixedSize(110, 35)
        btn_dosya.setStyleSheet("background: #333; border: 1px solid #555; border-radius: 4px; color: white;")
        btn_dosya.clicked.connect(self.dosya_sec)
        file_layout.addWidget(self.lbl_dosya)
        file_layout.addWidget(btn_dosya)
        
        grp_dosya = ModernInputGroup("Varsa Rapor", file_container)
        card_sonuc.add_widget(grp_dosya)
        
        form_layout.addWidget(card_sonuc)

        # ------------------------------------------
        # 4. BÖLÜM: ESKİ MUAYENE TABLOSU (Specific)
        # ------------------------------------------
        lbl_gecmis = QLabel("Seçili Ekipmanın Geçmiş Muayeneleri")
        lbl_gecmis.setStyleSheet("font-size: 14px; font-weight: bold; color: #ccc; margin-top: 10px;")
        form_layout.addWidget(lbl_gecmis)

        self.tbl_gecmis = QTableWidget()
        self.tbl_gecmis.setColumnCount(4)
        self.tbl_gecmis.setHorizontalHeaderLabels(["Fiz. Tarih", "Skopi Tarih", "Açıklama", "Rapor"])
        self.tbl_gecmis.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_gecmis.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_gecmis.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_gecmis.setFixedHeight(150)
        self.tbl_gecmis.setStyleSheet("""
            QTableWidget { background: #1e1e1e; border: 1px solid #444; gridline-color: #333; }
            QHeaderView::section { background: #2d2d2d; border: none; padding: 4px; font-weight: bold; color: #bbb; }
        """)
        self.tbl_gecmis.cellDoubleClicked.connect(self.gecmis_satir_tiklandi)
        form_layout.addWidget(self.tbl_gecmis)

        scroll.setWidget(form_inner)
        sol_layout.addWidget(scroll)

        # Butonlar
        self.pbar = QProgressBar()
        self.pbar.setVisible(False)
        self.pbar.setFixedHeight(4)
        self.pbar.setStyleSheet("QProgressBar { border: none; background: #333; } QProgressBar::chunk { background: #ab47bc; }")
        sol_layout.addWidget(self.pbar)
        
        h_btn = QHBoxLayout()
        self.btn_temizle = QPushButton("TEMİZLE")
        self.btn_temizle.setCursor(Qt.PointingHandCursor)
        self.btn_temizle.setFixedHeight(45)
        self.btn_temizle.setStyleSheet("background: transparent; border: 1px solid #555; color: #aaa; border-radius: 6px;")
        self.btn_temizle.clicked.connect(self.temizle)
        
        self.btn_kaydet = QPushButton("KAYDET")
        self.btn_kaydet.setCursor(Qt.PointingHandCursor)
        self.btn_kaydet.setFixedHeight(45)
        self.btn_kaydet.setStyleSheet("""
            QPushButton { background-color: #2e7d32; color: white; border-radius: 6px; font-weight: bold; font-size: 14px; border: none; }
            QPushButton:hover { background-color: #388e3c; }
        """)
        self.btn_kaydet.clicked.connect(self.kaydet)
        
        h_btn.addWidget(self.btn_temizle)
        h_btn.addWidget(self.btn_kaydet)
        sol_layout.addLayout(h_btn)

        # ==========================================
        # --- SAĞ PANEL (GENEL LİSTE) ---
        # ==========================================
        sag_widget = QWidget()
        sag_layout = QVBoxLayout(sag_widget)
        sag_layout.setContentsMargins(10, 0, 0, 0)
        sag_layout.setSpacing(10)
        
        # Filtre
        filter_frame = QFrame()
        filter_frame.setStyleSheet("background: #1e1e1e; border-radius: 8px; border: 1px solid #333;")
        h_filter = QHBoxLayout(filter_frame)
        h_filter.setContentsMargins(10, 10, 10, 10)
        
        lbl_baslik = QLabel("Tüm Muayene Kayıtları")
        lbl_baslik.setStyleSheet("font-size: 16px; font-weight: bold; color: #29b6f6;")
        
        self.txt_ara = QLineEdit()
        self.txt_ara.setPlaceholderText("🔍 Genel Ara...")
        self.txt_ara.setStyleSheet("background: #2d2d2d; border: 1px solid #444; border-radius: 20px; padding: 5px 15px; color: white;")
        self.txt_ara.textChanged.connect(self.tabloyu_filtrele)
        
        btn_yenile = QPushButton("⟳")
        btn_yenile.setFixedSize(35, 35)
        btn_yenile.clicked.connect(self.verileri_yukle)
        btn_yenile.setStyleSheet("background: #333; color: white; border: 1px solid #444; border-radius: 4px;")
        
        h_filter.addWidget(lbl_baslik)
        h_filter.addStretch()
        h_filter.addWidget(self.txt_ara)
        h_filter.addWidget(btn_yenile)
        sag_layout.addWidget(filter_frame)
        
        # Tablo
        self.tablo = QTableWidget()
        self.cols = ["KayitNo", "EkipmanNo", "F_MuayeneTarihi", "FizikselDurum", "S_MuayeneTarihi", "SkopiDurum", "Aciklamalar", "KontrolEden/Unvani", "BirimSorumlusu/Unvani", "Not", "Rapor"]
        self.tablo.setColumnCount(len(self.cols))
        self.tablo.setHorizontalHeaderLabels(["ID", "Ekipman", "Fiz. Tarih", "Fiz. Durum", "Skopi Tarih", "Skopi Durum", "Açıklama", "Kontrol Eden", "Sorumlu", "Not", "Rapor"])
        self.tablo.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tablo.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tablo.setSelectionBehavior(QTableWidget.SelectRows)
        self.tablo.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tablo.setAlternatingRowColors(True)
        self.tablo.setStyleSheet("""
            QTableWidget { background: #1e1e1e; border: none; gridline-color: #333; alternate-background-color: #252525; }
            QHeaderView::section { background: #2d2d2d; border: none; padding: 8px; color: #b0b0b0; font-weight: bold; font-size: 12px; }
            QTableWidget::item { padding: 5px; border-bottom: 1px solid #2a2a2a; }
        """)
        self.tablo.cellDoubleClicked.connect(self.satir_tiklandi)
        sag_layout.addWidget(self.tablo)
        
        self.lbl_sayi = QLabel("0 Kayıt")
        self.lbl_sayi.setAlignment(Qt.AlignRight)
        self.lbl_sayi.setStyleSheet("color: #777;")
        sag_layout.addWidget(self.lbl_sayi)
        
        # Splitter'a ekle
        splitter.addWidget(sol_widget)
        splitter.addWidget(sag_widget)
        splitter.setStretchFactor(0, 35)
        splitter.setStretchFactor(1, 65)
        
        main_layout.addWidget(splitter)

    # --- UI YARDIMCILARI ---
    def add_input(self, parent, label, widget, key):
        grp = ModernInputGroup(label, widget)
        if hasattr(parent, "add_widget"): parent.add_widget(grp)
        elif hasattr(parent, "addWidget"): parent.addWidget(grp)
        self.inputs[key] = widget

    def add_input_to_layout(self, layout, label, widget, key):
        grp = ModernInputGroup(label, widget)
        layout.addWidget(grp)
        self.inputs[key] = widget

    # --- MANTIK ---

    def dosya_sec(self):
        yol, _ = QFileDialog.getOpenFileName(self, "Rapor Seç", "", "PDF/Resim (*.pdf *.jpg *.png *.jpeg)")
        if yol:
            self.secilen_dosya = yol
            self.lbl_dosya.setText(os.path.basename(yol))
            self.lbl_dosya.setStyleSheet("color: #4caf50; font-weight: bold;")

    def verileri_yukle(self):
        self.pbar.setVisible(True)
        self.pbar.setRange(0, 0)
        self.loader = VeriYukleyici()
        self.loader.veri_hazir.connect(self.veriler_geldi)
        self.loader.hata_olustu.connect(lambda e: QMessageBox.warning(self, "Hata", e))
        self.loader.finished.connect(lambda: self.pbar.setVisible(False))
        self.loader.start()

    def veriler_geldi(self, rke_combo, rke_dict, muayene_list, headers):
        self.rke_dict = rke_dict
        self.tum_muayeneler = muayene_list
        self.header_map = {h.strip(): i for i, h in enumerate(headers)}
        
        self.cmb_rke.blockSignals(True)
        self.cmb_rke.clear()
        self.cmb_rke.addItems(rke_combo)
        self.cmb_rke.blockSignals(False)
        
        self.tabloyu_filtrele()

    def tabloyu_filtrele(self):
        self.tablo.setRowCount(0)
        ara = self.txt_ara.text().lower()
        
        count = 0
        for row in reversed(self.tum_muayeneler):
            full_text = " ".join(row).lower()
            if ara and ara not in full_text: continue
            
            r = self.tablo.rowCount()
            self.tablo.insertRow(r)
            
            def get(col_name):
                idx = self.header_map.get(col_name, -1)
                return row[idx] if idx != -1 and idx < len(row) else ""

            self.tablo.setItem(r, 0, QTableWidgetItem(get("KayitNo")))
            self.tablo.setItem(r, 1, QTableWidgetItem(get("EkipmanNo")))
            self.tablo.setItem(r, 2, QTableWidgetItem(get("F_MuayeneTarihi")))
            
            # Renklendirme
            fiz_durum = get("FizikselDurum")
            item_fiz = QTableWidgetItem(fiz_durum)
            if "Sağlam" in fiz_durum: item_fiz.setForeground(QColor("#66bb6a"))
            else: item_fiz.setForeground(QColor("#ffca28"))
            self.tablo.setItem(r, 3, item_fiz)
            
            self.tablo.setItem(r, 4, QTableWidgetItem(get("S_MuayeneTarihi")))
            
            sko_durum = get("SkopiDurum")
            item_sko = QTableWidgetItem(sko_durum)
            if "Uygun Değil" in sko_durum: item_sko.setForeground(QColor("#ef5350"))
            else: item_sko.setForeground(QColor("#66bb6a"))
            self.tablo.setItem(r, 5, item_sko)
            
            self.tablo.setItem(r, 6, QTableWidgetItem(get("Aciklamalar")))
            self.tablo.setItem(r, 7, QTableWidgetItem(get("KontrolEden/Unvani")))
            self.tablo.setItem(r, 8, QTableWidgetItem(get("BirimSorumlusu/Unvani")))
            self.tablo.setItem(r, 9, QTableWidgetItem(get("Not")))
            
            rapor = get("Rapor")
            link_item = QTableWidgetItem("📄 AÇ" if "http" in rapor else "-")
            if "http" in rapor:
                link_item.setForeground(QColor("#42a5f5"))
                link_item.setToolTip(rapor)
            self.tablo.setItem(r, 10, link_item)
            
            count += 1
        
        self.lbl_sayi.setText(f"{count} Kayıt")

    def ekipman_secildi(self):
        """Seçilen ekipman değiştiğinde alt tabloyu filtrele."""
        secilen_text = self.cmb_rke.currentText()
        if not secilen_text: return
        
        ekipman_no = self.rke_dict.get(secilen_text, secilen_text.split('|')[0].strip())
        
        self.tbl_gecmis.setRowCount(0)
        idx_ekipman = self.header_map.get("EkipmanNo", -1)
        if idx_ekipman == -1: return
        
        # Filtrele ve Ekle
        for row in self.tum_muayeneler:
            if len(row) > idx_ekipman and row[idx_ekipman] == ekipman_no:
                r = self.tbl_gecmis.rowCount()
                self.tbl_gecmis.insertRow(r)
                
                def get_v(key):
                    i = self.header_map.get(key, -1)
                    return row[i] if i != -1 else ""
                
                self.tbl_gecmis.setItem(r, 0, QTableWidgetItem(get_v("F_MuayeneTarihi")))
                self.tbl_gecmis.setItem(r, 1, QTableWidgetItem(get_v("S_MuayeneTarihi")))
                self.tbl_gecmis.setItem(r, 2, QTableWidgetItem(get_v("Aciklamalar")))
                
                rapor = get_v("Rapor")
                link_item = QTableWidgetItem("Link" if "http" in rapor else "-")
                if "http" in rapor: 
                    link_item.setForeground(QColor("#42a5f5"))
                    link_item.setToolTip(rapor)
                self.tbl_gecmis.setItem(r, 3, link_item)

    def gecmis_satir_tiklandi(self, row, col):
        if col == 3: # Rapor
            item = self.tbl_gecmis.item(row, col)
            link = item.toolTip()
            if "http" in link: QDesktopServices.openUrl(QUrl(link))

    def satir_tiklandi(self, row, col):
        # Sağdaki büyük tablodan rapor açma
        if col == 10:
            item = self.tablo.item(row, col)
            link = item.toolTip()
            if "http" in link: QDesktopServices.openUrl(QUrl(link))

    def temizle(self):
        self.cmb_rke.setCurrentIndex(-1)
        self.dt_fiziksel.setDate(QDate.currentDate())
        self.dt_skopi.setDate(QDate.currentDate())
        self.txt_kontrol.clear()
        self.txt_sorumlu.clear()
        self.cmb_fiziksel.setCurrentIndex(0)
        self.cmb_skopi.setCurrentIndex(0)
        self.txt_aciklama.clear()
        self.lbl_dosya.setText("Rapor Seçilmedi")
        self.secilen_dosya = None
        self.tbl_gecmis.setRowCount(0)

    def kaydet(self):
        rke_text = self.cmb_rke.currentText()
        if not rke_text:
            QMessageBox.warning(self, "Hata", "Lütfen bir ekipman seçiniz.")
            return
        
        ekipman_no = self.rke_dict.get(rke_text, rke_text.split('|')[0].strip())

        unique_id = f"M-{int(time.time())}"
        
        veri = {
            'KayitNo': unique_id,
            'EkipmanNo': ekipman_no,
            'F_MuayeneTarihi': self.dt_fiziksel.date().toString("yyyy-MM-dd"),
            'FizikselDurum': self.cmb_fiziksel.currentText(),
            'S_MuayeneTarihi': self.dt_skopi.date().toString("yyyy-MM-dd"),
            'SkopiDurum': self.cmb_skopi.currentText(),
            'Aciklamalar': self.txt_aciklama.toPlainText(),
            'KontrolEden': self.txt_kontrol.text(),
            'BirimSorumlusu': self.txt_sorumlu.text(),
            'Not': "" # Ek not alanı yoksa boş geçebiliriz veya description'a ekleriz
        }
        
        self.pbar.setVisible(True)
        self.pbar.setRange(0, 0)
        self.btn_kaydet.setEnabled(False)
        
        self.saver = KayitWorker(veri, self.secilen_dosya)
        self.saver.finished.connect(self.islem_basarili)
        self.saver.error.connect(lambda e: QMessageBox.critical(self, "Hata", e))
        self.saver.start()

    def islem_basarili(self, msg):
        self.pbar.setVisible(False)
        self.btn_kaydet.setEnabled(True)
        QMessageBox.information(self, "Başarılı", msg)
        self.temizle()
        self.verileri_yukle()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = RKEMuayenePenceresi()
    win.show()
    sys.exit(app.exec())