# -*- coding: utf-8 -*-
import sys
import os
import logging
import pandas as pd

# PySide6 Kütüphaneleri
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
    QTableView, QHeaderView, QLineEdit, QPushButton, 
    QLabel, QProgressBar, QAbstractItemView, QComboBox, QFrame,
    QGroupBox, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal, QAbstractTableModel

# --- LOGLAMA ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CihazListesi")

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# --- İMPORTLAR ---
try:
    from araclar.yetki_yonetimi import YetkiYoneticisi
    from temalar.tema import TemaYonetimi
    from google_baglanti import veritabani_getir
    from araclar.ortak_araclar import show_error, mdi_pencere_ac
except ImportError as e:
    print(f"Modül Hatası: {e}")
    # Fallback tanımlar
    def veritabani_getir(vt_tipi, sayfa_adi): return None
    def show_error(t, m, p): print(m)
    def mdi_pencere_ac(parent, form, title): form.show()
    class YetkiYoneticisi:
        @staticmethod
        def uygula(self, kod): pass
    class TemaYonetimi:
        @staticmethod
        def uygula_fusion_dark(app): pass

# =============================================================================
# 1. PANDAS VERİ MODELİ (KORUNDU)
# =============================================================================
class PandasModel(QAbstractTableModel):
    def __init__(self, data=pd.DataFrame()):
        super().__init__()
        self._data = data

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
            return self._data.columns[col]
        return None

# =============================================================================
# 2. ARKA PLAN İŞÇİSİ (KORUNDU)
# =============================================================================
class VeriYukleyici(QThread):
    veri_geldi = Signal(object, dict) # DataFrame, Sabitler Sözlüğü
    hata_olustu = Signal(str)
    
    def run(self):
        df = pd.DataFrame()
        sabitler_dict = {"AnaBilimDali": [], "Kaynak": []}
        
        # --- A) CİHAZLARI ÇEK ---
        try:
            ws_cihaz = veritabani_getir('cihaz', 'Cihazlar')
            
            if ws_cihaz:
                data = ws_cihaz.get_all_values()
                if data and len(data) > 1:
                    headers = [str(h).strip() for h in data[0]]
                    rows = data[1:]
                    df = pd.DataFrame(rows, columns=headers)
                    df = df.fillna("") 
                    
                    # İstenen Sütunları Filtrele
                    istenen_sutunlar = [
                        "cihaz_id", "Marka", "Model", "Kaynak", 
                        "SeriNo", "NDKLisansNo", "LisansDurum", 
                        "AnaBilimDali", "BulunduguBina", "CihazID"
                    ]
                    # Sadece mevcut olanları al
                    mevcut = [c for c in istenen_sutunlar if c in df.columns]
                    if mevcut:
                        df = df[mevcut]
            else:
                self.hata_olustu.emit("Veritabanı bağlantısı yok.")
                return

        except Exception as e:
            self.hata_olustu.emit(f"Cihaz verisi alınamadı: {e}")
            return

        # --- B) SABİTLERİ ÇEK ---
        try:
            ws_sabit = veritabani_getir('sabit', 'Sabitler')
            if ws_sabit:
                sabit_data = ws_sabit.get_all_records()
                if sabit_data:
                    df_sabit = pd.DataFrame(sabit_data)
                    cols = [c.strip() for c in df_sabit.columns]
                    df_sabit.columns = cols
                    
                    if "Kod" in cols and "MenuEleman" in cols:
                        sabitler_dict["AnaBilimDali"] = sorted(df_sabit[df_sabit["Kod"] == "AnaBilimDali"]["MenuEleman"].astype(str).unique().tolist())
                        sabitler_dict["Kaynak"] = sorted(df_sabit[df_sabit["Kod"] == "Kaynak"]["MenuEleman"].astype(str).unique().tolist())
        except Exception:
            pass 

        self.veri_geldi.emit(df, sabitler_dict)

