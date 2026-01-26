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
                               QScrollArea, QCompleter, QGroupBox, QSizePolicy, QDialog, 
                               QCheckBox, QListWidget, QAbstractItemView, QStyledItemDelegate)
from PySide6.QtCore import Qt, QDate, QThread, Signal, QSize, QUrl, QEvent, QTimer
from PySide6.QtGui import QColor, QBrush, QIcon, QDesktopServices, QFont, QStandardItemModel, QStandardItem, QPalette

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

# =============================================================================
# 0. YARDIMCI FONKSİYONLAR
# =============================================================================
def envanter_durumunu_belirle(fiziksel, skopi):
    """
    Muayene sonuçlarına göre rke_list tablosundaki Durum'u belirler.
    Kural: Fiziksel 'Sağlam' VE Skopi 'Uygun' (veya Yapılmadı) ise -> Kullanıma Uygun
    Aksi halde -> Kullanıma Uygun Değil
    """
    fiz_ok = (fiziksel == "Kulanıma Uygun")
    sko_ok = (skopi == "Kullanıma Uygun" or skopi == "Yapılmadı")
    
    if fiz_ok and sko_ok:
        return "Kullanıma Uygun"
    else:
        return "Kullanıma Uygun Değil"

# =============================================================================
# 1. ÖZEL BİLEŞENLER (CHECKABLE COMBOBOX)
# =============================================================================
class CheckableComboBox(QComboBox):
    def __init__(self, parent=None):
        super(CheckableComboBox, self).__init__(parent)
        self.view().pressed.connect(self.handleItemPressed)
        self.setModel(QStandardItemModel(self))
        self.setEditable(True)
        self.lineEdit().setReadOnly(True) 
        
        # Tema uyumu
        palette = self.lineEdit().palette()
        palette.setColor(QPalette.Base, QColor("#2d2d2d"))
        palette.setColor(QPalette.Text, QColor("#ffffff"))
        self.lineEdit().setPalette(palette)

    def handleItemPressed(self, index):
        item = self.model().itemFromIndex(index)
        if item.checkState() == Qt.Checked:
            item.setCheckState(Qt.Unchecked)
        else:
            item.setCheckState(Qt.Checked)
        
        # 🟢 KRİTİK DÜZELTME: Metin güncellemesini asenkron yaparak ezilmeyi önle
        QTimer.singleShot(10, self.updateText)

    def updateText(self):
        items = []
        for i in range(self.count()):
            item = self.model().item(i)
            if item.checkState() == Qt.Checked:
                items.append(item.text())
        
        text = ", ".join(items)
        self.lineEdit().setText(text)

    def setCheckedItems(self, text_list):
        if isinstance(text_list, str): 
            text_list = [x.strip() for x in text_list.split(',')] if text_list else []
        elif not text_list:
            text_list = []
            
        for i in range(self.count()):
            item = self.model().item(i)
            item.setCheckState(Qt.Checked if item.text() in text_list else Qt.Unchecked)
        self.updateText()

    def getCheckedItems(self):
        return self.lineEdit().text()

    def addItem(self, text, data=None):
        item = QStandardItem(text)
        item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        item.setData(Qt.Unchecked, Qt.CheckStateRole)
        self.model().appendRow(item)

    def addItems(self, texts):
        for text in texts: self.addItem(text)

# =============================================================================
# 2. WORKER THREADS
# =============================================================================

