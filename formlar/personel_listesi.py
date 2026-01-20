# -*- coding: utf-8 -*-
import sys
import os
import logging

# PySide6 Kütüphaneleri
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QProgressBar, QFrame, QAbstractItemView, QMessageBox, QComboBox
)

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# --- MODÜLLER ---
try:
    from google_baglanti import veritabani_getir
    # GÜNCELLEME: mdi_pencere_ac eklendi
    from araclar.ortak_araclar import (
        pencereyi_kapat, show_info, show_error, create_group_box, 
        mdi_pencere_ac 
    )
    from formlar.personel_detay import PersonelDetayPenceresi
    from formlar.personel_ekle import PersonelEklePenceresi
except ImportError as e:
    print(f"Modül Hatası: {e}")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PersonelListesi")

# ... (VeriYukleWorker ve SabitlerWorker sınıfları AYNEN KALIYOR) ...
class VeriYukleWorker(QThread):
    veri_indi = Signal(list)
    hata_olustu = Signal(str)
    def run(self):
        try:
            ws = veritabani_getir('personel', 'Personel')
            if ws: self.veri_indi.emit(ws.get_all_values())
            else: self.hata_olustu.emit("Veritabanına bağlanılamadı.")
        except Exception as e: self.hata_olustu.emit(str(e))

class SabitlerWorker(QThread):
    veri_indi = Signal(list)
    def run(self):
        try:
            ws = veritabani_getir('sabit', 'Sabitler')
            hizmet_siniflari = set()
            if ws:
                for satir in ws.get_all_records():
                    if str(satir.get('Kod', '')).strip() == "Hizmet_Sinifi":
                        hizmet_siniflari.add(str(satir.get('MenuEleman', '')).strip())
            sirali_liste = sorted(list(hizmet_siniflari))
            sirali_liste.insert(0, "Tümü")
            self.veri_indi.emit(sirali_liste)
        except Exception: self.veri_indi.emit(["Tümü"])

