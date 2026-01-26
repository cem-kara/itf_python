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
                               QComboBox, QDateEdit, QFrame, QGraphicsDropShadowEffect, 
                               QTextEdit, QScrollArea, QAbstractItemView, QCompleter, 
                               QProgressBar, QSplitter, QSizePolicy, QGroupBox)
from PySide6.QtCore import Qt, QDate, QThread, Signal
from PySide6.QtGui import QColor, QFont, QIcon

# --- LOGLAMA ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RKEYonetim")

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# --- İMPORTLAR ---
try:
    from araclar.yetki_yonetimi import YetkiYoneticisi
    from temalar.tema import TemaYonetimi
    from google_baglanti import veritabani_getir
    from araclar.ortak_araclar import show_info, show_error, pencereyi_kapat
except ImportError as e:
    print(f"Modül Hatası: {e}")
    # Fallback
    def veritabani_getir(vt, sayfa): return None
    def show_info(t, m, p): print(m)
    def show_error(t, m, p): print(m)
    def pencereyi_kapat(w): w.close()
    class TemaYonetimi:
        @staticmethod
        def uygula_fusion_dark(app): pass

# =============================================================================
# 1. WORKER THREADS (ARKA PLAN İŞLEMLERİ)
# =============================================================================

class RKEVeriYukleyici(QThread):
    # Sinyal: Sabitler_Dict, RKE_Data, RKE_Headers, Muayene_Data
    veri_hazir = Signal(dict, list, list, list)
    hata_olustu = Signal(str)

    def run(self):
        try:
            # 1. SABİTLERİ ÇEK (KESİN EŞLEŞME)
            sabitler = {}
            maps = {
                "AnaBilimDali": {}, 
                "Birim": {}, 
                "Koruyucu_Cinsi": {}, 
                "Bedeni": {}
            }
            
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

            # 2. RKE LİSTESİ
            rke_data = []
            rke_basliklar = []
            ws_rke = veritabani_getir('rke', 'rke_list')
            if ws_rke:
                raw_rke = ws_rke.get_all_values()
                if len(raw_rke) > 0:
                    rke_basliklar = [str(h).strip() for h in raw_rke[0]]
                    rke_data = raw_rke[1:]

            # 3. MUAYENE GEÇMİŞİ
            muayene_data = []
            ws_muayene = veritabani_getir('rke', 'rke_muayene')
            if ws_muayene:
                muayene_data = ws_muayene.get_all_values()

            self.veri_hazir.emit(maps, rke_data, rke_basliklar, muayene_data)

        except Exception as e:
            self.hata_olustu.emit(f"Veri yükleme hatası: {str(e)}")

class RKEIslemKaydedici(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)

    def __init__(self, mod, veri, satir_no=None):
        super().__init__()
        self.mod = mod  # INSERT veya UPDATE
        self.veri = veri
        self.satir_no = satir_no

    def run(self):
        try:
            ws = veritabani_getir('rke', 'rke_list')
            if not ws: raise Exception("Veritabanı bağlantısı yok.")

            if self.mod == "INSERT":
                ws.append_row(self.veri)
            elif self.mod == "UPDATE" and self.satir_no:
                # A'dan başlayarak veri uzunluğu kadar sütunu güncelle
                num_cols = len(self.veri)
                end_col_char = chr(ord('A') + num_cols - 1)
                if num_cols > 26: end_col_char = "Z" 
                
                range_name = f"A{self.satir_no}:{end_col_char}{self.satir_no}"
                ws.update(range_name=range_name, values=[self.veri])

            self.islem_tamam.emit()
        except Exception as e:
            self.hata_olustu.emit(str(e))

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
        self.lbl.setStyleSheet("color: #b0b0b0; font-size: 11px; font-weight: bold; text-transform: uppercase;")
        
        self.widget = widget
        self.widget.setMinimumHeight(30)
        
        # Manuel stiller kaldırıldı, tema.py yönetecek
        if isinstance(widget, QTextEdit):
            self.widget.setMinimumHeight(60)
        
        layout.addWidget(self.lbl)
        layout.addWidget(self.widget)

