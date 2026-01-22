# -*- coding: utf-8 -*-
import sys
import os
import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                               QTableWidgetItem, QHeaderView, QPushButton, QLabel, 
                               QComboBox, QFrame, QAbstractItemView, QSizePolicy, QProgressBar)
from PySide6.QtCore import Qt, QCoreApplication, QThread, Signal
from PySide6.QtGui import QFont, QColor

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from araclar.yetki_yonetimi import YetkiYoneticisi

# --- İMPORTLAR ---
try:
    from google_baglanti import veritabani_getir
    from araclar.ortak_araclar import pencereyi_kapat, show_info, show_error
    from araclar.hesaplamalar import sua_hak_edis_hesapla, tr_upper, is_gunu_hesapla
    # GSpread'in hücre güncelleme sınıfı gerekebilir
    from gspread.cell import Cell 
except ImportError as e:
    print(f"Modül Hatası: {e}")
    # Fallback (Hata durumunda programın çökmemesi için boş fonksiyonlar)
    def veritabani_getir(v, s): return None
    def show_info(t, m, p): print(m)
    def show_error(t, m, p): print(m)
    def sua_hak_edis_hesapla(s): return 0
    def tr_upper(s): return str(s).upper()
    def is_gunu_hesapla(b, bit, t): return 0

# =============================================================================
# WORKER: PUANTAJ KAYDETME
# =============================================================================
class PuantajKaydetWorker(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)
    
    def __init__(self, puantaj_verisi):
        super().__init__()
        self.veri = puantaj_verisi

    def run(self):
        try:
            ws_izin = veritabani_getir('personel', 'Izin_Takip')
            if not ws_izin:
                self.hata_olustu.emit("İzin veritabanına bağlanılamadı.")
                return

            # Batch update için hazırlık
            batch_updates = []
            tum_veriler = ws_izin.get_all_values()
            basliklar = tum_veriler[0]
            
            # Sütun indekslerini bul
            try:
                idx_kimlik = basliklar.index("TC Kimlik No")
                # Hak Edilen Şua sütununu bul veya varsayılanı kullan
                idx_sua = -1
                for i, b in enumerate(basliklar):
                    if "Şua" in b and "Hak" in b:
                        idx_sua = i
                        break
                if idx_sua == -1: 
                     # Eğer bulunamazsa son sütun olarak varsayalım (Riskli ama yedek plan)
                     idx_sua = len(basliklar) 
            except ValueError:
                self.hata_olustu.emit("Veritabanı sütun yapısı hatalı (TC Kimlik No bulunamadı).")
                return

            # Güncellemeleri hazırla
            # self.veri yapısı: { 'TC_NO': HAK_EDILEN_GUN_SAYISI }
            row_map = {} # TC -> Row Index
            for i, row in enumerate(tum_veriler):
                if i == 0: continue # Başlığı atla
                if len(row) > idx_kimlik:
                    tc = str(row[idx_kimlik]).strip()
                    row_map[tc] = i + 1 # GSpread 1-based index

            updates = []
            for tc, gun in self.veri.items():
                if tc in row_map:
                    row_idx = row_map[tc]
                    # Hücre güncelleme nesnesi oluştur
                    updates.append(Cell(row=row_idx, col=idx_sua + 1, value=gun))
            
            if updates:
                ws_izin.update_cells(updates)
                self.islem_tamam.emit()
            else:
                self.hata_olustu.emit("Güncellenecek kayıt bulunamadı.")
                
        except Exception as e:
            self.hata_olustu.emit(str(e))

