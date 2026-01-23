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
                               QProgressBar, QFrame, QGraphicsDropShadowEffect, QSplitter,
                               QCompleter, QAbstractItemView, QSizePolicy, QScrollArea,
                               QListWidget, QListWidgetItem) 
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

from araclar.yetki_yonetimi import YetkiYoneticisi

# --- İMPORTLAR ---
try:
    from google_baglanti import veritabani_getir, GoogleDriveService
    from araclar.ortak_araclar import show_info, show_error, pencereyi_kapat
except ImportError:
    def veritabani_getir(vt_tipi, sayfa_adi): return None
    def show_info(t, m, p): print(m)
    def show_error(t, m, p): print(m)
    def pencereyi_kapat(w): w.close()
    class GoogleDriveService:
        def upload_file(self, a, b): return None

# =============================================================================
# 1. WORKER THREADS (ARKA PLAN İŞLEMLERİ)
# =============================================================================

class VeriYukleyici(QThread):
    # Sinyal: RKE_Combo, RKE_Dict, Envanter_List, Envanter_Headers, Muayene_List, Muayene_Headers, Aciklama_Sabitleri
    veri_hazir = Signal(list, dict, list, list, list, list, list) 
    hata_olustu = Signal(str)

    def run(self):
        try:
            rke_combo = []
            rke_dict = {} 
            envanter_listesi = []
            envanter_headers = []
            muayene_listesi = []
            muayene_headers = []
            aciklama_listesi = []

            # 1. RKE LİSTESİ (ENVANTER)
            ws_rke = veritabani_getir('rke', 'rke_list')
            if ws_rke:
                raw_rke = ws_rke.get_all_values()
                if len(raw_rke) > 0:
                    envanter_headers = raw_rke[0]
                    envanter_listesi = raw_rke[1:]
                    
                    try:
                        idx_ekipman = envanter_headers.index("EkipmanNo")
                        idx_cins = envanter_headers.index("KoruyucuCinsi")
                        for row in envanter_listesi:
                            if len(row) > idx_ekipman:
                                eq_no = str(row[idx_ekipman]).strip()
                                c_txt = str(row[idx_cins]).strip() if len(row) > idx_cins else ""
                                if eq_no:
                                    display = f"{eq_no} | {c_txt}"
                                    rke_combo.append(display)
                                    rke_dict[display] = eq_no
                    except: pass

            # 2. MUAYENE GEÇMİŞİ
            ws_muayene = veritabani_getir('rke', 'rke_muayene')
            if ws_muayene:
                raw_muayene = ws_muayene.get_all_values()
                if len(raw_muayene) > 0:
                    muayene_headers = raw_muayene[0]
                    if len(raw_muayene) > 1:
                        muayene_listesi = raw_muayene[1:]

            # 3. SABİTLER (Açıklamalar İçin)
            ws_sabit = veritabani_getir('sabit', 'Sabitler')
            if ws_sabit:
                raw_sabit = ws_sabit.get_all_values()
                for row in raw_sabit[1:]: 
                    if len(row) > 2:
                        kod_turu = str(row[1]).strip()
                        deger = str(row[2]).strip()
                        if kod_turu == "Aciklamalar" and deger:
                            aciklama_listesi.append(deger)

            self.veri_hazir.emit(sorted(rke_combo), rke_dict, envanter_listesi, envanter_headers, muayene_listesi, muayene_headers, sorted(aciklama_listesi))

        except Exception as e:
            self.hata_olustu.emit(f"Veri yükleme hatası: {str(e)}")

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
                drive = GoogleDriveService()
                link = drive.upload_file(self.dosya_yolu, DRIVE_KLASOR_ID)
                if link: drive_link = link

            self.progress.emit("Muayene kaydediliyor...")
            ws = veritabani_getir('rke', 'rke_muayene')
            if not ws: raise Exception("Muayene tablosuna erişilemedi.")
            
            satir = [
                self.veri.get('KayitNo', ''),
                self.veri.get('EkipmanNo', ''),
                self.veri.get('F_MuayeneTarihi', ''),
                self.veri.get('FizikselDurum', ''),
                self.veri.get('S_MuayeneTarihi', ''),
                self.veri.get('SkopiDurum', ''),
                self.veri.get('Aciklamalar', ''),
                self.veri.get('KontrolEden', ''),
                self.veri.get('BirimSorumlusu', ''),
                self.veri.get('Not', ''),
                drive_link
            ]
            ws.append_row(satir)

            self.progress.emit("Envanter güncelleniyor...")
            ws_list = veritabani_getir('rke', 'rke_list')
            if ws_list:
                try:
                    ekipmanlar = ws_list.col_values(2) 
                    row_idx = ekipmanlar.index(self.veri['EkipmanNo']) + 1
                    
                    genel_durum = "Kullanıma Uygun"
                    if "Değil" in self.veri['SkopiDurum'] or "Hasarlı" in self.veri['FizikselDurum']:
                        genel_durum = "Kullanıma Uygun Değil"
                    
                    ws_list.update_cell(row_idx, 10, self.veri['F_MuayeneTarihi'])
                    ws_list.update_cell(row_idx, 11, genel_durum)
                except ValueError:
                    pass 

            self.finished.emit("Muayene başarıyla kaydedildi.")

        except Exception as e:
            self.error.emit(f"Kayıt hatası: {str(e)}")