class VeriYukleyici(QThread):
    veri_hazir = Signal(list, list, dict, list, list, list)
    hata_olustu = Signal(str)

    def run(self):
        try:
            rke_data = []
            rke_combo = []
            rke_dict = {} 
            muayene_listesi = []
            headers = []
            teknik_aciklamalar = []

            # 1. RKE LİSTESİ
            ws_rke = veritabani_getir('rke', 'rke_list')
            if ws_rke:
                rke_data = ws_rke.get_all_records()
                for row in rke_data:
                    ekipman_no = str(row.get('EkipmanNo', '')).strip()
                    cins = str(row.get('KoruyucuCinsi', '')).strip()
                    if ekipman_no:
                        display = f"{ekipman_no} | {cins}"
                        rke_combo.append(display)
                        rke_dict[display] = ekipman_no

            # 2. MUAYENE GEÇMİŞİ
            ws_muayene = veritabani_getir('rke', 'rke_muayene')
            if ws_muayene:
                raw_muayene = ws_muayene.get_all_values()
                if len(raw_muayene) > 0:
                    headers = raw_muayene[0]
                    muayene_listesi = raw_muayene[1:]

            # 3. SABİTLER (Teknik Açıklamalar)
            ws_sabit = veritabani_getir('sabit', 'Sabitler')
            if ws_sabit:
                sabitler = ws_sabit.get_all_records()
                for s in sabitler:
                    if str(s.get('Kod', '')).strip() == "RKE_Teknik":
                        eleman = str(s.get('MenuEleman', '')).strip()
                        if eleman: teknik_aciklamalar.append(eleman)
            
            if not teknik_aciklamalar:
                teknik_aciklamalar = ["Yırtık Yok", "Kurşun Bütünlüğü Tam", "Askılar Sağlam", "Temiz"]

            self.veri_hazir.emit(rke_data, sorted(rke_combo), rke_dict, muayene_listesi, headers, sorted(teknik_aciklamalar))

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
                drive = GoogleDriveService()
                link = drive.upload_file(self.dosya_yolu, DRIVE_KLASOR_ID)
                if link: drive_link = link

            self.progress.emit("Muayene kaydediliyor...")
            ws_muayene = veritabani_getir('rke', 'rke_muayene')
            if not ws_muayene: raise Exception("Veritabanı bağlantısı yok.")

            satir = [
                self.veri['KayitNo'], self.veri['EkipmanNo'],
                self.veri['F_MuayeneTarihi'], self.veri['FizikselDurum'],
                self.veri['S_MuayeneTarihi'], self.veri['SkopiDurum'],
                self.veri['Aciklamalar'], self.veri['KontrolEden'],
                self.veri['BirimSorumlusu'], self.veri['Not'], drive_link
            ]
            ws_muayene.append_row(satir)

            # ... (Önceki kodlar aynı) ...

            # 🟢 GÜNCELLEME: rke_list GÜNCELLEMESİ
            self.progress.emit("Envanter durumu güncelleniyor...")
            ws_list = veritabani_getir('rke', 'rke_list')
            if ws_list:
                ekipman_no = self.veri['EkipmanNo']
                cell = ws_list.find(ekipman_no)
                if cell:
                    # Durum Hesapla
                    yeni_durum = envanter_durumunu_belirle(self.veri['FizikselDurum'], self.veri['SkopiDurum'])
                    
                    # Gelecek Kontrol Tarihi Hesapla (Skopi Tarihi + 1 Yıl)
                    skopi_tarih_str = self.veri['S_MuayeneTarihi']
                    gelecek_kontrol_tarihi = ""
                    if skopi_tarih_str:
                        try:
                            # String'i tarihe çevir -> 1 yıl ekle -> tekrar string yap
                            dt_obj = datetime.datetime.strptime(skopi_tarih_str, "%Y-%m-%d")
                            gelecek_kontrol_tarihi = (dt_obj + relativedelta(years=1)).strftime("%Y-%m-%d")
                        except:
                            gelecek_kontrol_tarihi = skopi_tarih_str # Hata olursa aynısı kalsın

                    # Sütunları Bul
                    headers = ws_list.row_values(1)
                    try: col_tarih = headers.index("KontrolTarihi") + 1
                    except: col_tarih = -1
                    try: col_durum = headers.index("Durum") + 1
                    except: col_durum = -1
                    try: col_aciklama = headers.index("Açiklama") + 1
                    except: col_aciklama = -1
                    
                    # Güncelleme
                    if col_tarih > 0 and gelecek_kontrol_tarihi: 
                        ws_list.update_cell(cell.row, col_tarih, gelecek_kontrol_tarihi)
                    if col_durum > 0: 
                        ws_list.update_cell(cell.row, col_durum, yeni_durum)
                    if col_aciklama > 0: 
                        ws_list.update_cell(cell.row, col_aciklama, self.veri['Aciklamalar'])

            self.finished.emit("Kayıt ve güncelleme başarılı.")

        except Exception as e:
            self.error.emit(str(e))

