# -*- coding: utf-8 -*-
import sys
import os
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QProgressBar, QFrame, QAbstractItemView, QMessageBox, QListWidget, 
    QTabWidget, QDateEdit, QInputDialog, QComboBox, QGroupBox
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
    def veritabani_getir(t, s): return None
    def show_info(t, m, p): print(m)
    def show_error(t, m, p): print(m)
    def show_question(t, m, p): return True

# =============================================================================
# WORKER: GENEL VERİ YÜKLEME
# =============================================================================
class VeriYukleWorker(QThread):
    veri_indi = Signal(list)
    hata_olustu = Signal(str)
    
    def __init__(self, sayfa_adi):
        super().__init__()
        self.sayfa_adi = sayfa_adi 

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
# WORKER: EKLEME İŞLEMİ
# =============================================================================
class EkleWorker(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)

    def __init__(self, sayfa_adi, veri_listesi):
        super().__init__()
        self.sayfa_adi = sayfa_adi
        self.veri_listesi = veri_listesi 

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
# ANA FORM: AYARLAR PENCERESİ
# =============================================================================
class AyarlarPenceresi(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sistem Ayarları ve Tanımlamalar")
        self.resize(1100, 700)
        
        # --- VERİLER ---
        self.sabitler_data = []
        self.tatiller_data = []
        self.kategori_listesi = [] # Artık boş başlatıyoruz, veritabanından dolacak

        self.setup_ui()
        self.sabitleri_yukle() 

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
        # Veriler gelince dolacak, şimdilik boş
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
        
        # --- EKLEME ALANI ---
        h_add = QHBoxLayout()
        
        # 1. Kategori Başlığı
        self.lbl_secili_kat = QLabel("Seçiniz...")
        self.lbl_secili_kat.setFixedWidth(150)
        self.lbl_secili_kat.setStyleSheet("font-size: 16px; font-weight: bold; color: #4dabf7;")
        
        # 2. Değer Girişi
        self.txt_deger = QLineEdit()
        self.txt_deger.setPlaceholderText("Değer / İsim")
        self.txt_deger.setFixedHeight(35)
        
        # 3. Açıklama Girişi
        self.txt_aciklama = QLineEdit()
        self.txt_aciklama.setPlaceholderText("Açıklama (Opsiyonel)")
        self.txt_aciklama.setFixedHeight(35)
        
        # 4. Ekle Butonu
        self.btn_ekle_sabit = QPushButton("EKLE")
        self.btn_ekle_sabit.setFixedSize(80, 35)
        self.btn_ekle_sabit.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_ekle_sabit.clicked.connect(self.sabit_ekle)

        h_add.addWidget(self.lbl_secili_kat)
        h_add.addWidget(self.txt_deger)
        h_add.addWidget(self.txt_aciklama)
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

        # SİLME KAPALI UYARISI
        lbl_uyari = QLabel("ℹ️ Veri bütünlüğü için silme işlemi kapatılmıştır.")
        lbl_uyari.setStyleSheet("color: #666; font-style: italic;")
        right_layout.addWidget(lbl_uyari)

        layout.addLayout(right_layout)

    # -------------------------------------------------------------------------
    # SEKME 2: TATİL GÜNLERİ (UI)
    # -------------------------------------------------------------------------
    def setup_tab_tatil(self):
        layout = QVBoxLayout(self.tab_tatil)
        
        # 1. Ekleme Alanı
        grp_ekle = QGroupBox("Yeni Tatil Ekle")
        grp_ekle.setFixedHeight(90)
        grp_ekle.setStyleSheet("QGroupBox { border: 1px solid #555; border-radius: 5px; margin-top: 10px; font-weight: bold; color: #ccc; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }")
        
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

        # 2. Yıl Filtresi
        h_filtre = QHBoxLayout()
        h_filtre.addWidget(QLabel("Yıl Filtresi:"))
        
        self.cmb_tatil_yil = QComboBox()
        self.cmb_tatil_yil.addItem("Tümü")
        self.cmb_tatil_yil.setFixedWidth(120)
        self.cmb_tatil_yil.currentTextChanged.connect(self._tatil_filtrele)
        
        h_filtre.addWidget(self.cmb_tatil_yil)
        h_filtre.addStretch()
        
        layout.addLayout(h_filtre)

        # 3. Tablo
        self.table_tatil = QTableWidget()
        self.table_tatil.setColumnCount(2)
        self.table_tatil.setHorizontalHeaderLabels(["Tarih", "Açıklama"])
        self.table_tatil.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_tatil.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_tatil.setAlternatingRowColors(True)
        layout.addWidget(self.table_tatil)

        # 4. Alt Kısım
        h_bot = QHBoxLayout()
        btn_yenile = QPushButton(" Listeyi Yenile")
        btn_yenile.clicked.connect(self.tatilleri_yukle)
        
        lbl_uyari_tatil = QLabel("ℹ️ Silme işlemi iptal edilmiştir.")
        lbl_uyari_tatil.setStyleSheet("color: #666; font-style: italic;")
        
        h_bot.addWidget(btn_yenile)
        h_bot.addStretch()
        h_bot.addWidget(lbl_uyari_tatil)
        layout.addLayout(h_bot)

    # -------------------------------------------------------------------------
    # İŞLEMLER (LOGIC)
    # -------------------------------------------------------------------------
    
    # --- SABİTLER ---
    def sabitleri_yukle(self):
        self.sabit_worker = VeriYukleWorker('Sabitler')
        self.sabit_worker.veri_indi.connect(self._sabitler_geldi)
        self.sabit_worker.start()
        # Tatilleri de arka planda yükle
        self.tatilleri_yukle()

    def _sabitler_geldi(self, data):
        self.sabitler_data = data
        
        # --- GÜNCELLEME BURADA ---
        # Veritabanındaki 'Kod' sütunundan (genelde 1. sütun) benzersiz kategorileri çekiyoruz.
        benzersiz_kategoriler = set()
        for row in data:
            kod = str(row.get('Kod', '')).strip()
            if kod: # Boş değilse ekle
                benzersiz_kategoriler.add(kod)
        
        self.kategori_listesi = sorted(list(benzersiz_kategoriler))
        
        # ListWidget'ı güncelle
        current_row = self.list_kat.currentRow() # Eski seçimi hatırla
        self.list_kat.clear()
        self.list_kat.addItems(self.kategori_listesi)
        
        # Eski seçimi geri yükle veya ilkini seç
        if current_row >= 0 and current_row < self.list_kat.count():
            self.list_kat.setCurrentRow(current_row)
        elif self.list_kat.count() > 0:
            self.list_kat.setCurrentRow(0)

    def kategori_secildi(self, row_index):
        if row_index < 0: return
        kat = self.list_kat.item(row_index).text()
        self.lbl_secili_kat.setText(kat)
        self.txt_deger.clear()
        self.txt_aciklama.clear()
        
        filtrelenmis = [x for x in self.sabitler_data if str(x.get('Kod', '')).strip() == kat]
        
        self.table_sabit.setRowCount(len(filtrelenmis))
        for i, row in enumerate(filtrelenmis):
            self.table_sabit.setItem(i, 0, QTableWidgetItem(str(row.get('MenuEleman', ''))))
            self.table_sabit.setItem(i, 1, QTableWidgetItem(str(row.get('Aciklama', ''))))

    def sabit_ekle(self):
        kat = self.lbl_secili_kat.text()
        deger = self.txt_deger.text().strip()
        aciklama = self.txt_aciklama.text().strip()
        
        if not deger or kat == "Seçiniz...":
            show_info("Eksik", "Lütfen bir değer giriniz.", self)
            return
        
        self.btn_ekle_sabit.setEnabled(False)
        self.ekle_worker = EkleWorker('Sabitler', [kat, deger, aciklama])
        self.ekle_worker.islem_tamam.connect(lambda: [self.sabitleri_yukle(), self.btn_ekle_sabit.setEnabled(True)])
        self.ekle_worker.start()

    def yeni_kategori_ekle(self):
        # Bu fonksiyon artık sadece UI'a geçici ekler. 
        # Gerçek veritabanına, kullanıcı içine ilk veriyi ekleyince ("Kod" sütununa yazılarak) kaydolur.
        text, ok = QInputDialog.getText(self, 'Yeni Kategori', 'Kategori Kodu Giriniz (Örn: Personel_Durumu):')
        if ok and text:
            yeni_kat = text.strip()
            if yeni_kat not in self.kategori_listesi:
                self.list_kat.addItem(yeni_kat)
                self.list_kat.setCurrentRow(self.list_kat.count() - 1)

    # --- TATİLLER ---
    def tatilleri_yukle(self):
        self.tatil_worker = VeriYukleWorker('Tatiller')
        self.tatil_worker.veri_indi.connect(self._tatiller_geldi)
        self.tatil_worker.start()

    def _tatiller_geldi(self, data):
        self.tatiller_data = data
        
        yillar = set()
        for row in data:
            tarih = str(row.get('Tarih', ''))
            if len(tarih) >= 4:
                try:
                    yillar.add(tarih.split('.')[-1])
                except: pass
        
        sirali_yillar = sorted(list(yillar), reverse=True)
        
        mevcut_secim = self.cmb_tatil_yil.currentText()
        self.cmb_tatil_yil.blockSignals(True)
        self.cmb_tatil_yil.clear()
        self.cmb_tatil_yil.addItem("Tümü")
        self.cmb_tatil_yil.addItems(sirali_yillar)
        
        if mevcut_secim in sirali_yillar or mevcut_secim == "Tümü":
            self.cmb_tatil_yil.setCurrentText(mevcut_secim)
        else:
            self.cmb_tatil_yil.setCurrentIndex(0)
        self.cmb_tatil_yil.blockSignals(False)
        
        self._tatil_filtrele()

    def _tatil_filtrele(self):
        secilen_yil = self.cmb_tatil_yil.currentText()
        filtrelenmis_data = []
        if secilen_yil == "Tümü":
            filtrelenmis_data = self.tatiller_data
        else:
            for row in self.tatiller_data:
                tarih = str(row.get('Tarih', ''))
                if tarih.endswith(secilen_yil):
                    filtrelenmis_data.append(row)
        
        self.table_tatil.setRowCount(len(filtrelenmis_data))
        for i, row in enumerate(filtrelenmis_data):
            tarih = str(row.get('Tarih', ''))
            aciklama = str(row.get('Aciklama', row.get('Resmi_Tatil', '')))
            
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

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    try:
        from temalar.tema import TemaYonetimi
        app = QApplication(sys.argv)
        TemaYonetimi.uygula_fusion_dark(app)
    except:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        
    win = AyarlarPenceresi()
    win.show()
    sys.exit(app.exec())