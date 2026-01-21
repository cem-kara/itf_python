# -*- coding: utf-8 -*-
import sys
import os
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QProgressBar, QFrame, QAbstractItemView, QMessageBox, QListWidget, 
    QTabWidget, QDateEdit, QInputDialog, QComboBox
)
from PySide6.QtCore import Qt, QThread, Signal, QDate
from PySide6.QtGui import QFont, QColor

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# --- MODÜLLER ---
try:
    from google_baglanti import veritabani_getir
    from araclar.ortak_araclar import show_info, show_error, show_question
except ImportError as e:
    print(f"Modül Hatası: {e}")

# =============================================================================
# WORKER: GENEL VERİ YÜKLEME (HEM SABİTLER HEM TATİLLER İÇİN)
# =============================================================================
class VeriYukleWorker(QThread):
    veri_indi = Signal(list)
    hata_olustu = Signal(str)
    
    def __init__(self, sayfa_adi):
        super().__init__()
        self.sayfa_adi = sayfa_adi # 'Sabitler' veya 'Tatiller'

    def run(self):
        try:
            ws = veritabani_getir('sabit', self.sayfa_adi)
            if ws:
                self.veri_indi.emit(ws.get_all_records())
            else:
                self.hata_olustu.emit(f"'{self.sayfa_adi}' sayfasına erişilemedi.")
        except Exception as e:
            self.hata_olustu.emit(str(e))

# =============================================================================
# WORKER: EKLEME İŞLEMİ (DİNAMİK)
# =============================================================================
class EkleWorker(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)

    def __init__(self, sayfa_adi, veri_listesi):
        super().__init__()
        self.sayfa_adi = sayfa_adi
        self.veri_listesi = veri_listesi # Örn: ['Hizmet_Sinifi', 'GİH', '-'] veya ['01.01.2024', 'Yılbaşı']

    def run(self):
        try:
            ws = veritabani_getir('sabit', self.sayfa_adi)
            if ws:
                ws.append_row(self.veri_listesi)
                self.islem_tamam.emit()
            else:
                self.hata_olustu.emit("Bağlantı hatası.")
        except Exception as e:
            self.hata_olustu.emit(str(e))

# =============================================================================
# WORKER: SİLME İŞLEMİ (DİNAMİK)
# =============================================================================
class SilWorker(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)

    def __init__(self, sayfa_adi, aranan_deger, aranacak_sutun_idx):
        super().__init__()
        self.sayfa_adi = sayfa_adi
        self.deger = str(aranan_deger)
        self.col_idx = aranacak_sutun_idx # 1-based index (Excel gibi)

    def run(self):
        try:
            ws = veritabani_getir('sabit', self.sayfa_adi)
            if ws:
                # Belirtilen sütundaki tüm değerleri çekip index bulalım (Daha hızlı)
                col_values = ws.col_values(self.col_idx)
                
                try:
                    # Python list index 0-based, Excel row 1-based. 
                    # row_idx = index + 1
                    row_idx = col_values.index(self.deger) + 1
                    ws.delete_rows(row_idx)
                    self.islem_tamam.emit()
                except ValueError:
                    self.hata_olustu.emit("Silinecek veri bulunamadı.")
            else:
                self.hata_olustu.emit("Veritabanı bağlantısı yok.")
        except Exception as e:
            self.hata_olustu.emit(str(e))