class TopluKayitWorker(QThread):
    progress = Signal(int, int)
    finished = Signal()
    error = Signal(str)
    
    def __init__(self, ekipman_listesi, ortak_veri, dosya_yolu, fiziksel_aktif, skopi_aktif):
        super().__init__()
        self.ekipman_listesi = ekipman_listesi
        self.ortak_veri = ortak_veri
        self.dosya_yolu = dosya_yolu
        self.fiziksel_aktif = fiziksel_aktif
        self.skopi_aktif = skopi_aktif
        
    def run(self):
        try:
            drive_link = "-"
            if self.dosya_yolu and os.path.exists(self.dosya_yolu):
                drive = GoogleDriveService()
                link = drive.upload_file(self.dosya_yolu, DRIVE_KLASOR_ID)
                if link: drive_link = link
            
            ws_muayene = veritabani_getir('rke', 'rke_muayene')
            ws_list = veritabani_getir('rke', 'rke_list')
            if not ws_muayene or not ws_list: raise Exception("Veritabanı bağlantısı yok.")
            
            headers = ws_list.row_values(1)
            try: col_tarih = headers.index("KontrolTarihi") + 1
            except: col_tarih = -1
            try: col_durum = headers.index("Durum") + 1
            except: col_durum = -1
            try: col_aciklama = headers.index("Açiklama") + 1
            except: col_aciklama = -1
            try: col_ekipman_idx = headers.index("EkipmanNo") + 1
            except: col_ekipman_idx = 2 
            
            all_ekipman_nos = ws_list.col_values(col_ekipman_idx)
            rows_to_add = []
            batch_updates = [] 
            base_time = int(time.time())
            
            for idx, ekipman_no in enumerate(self.ekipman_listesi):
                unique_id = f"M-{base_time}-{idx}"
                f_tarih = self.ortak_veri['F_MuayeneTarihi'] if self.fiziksel_aktif else ""
                f_durum = self.ortak_veri['FizikselDurum'] if self.fiziksel_aktif else ""
                s_tarih = self.ortak_veri['S_MuayeneTarihi'] if self.skopi_aktif else ""
                s_durum = self.ortak_veri['SkopiDurum'] if self.skopi_aktif else ""
                
                # 1. Muayene Kaydı
                row = [
                    unique_id, ekipman_no, f_tarih, f_durum, s_tarih, s_durum,
                    self.ortak_veri['Aciklamalar'], self.ortak_veri['KontrolEden'],
                    self.ortak_veri['BirimSorumlusu'], self.ortak_veri['Not'], drive_link
                ]
                rows_to_add.append(row)
                
                # ... (Önceki kodlar aynı) ...
                
                # 2. Envanter Güncelleme Verisi Hazırla
                try:
                    row_num = all_ekipman_nos.index(ekipman_no) + 1
                    yeni_genel_durum = envanter_durumunu_belirle(f_durum, s_durum)
                    
                    # Gelecek Kontrol Tarihi Hesapla (Skopi Tarihi + 1 Yıl)
                    gelecek_kontrol_tarihi = ""
                    if s_tarih: # s_tarih, skopi_aktif ise doludur
                        try:
                            dt_obj = datetime.datetime.strptime(s_tarih, "%Y-%m-%d")
                            gelecek_kontrol_tarihi = (dt_obj + relativedelta(years=1)).strftime("%Y-%m-%d")
                        except:
                            gelecek_kontrol_tarihi = s_tarih

                    if col_tarih > 0 and gelecek_kontrol_tarihi: 
                        batch_updates.append({'range': f"{chr(64+col_tarih)}{row_num}", 'values': [[gelecek_kontrol_tarihi]]})
                    if col_durum > 0:
                        batch_updates.append({'range': f"{chr(64+col_durum)}{row_num}", 'values': [[yeni_genel_durum]]})
                    if col_aciklama > 0:
                        batch_updates.append({'range': f"{chr(64+col_aciklama)}{row_num}", 'values': [[self.ortak_veri['Aciklamalar']]]})
                        
                except ValueError:
                    pass

                self.progress.emit(idx + 1, len(self.ekipman_listesi))
            
            ws_muayene.append_rows(rows_to_add)
            if batch_updates: ws_list.batch_update(batch_updates)
            self.finished.emit()
            
        except Exception as e:
            self.error.emit(str(e))

# =============================================================================
# 3. UI BİLEŞENLERİ (ModernInputGroup, InfoCard) - KORUNDU
# =============================================================================
class ModernInputGroup(QWidget):
    def __init__(self, label_text, widget, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 5); layout.setSpacing(5)
        self.lbl = QLabel(label_text)
        self.lbl.setStyleSheet("color: #b0b0b0; font-size: 11px; font-weight: bold; text-transform: uppercase;")
        self.widget = widget; self.widget.setMinimumHeight(40); self.widget.setMinimumWidth(150)
        if isinstance(widget, QTextEdit): self.widget.setMinimumHeight(60)
        layout.addWidget(self.lbl); layout.addWidget(self.widget)

class InfoCard(QGroupBox):
    def __init__(self, title, parent=None, color="#4dabf7"):
        super().__init__(title, parent)
        self.setStyleSheet(f"QGroupBox {{ background-color: #2d2d2d; border: 1px solid #444; border-radius: 8px; margin-top: 20px; font-weight: bold; color: {color}; }} QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; padding: 0 10px; left: 10px; }}")
        shadow = QGraphicsDropShadowEffect(self); shadow.setBlurRadius(15); shadow.setColor(QColor(0, 0, 0, 80)); self.setGraphicsEffect(shadow)
        self.layout = QVBoxLayout(self); self.layout.setContentsMargins(15, 20, 15, 15); self.layout.setSpacing(15)
    def add_widget(self, w): self.layout.addWidget(w)
    def add_layout(self, l): self.layout.addLayout(l)