class TopluKayitWorker(QThread):
    finished = Signal(str)
    progress = Signal(int)
    error = Signal(str)

    def __init__(self, ekipman_listesi, form_verisi):
        super().__init__()
        self.ekipmanlar = ekipman_listesi
        self.veri = form_verisi

    def run(self):
        try:
            ws_muayene = veritabani_getir('rke', 'rke_muayene')
            ws_list = veritabani_getir('rke', 'rke_list')
            
            if not ws_muayene or not ws_list:
                raise Exception("Veritabanı bağlantısı kurulamadı.")

            tum_ekipmanlar = ws_list.col_values(2) 
            
            count = 0
            for eq_no in self.ekipmanlar:
                unique_id = f"M-{int(time.time())}-{count}"
                
                satir = [
                    unique_id,
                    eq_no,
                    self.veri.get('F_MuayeneTarihi', ''),
                    self.veri.get('FizikselDurum', ''),
                    self.veri.get('S_MuayeneTarihi', ''),
                    self.veri.get('SkopiDurum', ''),
                    self.veri.get('Aciklamalar', ''),
                    self.veri.get('KontrolEden', ''),
                    self.veri.get('BirimSorumlusu', ''),
                    self.veri.get('Not', ''),
                    "-"
                ]
                
                ws_muayene.append_row(satir)
                
                if eq_no in tum_ekipmanlar:
                    row_idx = tum_ekipmanlar.index(eq_no) + 1 
                    
                    s_durum = self.veri['SkopiDurum']
                    f_durum = self.veri['FizikselDurum']
                    genel_durum = "Kullanıma Uygun"
                    if "Değil" in s_durum or "Hasarlı" in f_durum or "Hurda" in f_durum:
                        genel_durum = "Kullanıma Uygun Değil"
                        
                    ws_list.update_cell(row_idx, 10, self.veri['F_MuayeneTarihi'])
                    ws_list.update_cell(row_idx, 11, genel_durum)
                
                count += 1
                self.progress.emit(count)
                
            self.finished.emit(f"{count} adet kayıt başarıyla işlendi.")

        except Exception as e:
            self.error.emit(str(e))

# =============================================================================
# 2. UI BİLEŞENLERİ
# =============================================================================