# =============================================================================
# PERSONEL LİSTESİ FORMU
# =============================================================================
class PersonelListesiPenceresi(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Personel Listesi")
        self.resize(1200, 700)
        self.ham_veri = []
        self.basliklar = []
        self._setup_ui()
        self._sabitleri_yukle()
        self._verileri_yenile()

    def _setup_ui(self):
        # ... (UI kurulum kodları AYNEN KALIYOR) ...
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # ÜST BAR
        top_bar = QHBoxLayout()
        self.txt_ara = QLineEdit()
        self.txt_ara.setPlaceholderText("🔍 İsim, TC veya Birim ara...")
        self.txt_ara.setFixedHeight(40)
        self.txt_ara.setStyleSheet("QLineEdit { border: 1px solid #555; border-radius: 20px; padding-left: 15px; background-color: #2b2b2b; color: white; } QLineEdit:focus { border: 1px solid #0067c0; }")
        self.txt_ara.textChanged.connect(self._filtrele_tetikle)

        self.cmb_hizmet_filtre = QComboBox()
        self.cmb_hizmet_filtre.setPlaceholderText("Hizmet Sınıfı")
        self.cmb_hizmet_filtre.setFixedHeight(40)
        self.cmb_hizmet_filtre.setMinimumWidth(200)
        self.cmb_hizmet_filtre.currentIndexChanged.connect(self._filtrele_tetikle)

        btn_yeni = QPushButton(" + Yeni Personel")
        btn_yeni.setFixedHeight(40)
        btn_yeni.setStyleSheet("QPushButton { background-color: #28a745; color: white; border-radius: 5px; font-weight: bold; }")
        btn_yeni.clicked.connect(self._yeni_personel_ac)

        btn_yenile = QPushButton(" Yenile")
        btn_yenile.setFixedHeight(40)
        btn_yenile.setStyleSheet("QPushButton { background-color: #0067c0; color: white; border-radius: 5px; font-weight: bold; }")
        btn_yenile.clicked.connect(self._verileri_yenile)

        top_bar.addWidget(self.txt_ara, 1)
        top_bar.addWidget(self.cmb_hizmet_filtre)
        top_bar.addWidget(btn_yeni)
        top_bar.addWidget(btn_yenile)
        main_layout.addLayout(top_bar)

        # TABLO
        self.table = QTableWidget()
        self.table.setColumnCount(6) 
        self.table.setHorizontalHeaderLabels(["TC Kimlik", "Ad Soyad", "Hizmet Sınıfı", "Ünvan", "Görev Yeri", "Cep Telefonu"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.cellDoubleClicked.connect(self._detay_ac)
        main_layout.addWidget(self.table)

        # FOOTER
        bottom_layout = QHBoxLayout()
        self.lbl_kayit_sayisi = QLabel("Toplam Kayıt: 0")
        self.progress = QProgressBar(); self.progress.setVisible(False)
        bottom_layout.addWidget(self.lbl_kayit_sayisi)
        bottom_layout.addWidget(self.progress)
        main_layout.addLayout(bottom_layout)

    # ... (Veri işleme ve filtreleme fonksiyonları AYNEN KALIYOR) ...
    def _sabitleri_yukle(self):
        self.sabit_worker = SabitlerWorker()
        self.sabit_worker.veri_indi.connect(lambda l: self.cmb_hizmet_filtre.addItems(l))
        self.sabit_worker.start()

    def _verileri_yenile(self):
        self.progress.setVisible(True); self.progress.setRange(0, 0)
        self.worker = VeriYukleWorker()
        self.worker.veri_indi.connect(self._veri_geldi)
        self.worker.hata_olustu.connect(lambda m: show_error(self, "Hata", m))
        self.worker.start()

    def _veri_geldi(self, veri_listesi):
        self.progress.setVisible(False)
        if not veri_listesi: return
        self.basliklar = veri_listesi[0]
        self.ham_veri = veri_listesi[1:] 
        self._filtrele_tetikle()

    def _filtrele_tetikle(self):
        text = self.txt_ara.text().lower().strip()
        secilen_sinif = self.cmb_hizmet_filtre.currentText()
        if not secilen_sinif: secilen_sinif = "Tümü"
        filtrelenmis_veri = []
        for satir in self.ham_veri:
            satir_str = " ".join([str(x).lower() for x in satir])
            sinif_degeri = satir[4] if len(satir) > 4 else ""
            if (text in satir_str) and ((secilen_sinif == "Tümü") or (sinif_degeri == secilen_sinif)):
                filtrelenmis_veri.append(satir)
        self._tabloyu_doldur(filtrelenmis_veri)

    def _tabloyu_doldur(self, veri_seti):
        self.table.setRowCount(len(veri_seti))
        self.lbl_kayit_sayisi.setText(f"Kayıt: {len(veri_seti)}")
        for i, row in enumerate(veri_seti):
            for j, idx in enumerate([0, 1, 4, 5, 6, 9]):
                val = row[idx] if len(row) > idx else ""
                self.table.setItem(i, j, QTableWidgetItem(str(val)))
            self.table.item(i, 0).setData(Qt.UserRole, row)

    # =========================================================================
    # GÜNCELLENEN KISIMLAR: MDI PENCERE AÇMA
    # =========================================================================

    def _detay_ac(self, row, column):
        """Seçilen satırın detayını MDI içinde açar."""
        item = self.table.item(row, 0)
        if item:
            personel_data = item.data(Qt.UserRole)
            
            # Formu oluştur
            self.detay_penceresi = PersonelDetayPenceresi(personel_data)
            
            # Sinyal bağlantısı (Listeyi güncellemek için)
            self.detay_penceresi.veri_guncellendi.connect(self._verileri_yenile)
            
            # MDI içinde aç
            mdi_pencere_ac(self, self.detay_penceresi, "Personel Detay Kartı")

    def _yeni_personel_ac(self):
        """Yeni personel formunu MDI içinde açar."""
        self.ekle_penceresi = PersonelEklePenceresi()
        
        # MDI içinde aç
        mdi_pencere_ac(self, self.ekle_penceresi, "Yeni Personel Ekle")

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from temalar.tema import TemaYonetimi
    app = QApplication(sys.argv)
    TemaYonetimi.uygula_fusion_dark(app)
    win = PersonelListesiPenceresi()
    win.show()
    sys.exit(app.exec())