# =============================================================================
# 4. TOPLU MUAYENE DİALOG
# =============================================================================
class TopluMuayeneDialog(QDialog):
    def __init__(self, secilen_ekipmanlar, teknik_aciklamalar, kullanici_adi=None, parent=None):
        super().__init__(parent)
        self.ekipmanlar = secilen_ekipmanlar
        self.teknik_aciklamalar = teknik_aciklamalar
        self.kullanici_adi = kullanici_adi
        self.dosya_yolu = None
        self.setWindowTitle(f"Toplu Muayene ({len(self.ekipmanlar)} Adet)")
        self.resize(700, 650)
        self.setup_ui()
        
    def setup_ui(self):
        main_lay = QVBoxLayout(self)
        
        gb_list = QGroupBox(f"Ekipmanlar ({len(self.ekipmanlar)})")
        v_list = QVBoxLayout(gb_list)
        lst = QListWidget(); lst.addItems(self.ekipmanlar); lst.setFixedHeight(100)
        v_list.addWidget(lst); main_lay.addWidget(gb_list)
        
        gb_fiz = QGroupBox("Fiziksel Muayene"); gb_fiz.setCheckable(True); gb_fiz.setChecked(True); self.chk_fiz = gb_fiz
        h_fiz = QHBoxLayout(gb_fiz)
        self.dt_fiz = QDateEdit(QDate.currentDate()); self.dt_fiz.setCalendarPopup(True)
        self.cmb_fiz = QComboBox(); self.cmb_fiz.addItems(["Kulanıma Uygun", "Kullanıma Uygun Değil"])
        h_fiz.addWidget(QLabel("Tarih:")); h_fiz.addWidget(self.dt_fiz); h_fiz.addWidget(QLabel("Durum:")); h_fiz.addWidget(self.cmb_fiz)
        main_lay.addWidget(gb_fiz)
        
        gb_sko = QGroupBox("Skopi Muayene"); gb_sko.setCheckable(True); gb_sko.setChecked(False); self.chk_sko = gb_sko
        h_sko = QHBoxLayout(gb_sko)
        self.dt_sko = QDateEdit(QDate.currentDate()); self.dt_sko.setCalendarPopup(True)
        self.cmb_sko = QComboBox(); self.cmb_sko.addItems(["Kullanıma Uygun", "Kullanıma Uygun Değil", "Yapılmadı"])
        h_sko.addWidget(QLabel("Tarih:")); h_sko.addWidget(self.dt_sko); h_sko.addWidget(QLabel("Durum:")); h_sko.addWidget(self.cmb_sko)
        main_lay.addWidget(gb_sko)
        
        gb_ortak = QGroupBox("Ortak Bilgiler"); form_lay = QVBoxLayout(gb_ortak)
        h_pers = QHBoxLayout()
        self.txt_kontrol = QLineEdit(); self.txt_kontrol.setPlaceholderText("Kontrol Eden")
        if self.kullanici_adi: self.txt_kontrol.setText(self.kullanici_adi)
        self.txt_sorumlu = QLineEdit(); self.txt_sorumlu.setPlaceholderText("Birim Sorumlusu")
        h_pers.addWidget(QLabel("Kontrol Eden:")); h_pers.addWidget(self.txt_kontrol); h_pers.addWidget(QLabel("Sorumlu:")); h_pers.addWidget(self.txt_sorumlu)
        form_lay.addLayout(h_pers)
        
        self.cmb_aciklama = CheckableComboBox()
        self.cmb_aciklama.addItems(self.teknik_aciklamalar)
        form_lay.addWidget(QLabel("Teknik Açıklama (Çoklu Seçim):")); form_lay.addWidget(self.cmb_aciklama)
        
        h_file = QHBoxLayout()
        self.lbl_file = QLabel("Dosya Yok"); btn_file = QPushButton("📂 Ortak Rapor"); btn_file.clicked.connect(self.dosya_sec)
        h_file.addWidget(self.lbl_file); h_file.addWidget(btn_file)
        form_lay.addLayout(h_file); main_lay.addWidget(gb_ortak)
        
        self.pbar = QProgressBar(); self.pbar.setVisible(False); main_lay.addWidget(self.pbar)
        h_btns = QHBoxLayout()
        btn_iptal = QPushButton("İptal"); btn_iptal.clicked.connect(self.reject)
        self.btn_kaydet = QPushButton("✅ Başlat"); self.btn_kaydet.setStyleSheet("background-color: #2e7d32; color: white; padding: 10px;")
        self.btn_kaydet.clicked.connect(self.kaydet)
        h_btns.addStretch(); h_btns.addWidget(btn_iptal); h_btns.addWidget(self.btn_kaydet)
        main_lay.addLayout(h_btns)
        
    def dosya_sec(self):
        yol, _ = QFileDialog.getOpenFileName(self, "Rapor", "", "PDF/Resim (*.pdf *.jpg)")
        if yol: self.dosya_yolu = yol; self.lbl_file.setText(os.path.basename(yol))
            
    def kaydet(self):
        if not self.chk_fiz.isChecked() and not self.chk_sko.isChecked():
            QMessageBox.warning(self, "Uyarı", "Muayene seçin."); return
        ortak_veri = {
            'F_MuayeneTarihi': self.dt_fiz.date().toString("yyyy-MM-dd"), 'FizikselDurum': self.cmb_fiz.currentText(),
            'S_MuayeneTarihi': self.dt_sko.date().toString("yyyy-MM-dd"), 'SkopiDurum': self.cmb_sko.currentText(),
            'Aciklamalar': self.cmb_aciklama.getCheckedItems(), 'KontrolEden': self.txt_kontrol.text(),
            'BirimSorumlusu': self.txt_sorumlu.text(), 'Not': "Toplu Kayıt"
        }
        self.btn_kaydet.setEnabled(False); self.pbar.setVisible(True); self.pbar.setRange(0, len(self.ekipmanlar))
        self.worker = TopluKayitWorker(self.ekipmanlar, ortak_veri, self.dosya_yolu, self.chk_fiz.isChecked(), self.chk_sko.isChecked())
        self.worker.progress.connect(self.pbar.setValue); self.worker.finished.connect(self.accept)
        self.worker.error.connect(lambda e: QMessageBox.critical(self, "Hata", e)); self.worker.start()