class ModernInputGroup(QWidget):
    def __init__(self, label_text, widget, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 5)
        layout.setSpacing(5)
        
        self.lbl = QLabel(label_text)
        self.lbl.setStyleSheet("color: #cfcfcf; font-size: 12px; font-weight: 600; font-family: 'Segoe UI';")
        
        self.widget = widget
        self.widget.setMinimumHeight(30)
        
        base_style = "border: 1px solid #454545; border-radius: 6px; padding: 0 10px; background-color: #2d2d2d; color: #ffffff; font-size: 13px;"
        focus_style = "border: 1px solid #42a5f5; background-color: #323232;"
        
        if isinstance(widget, QTextEdit) or isinstance(widget, QListWidget):
            self.widget.setMinimumHeight(80) 
            self.widget.setStyleSheet(f"""
                QTextEdit, QListWidget {{ {base_style} padding: 5px; }} 
                QTextEdit:focus, QListWidget:focus {{ {focus_style} }}
            """)
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
        self.layout.setSpacing(5)
        
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
    # 🟢 DEĞİŞİKLİK 1: Parametreler
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.setWindowTitle("RKE Muayene Girişi")
        self.resize(1400, 900)
        self.setStyleSheet("background-color: #121212; color: #e0e0e0; font-family: 'Segoe UI';")
        
        self.rke_dict = {} 
        self.tum_envanter = []
        self.envanter_headers = []
        self.tum_muayeneler = []
        self.muayene_headers = []
        self.aciklamalar_listesi = []
        
        self.secilen_dosya = None
        self.inputs = {}
        
        self.setup_ui()
        
        # 🟢 DEĞİŞİKLİK 2: Yetki
        YetkiYoneticisi.uygula(self, "rke_muayene")
        
        self.verileri_yukle()

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle { background-color: #2b2b2b; }")

        # --- SOL PANEL (FORM) ---
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

        # 1. KART: EKİPMAN SEÇİMİ
        card_ekipman = InfoCard("Ekipman Seçimi", color="#ab47bc")
        self.cmb_rke = QComboBox()
        self.cmb_rke.setEditable(True)
        self.cmb_rke.setPlaceholderText("Ekipman No Ara...")
        self.cmb_rke.completer().setCompletionMode(QCompleter.PopupCompletion)
        self.cmb_rke.currentIndexChanged.connect(self.ekipman_secildi) 
        self.add_input(card_ekipman, "Ekipman No", self.cmb_rke, "ekipman")
        form_layout.addWidget(card_ekipman)

        # 2. KART: MUAYENE DETAYLARI
        card_detay = InfoCard("Muayene Detayları", color="#29b6f6")
        
        row_fiz = QHBoxLayout(); row_fiz.setSpacing(15)
        self.dt_fiziksel = QDateEdit(); self.dt_fiziksel.setCalendarPopup(True); self.dt_fiziksel.setDate(QDate.currentDate()); self.dt_fiziksel.setDisplayFormat("yyyy-MM-dd")
        self.cmb_fiziksel = QComboBox(); self.cmb_fiziksel.setEditable(True)
        self.cmb_fiziksel.addItems(["Kullanıma Uygun", "Kullanıma Uygun Değil"])
        self.add_input_to_layout(row_fiz, "Fiziksel Muayene Tarihi", self.dt_fiziksel, "tarih_f")
        self.add_input_to_layout(row_fiz, "Fiziksel Durum", self.cmb_fiziksel, "durum_f")
        card_detay.add_layout(row_fiz)
        
        row_sko = QHBoxLayout(); row_sko.setSpacing(15)
        self.dt_skopi = QDateEdit(); self.dt_skopi.setCalendarPopup(True); self.dt_skopi.setDate(QDate.currentDate()); self.dt_skopi.setDisplayFormat("yyyy-MM-dd")
        self.cmb_skopi = QComboBox(); self.cmb_skopi.setEditable(True)
        self.cmb_skopi.addItems(["Kullanıma Uygun", "Kullanıma Uygun Değil", "Yapılmadı"])
        self.add_input_to_layout(row_sko, "Skopi Kontrol Tarihi", self.dt_skopi, "tarih_s")
        self.add_input_to_layout(row_sko, "Skopi Durumu", self.cmb_skopi, "durum_s")
        card_detay.add_layout(row_sko)
        form_layout.addWidget(card_detay)

        # 3. KART: SONUÇ VE RAPORLAMA
        card_sonuc = InfoCard("Sonuç ve Raporlama", color="#ffa726")
        
        row_pers = QHBoxLayout(); row_pers.setSpacing(15)
        self.txt_kontrol = QLineEdit(); self.txt_kontrol.setPlaceholderText("Kontrol Eden Kişi")
        # 🟢 OTOMATİK DOLDURMA
        if self.kullanici_adi:
            self.txt_kontrol.setText(str(self.kullanici_adi))
            
        self.txt_sorumlu = QLineEdit(); self.txt_sorumlu.setPlaceholderText("Birim Sorumlusu")
        self.add_input_to_layout(row_pers, "Kontrol Eden", self.txt_kontrol, "kontrol_eden")
        self.add_input_to_layout(row_pers, "Birim Sorumlusu", self.txt_sorumlu, "birim_sorumlu")
        card_sonuc.add_layout(row_pers)
        
        self.lst_aciklama = QListWidget()
        self.lst_aciklama.setSelectionMode(QAbstractItemView.NoSelection) 
        self.add_input(card_sonuc, "Teknik Açıklama (Birden fazla seçilebilir)", self.lst_aciklama, "aciklama")
        
        file_container = QWidget()
        file_layout = QHBoxLayout(file_container); file_layout.setContentsMargins(0,0,0,0)
        self.lbl_dosya = QLabel("Rapor Seçilmedi")
        self.lbl_dosya.setStyleSheet("color: #777; font-style: italic;")
        btn_dosya = QPushButton("📂 Rapor Yükle"); btn_dosya.setFixedSize(110, 35)
        btn_dosya.setStyleSheet("background: #333; border: 1px solid #555; border-radius: 4px; color: white;")
        btn_dosya.clicked.connect(self.dosya_sec)
        file_layout.addWidget(self.lbl_dosya); file_layout.addWidget(btn_dosya)
        grp_dosya = ModernInputGroup("Rapor Dosyası", file_container)
        card_sonuc.add_widget(grp_dosya)
        form_layout.addWidget(card_sonuc)

        # 4. BÖLÜM: ESKİ MUAYENE TABLOSU
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
        self.tbl_gecmis.setStyleSheet("QTableWidget { background: #1e1e1e; border: 1px solid #444; gridline-color: #333; } QHeaderView::section { background: #2d2d2d; border: none; padding: 4px; font-weight: bold; color: #bbb; }")
        self.tbl_gecmis.cellDoubleClicked.connect(self.gecmis_satir_tiklandi)
        form_layout.addWidget(self.tbl_gecmis)

        scroll.setWidget(form_inner)
        sol_layout.addWidget(scroll)

        # Alt Butonlar
        self.pbar = QProgressBar(); self.pbar.setVisible(False); self.pbar.setFixedHeight(4); sol_layout.addWidget(self.pbar)
        h_btn = QHBoxLayout()
        self.btn_temizle = QPushButton("TEMİZLE"); self.btn_temizle.setObjectName("btn_temizle"); self.btn_temizle.setFixedHeight(45)
        self.btn_temizle.setStyleSheet("background: transparent; border: 1px solid #555; color: #aaa; border-radius: 6px;")
        self.btn_temizle.clicked.connect(self.temizle)
        
        self.btn_kaydet = QPushButton("KAYDET (TEK)"); self.btn_kaydet.setObjectName("btn_kaydet"); self.btn_kaydet.setFixedHeight(45)
        self.btn_kaydet.setStyleSheet("QPushButton { background-color: #2e7d32; color: white; border-radius: 6px; font-weight: bold; font-size: 13px; border: none; } QPushButton:hover { background-color: #388e3c; }")
        self.btn_kaydet.clicked.connect(self.kaydet)
        
        self.btn_toplu = QPushButton("SEÇİLİLERİ GÜNCELLE (TOPLU)"); self.btn_toplu.setObjectName("btn_toplu"); self.btn_toplu.setFixedHeight(45)
        self.btn_toplu.setStyleSheet("QPushButton { background-color: #F57C00; color: white; border-radius: 6px; font-weight: bold; font-size: 13px; border: none; } QPushButton:hover { background-color: #FB8C00; }")
        self.btn_toplu.clicked.connect(self.toplu_kayit_baslat)
        
        h_btn.addWidget(self.btn_temizle); h_btn.addWidget(self.btn_kaydet); h_btn.addWidget(self.btn_toplu)
        sol_layout.addLayout(h_btn)

        # --- SAĞ PANEL ---
        sag_widget = QWidget(); sag_layout = QVBoxLayout(sag_widget)
        sag_layout.setContentsMargins(10, 0, 0, 0); sag_layout.setSpacing(10)
        
        filter_frame = QFrame(); filter_frame.setStyleSheet("background: #1e1e1e; border-radius: 8px; border: 1px solid #333;")
        h_filter = QHBoxLayout(filter_frame); h_filter.setContentsMargins(10, 10, 10, 10)
        lbl_list_baslik = QLabel("RKE Envanter Listesi"); lbl_list_baslik.setStyleSheet("font-size: 16px; font-weight: bold; color: #29b6f6;")
        self.cmb_filtre_abd = QComboBox(); self.cmb_filtre_abd.addItem("Tüm ABD"); self.cmb_filtre_abd.setStyleSheet("QComboBox { background: #2d2d2d; border: 1px solid #444; border-radius: 4px; padding: 5px; color: white; min-width: 150px; }")
        self.cmb_filtre_abd.currentIndexChanged.connect(self.tabloyu_filtrele)
        self.txt_ara = QLineEdit(); self.txt_ara.setPlaceholderText("🔍 Envanter Ara..."); self.txt_ara.setStyleSheet("background: #2d2d2d; border: 1px solid #444; border-radius: 20px; padding: 5px 15px; color: white;")
        self.txt_ara.textChanged.connect(self.tabloyu_filtrele)
        btn_yenile = QPushButton("⟳"); btn_yenile.setFixedSize(35, 35); btn_yenile.clicked.connect(self.verileri_yukle); btn_yenile.setStyleSheet("background: #333; color: white; border: 1px solid #444; border-radius: 4px;")
        h_filter.addWidget(lbl_list_baslik); h_filter.addStretch(); h_filter.addWidget(self.cmb_filtre_abd); h_filter.addWidget(self.txt_ara); h_filter.addWidget(btn_yenile)
        sag_layout.addWidget(filter_frame)
        
        self.tablo = QTableWidget()
        self.cols_envanter = ["EkipmanNo", "AnaBilimDali", "Birim", "KoruyucuCinsi", "KursunEsdegeri", "Durum"]
        self.tablo.setColumnCount(len(self.cols_envanter))
        self.tablo.setHorizontalHeaderLabels(["Ekipman No", "ABD", "Birim", "Cins", "Pb", "Durum"])
        self.tablo.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tablo.setSelectionBehavior(QTableWidget.SelectRows)
        self.tablo.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tablo.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tablo.setAlternatingRowColors(True)
        self.tablo.setStyleSheet("QTableWidget { background: #1e1e1e; border: none; gridline-color: #333; alternate-background-color: #252525; } QHeaderView::section { background: #2d2d2d; border: none; padding: 8px; color: #b0b0b0; font-weight: bold; font-size: 12px; } QTableWidget::item { padding: 5px; border-bottom: 1px solid #2a2a2a; } QTableWidget::item:selected { background-color: #3949ab; color: white; }")
        self.tablo.clicked.connect(self.tablo_satir_secildi)
        sag_layout.addWidget(self.tablo)
        
        self.lbl_sayi = QLabel("0 Kayıt"); self.lbl_sayi.setAlignment(Qt.AlignRight); self.lbl_sayi.setStyleSheet("color: #777;")
        sag_layout.addWidget(self.lbl_sayi)
        
        splitter.addWidget(sol_widget); splitter.addWidget(sag_widget); splitter.setStretchFactor(0, 35); splitter.setStretchFactor(1, 65)
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

    def get_secilen_aciklamalar(self):
        """ListWidget'tan seçili (tikli) olanları string olarak döndürür."""
        secilenler = []
        for i in range(self.lst_aciklama.count()):
            item = self.lst_aciklama.item(i)
            if item.checkState() == Qt.Checked:
                secilenler.append(item.text())
        return ", ".join(secilenler)

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
        self.loader.hata_olustu.connect(lambda e: show_error("Hata", e, self))
        self.loader.finished.connect(lambda: self.pbar.setVisible(False))
        self.loader.start()

    def veriler_geldi(self, rke_combo, rke_dict, envanter_list, envanter_headers, muayene_list, muayene_headers, aciklama_listesi):
        self.rke_dict = rke_dict
        self.tum_envanter = envanter_list
        self.envanter_headers = [h.strip() for h in envanter_headers]
        self.tum_muayeneler = muayene_list
        self.muayene_headers = {h.strip(): i for i, h in enumerate(muayene_headers)}
        self.aciklamalar_listesi = aciklama_listesi
        
        self.cmb_rke.blockSignals(True)
        self.cmb_rke.clear()
        self.cmb_rke.addItems(rke_combo)
        self.cmb_rke.blockSignals(False)
        
        # Açıklama Listesini Doldur (Checkboxlu)
        self.lst_aciklama.clear()
        for aciklama in self.aciklamalar_listesi:
            item = QListWidgetItem(aciklama)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.lst_aciklama.addItem(item)
        
        idx_abd = -1
        if "AnaBilimDali" in self.envanter_headers:
            idx_abd = self.envanter_headers.index("AnaBilimDali")
        if idx_abd != -1:
            abd_set = set()
            for r in self.tum_envanter:
                if len(r) > idx_abd: abd_set.add(str(r[idx_abd]).strip())
            self.cmb_filtre_abd.blockSignals(True)
            self.cmb_filtre_abd.clear()
            self.cmb_filtre_abd.addItem("Tüm ABD")
            self.cmb_filtre_abd.addItems(sorted(list(abd_set)))
            self.cmb_filtre_abd.blockSignals(False)
        self.tabloyu_filtrele()

    def tabloyu_filtrele(self):
        self.tablo.setRowCount(0)
        ara = self.txt_ara.text().lower()
        filtre_abd = self.cmb_filtre_abd.currentText()
        try: idxs = {col: self.envanter_headers.index(col) for col in self.cols_envanter}
        except ValueError: return

        count = 0
        for row in self.tum_envanter:
            full_text = " ".join([str(x) for x in row]).lower()
            if ara and ara not in full_text: continue
            if filtre_abd != "Tüm ABD":
                idx_abd = idxs.get("AnaBilimDali")
                val_abd = str(row[idx_abd]) if len(row) > idx_abd else ""
                if val_abd != filtre_abd: continue
            
            r = self.tablo.rowCount()
            self.tablo.insertRow(r)
            for c, col_name in enumerate(self.cols_envanter):
                idx = idxs[col_name]
                val = str(row[idx]) if len(row) > idx else ""
                item = QTableWidgetItem(val)
                if col_name == "Durum":
                    if "Uygun Değil" in val or "Hurda" in val: item.setForeground(QColor("#ef5350"))
                    elif "Uygun" in val: item.setForeground(QColor("#66bb6a"))
                self.tablo.setItem(r, c, item)
            count += 1
        self.lbl_sayi.setText(f"{count} Envanter Kaydı")

    def tablo_satir_secildi(self):
        selected_row = self.tablo.currentRow()
        if selected_row < 0: return
        ekipman_no = self.tablo.item(selected_row, 0).text()
        index = self.cmb_rke.findText(ekipman_no, Qt.MatchContains)
        if index >= 0: self.cmb_rke.setCurrentIndex(index)

    def ekipman_secildi(self):
        secilen_text = self.cmb_rke.currentText()
        if not secilen_text: return
        ekipman_no = self.rke_dict.get(secilen_text, secilen_text.split('|')[0].strip())
        self.tbl_gecmis.setRowCount(0)
        try:
            i_ekip = self.muayene_headers.get("EkipmanNo", -1)
            i_fizT = self.muayene_headers.get("F_MuayeneTarihi", -1)
            i_skoT = self.muayene_headers.get("S_MuayeneTarihi", -1)
            i_acik = self.muayene_headers.get("Aciklamalar", -1)
            i_rap = self.muayene_headers.get("Rapor", -1)
        except: return
        if i_ekip == -1: return

        for row in reversed(self.tum_muayeneler):
            if len(row) > i_ekip and str(row[i_ekip]) == ekipman_no:
                r = self.tbl_gecmis.rowCount()
                self.tbl_gecmis.insertRow(r)
                val_fizT = row[i_fizT] if len(row) > i_fizT else ""
                val_skoT = row[i_skoT] if len(row) > i_skoT else ""
                val_acik = row[i_acik] if len(row) > i_acik else ""
                val_rap = row[i_rap] if len(row) > i_rap else ""
                self.tbl_gecmis.setItem(r, 0, QTableWidgetItem(val_fizT))
                self.tbl_gecmis.setItem(r, 1, QTableWidgetItem(val_skoT))
                self.tbl_gecmis.setItem(r, 2, QTableWidgetItem(val_acik))
                link_item = QTableWidgetItem("Link" if "http" in val_rap else "-")
                if "http" in val_rap: 
                    link_item.setForeground(QColor("#42a5f5"))
                    link_item.setToolTip(val_rap)
                self.tbl_gecmis.setItem(r, 3, link_item)

    def gecmis_satir_tiklandi(self, row, col):
        # Eğer açıklamaya çift tıklandıysa (Col 2), o açıklamaları yukarıdaki listeye set et
        if col == 2:
            mevcut_aciklama = self.tbl_gecmis.item(row, col).text()
            # Önce hepsini temizle
            for i in range(self.lst_aciklama.count()):
                self.lst_aciklama.item(i).setCheckState(Qt.Unchecked)
            
            # Eşleşenleri işaretle
            for i in range(self.lst_aciklama.count()):
                item = self.lst_aciklama.item(i)
                if item.text() in mevcut_aciklama:
                    item.setCheckState(Qt.Checked)
        
        if col == 3:
            item = self.tbl_gecmis.item(row, col)
            link = item.toolTip()
            if "http" in link: QDesktopServices.openUrl(QUrl(link))

    def temizle(self):
        self.cmb_rke.setCurrentIndex(-1)
        self.dt_fiziksel.setDate(QDate.currentDate())
        self.dt_skopi.setDate(QDate.currentDate())
        # Otomatik doldurmayı tekrar yap (Sildiyse geri gelsin)
        if self.kullanici_adi:
            self.txt_kontrol.setText(str(self.kullanici_adi))
        else:
            self.txt_kontrol.clear()
            
        self.txt_sorumlu.clear()
        self.cmb_fiziksel.setCurrentIndex(0)
        self.cmb_skopi.setCurrentIndex(0)
        # Listeyi temizle (unchecked yap)
        for i in range(self.lst_aciklama.count()):
            self.lst_aciklama.item(i).setCheckState(Qt.Unchecked)
        self.lbl_dosya.setText("Rapor Seçilmedi")
        self.secilen_dosya = None
        self.tbl_gecmis.setRowCount(0)

    def kaydet(self):
        rke_text = self.cmb_rke.currentText()
        if not rke_text:
            show_error("Hata", "Lütfen bir ekipman seçiniz.", self)
            return
        ekipman_no = self.rke_dict.get(rke_text, rke_text.split('|')[0].strip())
        unique_id = f"M-{int(time.time())}"
        
        aciklamalar = self.get_secilen_aciklamalar()
        
        veri = {
            'KayitNo': unique_id,
            'EkipmanNo': ekipman_no,
            'F_MuayeneTarihi': self.dt_fiziksel.date().toString("yyyy-MM-dd"),
            'FizikselDurum': self.cmb_fiziksel.currentText(),
            'S_MuayeneTarihi': self.dt_skopi.date().toString("yyyy-MM-dd"),
            'SkopiDurum': self.cmb_skopi.currentText(),
            'Aciklamalar': aciklamalar,
            'KontrolEden': self.txt_kontrol.text(),
            'BirimSorumlusu': self.txt_sorumlu.text(),
            'Not': "" 
        }
        self.ui_kilitle(True)
        self.saver = KayitWorker(veri, self.secilen_dosya)
        self.saver.finished.connect(self.islem_basarili)
        self.saver.error.connect(self.islem_hatali)
        self.saver.start()

    def toplu_kayit_baslat(self):
        selected_rows = self.tablo.selectionModel().selectedRows()
        if not selected_rows:
            show_info("Uyarı", "Lütfen sağdaki listeden en az bir ekipman seçiniz.", self)
            return
        ekipmanlar = set()
        for idx in selected_rows:
            eq_no = self.tablo.item(idx.row(), 0).text()
            if eq_no: ekipmanlar.add(eq_no)
        if not ekipmanlar: return
        
        cevap = QMessageBox.question(self, "Toplu Onay", f"{len(ekipmanlar)} adet ekipman için muayene kaydı oluşturulacak.\nSol taraftaki form verileri kullanılacaktır.\nOnaylıyor musunuz?", QMessageBox.Yes | QMessageBox.No)
        if cevap == QMessageBox.No: return
        
        aciklamalar = self.get_secilen_aciklamalar()
        
        veri = {
            'F_MuayeneTarihi': self.dt_fiziksel.date().toString("yyyy-MM-dd"),
            'FizikselDurum': self.cmb_fiziksel.currentText(),
            'S_MuayeneTarihi': self.dt_skopi.date().toString("yyyy-MM-dd"),
            'SkopiDurum': self.cmb_skopi.currentText(),
            'Aciklamalar': aciklamalar,
            'KontrolEden': self.txt_kontrol.text(),
            'BirimSorumlusu': self.txt_sorumlu.text(),
            'Not': "" 
        }
        self.ui_kilitle(True)
        self.toplu_saver = TopluKayitWorker(list(ekipmanlar), veri)
        self.toplu_saver.finished.connect(self.islem_basarili)
        self.toplu_saver.error.connect(self.islem_hatali)
        self.toplu_saver.progress.connect(lambda val: self.setWindowTitle(f"İşleniyor: {val}..."))
        self.toplu_saver.start()

    def ui_kilitle(self, kilitli):
        self.btn_kaydet.setEnabled(not kilitli)
        self.btn_toplu.setEnabled(not kilitli)
        self.pbar.setVisible(kilitli)
        self.pbar.setRange(0, 0)

    def islem_basarili(self, msg):
        self.ui_kilitle(False)
        self.setWindowTitle("RKE Muayene Girişi")
        show_info("Başarılı", msg, self)
        self.temizle()
        self.verileri_yukle()

    def islem_hatali(self, err):
        self.ui_kilitle(False)
        self.setWindowTitle("RKE Muayene Girişi")
        show_error("Hata", err, self)

    # 🟢 DEĞİŞİKLİK 3: Thread Güvenliği
    def closeEvent(self, event):
        if hasattr(self, 'loader') and self.loader.isRunning():
            self.loader.quit()
            self.loader.wait(500)
        if hasattr(self, 'saver') and self.saver.isRunning():
            self.saver.quit()
            self.saver.wait(500)
        if hasattr(self, 'toplu_saver') and self.toplu_saver.isRunning():
            self.toplu_saver.quit()
            self.toplu_saver.wait(500)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    from temalar.tema import TemaYonetimi
    TemaYonetimi.uygula_fusion_dark(app)
    win = RKEMuayenePenceresi()
    win.show()
    sys.exit(app.exec())