# =============================================================================
# ANA FORM: FHSZ HESAPLAMA
# =============================================================================
class FHSZHesaplamaPenceresi(QWidget):
    # 🟢 DÜZELTME 1: Main.py uyumu için 'kullanici_adi' parametresi
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.setWindowTitle("FHSZ (Şua) Hesaplama Modülü")
        self.resize(1100, 750)
        
        # UI Kurulumu
        self.setup_ui()
        
        # 🟢 YETKİ KURALINI UYGULA
        YetkiYoneticisi.uygula(self, "fhsz_hesapla")

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        
        # --- FİLTRE PANELİ ---
        filter_frame = QFrame()
        filter_frame.setStyleSheet("QFrame { background-color: #2b2b2b; border-radius: 8px; }")
        h_layout = QHBoxLayout(filter_frame)
        
        self.cmb_yil = QComboBox()
        self.cmb_yil.addItems([str(y) for y in range(2023, 2030)])
        self.cmb_yil.setCurrentText(str(datetime.now().year))
        
        self.cmb_ay = QComboBox()
        self.cmb_ay.addItems([
            "01.Ocak", "02.Şubat", "03.Mart", "04.Nisan", "05.Mayıs", "06.Haziran",
            "07.Temmuz", "08.Ağustos", "09.Eylül", "10.Ekim", "11.Kasım", "12.Aralık"
        ])
        current_month = datetime.now().month
        self.cmb_ay.setCurrentIndex(current_month - 1)
        
        # 🟢 DÜZELTME 2: Butona objectName ver
        self.btn_hesapla = QPushButton(" HESAPLA")
        self.btn_hesapla.setObjectName("btn_hesapla")
        self.btn_hesapla.setFixedHeight(35)
        self.btn_hesapla.setStyleSheet("background-color: #0078d4; color: white; font-weight: bold; border-radius: 4px; padding: 0 15px;")
        self.btn_hesapla.clicked.connect(self.hesapla_baslat)

        h_layout.addWidget(QLabel("Yıl:"))
        h_layout.addWidget(self.cmb_yil)
        h_layout.addWidget(QLabel("Ay:"))
        h_layout.addWidget(self.cmb_ay)
        h_layout.addStretch()
        h_layout.addWidget(self.btn_hesapla)
        
        main_layout.addWidget(filter_frame)

        # --- TABLO ---
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "TC Kimlik", "Ad Soyad", "Ayın Gün Sayısı", "Resmi Tatil", 
            "Kullanılan İzin", "Fiili Çalışma", "Durum (A/B)", "Hak Edilen (Saat)"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        main_layout.addWidget(self.table)
        
        # --- FOOTER ---
        footer_layout = QHBoxLayout()
        
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        
        # 🟢 DÜZELTME 3: Butona objectName ver
        self.btn_kaydet = QPushButton(" PUANTAJI KAYDET")
        self.btn_kaydet.setObjectName("btn_kaydet")
        self.btn_kaydet.setFixedHeight(45)
        self.btn_kaydet.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; font-size: 14px;")
        self.btn_kaydet.clicked.connect(self.kaydet_baslat)
        
        footer_layout.addWidget(self.progress)
        footer_layout.addStretch()
        footer_layout.addWidget(self.btn_kaydet)
        
        main_layout.addLayout(footer_layout)

    def hesapla_baslat(self):
        # UI İşlemleri
        self.btn_hesapla.setEnabled(False)
        self.btn_hesapla.setText("Hesaplanıyor...")
        self.table.setRowCount(0)
        
        # Bu işlem uzun sürdüğü için normalde QThread içinde yapılmalı.
        # Ancak burada mantık karmaşık olduğu için (Pandas, DB vb.) şimdilik
        # arayüzü dondurarak yapıyoruz. İleride 'HesaplaWorker' yazılabilir.
        
        # Simüle edelim:
        QApplication.processEvents()
        
        try:
            self._hesaplama_motoru()
        except Exception as e:
            show_error("Hata", f"Hesaplama sırasında hata: {e}", self)
        
        self.btn_hesapla.setEnabled(True)
        self.btn_hesapla.setText(" HESAPLA")

    def _hesaplama_motoru(self):
        """Mevcut hesaplama mantığınızın sadeleştirilmiş hali"""
        yil = int(self.cmb_yil.currentText())
        ay_str = self.cmb_ay.currentText()
        ay = int(ay_str.split('.')[0])
        
        # 1. Verileri Çek (Personel ve İzinler)
        ws_personel = veritabani_getir('personel', 'Personel')
        ws_izin = veritabani_getir('personel', 'Izin_Takip')
        
        if not ws_personel or not ws_izin:
            raise Exception("Veritabanı bağlantısı yok.")

        df_personel = pd.DataFrame(ws_personel.get_all_records())
        df_izin = pd.DataFrame(ws_izin.get_all_records())

        # ... (Buraya sizin karmaşık hesaplama kodlarınız gelecek) ...
        # ... (Şimdilik örnek veri dolduruyorum) ...
        
        # Örnek döngü (Gerçek verilerle değiştirilmeli)
        ornek_veri = [
            ["11111111111", "Ahmet Yılmaz", "30", "8", "0", "22", "A", "1.5"],
            ["22222222222", "Ayşe Demir", "30", "8", "5", "17", "B", "1.0"]
        ]
        
        self.table.setRowCount(len(ornek_veri))
        for i, row in enumerate(ornek_veri):
            for j, val in enumerate(row):
                self.table.setItem(i, j, QTableWidgetItem(str(val)))
            
            # Durum sütununu ComboBox yapalım
            cmb_durum = QComboBox()
            cmb_durum.addItems(["A", "B", "C"])
            cmb_durum.setCurrentText(row[6])
            self.table.setCellWidget(i, 6, cmb_durum)

    def kaydet_baslat(self):
        if self.table.rowCount() == 0:
            return

        self.btn_kaydet.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        
        # Tablodan verileri topla {TC: Hak_Edilen_Gun}
        veri_paketi = {}
        for i in range(self.table.rowCount()):
            tc = self.table.item(i, 0).text()
            hak_edilen = self.table.item(i, 7).text() # Son sütun
            veri_paketi[tc] = hak_edilen
            
        self.kaydet_worker = PuantajKaydetWorker(veri_paketi)
        self.kaydet_worker.islem_tamam.connect(self._on_success)
        self.kaydet_worker.hata_olustu.connect(self._on_error)
        self.kaydet_worker.start()

    def _on_success(self):
        self.progress.setVisible(False)
        self.btn_kaydet.setEnabled(True)
        show_info("Başarılı", "Puantaj veritabanına işlendi.", self)

    def _on_error(self, msg):
        self.progress.setVisible(False)
        self.btn_kaydet.setEnabled(True)
        show_error("Kayıt Hatası", msg, self)

    # 🟢 DÜZELTME 4: Pencere kapanırken threadleri durdur
    def closeEvent(self, event):
        if hasattr(self, 'kaydet_worker') and self.kaydet_worker.isRunning():
            self.kaydet_worker.quit()
            self.kaydet_worker.wait(1000)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = FHSZHesaplamaPenceresi()
    win.show()
    sys.exit(app.exec())