# =============================================================================
# 5. ANA PENCERE
# =============================================================================
class RKEMuayenePenceresi(QWidget):
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki; self.kullanici_adi = kullanici_adi
        self.setWindowTitle("RKE Muayene Girişi"); self.resize(1400, 850)
        self.rke_data = []; self.rke_dict = {}; self.tum_muayeneler = []; self.teknik_aciklamalar = []
        self.secilen_dosya = None; self.header_map = {}; self.inputs = {}
        self.setup_ui()
        YetkiYoneticisi.uygula(self, "rke_muayene")
        self.verileri_yukle()

    def setup_ui(self):
        main_layout = QHBoxLayout(self); main_layout.setContentsMargins(15, 15, 15, 15); main_layout.setSpacing(15)
        splitter = QSplitter(Qt.Horizontal); splitter.setHandleWidth(2); splitter.setStyleSheet("QSplitter::handle { background-color: #2b2b2b; }")

        # SOL PANEL
        sol_widget = QWidget(); sol_layout = QVBoxLayout(sol_widget); sol_layout.setContentsMargins(0, 0, 15, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame); scroll.setStyleSheet("background: transparent;")
        form_inner = QWidget(); form_inner.setStyleSheet("background: transparent;")
        form_layout = QVBoxLayout(form_inner); form_layout.setSpacing(20); form_layout.setContentsMargins(5, 5, 5, 20)

        # 1. Ekipman
        card_ekipman = InfoCard("Ekipman Seçimi", color="#ab47bc")
        self.cmb_rke = QComboBox(); self.cmb_rke.setEditable(True); self.cmb_rke.setPlaceholderText("Ara...")
        self.cmb_rke.completer().setCompletionMode(QCompleter.PopupCompletion)
        self.cmb_rke.currentIndexChanged.connect(self.ekipman_secildi)
        self.add_input(card_ekipman, "Ekipman No", self.cmb_rke, "ekipman")
        form_layout.addWidget(card_ekipman)

        # 2. Detaylar
        card_detay = InfoCard("Muayene Detayları", color="#29b6f6")
        row_fiz = QHBoxLayout(); row_fiz.setSpacing(15)
        self.dt_fiziksel = QDateEdit(QDate.currentDate()); self.dt_fiziksel.setCalendarPopup(True); self.dt_fiziksel.setDisplayFormat("yyyy-MM-dd")
        self.cmb_fiziksel = QComboBox(); self.cmb_fiziksel.setEditable(True); self.cmb_fiziksel.addItems(["Kulanıma Uygun", "Kullanıma Uygun Değil"])
        self.add_input_to_layout(row_fiz, "Fiziksel Muayene Tarihi", self.dt_fiziksel, "tarih_f")
        self.add_input_to_layout(row_fiz, "Fiziksel Muayene Durumu", self.cmb_fiziksel, "durum_f")
        card_detay.add_layout(row_fiz)
        
        row_sko = QHBoxLayout(); row_sko.setSpacing(15)
        self.dt_skopi = QDateEdit(QDate.currentDate()); self.dt_skopi.setCalendarPopup(True); self.dt_skopi.setDisplayFormat("yyyy-MM-dd")
        self.cmb_skopi = QComboBox(); self.cmb_skopi.setEditable(True); self.cmb_skopi.addItems(["Kullanıma Uygun", "Kullanıma Uygun Değil", "Yapılmadı"])
        self.add_input_to_layout(row_sko, "Skopi Muayene Tarihi", self.dt_skopi, "tarih_s")
        self.add_input_to_layout(row_sko, "Skopi Muayene Durumu", self.cmb_skopi, "durum_s")
        card_detay.add_layout(row_sko)
        form_layout.addWidget(card_detay)

        # 3. Sonuç
        card_sonuc = InfoCard("Sonuç ve Raporlama", color="#ffa726")
        row_pers = QHBoxLayout(); row_pers.setSpacing(15)
        self.txt_kontrol = QLineEdit(); self.txt_kontrol.setPlaceholderText("Kontrol Eden")
        if self.kullanici_adi: self.txt_kontrol.setText(str(self.kullanici_adi))
        self.txt_sorumlu = QLineEdit(); self.txt_sorumlu.setPlaceholderText("Birim Sorumlusu")
        self.add_input_to_layout(row_pers, "Kontrol Eden", self.txt_kontrol, "kontrol_eden")
        self.add_input_to_layout(row_pers, "Birim Sorumlusu", self.txt_sorumlu, "birim_sorumlu")
        card_sonuc.add_layout(row_pers)
        
        self.cmb_aciklama = CheckableComboBox()
        self.add_input(card_sonuc, "Teknik Açıklama (Çoklu Seçim)", self.cmb_aciklama, "aciklama")
        
        file_cont = QWidget(); fl = QHBoxLayout(file_cont); fl.setContentsMargins(0,0,0,0)
        self.lbl_dosya = QLabel("Rapor Yok"); self.lbl_dosya.setStyleSheet("color: #777; font-style: italic;")
        btn_dosya = QPushButton("📂 Rapor Yükle"); btn_dosya.setFixedSize(110, 35); btn_dosya.clicked.connect(self.dosya_sec)
        fl.addWidget(self.lbl_dosya); fl.addWidget(btn_dosya)
        card_sonuc.add_widget(ModernInputGroup("Varsa Rapor", file_cont))
        form_layout.addWidget(card_sonuc)

        # 4. Geçmiş Tablo
        grp_gecmis = QGroupBox("Seçili Ekipmanın Geçmişi")
        grp_gecmis.setStyleSheet("QGroupBox { color: #ccc; font-weight: bold; margin-top: 10px; }")
        gl = QVBoxLayout(grp_gecmis)
        self.tbl_gecmis = QTableWidget(); self.tbl_gecmis.setColumnCount(4)
        self.tbl_gecmis.setHorizontalHeaderLabels(["Fiz. Tarih", "Skopi Tarih", "Açıklama", "Rapor"])
        self.tbl_gecmis.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_gecmis.setSelectionBehavior(QAbstractItemView.SelectRows); self.tbl_gecmis.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_gecmis.setFixedHeight(150); self.tbl_gecmis.cellDoubleClicked.connect(self.gecmis_satir_tiklandi)
        gl.addWidget(self.tbl_gecmis); form_layout.addWidget(grp_gecmis)

        scroll.setWidget(form_inner); sol_layout.addWidget(scroll)
        self.pbar = QProgressBar(); self.pbar.setVisible(False); self.pbar.setFixedHeight(4); sol_layout.addWidget(self.pbar)
        h_btn = QHBoxLayout()
        self.btn_temizle = QPushButton("TEMİZLE"); self.btn_temizle.setFixedHeight(45); self.btn_temizle.clicked.connect(self.temizle)
        self.btn_kaydet = QPushButton("KAYDET"); self.btn_kaydet.setFixedHeight(45); self.btn_kaydet.clicked.connect(self.kaydet)
        self.btn_kaydet.setStyleSheet("background-color: #2e7d32; color: white; border-radius: 6px; font-weight: bold;")
        h_btn.addWidget(self.btn_temizle); h_btn.addWidget(self.btn_kaydet); sol_layout.addLayout(h_btn)

        # SAĞ PANEL
        sag_widget = QWidget(); sag_layout = QVBoxLayout(sag_widget); sag_layout.setContentsMargins(10, 0, 0, 0); sag_layout.setSpacing(10)
        grp_filtre = QGroupBox("RKE Envanter Listesi"); grp_filtre.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        grp_filtre.setStyleSheet("QGroupBox { color: #29b6f6; font-weight: bold; font-size: 14px; }")
        hf = QHBoxLayout(grp_filtre); hf.setContentsMargins(10, 20, 10, 10)
        self.cmb_filtre_abd = QComboBox(); self.cmb_filtre_abd.addItem("Tüm ABD"); self.cmb_filtre_abd.setMinimumWidth(150)
        self.cmb_filtre_abd.currentIndexChanged.connect(self.tabloyu_filtrele)
        self.txt_ara = QLineEdit(); self.txt_ara.setPlaceholderText("Ara..."); self.txt_ara.textChanged.connect(self.tabloyu_filtrele)
        btn_yenile = QPushButton("⟳"); btn_yenile.setFixedSize(35, 35); btn_yenile.clicked.connect(self.verileri_yukle)
        hf.addWidget(self.cmb_filtre_abd); hf.addWidget(self.txt_ara); hf.addWidget(btn_yenile); sl = sag_layout
        sl.addWidget(grp_filtre)
        
        self.tablo = QTableWidget(); self.cols_rke = ["EkipmanNo", "AnaBilimDali", "Birim", "KoruyucuCinsi", "KontrolTarihi", "Durum"]
        self.tablo.setColumnCount(len(self.cols_rke))
        self.tablo.setHorizontalHeaderLabels(["Ekipman No", "ABD", "Birim", "Cinsi", "Kontrol Tarihi", "Durum"])
        self.tablo.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectRows); self.tablo.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tablo.setEditTriggers(QAbstractItemView.NoEditTriggers); self.tablo.setAlternatingRowColors(True)
        self.tablo.cellClicked.connect(self.sag_tablo_tiklandi); sl.addWidget(self.tablo)
        
        self.btn_toplu = QPushButton("⚡ Seçili Ekipmanlara Toplu Muayene Ekle"); self.btn_toplu.setMinimumHeight(40)
        self.btn_toplu.setStyleSheet("background-color: #F57C00; color: white; border-radius: 6px; font-weight: bold;")
        self.btn_toplu.clicked.connect(self.ac_toplu_dialog); sl.addWidget(self.btn_toplu)
        
        self.lbl_sayi = QLabel("0 Kayıt"); self.lbl_sayi.setAlignment(Qt.AlignRight); self.lbl_sayi.setStyleSheet("color: #777;"); sl.addWidget(self.lbl_sayi)
        
        splitter.addWidget(sol_widget); splitter.addWidget(sag_widget); splitter.setStretchFactor(0, 35); splitter.setStretchFactor(1, 65)
        main_layout.addWidget(splitter)

    # --- UI YARDIMCILARI ---
    def add_input(self, parent, label, widget, key):
        grp = ModernInputGroup(label, widget)
        if isinstance(parent, InfoCard): parent.add_widget(grp)
        elif hasattr(parent, "addWidget"): parent.addWidget(grp)
        elif hasattr(parent, "addLayout"): parent.addWidget(grp)
        self.inputs[key] = widget

    def add_input_to_layout(self, layout, label, widget, key):
        grp = ModernInputGroup(label, widget); layout.addWidget(grp); self.inputs[key] = widget

    # --- MANTIK ---
    def dosya_sec(self):
        yol, _ = QFileDialog.getOpenFileName(self, "Rapor", "", "PDF/Resim (*.pdf *.jpg)")
        if yol: self.secilen_dosya = yol; self.lbl_dosya.setText(os.path.basename(yol))

    def verileri_yukle(self):
        self.pbar.setVisible(True); self.pbar.setRange(0, 0)
        self.loader = VeriYukleyici()
        self.loader.veri_hazir.connect(self.veriler_geldi)
        self.loader.hata_olustu.connect(lambda e: show_error("Hata", e, self))
        self.loader.finished.connect(lambda: self.pbar.setVisible(False))
        self.loader.start()

    def veriler_geldi(self, rke_data, rke_combo, rke_dict, muayene_list, headers, teknik_aciklamalar):
        self.rke_data = rke_data; self.rke_dict = rke_dict; self.tum_muayeneler = muayene_list
        self.header_map = {h.strip(): i for i, h in enumerate(headers)}
        self.teknik_aciklamalar = teknik_aciklamalar
        self.cmb_rke.blockSignals(True); self.cmb_rke.clear(); self.cmb_rke.addItems(rke_combo); self.cmb_rke.blockSignals(False)
        self.cmb_aciklama.clear(); self.cmb_aciklama.addItems(self.teknik_aciklamalar)
        
        abd = set([str(row.get("AnaBilimDali", "")).strip() for row in rke_data if str(row.get("AnaBilimDali", "")).strip()])
        self.cmb_filtre_abd.blockSignals(True); self.cmb_filtre_abd.clear(); self.cmb_filtre_abd.addItem("Tüm ABD"); self.cmb_filtre_abd.addItems(sorted(list(abd))); self.cmb_filtre_abd.blockSignals(False)
        self.tabloyu_filtrele()

    def tabloyu_filtrele(self):
        self.tablo.setRowCount(0); ara = self.txt_ara.text().lower(); secilen_abd = self.cmb_filtre_abd.currentText()
        count = 0
        for row in self.rke_data:
            abd = str(row.get("AnaBilimDali", "")).strip()
            if secilen_abd != "Tüm ABD" and abd != secilen_abd: continue
            if ara and ara not in " ".join([str(v) for v in row.values()]).lower(): continue
            r = self.tablo.rowCount(); self.tablo.insertRow(r)
            for i, key in enumerate(self.cols_rke):
                val = str(row.get(key, "")); item = QTableWidgetItem(val)
                if key == "Durum":
                    if "Uygun Değil" in val or "Hurda" in val: item.setForeground(QColor("#ef5350"))
                    elif "Uygun" in val: item.setForeground(QColor("#66bb6a"))
                self.tablo.setItem(r, i, item)
            self.tablo.item(r, 0).setData(Qt.UserRole, str(row.get("EkipmanNo", "")))
            count += 1
        self.lbl_sayi.setText(f"{count} Ekipman")

    def sag_tablo_tiklandi(self, row, col):
        item = self.tablo.item(row, 0)
        if item:
            idx = self.cmb_rke.findText(item.data(Qt.UserRole), Qt.MatchContains)
            if idx >= 0: self.cmb_rke.setCurrentIndex(idx)

    def ekipman_secildi(self):
        secilen_text = self.cmb_rke.currentText()
        if not secilen_text: return
        ekipman_no = self.rke_dict.get(secilen_text, secilen_text.split('|')[0].strip())
        self.tbl_gecmis.setRowCount(0)
        idx_ekipman = self.header_map.get("EkipmanNo", -1)
        if idx_ekipman == -1: return
        for row in self.tum_muayeneler:
            if len(row) > idx_ekipman and row[idx_ekipman] == ekipman_no:
                r = self.tbl_gecmis.rowCount(); self.tbl_gecmis.insertRow(r)
                def get_v(key): i = self.header_map.get(key, -1); return row[i] if i != -1 else ""
                self.tbl_gecmis.setItem(r, 0, QTableWidgetItem(get_v("F_MuayeneTarihi")))
                self.tbl_gecmis.setItem(r, 1, QTableWidgetItem(get_v("S_MuayeneTarihi")))
                self.tbl_gecmis.setItem(r, 2, QTableWidgetItem(get_v("Aciklamalar")))
                rapor = get_v("Rapor")
                link_item = QTableWidgetItem("Link" if "http" in rapor else "-")
                if "http" in rapor: link_item.setForeground(QColor("#42a5f5")); link_item.setToolTip(rapor)
                self.tbl_gecmis.setItem(r, 3, link_item)

    def gecmis_satir_tiklandi(self, row, col):
        if col == 3:
            item = self.tbl_gecmis.item(row, col); link = item.toolTip()
            if "http" in link: QDesktopServices.openUrl(QUrl(link))

    def temizle(self):
        self.cmb_rke.setCurrentIndex(-1)
        self.dt_fiziksel.setDate(QDate.currentDate()); self.dt_skopi.setDate(QDate.currentDate())
        self.txt_kontrol.clear(); self.txt_sorumlu.clear()
        if self.kullanici_adi: self.txt_kontrol.setText(str(self.kullanici_adi))
        self.cmb_fiziksel.setCurrentIndex(0); self.cmb_skopi.setCurrentIndex(0)
        self.cmb_aciklama.setCheckedItems([]); self.lbl_dosya.setText("Rapor Seçilmedi"); self.secilen_dosya = None
        self.tbl_gecmis.setRowCount(0)

    def kaydet(self):
        rke_text = self.cmb_rke.currentText()
        if not rke_text: show_error("Hata", "Ekipman seçin.", self); return
        ekipman_no = self.rke_dict.get(rke_text, rke_text.split('|')[0].strip())
        unique_id = f"M-{int(time.time())}"
        veri = {
            'KayitNo': unique_id, 'EkipmanNo': ekipman_no,
            'F_MuayeneTarihi': self.dt_fiziksel.date().toString("yyyy-MM-dd"),
            'FizikselDurum': self.cmb_fiziksel.currentText(),
            'S_MuayeneTarihi': self.dt_skopi.date().toString("yyyy-MM-dd"),
            'SkopiDurum': self.cmb_skopi.currentText(),
            'Aciklamalar': self.cmb_aciklama.getCheckedItems(),
            'KontrolEden': self.txt_kontrol.text(), 'BirimSorumlusu': self.txt_sorumlu.text(),
            'Not': "" 
        }
        self.pbar.setVisible(True); self.pbar.setRange(0, 0); self.btn_kaydet.setEnabled(False)
        self.saver = KayitWorker(veri, self.secilen_dosya)
        self.saver.finished.connect(self.islem_basarili)
        self.saver.error.connect(lambda e: show_error("Hata", e, self))
        self.saver.start()

    def islem_basarili(self, msg):
        self.pbar.setVisible(False); self.btn_kaydet.setEnabled(True)
        show_info("Başarılı", msg, self); self.temizle(); self.verileri_yukle()

    def ac_toplu_dialog(self):
        secili = self.tablo.selectionModel().selectedRows()
        if not secili: show_info("Uyarı", "Ekipman seçin.", self); return
        ekipmanlar = sorted(list(set([self.tablo.item(i.row(), 0).data(Qt.UserRole) for i in secili if self.tablo.item(i.row(), 0)])))
        dlg = TopluMuayeneDialog(ekipmanlar, self.teknik_aciklamalar, self.kullanici_adi, self)
        if dlg.exec() == QDialog.Accepted:
            show_info("Bilgi", "Toplu kayıt başarılı.", self); self.verileri_yukle()

    def closeEvent(self, event):
        if hasattr(self, 'loader') and self.loader.isRunning(): self.loader.quit(); self.loader.wait(500)
        if hasattr(self, 'saver') and self.saver.isRunning(): self.saver.quit(); self.saver.wait(500)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    try:
        from temalar.tema import TemaYonetimi
        TemaYonetimi.uygula_fusion_dark(app)
    except Exception as e:
        print(f"Tema uygulanamadı: {e}")
        app.setStyle("Fusion")
    win = RKEMuayenePenceresi()
    win.show()
    sys.exit(app.exec())