# =============================================================================
# 3. GÖRÜNÜM (UI)
# =============================================================================
class CihazListesiPenceresi(QWidget):
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.setWindowTitle("Cihaz Envanter Listesi")
        self.resize(1200, 700)
        
        self.full_df = pd.DataFrame()
        self.filtered_df = pd.DataFrame()
        
        self.setup_ui()
        
        # Yetki Uygula
        YetkiYoneticisi.uygula(self, "cihaz_listesi")
        
        self.verileri_yenile()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        
        # --- ÜST BAR (GROUPBOX OLARAK DÜZENLENDİ) ---
        grp_filtre = QGroupBox("Filtreleme ve İşlemler")
        # Dikeyde sadece gerektiği kadar yer kaplasın
        grp_filtre.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        
        top_layout = QHBoxLayout(grp_filtre)
        
        self.combo_abd = QComboBox()
        self.combo_abd.addItem("Tümü")
        self.combo_abd.setMinimumWidth(150)
        self.combo_abd.currentTextChanged.connect(self.filtre_uygula)
        
        self.combo_kaynak = QComboBox()
        self.combo_kaynak.addItem("Tümü")
        self.combo_kaynak.setMinimumWidth(150)
        self.combo_kaynak.currentTextChanged.connect(self.filtre_uygula)

        self.txt_ara = QLineEdit()
        self.txt_ara.setPlaceholderText("Ara...")
        self.txt_ara.textChanged.connect(self.filtre_uygula)
        
        # Yenile Butonu
        self.btn_yenile = QPushButton("⟳")
        self.btn_yenile.setObjectName("btn_yenile")
        self.btn_yenile.setFixedHeight(30)
        self.btn_yenile.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; padding: 0 10px;")
        self.btn_yenile.clicked.connect(self.verileri_yenile)
        
        # Yeni Ekle Butonu
        self.btn_yeni_ekle = QPushButton(" + Yeni Cihaz")
        self.btn_yeni_ekle.setObjectName("btn_yeni")
        self.btn_yeni_ekle.setFixedHeight(30)
        self.btn_yeni_ekle.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; padding: 0 10px;")
        self.btn_yeni_ekle.clicked.connect(self.yeni_cihaz_ekle)

        top_layout.addWidget(QLabel("Birim:"))
        top_layout.addWidget(self.combo_abd)
        top_layout.addWidget(QLabel("Kaynak:"))
        top_layout.addWidget(self.combo_kaynak)
        top_layout.addStretch()
        top_layout.addWidget(self.txt_ara)
        top_layout.addWidget(self.btn_yeni_ekle)
        top_layout.addWidget(self.btn_yenile)
        
        main_layout.addWidget(grp_filtre)
        
        # --- PROGRESS ---
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setStyleSheet("height: 4px; background: #333; border: none;") 
        main_layout.addWidget(self.progress)

        # --- TABLO (QTableView KORUNDU) ---
        self.tablo = QTableView()
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tablo.setSortingEnabled(True)
        self.tablo.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tablo.doubleClicked.connect(self.satir_tiklandi)
        main_layout.addWidget(self.tablo)
        
        self.lbl_info = QLabel("Hazır")
        main_layout.addWidget(self.lbl_info)

    def verileri_yenile(self):
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.lbl_info.setText("Yükleniyor...")
        self.tablo.setModel(None)
        
        self.worker = VeriYukleyici()
        self.worker.veri_geldi.connect(self.veri_yuklendi)
        self.worker.hata_olustu.connect(self.hata_yakala)
        self.worker.start()

    def veri_yuklendi(self, df, sabitler):
        self.progress.setVisible(False)
        self.full_df = df
        
        self.combo_abd.blockSignals(True)
        self.combo_kaynak.blockSignals(True)
        
        mevcut_abd = self.combo_abd.currentText()
        mevcut_kaynak = self.combo_kaynak.currentText()
        
        self.combo_abd.clear(); self.combo_kaynak.clear()
        self.combo_abd.addItem("Tümü"); self.combo_kaynak.addItem("Tümü")
        
        if sabitler["AnaBilimDali"]: self.combo_abd.addItems(sabitler["AnaBilimDali"])
        if sabitler["Kaynak"]: self.combo_kaynak.addItems(sabitler["Kaynak"])
            
        self.combo_abd.setCurrentText(mevcut_abd)
        self.combo_kaynak.setCurrentText(mevcut_kaynak)
        
        self.combo_abd.blockSignals(False)
        self.combo_kaynak.blockSignals(False)
        
        if df.empty:
            self.lbl_info.setText("Veri bulunamadı veya boş.")
            return
            
        self.filtre_uygula()

    def filtre_uygula(self):
        if self.full_df.empty: return
        
        df = self.full_df.copy()
        text = self.txt_ara.text().lower().strip()
        abd = self.combo_abd.currentText()
        kaynak = self.combo_kaynak.currentText()
        
        if abd != "Tümü" and "AnaBilimDali" in df.columns:
            df = df[df["AnaBilimDali"].astype(str) == abd]
            
        if kaynak != "Tümü" and "Kaynak" in df.columns:
            df = df[df["Kaynak"].astype(str) == kaynak]
            
        if text:
            mask = df.astype(str).apply(lambda x: x.str.lower().str.contains(text, na=False)).any(axis=1)
            df = df[mask]
            
        self.filtered_df = df
        # PandasModel Kullanımı KORUNDU
        model = PandasModel(df)
        self.tablo.setModel(model)
        self.lbl_info.setText(f"Gösterilen: {len(df)}")

    def hata_yakala(self, mesaj):
        self.progress.setVisible(False)
        show_error("Hata", mesaj, self)
        self.lbl_info.setText("Hata oluştu.")

    def satir_tiklandi(self, index):
        try:
            row = index.row()
            col_name = "cihaz_id" if "cihaz_id" in self.filtered_df.columns else "CihazID"
            
            if col_name in self.filtered_df.columns:
                # ESKİ KOD (Hata veren):
                # val = str(self.filtered_df.iloc[row][self.filtered_df.columns.get_loc(col_name)])
                
                # YENİ KOD (Düzeltilmiş):
                # DataFrame üzerinde doğrudan iloc[row, col] kullanımı
                col_index = self.filtered_df.columns.get_loc(col_name)
                val = str(self.filtered_df.iloc[row, col_index])
            else:
                # Sütun yoksa ilk sütunu al (Burada da aynı mantıkla düzeltme yapılabilir)
                val = str(self.filtered_df.iloc[row, 0])
                
            self.detay_ac(val)
        except Exception as e:
            logger.error(f"Tıklama Hatası: {e}")

    def detay_ac(self, cihaz_id):
        try:
            from formlar.cihaz_detay import CihazDetayPenceresi
            detay = CihazDetayPenceresi(cihaz_id, self.yetki, self.kullanici_adi)
            mdi_pencere_ac(self, detay, f"Cihaz Detay: {cihaz_id}")
        except ImportError:
            show_error("Modül Eksik", "Cihaz detay modülü henüz yüklenmemiş.", self)
        except Exception as e:
            show_error("Hata", str(e), self)

    def yeni_cihaz_ekle(self):
        try:
            from formlar.cihaz_ekle import CihazEklePenceresi
            ekle = CihazEklePenceresi(self.yetki, self.kullanici_adi)
            mdi_pencere_ac(self, ekle, "Yeni Cihaz Ekle")
        except ImportError:
            show_error("Modül Eksik", "Cihaz ekleme modülü bulunamadı.", self)

    def closeEvent(self, event):
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(500)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Tema uygulaması eklendi
    try:
        TemaYonetimi.uygula_fusion_dark(app)
    except Exception as e:
        print(f"Tema uygulanamadı: {e}")
        app.setStyle("Fusion")
        
    win = CihazListesiPenceresi()
    win.show()
    sys.exit(app.exec())