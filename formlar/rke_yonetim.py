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
                               QComboBox, QDateEdit, QFormLayout, QGroupBox, QSplitter, 
                               QSizePolicy, QFrame, QGraphicsDropShadowEffect, 
                               QScrollArea, QAbstractItemView, QCompleter, QProgressBar)
from PySide6.QtCore import Qt, QDate, QThread, Signal, QSize
from PySide6.QtGui import QColor, QBrush, QIcon, QFont

# --- LOGLAMA ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RKEYonetim")

# --- BAĞLANTILAR ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from araclar.yetki_yonetimi import YetkiYoneticisi

try:
    from google_baglanti import veritabani_getir
    from araclar.ortak_araclar import show_info, show_error, pencereyi_kapat
except ImportError:
    def veritabani_getir(vt_tipi, sayfa_adi): return None
    def show_info(t, m, p): print(m)
    def show_error(t, m, p): print(m)
    def pencereyi_kapat(w): w.close()

# =============================================================================
# 1. WORKER THREADS (ARKA PLAN İŞLEMLERİ)
# =============================================================================

class RKEVeriYukleyici(QThread):
    # Sinyal: (RKE_Listesi, ABD_Listesi, Kaynak_Listesi)
    veri_hazir = Signal(list, list, list)
    hata_olustu = Signal(str)

    def run(self):
        try:
            rke_listesi = []
            abd_listesi = []
            kaynak_listesi = []

            # 1. RKE Listesini Çek
            ws_rke = veritabani_getir('rke', 'rke_list')
            if ws_rke:
                raw_data = ws_rke.get_all_values()
                if len(raw_data) > 1:
                    # Başlıkları atla
                    rke_listesi = raw_data[1:]

            # 2. Sabitleri Çek (ABD ve Kaynak)
            ws_sabit = veritabani_getir('sabit', 'Sabitler')
            if ws_sabit:
                raw_sabit = ws_sabit.get_all_records()
                for row in raw_sabit:
                    kod = str(row.get('Kod', '')).strip()
                    eleman = str(row.get('MenuEleman', '')).strip()
                    
                    if kod == "AnaBilimDali":
                        abd_listesi.append(eleman)
                    elif kod == "Kaynak":
                        kaynak_listesi.append(eleman)

            self.veri_hazir.emit(rke_listesi, sorted(abd_listesi), sorted(kaynak_listesi))

        except Exception as e:
            self.hata_olustu.emit(str(e))

class RKEIslemKaydedici(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)

    def __init__(self, mod, veri, satir_idx=None):
        super().__init__()
        self.mod = mod  # "INSERT" veya "UPDATE"
        self.veri = veri
        self.satir_idx = satir_idx # Güncelleme için satır numarası (GSpread 1-based index)

    def run(self):
        try:
            ws = veritabani_getir('rke', 'rke_list')
            if not ws: raise Exception("Veritabanı bağlantısı yok.")

            if self.mod == "INSERT":
                ws.append_row(self.veri)
            
            elif self.mod == "UPDATE" and self.satir_idx:
                # Satırı güncelle (A sütunundan başlayarak)
                # Sütun sayısı kadar alanı güncelle
                range_adresi = f"A{self.satir_idx}:L{self.satir_idx}" # A'dan L'ye kadar varsayalım
                ws.update(range_name=range_adresi, values=[self.veri])

            self.islem_tamam.emit()

        except Exception as e:
            self.hata_olustu.emit(str(e))

