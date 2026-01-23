# -*- coding: utf-8 -*-
import sys
import os
import logging
import pandas as pd

from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                               QTableView, QHeaderView, QLineEdit, QPushButton, 
                               QLabel, QMessageBox, QMdiSubWindow, QProgressBar, 
                               QAbstractItemView, QMdiArea, QComboBox, QFrame)
from PySide6.QtCore import Qt, QThread, Signal, QAbstractTableModel
from PySide6.QtGui import QFont, QColor

# --- LOGLAMA ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ArizaListesi")

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from araclar.yetki_yonetimi import YetkiYoneticisi

# --- İMPORTLAR ---
try:
    from google_baglanti import veritabani_getir
    from araclar.ortak_araclar import show_error, mdi_pencere_ac
except ImportError as e:
    print(f"Modül Hatası: {e}")
    def veritabani_getir(vt_tipi, sayfa_adi): return None
    def show_error(t, m, p): print(m)
    def mdi_pencere_ac(parent, form, title): form.show()

# =============================================================================
# 1. PANDAS VERİ MODELİ (GELİŞMİŞ BAŞLIK YÖNETİMİ)
# =============================================================================
class PandasModel(QAbstractTableModel):
    def __init__(self, data=pd.DataFrame()):
        super().__init__()
        self._data = data
        
        # Başlık Eşleştirme
        self.header_map = {
            "ArizaID":      "Arıza No",
            "ariza_id":     "Arıza No", 
            "CihazID":      "Cihaz Kodu",
            "cihaz_id":     "Cihaz Kodu",
            "baslangic_tarihi": "Bildirim Tarihi",
            "Tarih":        "Bildirim Tarihi",
            "Saat":         "Saat",
            "Bildiren":     "Bildiren Personel",
            "ArizaTipi":    "Arıza Türü",
            "Oncelik":      "Aciliyet",
            "Konu":         "Arıza Konusu",
            "Durum":        "Son Durum",
            "ariza_acikla": "Açıklama",
            "Rapor":        "Rapor Durumu"
        }

    def rowCount(self, parent=None):
        return self._data.shape[0]

    def columnCount(self, parent=None):
        return self._data.shape[1]

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid():
            if role == Qt.DisplayRole:
                val = self._data.iloc[index.row(), index.column()]
                return str(val) if pd.notna(val) else ""
            elif role == Qt.TextAlignmentRole:
                return Qt.AlignCenter
        return None

    def headerData(self, col, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            original_header = self._data.columns[col]
            return self.header_map.get(original_header, original_header)
        return None

# =============================================================================
# 2. ARKA PLAN İŞÇİSİ
# =============================================================================
class VeriYukleyici(QThread):
    veri_geldi = Signal(object)
    hata_olustu = Signal(str)
    
    def run(self):
        try:
            ws_ariza = veritabani_getir('cihaz', 'cihaz_ariza')
            if not ws_ariza:
                self.hata_olustu.emit("Veritabanı bağlantısı başarısız.")
                return
            
            data = ws_ariza.get_all_values()
            
            if not data or len(data) < 2:
                self.veri_geldi.emit(pd.DataFrame())
                return

            headers = [str(h).strip() for h in data[0]]
            rows = data[1:]
            df = pd.DataFrame(rows, columns=headers)
            df = df.fillna("")
            
            # Sütun filtreleme ve sıralama
            istenen_sutunlar = [
                "ArizaID", "CihazID", "Tarih", "Saat", "Bildiren", 
                "ArizaTipi", "Oncelik", "Konu", "Durum"
            ]
            
            mevcut_sutunlar = [c for c in istenen_sutunlar if c in df.columns]
            if mevcut_sutunlar:
                df = df[mevcut_sutunlar]
                # Tarih sıralaması (Varsa)
                tarih_col = next((c for c in df.columns if c.lower() == "tarih"), None)
                if tarih_col:
                    try:
                        df['temp_date'] = pd.to_datetime(df[tarih_col], dayfirst=True, errors='coerce')
                        df = df.sort_values(by='temp_date', ascending=False)
                        df = df.drop(columns=['temp_date'])
                    except: pass

            self.veri_geldi.emit(df)
            
        except Exception as e:
            logger.error(f"Veri çekme hatası: {e}")
            self.hata_olustu.emit(str(e))

# =============================================================================
# 3. GÖRÜNÜM (UI)
# =============================================================================
class ArizaListesiPenceresi(QWidget):
    # 🟢 DEĞİŞİKLİK 1: Parametreler
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.setWindowTitle("Arıza Takip Listesi")
        self.resize(1200, 750)
        self.setStyleSheet("background-color: #121212; color: #e0e0e0;")
        
        self.full_df = pd.DataFrame()
        self.filtered_df = pd.DataFrame()
        
        self.setup_ui()
        
        # 🟢 DEĞİŞİKLİK 2: Yetki
        YetkiYoneticisi.uygula(self, "ariza_listesi")
        
        self.verileri_yenile()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # --- HEADER ---
        top_frame = QFrame()
        top_frame.setFixedHeight(70)
        top_frame.setStyleSheet("QFrame { background-color: #1e1e1e; border-radius: 8px; border: 1px solid #333; }")
        top_layout = QHBoxLayout(top_frame)
        top_layout.setContentsMargins(15, 10, 15, 10)
        top_layout.setSpacing(15)
        
        lbl_baslik = QLabel("Arıza Takip")
        lbl_baslik.setStyleSheet("font-size: 18px; font-weight: bold; color: #ff5252; border: none;")
        
        self.combo_durum = QComboBox()
        self.combo_durum.addItems(["Tüm Durumlar", "Açık", "İşlemde", "Kapalı", "Beklemede"])
        self.combo_durum.setMinimumWidth(130)
        self.combo_durum.setStyleSheet(self.combo_style())
        self.combo_durum.currentTextChanged.connect(self.filtre_uygula)
        
        self.combo_oncelik = QComboBox()
        self.combo_oncelik.addItems(["Tüm Öncelikler", "Acil (Kritik)", "Yüksek", "Normal", "Düşük"])
        self.combo_oncelik.setMinimumWidth(130)
        self.combo_oncelik.setStyleSheet(self.combo_style())
        self.combo_oncelik.currentTextChanged.connect(self.filtre_uygula)

        self.txt_ara = QLineEdit()
        self.txt_ara.setPlaceholderText("ID, Cihaz, Konu veya Personel ara...")
        self.txt_ara.setStyleSheet("QLineEdit { padding: 8px; border-radius: 4px; border: 1px solid #444; background: #2b2b2b; color: white; min-width: 200px; } QLineEdit:focus { border: 1px solid #ff5252; }")
        self.txt_ara.textChanged.connect(self.filtre_uygula)
        
        # 🟢 DEĞİŞİKLİK 3: Yeni Ekle Butonu
        self.btn_yeni = QPushButton(" + Yeni Kayıt")
        self.btn_yeni.setObjectName("btn_yeni") # Yetki için
        self.btn_yeni.setFixedSize(120, 35)
        self.btn_yeni.setCursor(Qt.PointingHandCursor)
        self.btn_yeni.clicked.connect(self.yeni_kayit_ac)
        self.btn_yeni.setStyleSheet("QPushButton { background-color: #d32f2f; color: white; border-radius: 4px; font-weight: bold; border: none; } QPushButton:hover { background-color: #b71c1c; }")

        self.btn_yenile = QPushButton("⟳")
        self.btn_yenile.setObjectName("btn_yenile") # Yetki için
        self.btn_yenile.setFixedSize(35, 35)
        self.btn_yenile.setCursor(Qt.PointingHandCursor)
        self.btn_yenile.clicked.connect(self.verileri_yenile)
        self.btn_yenile.setStyleSheet("QPushButton { background-color: #333; color: white; border-radius: 4px; font-size: 16px; border: 1px solid #444; } QPushButton:hover { background-color: #444; }")
        
        top_layout.addWidget(lbl_baslik)
        top_layout.addWidget(self.combo_durum)
        top_layout.addWidget(self.combo_oncelik)
        top_layout.addStretch()
        top_layout.addWidget(self.txt_ara)
        top_layout.addWidget(self.btn_yeni) # Yeni Ekle butonu
        top_layout.addWidget(self.btn_yenile)
        
        main_layout.addWidget(top_frame)
        
        # Progress
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(4)
        self.progress.setStyleSheet("background: transparent; border: none; QProgressBar::chunk { background-color: #ff5252; }")
        self.progress.setVisible(False)
        main_layout.addWidget(self.progress)

        # Tablo
        self.tablo = QTableView()
        self.tablo.setAlternatingRowColors(True)
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tablo.setSortingEnabled(True)
        self.tablo.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tablo.verticalHeader().setVisible(False)
        self.tablo.doubleClicked.connect(self.satir_tiklandi)
        self.tablo.setStyleSheet("QTableView { background-color: #1e1e1e; gridline-color: #333; border: none; selection-background-color: #b71c1c; selection-color: white; } QHeaderView::section { background-color: #2b2b2b; color: #ccc; padding: 8px; border: none; border-bottom: 2px solid #ff5252; font-weight: bold; } QTableView::item { padding: 5px; }")
        main_layout.addWidget(self.tablo)
        
        self.lbl_info = QLabel("Hazır")
        self.lbl_info.setStyleSheet("color: #777; font-size: 12px; margin-left: 5px;")
        main_layout.addWidget(self.lbl_info)

    def combo_style(self):
        return "QComboBox { background-color: #2b2b2b; border: 1px solid #444; border-radius: 4px; padding: 5px; color: #e0e0e0; } QComboBox::drop-down { border: none; }"

    def verileri_yenile(self):
        self.progress.setVisible(True)
        self.lbl_info.setText("Veriler güncelleniyor...")
        self.btn_kilit(True)
        self.worker = VeriYukleyici()
        self.worker.veri_geldi.connect(self.veri_yuklendi)
        self.worker.hata_olustu.connect(self.hata_yakala)
        self.worker.start()

    def veri_yuklendi(self, df):
        self.progress.setVisible(False)
        self.btn_kilit(False)
        self.full_df = df
        if df.empty:
            self.lbl_info.setText("Kayıt bulunamadı.")
            self.tablo.setModel(None)
            return
        self.filtre_uygula()

    def filtre_uygula(self):
        if self.full_df.empty: return
        df = self.full_df.copy()
        
        text = self.txt_ara.text().lower().strip()
        if text:
            mask = df.astype(str).apply(lambda x: x.str.lower().str.contains(text, na=False)).any(axis=1)
            df = df[mask]
            
        durum = self.combo_durum.currentText()
        if durum != "Tüm Durumlar" and "Durum" in df.columns:
            df = df[df["Durum"].astype(str).str.contains(durum, case=False, na=False)]
            
        oncelik = self.combo_oncelik.currentText()
        if oncelik != "Tüm Öncelikler" and "Oncelik" in df.columns:
            df = df[df["Oncelik"].astype(str).str.contains(oncelik, case=False, na=False)]

        self.filtered_df = df
        self.tablo.setModel(PandasModel(df))
        self.lbl_info.setText(f"Toplam {len(df)} kayıt listelendi.")

    def hata_yakala(self, mesaj):
        self.progress.setVisible(False)
        self.btn_kilit(False)
        show_error("Hata", mesaj, self)
        self.lbl_info.setText("Hata oluştu.")

    def btn_kilit(self, kilitli):
        self.txt_ara.setEnabled(not kilitli)
        self.combo_durum.setEnabled(not kilitli)
        self.combo_oncelik.setEnabled(not kilitli)
        self.btn_yenile.setEnabled(not kilitli)

    def satir_tiklandi(self, index):
        try:
            row = index.row()
            # ID sütununu bul
            if "ArizaID" in self.filtered_df.columns:
                ariza_id = str(self.filtered_df.iloc[row]["ArizaID"])
            else:
                # Sütun adı farklıysa veya index 0 varsayımı
                ariza_id = str(self.filtered_df.iloc[row, 0])
                
            self.detay_ac(ariza_id)
        except Exception as e:
            logger.error(f"Satır hatası: {e}")

    def detay_ac(self, ariza_id):
        try:
            from formlar.ariza_islem import ArizaIslemPenceresi
            # Yetki ve kullanıcı adını iletiyoruz
            # ana_pencere=self diyerek veri güncellendiğinde listeyi yenilemesini sağlıyoruz
            detay_form = ArizaIslemPenceresi(ariza_id, yetki=self.yetki, kullanici_adi=self.kullanici_adi, ana_pencere=self)
            mdi_pencere_ac(self, detay_form, f"Arıza Detay: {ariza_id}")
        except ImportError:
            show_error("Modül Eksik", "Ariza işlem modülü (ariza_islem.py) bulunamadı.", self)
        except Exception as e:
            show_error("Hata", str(e), self)

    def yeni_kayit_ac(self):
        try:
            from formlar.ariza_kayit import ArizaKayitPenceresi
            # Yetki ve kullanıcı adını iletiyoruz
            yeni_form = ArizaKayitPenceresi(yetki=self.yetki, kullanici_adi=self.kullanici_adi)
            mdi_pencere_ac(self, yeni_form, "Yeni Arıza Kaydı")
        except ImportError:
            show_error("Modül Eksik", "Ariza kayıt modülü (ariza_kayit.py) bulunamadı.", self)

    # 🟢 DEĞİŞİKLİK 4: Thread Güvenliği
    def closeEvent(self, event):
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(500)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    from temalar.tema import TemaYonetimi
    TemaYonetimi.uygula_fusion_dark(app)
    win = ArizaListesiPenceresi()
    win.show()
    sys.exit(app.exec())