# =============================================================================
# ANA FORM: AYARLAR PENCERESİ
# =============================================================================
class AyarlarPenceresi(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sistem Ayarları ve Tanımlamalar")
        self.resize(1100, 700)
        
        # --- LİSTELER ---
        self.sabitler_data = []
        self.tatiller_data = []
        
        # Sizin verdiğiniz güncel kategori listesi
        self.kategori_listesi = sorted([
            "Amaç", "AnaBilimDali", "Bedeni", "Birim", "Birim_Sorumlusu/Unvani",
            "Gorev_Yeri", "Gorev", "Hizmet_Sinifi", "Izin_Tipi", "Kadro_Unvani",
            "Kaynak", "Kontrol_Eden/Unvani", "Koruyucu_Cinsi", "Lisans_Durum",
            "Marka", "Cihaz_Tipi", "Garanti_Durum", "Kalibrasyon_Durum",
            "Bakim_Durum", "Drive_Klasor", "Fhsz_kriter"
        ])

        self.setup_ui()
        self.sabitleri_yukle() # İlk açılışta verileri çek

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # --- SEKMELER ---
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #444; background: #1e1e1e; }
            QTabBar::tab { background: #2d2d30; color: #ccc; padding: 10px 20px; font-weight: bold; }
            QTabBar::tab:selected { background: #0078d4; color: white; }
        """)

        # Sekme 1: Genel Tanımlar
        self.tab_genel = QWidget()
        self.setup_tab_genel()
        self.tabs.addTab(self.tab_genel, "📋 Genel Tanımlamalar")

        # Sekme 2: Tatil Günleri
        self.tab_tatil = QWidget()
        self.setup_tab_tatil()
        self.tabs.addTab(self.tab_tatil, "📅 Resmi Tatiller (FHSZ)")

        main_layout.addWidget(self.tabs)

    # -------------------------------------------------------------------------
    # SEKME 1: GENEL TANIMLAMALAR (UI)
    # -------------------------------------------------------------------------
    def setup_tab_genel(self):
        layout = QHBoxLayout(self.tab_genel)
        layout.setContentsMargins(10, 10, 10, 10)

        # -- SOL: Kategoriler --
        left_frame = QFrame()
        left_frame.setFixedWidth(280)
        left_frame.setStyleSheet("QFrame { background-color: #252526; border-radius: 8px; }")
        l_layout = QVBoxLayout(left_frame)
        
        l_layout.addWidget(QLabel("📂 KATEGORİLER"))
        self.list_kat = QListWidget()
        self.list_kat.setStyleSheet("background: #1e1e1e; border: none; font-size: 13px;")
        self.list_kat.addItems(self.kategori_listesi)
        self.list_kat.currentRowChanged.connect(self.kategori_secildi)
        l_layout.addWidget(self.list_kat)
        
        # Yeni Kategori Ekle Butonu
        btn_yeni_kat = QPushButton(" + Özel Kategori Ekle")
        btn_yeni_kat.setStyleSheet("background-color: #333; color: #aaa; border: 1px solid #555;")
        btn_yeni_kat.clicked.connect(self.yeni_kategori_ekle)
        l_layout.addWidget(btn_yeni_kat)

        layout.addWidget(left_frame)

        # -- SAĞ: İçerik Tablosu --
        right_layout = QVBoxLayout()
        
        # Ekleme Alanı
        h_add = QHBoxLayout()
        self.lbl_secili_kat = QLabel("Seçiniz...")
        self.lbl_secili_kat.setStyleSheet("font-size: 16px; font-weight: bold; color: #4dabf7;")
        
        self.txt_deger = QLineEdit()
        self.txt_deger.setPlaceholderText("Yeni Değer / Menü Elemanı")
        self.txt_deger.setFixedHeight(35)
        
        self.btn_ekle_sabit = QPushButton("EKLE")
        self.btn_ekle_sabit.setFixedSize(80, 35)
        self.btn_ekle_sabit.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_ekle_sabit.clicked.connect(self.sabit_ekle)

        h_add.addWidget(self.lbl_secili_kat)
        h_add.addStretch()
        h_add.addWidget(self.txt_deger)
        h_add.addWidget(self.btn_ekle_sabit)
        
        right_layout.addLayout(h_add)

        # Tablo
        self.table_sabit = QTableWidget()
        self.table_sabit.setColumnCount(2)
        self.table_sabit.setHorizontalHeaderLabels(["Değer (Menu Elemanı)", "Açıklama"])
        self.table_sabit.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_sabit.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_sabit.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_sabit.setAlternatingRowColors(True)
        right_layout.addWidget(self.table_sabit)

        # Sil Butonu
        btn_sil_sabit = QPushButton(" Seçili Satırı Sil")
        btn_sil_sabit.setStyleSheet("background-color: #d13438; color: white; font-weight: bold; padding: 8px;")
        btn_sil_sabit.clicked.connect(self.sabit_sil)
        right_layout.addWidget(btn_sil_sabit)

        layout.addLayout(right_layout)

    # -------------------------------------------------------------------------
    # SEKME 2: TATİL GÜNLERİ (UI)
    # -------------------------------------------------------------------------
    def setup_tab_tatil(self):
        layout = QVBoxLayout(self.tab_tatil)
        
        # Ekleme Alanı
        grp_ekle = QGroupBox("Yeni Tatil Ekle")
        grp_ekle.setFixedHeight(100)
        h_layout = QHBoxLayout(grp_ekle)
        
        self.date_tatil = QDateEdit()
        self.date_tatil.setCalendarPopup(True)
        self.date_tatil.setDisplayFormat("dd.MM.yyyy")
        self.date_tatil.setDate(QDate.currentDate())
        self.date_tatil.setFixedWidth(120)
        self.date_tatil.setFixedHeight(35)
        
        self.txt_tatil_aciklama = QLineEdit()
        self.txt_tatil_aciklama.setPlaceholderText("Tatil Açıklaması (Örn: Cumhuriyet Bayramı)")
        self.txt_tatil_aciklama.setFixedHeight(35)
        
        btn_ekle_tatil = QPushButton("TATİL EKLE")
        btn_ekle_tatil.setFixedSize(120, 35)
        btn_ekle_tatil.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; border-radius: 4px;")
        btn_ekle_tatil.clicked.connect(self.tatil_ekle)
        
        h_layout.addWidget(QLabel("Tarih:"))
        h_layout.addWidget(self.date_tatil)
        h_layout.addWidget(QLabel("Açıklama:"))
        h_layout.addWidget(self.txt_tatil_aciklama)
        h_layout.addWidget(btn_ekle_tatil)
        
        layout.addWidget(grp_ekle)

        # Tablo
        self.table_tatil = QTableWidget()
        self.table_tatil.setColumnCount(2)
        self.table_tatil.setHorizontalHeaderLabels(["Tarih", "Açıklama"])
        self.table_tatil.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_tatil.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_tatil.setAlternatingRowColors(True)
        layout.addWidget(self.table_tatil)

        # Alt Butonlar
        h_bot = QHBoxLayout()
        btn_yenile = QPushButton(" Listeyi Yenile")
        btn_yenile.clicked.connect(self.tatilleri_yukle)
        
        btn_sil_tatil = QPushButton(" Seçili Tatili Sil")
        btn_sil_tatil.setStyleSheet("background-color: #d13438; color: white; font-weight: bold;")
        btn_sil_tatil.clicked.connect(self.tatil_sil)
        
        h_bot.addWidget(btn_yenile)
        h_bot.addStretch()
        h_bot.addWidget(btn_sil_tatil)
        layout.addLayout(h_bot)

        # Sekme açıldığında yüklemesi için sinyal
        # (Şimdilik manuel çağırıyoruz init'te)

    # -------------------------------------------------------------------------
    # İŞLEMLER (LOGIC)
    # -------------------------------------------------------------------------
    
    # --- SABİTLER ---
    def sabitleri_yukle(self):
        self.sabit_worker = VeriYukleWorker('Sabitler')
        self.sabit_worker.veri_indi.connect(self._sabitler_geldi)
        self.sabit_worker.start()
        # Tatilleri de arka planda yükleyelim
        self.tatilleri_yukle()

    def _sabitler_geldi(self, data):
        self.sabitler_data = data
        # Eğer bir kategori seçiliyse tabloyu yenile
        self.kategori_secildi(self.list_kat.currentRow())

    def kategori_secildi(self, row_index):
        if row_index < 0: return
        kat = self.list_kat.item(row_index).text()
        self.lbl_secili_kat.setText(kat)
        self.txt_deger.clear()
        
        # Filtreleme (Kod sütunu)
        filtrelenmis = [x for x in self.sabitler_data if str(x.get('Kod', '')).strip() == kat]
        
        self.table_sabit.setRowCount(len(filtrelenmis))
        for i, row in enumerate(filtrelenmis):
            self.table_sabit.setItem(i, 0, QTableWidgetItem(str(row.get('MenuEleman', ''))))
            self.table_sabit.setItem(i, 1, QTableWidgetItem(str(row.get('Aciklama', ''))))

    def sabit_ekle(self):
        kat = self.lbl_secili_kat.text()
        deger = self.txt_deger.text().strip()
        if not deger or kat == "Seçiniz...":
            return
        
        self.btn_ekle_sabit.setEnabled(False)
        # Sütun Sırası: Kod, MenuEleman, Aciklama
        self.ekle_worker = EkleWorker('Sabitler', [kat, deger, ""])
        self.ekle_worker.islem_tamam.connect(lambda: [self.sabitleri_yukle(), self.btn_ekle_sabit.setEnabled(True)])
        self.ekle_worker.start()

    def sabit_sil(self):
        row = self.table_sabit.currentRow()
        if row < 0: return
        deger = self.table_sabit.item(row, 0).text()
        
        if show_question("Sil", f"'{deger}' silinecek. Emin misiniz?", self):
            # Sabitler sayfasında 'MenuEleman' 2. sütundur.
            self.sil_worker = SilWorker('Sabitler', deger, 2)
            self.sil_worker.islem_tamam.connect(self.sabitleri_yukle)
            self.sil_worker.hata_olustu.connect(lambda e: show_error("Hata", e, self))
            self.sil_worker.start()

    def yeni_kategori_ekle(self):
        text, ok = QInputDialog.getText(self, 'Yeni Kategori', 'Kategori Kodu Giriniz:')
        if ok and text:
            self.list_kategoriler.addItem(text.strip())

    # --- TATİLLER ---
    def tatilleri_yukle(self):
        self.tatil_worker = VeriYukleWorker('Tatiller')
        self.tatil_worker.veri_indi.connect(self._tatiller_geldi)
        self.tatil_worker.start()

    def _tatiller_geldi(self, data):
        self.tatiller_data = data
        self.table_tatil.setRowCount(len(data))
        # Veriyi Tarihe Göre Sıralamak İsterseniz burada sort yapabilirsiniz
        # data.sort(key=lambda x: datetime.strptime(x['Tarih'], '%d.%m.%Y')) 
        
        for i, row in enumerate(data):
            # Sütun adları Google Sheet'te 'Tarih' ve 'Aciklama' olmalı
            tarih = str(row.get('Tarih', ''))
            aciklama = str(row.get('Aciklama', row.get('Tatil Adi', ''))) # Esneklik
            
            self.table_tatil.setItem(i, 0, QTableWidgetItem(tarih))
            self.table_tatil.setItem(i, 1, QTableWidgetItem(aciklama))

    def tatil_ekle(self):
        tarih = self.date_tatil.date().toString("dd.MM.yyyy")
        aciklama = self.txt_tatil_aciklama.text().strip()
        
        if not aciklama:
            show_error("Uyarı", "Tatil açıklaması giriniz.", self)
            return
            
        self.t_ekle_worker = EkleWorker('Tatiller', [tarih, aciklama])
        self.t_ekle_worker.islem_tamam.connect(lambda: [self.tatilleri_yukle(), self.txt_tatil_aciklama.clear()])
        self.t_ekle_worker.start()

    def tatil_sil(self):
        row = self.table_tatil.currentRow()
        if row < 0: return
        tarih = self.table_tatil.item(row, 0).text()
        
        if show_question("Sil", f"{tarih} tarihli tatil silinecek. Emin misiniz?", self):
            # Tatiller sayfasında 'Tarih' 1. sütundur.
            self.t_sil_worker = SilWorker('Tatiller', tarih, 1)
            self.t_sil_worker.islem_tamam.connect(self.tatilleri_yukle)
            self.t_sil_worker.start()

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from temalar.tema import TemaYonetimi
    app = QApplication(sys.argv)
    TemaYonetimi.uygula_fusion_dark(app)
    win = AyarlarPenceresi()
    win.show()
    sys.exit(app.exec())