class InfoCard(QGroupBox):
    """
    Görsel gruplama sağlayan kart bileşeni (QGroupBox).
    """
    def __init__(self, title, parent=None, color="#42a5f5"):
        super().__init__(title, parent)
        
        self.setStyleSheet(f"""
            QGroupBox {{
                background-color: #2d2d2d;
                border: 1px solid #444;
                border-radius: 8px;
                margin-top: 20px; 
                font-weight: bold;
                color: {color}; 
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 10px;
                left: 10px;
            }}
        """)
        
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15); shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 20, 15, 15)
        self.layout.setSpacing(10)

    def add_widget(self, w): self.layout.addWidget(w)
    def add_layout(self, l): self.layout.addLayout(l)

# =============================================================================
# 3. ANA PENCERE: RKE YÖNETİM
# =============================================================================

class RKEYonetimPenceresi(QWidget):
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.setWindowTitle("RKE Envanter Yönetimi")
        self.resize(1350, 850)
        # Manuel stil kaldırıldı
        
        # Değişkenler
        self.sabitler = {}
        self.rke_listesi = []
        self.rke_basliklar = []
        self.muayene_listesi = []
        self.secili_satir_id = None
        self.secili_satir_index = None 
        
        self.inputs = {}

        self.setup_ui()
        YetkiYoneticisi.uygula(self, "rke_yonetim")
        self.verileri_yukle()

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        
        splitter = QSplitter(Qt.Horizontal)
        
        # --- SOL PANEL (FORM) ---
        form_container = QWidget()
        form_layout = QVBoxLayout(form_container)
        form_layout.setContentsMargins(0, 0, 10, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        form_inner = QWidget()
        form_inner.setStyleSheet("background: transparent;")
        inner_layout = QVBoxLayout(form_inner)
        inner_layout.setSpacing(15)
        inner_layout.setContentsMargins(5, 5, 5, 20)

        # 1. KART: KİMLİK BİLGİLERİ (OTOMATİK VE SABİT)
        card_kimlik = InfoCard("Kimlik Bilgileri", color="#ffca28")
        self.add_input(card_kimlik, "Kayıt No (ID)", "KayitNo", read_only=True)
        self.add_input(card_kimlik, "Ekipman No (Otomatik)", "EkipmanNo", read_only=True)
        self.add_input(card_kimlik, "Koruyucu No (Tam Kod)", "KoruyucuNumarasi", read_only=True)
        self.add_input(card_kimlik, "Barkod", "Barkod")
        self.add_input(card_kimlik, "Varsa Demirbaş No", "Varsa_Demirbaş_No")
        inner_layout.addWidget(card_kimlik)

        # 2. KART: ÖZELLİKLER (SEÇİMLİ)
        card_ozellik = InfoCard("Ekipman Özellikleri", color="#66bb6a")
        
        self.add_input(card_ozellik, "Ana Bilim Dalı", "AnaBilimDali", "combo")
        self.inputs["AnaBilimDali"].currentIndexChanged.connect(self.kod_hesapla)
        
        self.add_input(card_ozellik, "Birim", "Birim", "combo")
        self.inputs["Birim"].currentIndexChanged.connect(self.kod_hesapla)
        
        self.add_input(card_ozellik, "Koruyucu Cinsi", "KoruyucuCinsi", "combo")
        self.inputs["KoruyucuCinsi"].currentIndexChanged.connect(self.kod_hesapla)

        row_tech = QHBoxLayout()
        self.add_input(row_tech, "Kurşun Eşdeğeri", "KursunEsdegeri", "combo")
        self.inputs["KursunEsdegeri"].setEditable(True)
        self.inputs["KursunEsdegeri"].addItems(["0.25 mmPb", "0.35 mmPb", "0.50 mmPb", "1.0 mmPb"])
        
        self.add_input(row_tech, "Beden", "Beden", "combo")
        card_ozellik.add_layout(row_tech)

        self.add_input(card_ozellik, "Hizmet Yılı", "HizmetYili", "date")
        self.inputs["HizmetYili"].setDisplayFormat("yyyy")
        inner_layout.addWidget(card_ozellik)

        # 3. KART: DURUM VE TARİH
        card_durum = InfoCard("Durum ve Geçmiş", color="#ef5350")
        
        self.add_input(card_durum, "Envantere Kayıt Tarihi", "KayitTarih", "date")
        self.add_input(card_durum, "Son Kontrol Tarihi", "KontrolTarihi", "date")
        
        self.add_input(card_durum, "Güncel Durum", "Durum", "combo")
        self.inputs["Durum"].addItems(["Kullanıma Uygun", "Kullanıma Uygun Değil", "Hurda", "Tamirde"])
        
        self.txt_aciklama = QTextEdit()
        self.txt_aciklama.setPlaceholderText("Ekipman hakkında notlar...")
        self.add_custom_input(card_durum, "Açıklama", self.txt_aciklama)
        self.inputs["Açiklama"] = self.txt_aciklama
        
        inner_layout.addWidget(card_durum)

        # 4. KART: MUAYENE GEÇMİŞİ (LİSTE)
        card_gecmis = InfoCard("Muayene Geçmişi", color="#ab47bc")
        self.tbl_gecmis = QTableWidget()
        self.tbl_gecmis.setColumnCount(3)
        self.tbl_gecmis.setHorizontalHeaderLabels(["Tarih", "Sonuç", "Açıklama"])
        self.tbl_gecmis.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_gecmis.setFixedHeight(120)
        self.tbl_gecmis.verticalHeader().setVisible(False)
        self.tbl_gecmis.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_gecmis.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # Manuel stil kaldırıldı, tema yönetecek
        card_gecmis.add_widget(self.tbl_gecmis)
        inner_layout.addWidget(card_gecmis)

        scroll.setWidget(form_inner)
        form_layout.addWidget(scroll)

        # --- BUTONLAR ---
        self.pbar = QProgressBar()
        self.pbar.setVisible(False)
        self.pbar.setFixedHeight(4)
        form_layout.addWidget(self.pbar)

        h_btn = QHBoxLayout()
        
        self.btn_yeni = QPushButton("TEMİZLE / YENİ")
        self.btn_yeni.setObjectName("btn_yeni") 
        self.btn_yeni.setFixedHeight(45)
        self.btn_yeni.setStyleSheet("background: transparent; border: 1px solid #555; color: #ccc; border-radius: 6px;")
        self.btn_yeni.clicked.connect(self.temizle)
        
        self.btn_kaydet = QPushButton("KAYDET")
        self.btn_kaydet.setObjectName("btn_kaydet") 
        self.btn_kaydet.setFixedHeight(45)
        self.btn_kaydet.setStyleSheet("background-color: #2e7d32; color: white; border: none; border-radius: 6px; font-weight: bold;")
        self.btn_kaydet.clicked.connect(self.kaydet)
        
        h_btn.addWidget(self.btn_yeni)
        h_btn.addWidget(self.btn_kaydet)
        form_layout.addLayout(h_btn)

        # --- SAĞ PANEL (LİSTE) ---
        liste_container = QWidget()
        liste_layout = QVBoxLayout(liste_container)
        liste_layout.setContentsMargins(10, 0, 0, 0)

        # Filtre (GroupBox ile)
        grp_filtre = QGroupBox("Filtreleme")
        grp_filtre.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        h_filter = QHBoxLayout(grp_filtre)
        h_filter.setContentsMargins(10, 20, 10, 10)
        
        self.cmb_filtre_abd = QComboBox()
        self.cmb_filtre_abd.addItem("Tüm ABD")
        self.cmb_filtre_abd.setMinimumWidth(150)
        self.cmb_filtre_abd.currentIndexChanged.connect(self.tabloyu_filtrele)
        
        self.txt_ara = QLineEdit()
        self.txt_ara.setPlaceholderText("Ara...")
        self.txt_ara.textChanged.connect(self.tabloyu_filtrele)
        
        btn_yenile = QPushButton("⟳")
        btn_yenile.setFixedSize(35,35)
        btn_yenile.clicked.connect(self.verileri_yukle)
        # Stil temaya bırakıldı
        
        h_filter.addWidget(self.cmb_filtre_abd)
        h_filter.addWidget(self.txt_ara)
        h_filter.addWidget(btn_yenile)
        liste_layout.addWidget(grp_filtre)

        # Tablo
        self.tablo = QTableWidget()
        # Veritabanı Sırası (15 Sütun)
        self.cols_vt = [
            "KayitNo", "EkipmanNo", "KoruyucuNumarasi", "AnaBilimDali", "Birim", 
            "KoruyucuCinsi", "KursunEsdegeri", "HizmetYili", "Bedeni", "KontrolTarihi", 
            "Durum", "Açiklama", "Varsa_Demirbaş_No", "KayitTarih", "Barkod"
        ]
        self.cols_header = [
            "ID", "Ekipman No", "Koruyucu No", "ABD", "Birim", 
            "Cins", "Pb", "Yıl", "Beden", "Son Kontrol", 
            "Durum", "Açıklama", "Demirbaş", "Kayıt T.", "Barkod"
        ]
        
        self.tablo.setColumnCount(len(self.cols_vt))
        self.tablo.setHorizontalHeaderLabels(self.cols_header)
        self.tablo.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tablo.setColumnHidden(0, True) # ID Gizle
        self.tablo.setColumnHidden(11, True) # Açıklama Gizle
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tablo.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tablo.setAlternatingRowColors(True)
        # Manuel stil kaldırıldı
        self.tablo.cellDoubleClicked.connect(self.satir_secildi)
        liste_layout.addWidget(self.tablo)
        
        self.lbl_sayi = QLabel("0 Kayıt")
        self.lbl_sayi.setAlignment(Qt.AlignRight)
        liste_layout.addWidget(self.lbl_sayi)

        splitter.addWidget(form_container)
        splitter.addWidget(liste_container)
        splitter.setStretchFactor(0, 35)
        splitter.setStretchFactor(1, 65)
        
        main_layout.addWidget(splitter)

    # --- UI YARDIMCILARI ---
    def add_input(self, parent, label, key, tip="text", read_only=False):
        widget = None
        if tip == "text": widget = QLineEdit()
        elif tip == "combo": widget = QComboBox()
        elif tip == "date": 
            widget = QDateEdit(); widget.setCalendarPopup(True); widget.setDate(QDate.currentDate())
            widget.setDisplayFormat("yyyy-MM-dd")
        
        if read_only and isinstance(widget, QLineEdit): 
            widget.setReadOnly(True)
            # ReadOnly stil temizlendi, tema halleder
        
        grp = ModernInputGroup(label, widget)
        
        # 🟢 GÜVENLİ EKLEME: Hem InfoCard(QGroupBox) hem Layout desteği
        if isinstance(parent, InfoCard):
            parent.add_widget(grp)
        elif hasattr(parent, "addWidget"): # QVBoxLayout vb.
            parent.addWidget(grp)
        elif hasattr(parent, "addLayout"):
            parent.addWidget(grp)
            
        self.inputs[key] = widget
        return widget

    def add_custom_input(self, parent, label, widget):
        grp = ModernInputGroup(label, widget)
        if hasattr(parent, "add_widget"): parent.add_widget(grp)
        elif hasattr(parent, "addWidget"): parent.addWidget(grp)

    # --- MANTIK ---
    def verileri_yukle(self):
        self.pbar.setVisible(True)
        self.pbar.setRange(0, 0)
        self.loader = RKEVeriYukleyici()
        self.loader.veri_hazir.connect(self.veriler_geldi)
        self.loader.hata_olustu.connect(lambda e: show_error("Hata", e, self))
        self.loader.finished.connect(lambda: self.pbar.setVisible(False))
        self.loader.start()

    def veriler_geldi(self, sabitler, rke_data, rke_headers, muayene_data):
        self.sabitler = sabitler
        self.rke_listesi = rke_data
        self.rke_basliklar = rke_headers
        self.muayene_listesi = muayene_data
        
        # Kesin eşleşme ile Combobox Doldurma
        def fill(ui_key, db_key):
            self.inputs[ui_key].blockSignals(True)
            self.inputs[ui_key].clear()
            self.inputs[ui_key].addItem("")
            
            if db_key in self.sabitler:
                items = sorted(list(self.sabitler[db_key].keys()))
                self.inputs[ui_key].addItems(items)
            
            self.inputs[ui_key].blockSignals(False)

        fill("AnaBilimDali", "AnaBilimDali")
        fill("Birim", "Birim")
        fill("KoruyucuCinsi", "Koruyucu_Cinsi") # Sabitlerdeki kod
        fill("Beden", "Beden")

        # Filtre Combo
        self.cmb_filtre_abd.blockSignals(True)
        self.cmb_filtre_abd.clear(); self.cmb_filtre_abd.addItem("Tüm ABD")
        if "AnaBilimDali" in self.sabitler:
            self.cmb_filtre_abd.addItems(sorted(list(self.sabitler["AnaBilimDali"].keys())))
        self.cmb_filtre_abd.blockSignals(False)
        
        self.tabloyu_filtrele()

    def tabloyu_filtrele(self):
        self.tablo.setRowCount(0)
        f_abd = self.cmb_filtre_abd.currentText()
        ara = self.txt_ara.text().lower()

        try:
            map_idx = {col: self.rke_basliklar.index(col) for col in self.cols_vt if col in self.rke_basliklar}
        except: return

        count = 0
        for i, row in enumerate(self.rke_listesi):
            idx_abd = map_idx.get("AnaBilimDali", -1)
            abd_val = row[idx_abd] if idx_abd != -1 and len(row) > idx_abd else ""
            
            if f_abd != "Tüm ABD" and abd_val != f_abd: continue
            
            full_text = " ".join([str(x) for x in row]).lower()
            if ara and ara not in full_text: continue
            
            r = self.tablo.rowCount()
            self.tablo.insertRow(r)
            
            for c_idx, col_name in enumerate(self.cols_vt):
                val = ""
                if col_name in map_idx and map_idx[col_name] < len(row):
                    val = row[map_idx[col_name]]
                
                item = QTableWidgetItem(str(val))
                if col_name == "Durum":
                    if "Değil" in val or "Hurda" in val: item.setForeground(QColor("#ef5350"))
                    else: item.setForeground(QColor("#66bb6a"))
                
                self.tablo.setItem(r, c_idx, item)
            
            self.tablo.item(r, 0).setData(Qt.UserRole, i + 2) 
            count += 1
            
        self.lbl_sayi.setText(f"{count} Kayıt Listelendi")

    def kod_hesapla(self):
        # Kod hesaplama mantığı
        abd = self.inputs["AnaBilimDali"].currentText()
        birim = self.inputs["Birim"].currentText()
        cins = self.inputs["KoruyucuCinsi"].currentText()
        
        def get_short(grp, val):
            if grp in self.sabitler and val in self.sabitler[grp]:
                return self.sabitler[grp][val]
            return "UNK"

        k_abd = get_short("AnaBilimDali", abd)
        k_birim = get_short("Birim", birim)
        k_cins = get_short("Koruyucu_Cinsi", cins)
        
        if not self.secili_satir_id:
            try:
                # Cins'e göre say (rke_list'deki 'KoruyucuCinsi' sütununa bak)
                idx_cins = self.rke_basliklar.index("KoruyucuCinsi")
                sayac = 1
                for r in self.rke_listesi:
                    if len(r) > idx_cins and r[idx_cins] == cins: sayac += 1
                self.inputs["EkipmanNo"].setText(f"RKE-{k_cins}-{sayac}")
            except: pass

        if birim == "Radyoloji Depo":
            self.inputs["KoruyucuNumarasi"].setText("")
        elif abd and birim and cins:
            try:
                idx_abd = self.rke_basliklar.index("AnaBilimDali")
                idx_birim = self.rke_basliklar.index("Birim")
                idx_cins = self.rke_basliklar.index("KoruyucuCinsi")
                
                sayac = 1
                for r in self.rke_listesi:
                    if (len(r) > idx_cins and r[idx_abd] == abd and 
                        r[idx_birim] == birim and r[idx_cins] == cins):
                        sayac += 1
                self.inputs["KoruyucuNumarasi"].setText(f"{k_abd}-{k_birim}-{k_cins}-{sayac}")
            except: pass

    def satir_secildi(self, row, col):
        item = self.tablo.item(row, 0)
        self.secili_satir_id = item.text()
        self.secili_satir_index = item.data(Qt.UserRole)
        
        idx_id = -1
        if "KayitNo" in self.rke_basliklar: idx_id = self.rke_basliklar.index("KayitNo")
        
        if idx_id == -1: return
        
        bulunan = next((r for r in self.rke_listesi if len(r) > idx_id and r[idx_id] == self.secili_satir_id), None)
        if not bulunan: return
        
        def get(col):
            try: return bulunan[self.rke_basliklar.index(col)]
            except: return ""

        for key in self.inputs:
            val = get(key)
            widget = self.inputs[key]
            
            if isinstance(widget, QLineEdit): widget.setText(val)
            elif isinstance(widget, QTextEdit): widget.setText(val)
            elif isinstance(widget, QComboBox): widget.setCurrentText(val)
            elif isinstance(widget, QDateEdit): 
                if val: 
                    try: widget.setDate(QDate.fromString(val, "yyyy-MM-dd"))
                    except: pass

        # Özel Tarih (Sadece Yıl)
        yil = get("HizmetYili")
        if yil: 
            try: self.inputs["HizmetYili"].setDate(QDate(int(yil), 1, 1))
            except: pass

        # Kilitler
        self.inputs["Durum"].setEnabled(False)
        self.inputs["KontrolTarihi"].setEnabled(False)

        self.btn_kaydet.setText("GÜNCELLE")
        self.btn_kaydet.setStyleSheet("background-color: #ff9800; color: #222; border-radius: 6px; font-weight: bold;")
        
        self.gecmisi_yukle(self.inputs["EkipmanNo"].text())

    def gecmisi_yukle(self, ekipman_no):
        self.tbl_gecmis.setRowCount(0)
        if not self.muayene_listesi: return
        
        headers = self.muayene_listesi[0]
        try:
            idx_ekip = headers.index("EkipmanNo")
            idx_tarih = headers.index("F_MuayeneTarihi")
            idx_sonuc = headers.index("FizikselDurum")
            idx_acik = headers.index("Aciklamalar")
        except: return
        
        for row in self.muayene_listesi[1:]:
            if len(row) > idx_ekip and row[idx_ekip] == ekipman_no:
                r = self.tbl_gecmis.rowCount()
                self.tbl_gecmis.insertRow(r)
                self.tbl_gecmis.setItem(r, 0, QTableWidgetItem(row[idx_tarih] if len(row)>idx_tarih else ""))
                self.tbl_gecmis.setItem(r, 1, QTableWidgetItem(row[idx_sonuc] if len(row)>idx_sonuc else ""))
                self.tbl_gecmis.setItem(r, 2, QTableWidgetItem(row[idx_acik] if len(row)>idx_acik else ""))

    def temizle(self):
        self.secili_satir_id = None
        self.secili_satir_index = None
        
        for widget in self.inputs.values():
            if isinstance(widget, QLineEdit): widget.clear()
            elif isinstance(widget, QTextEdit): widget.clear()
            elif isinstance(widget, QComboBox): widget.setCurrentIndex(0)
            elif isinstance(widget, QDateEdit): widget.setDate(QDate.currentDate())
            
        self.inputs["KayitNo"].setText("Otomatik")
        
        self.inputs["Durum"].setEnabled(True)
        self.inputs["KontrolTarihi"].setEnabled(True)
        self.tbl_gecmis.setRowCount(0)
        
        self.btn_kaydet.setText("KAYDET")
        self.btn_kaydet.setStyleSheet("background-color: #2e7d32; color: white; border-radius: 6px; font-weight: bold;")

    def kaydet(self):
        if not self.inputs["EkipmanNo"].text():
            show_error("Eksik", "Ekipman No zorunludur.", self)
            return

        kayit_id = self.secili_satir_id if self.secili_satir_id else f"RKE-{int(time.time())}"
        
        # 15 Sütunluk Veri Yapısı
        yeni_veri = [
            kayit_id,
            self.inputs["EkipmanNo"].text(),
            self.inputs["KoruyucuNumarasi"].text(),
            self.inputs["AnaBilimDali"].currentText(),
            self.inputs["Birim"].currentText(),
            self.inputs["KoruyucuCinsi"].currentText(),
            self.inputs["KursunEsdegeri"].currentText(),
            self.inputs["HizmetYili"].text(),
            self.inputs["Bedeni"].currentText(),
            self.inputs["KontrolTarihi"].text(),
            self.inputs["Durum"].currentText(),
            self.inputs["Açiklama"].toPlainText(),
            self.inputs["Varsa_Demirbaş_No"].text(),
            self.inputs["KayitTarih"].text(), 
            self.inputs["Barkod"].text()
        ]
        
        mod = "UPDATE" if self.secili_satir_id else "INSERT"
        
        self.pbar.setVisible(True)
        self.pbar.setRange(0, 0)
        self.btn_kaydet.setEnabled(False)
        
        self.saver = RKEIslemKaydedici(mod, yeni_veri, self.secili_satir_index)
        self.saver.islem_tamam.connect(self.islem_basarili)
        self.saver.hata_olustu.connect(lambda e: show_error("Hata", e, self))
        self.saver.start()

    def islem_basarili(self):
        self.pbar.setVisible(False)
        self.btn_kaydet.setEnabled(True)
        show_info("Başarılı", "İşlem tamamlandı.", self)
        self.temizle()
        self.verileri_yukle()

    # Thread Güvenliği
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
    from temalar.tema import TemaYonetimi
    TemaYonetimi.uygula_fusion_dark(app)
    win = RKEYonetimPenceresi()
    win.show()
    sys.exit(app.exec())