# =============================================================================
# 2. UI BİLEŞENLERİ (MODERN STİL)
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
        
        self.widget.setStyleSheet(f"""
            QLineEdit, QComboBox, QDateEdit {{ {base_style} }}
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{ {focus_style} }}
            QComboBox::drop-down {{ width: 25px; border: none; }}
            QDateEdit::drop-down {{ width: 25px; border: none; }}
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
# 3. ANA PENCERE: RKE YÖNETİM
# =============================================================================

class RKEYonetimPenceresi(QWidget):
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.setWindowTitle("RKE Envanter Yönetimi")
        self.resize(1300, 800)
        self.setStyleSheet("background-color: #121212; color: #e0e0e0; font-family: 'Segoe UI';")
        
        self.inputs = {}
        self.tum_veri = []
        self.secili_satir_id = None
        self.secili_satir_index = None # DB Row Index
        
        self.setup_ui()
        YetkiYoneticisi.uygula(self, "rke_yonetim")
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
        sol_layout.setContentsMargins(0, 0, 10, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        form_inner = QWidget()
        form_inner.setStyleSheet("background: transparent;")
        form_layout = QVBoxLayout(form_inner)
        form_layout.setSpacing(20)
        
        # Kart 1: Kimlik
        card_kimlik = InfoCard("Ekipman Kimliği", color="#ab47bc")
        
        self.txt_id = QLineEdit(); self.txt_id.setPlaceholderText("Otomatik Üretilir")
        self.txt_id.setReadOnly(True); self.txt_id.setStyleSheet("color: #777; font-style: italic;")
        self.add_input(card_kimlik, "Kayıt ID", self.txt_id, "id")
        
        self.txt_ekipman_no = QLineEdit()
        self.add_input(card_kimlik, "Ekipman No (Etiket)", self.txt_ekipman_no, "ekipman_no")
        
        row1 = QHBoxLayout(); row1.setSpacing(15)
        self.cmb_cins = QComboBox(); self.cmb_cins.addItems(["Kurşun Önlük", "Tiroid Koruyucu", "Gonad Koruyucu", "Kurşun Gözlük", "Paravan", "Diğer"])
        self.cmb_pb = QComboBox(); self.cmb_pb.addItems(["0.25 mmPb", "0.35 mmPb", "0.50 mmPb", "1.00 mmPb"])
        self.add_input_to_layout(row1, "Koruyucu Cinsi", self.cmb_cins, "cins")
        self.add_input_to_layout(row1, "Kurşun Eşdeğeri", self.cmb_pb, "pb")
        card_kimlik.add_layout(row1)
        
        form_layout.addWidget(card_kimlik)
        
        # Kart 2: Lokasyon
        card_lokasyon = InfoCard("Lokasyon Bilgisi", color="#29b6f6")
        self.cmb_abd = QComboBox()
        self.cmb_birim = QComboBox(); self.cmb_birim.setEditable(True)
        self.add_input(card_lokasyon, "Ana Bilim Dalı", self.cmb_abd, "abd")
        self.add_input(card_lokasyon, "Birim / Oda", self.cmb_birim, "birim")
        form_layout.addWidget(card_lokasyon)
        
        # Kart 3: Detaylar
        card_detay = InfoCard("Diğer Özellikler", color="#ffa726")
        row2 = QHBoxLayout(); row2.setSpacing(15)
        self.txt_yil = QLineEdit()
        self.cmb_beden = QComboBox(); self.cmb_beden.addItems(["Standart", "S", "M", "L", "XL", "XXL"])
        self.add_input_to_layout(row2, "Üretim Yılı", self.txt_yil, "yil")
        self.add_input_to_layout(row2, "Beden", self.cmb_beden, "beden")
        card_detay.add_layout(row2)
        
        self.dt_tarih = QDateEdit(); self.dt_tarih.setCalendarPopup(True); self.dt_tarih.setDate(QDate.currentDate()); self.dt_tarih.setDisplayFormat("yyyy-MM-dd")
        self.add_input(card_detay, "Envantere Giriş Tarihi", self.dt_tarih, "tarih")
        
        self.cmb_durum = QComboBox(); self.cmb_durum.addItems(["Kullanıma Uygun", "Kullanıma Uygun Değil", "Hurda"])
        self.add_input(card_detay, "Güncel Durum", self.cmb_durum, "durum")
        
        form_layout.addWidget(card_detay)
        
        scroll.setWidget(form_inner)
        sol_layout.addWidget(scroll)
        
        # Butonlar
        self.pbar = QProgressBar(); self.pbar.setVisible(False); self.pbar.setFixedHeight(4); sol_layout.addWidget(self.pbar)
        
        h_btn = QHBoxLayout()
        self.btn_temizle = QPushButton("TEMİZLE / YENİ"); self.btn_temizle.setObjectName("btn_temizle"); self.btn_temizle.setFixedHeight(45)
        self.btn_temizle.setStyleSheet("background: transparent; border: 1px solid #555; color: #aaa; border-radius: 6px;")
        self.btn_temizle.clicked.connect(self.temizle)
        
        self.btn_kaydet = QPushButton("KAYDET"); self.btn_kaydet.setObjectName("btn_kaydet"); self.btn_kaydet.setFixedHeight(45)
        self.btn_kaydet.setStyleSheet("QPushButton { background-color: #2e7d32; color: white; border-radius: 6px; font-weight: bold; font-size: 13px; border: none; } QPushButton:hover { background-color: #388e3c; }")
        self.btn_kaydet.clicked.connect(self.kaydet)
        
        h_btn.addWidget(self.btn_temizle); h_btn.addWidget(self.btn_kaydet)
        sol_layout.addLayout(h_btn)
        
        # --- SAĞ PANEL (LİSTE) ---
        sag_widget = QWidget(); sag_layout = QVBoxLayout(sag_widget)
        sag_layout.setContentsMargins(10, 0, 0, 0); sag_layout.setSpacing(10)
        
        # Filtre
        filter_frame = QFrame(); filter_frame.setStyleSheet("background: #1e1e1e; border-radius: 8px; border: 1px solid #333;")
        h_filter = QHBoxLayout(filter_frame); h_filter.setContentsMargins(10, 10, 10, 10)
        lbl_baslik = QLabel("RKE Envanter Listesi"); lbl_baslik.setStyleSheet("font-size: 16px; font-weight: bold; color: #29b6f6;")
        self.txt_ara = QLineEdit(); self.txt_ara.setPlaceholderText("Ara..."); self.txt_ara.setStyleSheet("background: #2d2d2d; border: 1px solid #444; border-radius: 20px; padding: 5px 15px; color: white;")
        self.txt_ara.textChanged.connect(self.tabloyu_filtrele)
        btn_yenile = QPushButton("⟳"); btn_yenile.setFixedSize(35, 35); btn_yenile.clicked.connect(self.verileri_yukle); btn_yenile.setStyleSheet("background: #333; color: white; border: 1px solid #444; border-radius: 4px;")
        h_filter.addWidget(lbl_baslik); h_filter.addStretch(); h_filter.addWidget(self.txt_ara); h_filter.addWidget(btn_yenile)
        sag_layout.addWidget(filter_frame)
        
        # Tablo
        self.tablo = QTableWidget()
        self.tablo.setColumnCount(6)
        self.tablo.setHorizontalHeaderLabels(["ID", "Ekipman No", "ABD", "Cins", "Pb", "Durum"])
        self.tablo.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tablo.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tablo.setSelectionBehavior(QTableWidget.SelectRows)
        self.tablo.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tablo.setAlternatingRowColors(True)
        self.tablo.setStyleSheet("QTableWidget { background: #1e1e1e; border: none; gridline-color: #333; alternate-background-color: #252525; } QHeaderView::section { background: #2d2d2d; border: none; padding: 8px; color: #b0b0b0; font-weight: bold; font-size: 12px; } QTableWidget::item { padding: 5px; border-bottom: 1px solid #2a2a2a; } QTableWidget::item:selected { background-color: #3949ab; color: white; }")
        self.tablo.cellClicked.connect(self.satir_secildi)
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

    # --- MANTIK ---
    def verileri_yukle(self):
        self.pbar.setVisible(True)
        self.pbar.setRange(0, 0)
        self.loader = RKEVeriYukleyici()
        self.loader.veri_hazir.connect(self.verileri_doldur)
        self.loader.hata_olustu.connect(lambda e: show_error("Hata", e, self))
        self.loader.finished.connect(lambda: self.pbar.setVisible(False))
        self.loader.start()

    def verileri_doldur(self, rke_list, abd_list, kaynak_list):
        self.tum_veri = rke_list
        
        self.inputs["abd"].clear()
        self.inputs["abd"].addItems(abd_list)
        
        # Birimler şimdilik manuel veya ABD'ye göre filtrelenebilir (Basit tutuyoruz)
        self.inputs["birim"].clear()
        self.inputs["birim"].addItem("Radyoloji")
        self.inputs["birim"].addItem("Ameliyathane")
        self.inputs["birim"].addItem("Anjiyo")
        
        self.tabloyu_guncelle()

    def tabloyu_guncelle(self):
        self.tablo.setRowCount(0)
        text = self.txt_ara.text().lower()
        
        for i, row in enumerate(self.tum_veri):
            # Sıra: ID[0], EkipmanNo[1], ABD[2], Birim[3], Cins[4], Pb[5], Yil[6], Beden[7], Tarih[8], Durum[9] ...
            if len(row) < 10: continue
            
            full_str = " ".join([str(x) for x in row]).lower()
            if text and text not in full_str: continue
            
            r = self.tablo.rowCount()
            self.tablo.insertRow(r)
            
            self.tablo.setItem(r, 0, QTableWidgetItem(str(row[0])))
            self.tablo.setItem(r, 1, QTableWidgetItem(str(row[1])))
            self.tablo.setItem(r, 2, QTableWidgetItem(str(row[2])))
            self.tablo.setItem(r, 3, QTableWidgetItem(str(row[4])))
            self.tablo.setItem(r, 4, QTableWidgetItem(str(row[5])))
            
            durum = str(row[11]) if len(row) > 11 else str(row[9]) # Bazen sütun kayabilir
            item_durum = QTableWidgetItem(durum)
            if "Değil" in durum or "Hurda" in durum: item_durum.setForeground(QColor("#ef5350"))
            else: item_durum.setForeground(QColor("#66bb6a"))
            self.tablo.setItem(r, 5, item_durum)
            
            # Satırın gerçek indeksini (Google Sheets satır no = i + 2 [başlık hariç]) sakla
            self.tablo.item(r, 0).setData(Qt.UserRole, i + 2)
            self.tablo.item(r, 0).setData(Qt.UserRole + 1, row) # Tüm veri

    def tabloyu_filtrele(self):
        self.tabloyu_guncelle()

    def satir_secildi(self, row, col):
        item = self.tablo.item(row, 0)
        if not item: return
        
        satir_idx = item.data(Qt.UserRole)
        row_data = item.data(Qt.UserRole + 1)
        
        self.secili_satir_id = str(row_data[0])
        self.secili_satir_index = satir_idx
        
        self.btn_kaydet.setText("GÜNCELLE")
        self.btn_kaydet.setStyleSheet("background-color: #FFA000; color: white; border-radius: 6px; font-weight: bold; border: none;")
        
        # Formu Doldur
        try:
            self.inputs["id"].setText(str(row_data[0]))
            self.inputs["ekipman_no"].setText(str(row_data[1]))
            self.inputs["abd"].setCurrentText(str(row_data[2]))
            self.inputs["birim"].setCurrentText(str(row_data[3]))
            self.inputs["cins"].setCurrentText(str(row_data[4]))
            self.inputs["pb"].setCurrentText(str(row_data[5]))
            self.inputs["yil"].setText(str(row_data[6]))
            self.inputs["beden"].setCurrentText(str(row_data[7]))
            
            tarih_str = str(row_data[8])
            if tarih_str: self.inputs["tarih"].setDate(QDate.fromString(tarih_str, "yyyy-MM-dd"))
            
            # Durum sütunu bazen farklı yerde olabilir (9 veya 11)
            durum_val = str(row_data[9])
            if durum_val not in ["Kullanıma Uygun", "Hurda"]: 
                # Belki 11. sütundadır (Muayene sonucu güncelliyor olabilir)
                if len(row_data) > 11: durum_val = str(row_data[11])
            
            self.inputs["durum"].setCurrentText(durum_val)
            
        except Exception as e:
            logger.error(f"Form doldurma hatası: {e}")

    def temizle(self):
        self.secili_satir_id = None
        self.secili_satir_index = None
        self.btn_kaydet.setText("KAYDET")
        self.btn_kaydet.setStyleSheet("background-color: #2e7d32; color: white; border-radius: 6px; font-weight: bold; border: none;")
        
        self.inputs["id"].setText("Otomatik")
        self.inputs["ekipman_no"].clear()
        self.inputs["yil"].clear()
        self.inputs["tarih"].setDate(QDate.currentDate())
        self.inputs["durum"].setCurrentIndex(0)

    def kaydet(self):
        if not self.inputs["ekipman_no"].text():
            show_error("Eksik", "Ekipman numarası girilmelidir.", self)
            return

        # ID Üret (Yeni ise)
        kayit_id = self.secili_satir_id if self.secili_satir_id else f"RKE-{int(time.time())}"
        
        # Veri Sırası: ID, EkipmanNo, ABD, Birim, Cins, Pb, Yil, Beden, Tarih, Durum, (SonMuayeneTarih), (GenelDurum), (EklenmeTarihi)
        # Google Sheets yapısına uygun olmalı
        
        yeni_veri = [
            kayit_id,
            self.inputs["ekipman_no"].text(),
            self.inputs["abd"].currentText(),
            self.inputs["birim"].currentText(),
            self.inputs["cins"].currentText(),
            self.inputs["pb"].currentText(),
            self.inputs["yil"].text(), 
            self.inputs["beden"].currentText(),
            self.inputs["tarih"].text(),
            self.inputs["durum"].currentText(),
            "", "", 
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

    # 🟢 DEĞİŞİKLİK 3: Thread Güvenliği
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