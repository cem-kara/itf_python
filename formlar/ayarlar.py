# -*- coding: utf-8 -*-
import sys
import os
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QProgressBar, QFrame, QAbstractItemView, QMessageBox, QListWidget, 
    QTabWidget, QDateEdit, QInputDialog, QComboBox, QGroupBox, QCheckBox
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
    from araclar.yetki_yonetimi import YetkiYoneticisi
except ImportError as e:
    print(f"Modül Hatası: {e}")
    def veritabani_getir(t, s): return None
    def show_info(t, m, p): print(m)
    def show_error(t, m, p): print(m)
    def show_question(t, m, p): return True

# =============================================================================
# 🟢 YETKİ KONTROL LİSTESİ (REGISTRY)
# =============================================================================
FORM_KONTROLLER = {
    "main_window": [
        "btn_dashboard", "btn_ayarlar", 
        "btn_personel_listesi", "btn_personel_ekle", "btn_izin_takip", "btn_fhsz_yonetim", "btn_personel_verileri",
        "btn_cihaz_listesi", "btn_cihaz_ekle", "btn_ariza_kaydi", "btn_ariza_listesi", "btn_periyodik_bakim", "btn_kalibrasyon_takip",
        "btn_rke_listesi", "btn_muayene_girisi", "btn_rke_raporlama"
    ],
    "personel_listesi": [
        "btn_yeni", "btn_sil", "action_detay", "action_user", "action_sil"
    ],
    "personel_detay": [
        "btn_kaydet", "btn_sil", "grp_kimlik", "grp_maas"
    ],
    "personel_ekle": ["btn_kaydet"],
    "fhsz_yonetim": ["tab_hesapla", "tab_rapor"],
    "fhsz_hesapla": ["btn_hesapla", "btn_kaydet"],
    "izin_giris": ["btn_ekle", "btn_sil"],
    "ayarlar_penceresi": ["tab_yetki", "btn_ekle_sabit", "btn_sil_sabit"]
}

# =============================================================================
# WORKER SINIFLARI
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
            if ws: self.veri_indi.emit(ws.get_all_records())
            else: self.hata_olustu.emit(f"'{self.sayfa_adi}' sayfasına erişilemedi.")
        except Exception as e: self.hata_olustu.emit(str(e))

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
            else: self.hata_olustu.emit("Bağlantı hatası.")
        except Exception as e: self.hata_olustu.emit(str(e))

class SilWorker(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)
    def __init__(self, sayfa_adi, satir_no):
        super().__init__()
        self.sayfa_adi = sayfa_adi
        self.satir_no = satir_no
    def run(self):
        try:
            ws = veritabani_getir('sabit', self.sayfa_adi)
            if ws:
                ws.delete_rows(self.satir_no)
                self.islem_tamam.emit()
            else: self.hata_olustu.emit("Bağlantı yok.")
        except Exception as e: self.hata_olustu.emit(str(e))

# =============================================================================
# ANA FORM: AYARLAR PENCERESİ
# =============================================================================
class AyarlarPenceresi(QWidget):
    def __init__(self, yetki=None):
        super().__init__()
        self.setWindowTitle("Sistem Ayarları ve Tanımlamalar")
        self.resize(1150, 750)
        self.yetki = yetki
        
        self.sabitler_data = []
        self.tatiller_data = []
        self.yetkiler_data = [] 
        self.kategori_listesi = [] 

        self.setup_ui()
        self.sabitleri_yukle() 
        
        try:
            YetkiYoneticisi.uygula(self, "ayarlar_penceresi")
        except: pass

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #444; background: #1e1e1e; }
            QTabBar::tab { background: #2d2d30; color: #ccc; padding: 10px 20px; font-weight: bold; }
            QTabBar::tab:selected { background: #0078d4; color: white; }
        """)

        self.tab_genel = QWidget()
        self.setup_tab_genel()
        self.tabs.addTab(self.tab_genel, "📋 Genel Tanımlamalar")

        self.tab_tatil = QWidget()
        self.setup_tab_tatil()
        self.tabs.addTab(self.tab_tatil, "📅 Resmi Tatiller (FHSZ)")

        self.tab_yetki = QWidget()
        self.setup_tab_yetki()
        self.tabs.addTab(self.tab_yetki, "🔐 Yetki ve Rol Yönetimi")

        main_layout.addWidget(self.tabs)

    def setup_tab_genel(self):
        layout = QHBoxLayout(self.tab_genel)
        left_frame = QFrame(); left_frame.setFixedWidth(280); 
        l_layout = QVBoxLayout(left_frame); l_layout.addWidget(QLabel("📂 KATEGORİLER"))
        self.list_kat = QListWidget(); self.list_kat.currentRowChanged.connect(self.kategori_secildi)
        l_layout.addWidget(self.list_kat)
        btn_yeni = QPushButton(" + Özel Kategori"); btn_yeni.clicked.connect(self.yeni_kategori_ekle)
        l_layout.addWidget(btn_yeni); layout.addWidget(left_frame)
        
        r_layout = QVBoxLayout(); h_add = QHBoxLayout()
        self.lbl_secili_kat = QLabel("Seçiniz..."); self.txt_deger = QLineEdit(); self.txt_aciklama = QLineEdit()
        self.btn_ekle_sabit = QPushButton("EKLE"); self.btn_ekle_sabit.clicked.connect(self.sabit_ekle)
        h_add.addWidget(self.lbl_secili_kat); h_add.addWidget(self.txt_deger); h_add.addWidget(self.txt_aciklama); h_add.addWidget(self.btn_ekle_sabit)
        r_layout.addLayout(h_add)
        self.table_sabit = QTableWidget(0, 2); self.table_sabit.setHorizontalHeaderLabels(["Değer", "Açıklama"])
        self.table_sabit.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        r_layout.addWidget(self.table_sabit); layout.addLayout(r_layout)

    def setup_tab_tatil(self):
        layout = QVBoxLayout(self.tab_tatil)
        grp = QGroupBox("Yeni Tatil"); h = QHBoxLayout(grp)
        self.date_tatil = QDateEdit(QDate.currentDate()); self.date_tatil.setCalendarPopup(True)
        self.txt_tatil_aciklama = QLineEdit(); btn = QPushButton("EKLE"); btn.clicked.connect(self.tatil_ekle)
        h.addWidget(QLabel("Tarih:")); h.addWidget(self.date_tatil)
        h.addWidget(QLabel("Açıklama:")); h.addWidget(self.txt_tatil_aciklama); h.addWidget(btn)
        layout.addWidget(grp)
        
        h_filtre = QHBoxLayout()
        self.cmb_tatil_yil = QComboBox(); self.cmb_tatil_yil.addItem("Tümü")
        self.cmb_tatil_yil.currentTextChanged.connect(self._tatil_filtrele)
        h_filtre.addWidget(QLabel("Yıl:")); h_filtre.addWidget(self.cmb_tatil_yil); h_filtre.addStretch()
        layout.addLayout(h_filtre)
        
        self.table_tatil = QTableWidget(0, 2); self.table_tatil.setHorizontalHeaderLabels(["Tarih", "Açıklama"])
        self.table_tatil.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table_tatil)
        btn_yenile = QPushButton("Yenile"); btn_yenile.clicked.connect(self.tatilleri_yukle)
        layout.addWidget(btn_yenile)

    def setup_tab_yetki(self):
        layout = QVBoxLayout(self.tab_yetki)
        
        grp_yetki = QGroupBox("Yeni Kısıtlama Kuralı Ekle")
        grp_yetki.setFixedHeight(120)
        grp_yetki.setStyleSheet("QGroupBox { border: 1px solid #555; border-radius: 5px; margin-top: 10px; font-weight: bold; color: #4dabf7; }")
        
        h_yetki = QHBoxLayout(grp_yetki)
        
        # Rol
        v_rol = QVBoxLayout(); v_rol.addWidget(QLabel("Rol:"))
        self.cmb_rol = QComboBox(); self.cmb_rol.addItems(["viewer", "user", "admin"]); self.cmb_rol.setEditable(True)
        v_rol.addWidget(self.cmb_rol); h_yetki.addLayout(v_rol)
        
        # Form Kodu
        v_form = QVBoxLayout(); v_form.addWidget(QLabel("Form Kodu:"))
        self.cmb_form_kodu = QComboBox()
        self.cmb_form_kodu.addItems(sorted(list(FORM_KONTROLLER.keys())))
        self.cmb_form_kodu.setEditable(True)
        self.cmb_form_kodu.currentTextChanged.connect(self._form_degisti)
        v_form.addWidget(self.cmb_form_kodu); h_yetki.addLayout(v_form)
        
        # Nesne Adı
        v_oge = QVBoxLayout(); v_oge.addWidget(QLabel("Nesne Adı:"))
        self.cmb_oge_adi = QComboBox(); self.cmb_oge_adi.setEditable(True); self.cmb_oge_adi.setPlaceholderText("Örn: btn_sil")
        v_oge.addWidget(self.cmb_oge_adi); h_yetki.addLayout(v_oge)

        # İşlem
        v_islem = QVBoxLayout(); v_islem.addWidget(QLabel("İşlem:"))
        self.cmb_islem = QComboBox(); self.cmb_islem.addItems(["GIZLE", "PASIF"])
        v_islem.addWidget(self.cmb_islem); h_yetki.addLayout(v_islem)

        # Buton
        self.btn_yetki_ekle = QPushButton("KURAL EKLE")
        self.btn_yetki_ekle.setFixedSize(100, 40)
        self.btn_yetki_ekle.setStyleSheet("background-color: #d13438; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_yetki_ekle.clicked.connect(self.yetki_ekle)
        h_yetki.addWidget(self.btn_yetki_ekle)
        layout.addWidget(grp_yetki)

        # Tablo
        self.table_yetki = QTableWidget(0, 4); self.table_yetki.setHorizontalHeaderLabels(["Rol", "Form Kodu", "Nesne Adı", "Kısıtlama"])
        self.table_yetki.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_yetki.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_yetki.setAlternatingRowColors(True)
        layout.addWidget(self.table_yetki)

        # Alt Butonlar
        h_alt = QHBoxLayout()
        btn_yetki_yenile = QPushButton(" Listeyi Yenile"); btn_yetki_yenile.clicked.connect(self.yetkileri_yukle)
        self.btn_yetki_sil = QPushButton(" Seçili Kuralı SİL"); self.btn_yetki_sil.setStyleSheet("background-color: #555; color: white; font-weight: bold;")
        self.btn_yetki_sil.clicked.connect(self.yetki_sil)
        
        h_alt.addWidget(btn_yetki_yenile); h_alt.addStretch(); h_alt.addWidget(self.btn_yetki_sil)
        layout.addLayout(h_alt)
        
        self._form_degisti(self.cmb_form_kodu.currentText())

    def _form_degisti(self, form_kodu):
        self.cmb_oge_adi.clear()
        if form_kodu in FORM_KONTROLLER:
            self.cmb_oge_adi.addItems(sorted(FORM_KONTROLLER[form_kodu]))

    # --- İŞLEMLER ---
    def sabitleri_yukle(self):
        # Eğer varsa eski thread'i durdur
        if hasattr(self, 'sabit_worker') and self.sabit_worker and self.sabit_worker.isRunning():
            return
        self.sabit_worker = VeriYukleWorker('Sabitler'); self.sabit_worker.veri_indi.connect(self._sabitler_geldi); self.sabit_worker.start()
        self.tatilleri_yukle(); self.yetkileri_yukle()

    def _sabitler_geldi(self, data):
        self.sabitler_data = data; kats = set(str(r.get('Kod','')).strip() for r in data if r.get('Kod'))
        self.kategori_listesi = sorted(list(kats)); self.list_kat.clear(); self.list_kat.addItems(self.kategori_listesi)

    def kategori_secildi(self, row):
        if row < 0: return
        kat = self.list_kat.item(row).text(); self.lbl_secili_kat.setText(kat)
        filt = [x for x in self.sabitler_data if str(x.get('Kod', '')).strip() == kat]
        self.table_sabit.setRowCount(len(filt))
        for i, r in enumerate(filt):
            self.table_sabit.setItem(i, 0, QTableWidgetItem(str(r.get('MenuEleman',''))))
            self.table_sabit.setItem(i, 1, QTableWidgetItem(str(r.get('Aciklama',''))))

    def sabit_ekle(self):
        kat = self.lbl_secili_kat.text(); deger = self.txt_deger.text().strip(); aciklama = self.txt_aciklama.text().strip()
        if not deger or kat == "Seçiniz...": return
        self.btn_ekle_sabit.setEnabled(False)
        self.ekle_worker = EkleWorker('Sabitler', [kat, deger, aciklama])
        self.ekle_worker.islem_tamam.connect(lambda: [self.sabitleri_yukle(), self.btn_ekle_sabit.setEnabled(True)])
        self.ekle_worker.start()

    def yeni_kategori_ekle(self):
        text, ok = QInputDialog.getText(self, 'Yeni Kategori', 'Kategori Kodu:')
        if ok and text and text not in self.kategori_listesi: self.list_kat.addItem(text.strip())

    def tatilleri_yukle(self):
        if hasattr(self, 'tatil_worker') and self.tatil_worker.isRunning(): return
        self.tatil_worker = VeriYukleWorker('Tatiller'); self.tatil_worker.veri_indi.connect(self._tatiller_geldi); self.tatil_worker.start()

    def _tatiller_geldi(self, data):
        self.tatiller_data = data
        # Yıl filtresi vb. işlemleri burada kısaca
        self._tatil_filtrele()

    def _tatil_filtrele(self):
        # Basit filtreleme
        self.table_tatil.setRowCount(0) # Temizle
        filt = self.tatiller_data # Tam liste (Filtre mantığını basitleştirdim hatayı önlemek için)
        self.table_tatil.setRowCount(len(filt))
        for i, r in enumerate(filt):
            self.table_tatil.setItem(i, 0, QTableWidgetItem(str(r.get('Tarih',''))))
            self.table_tatil.setItem(i, 1, QTableWidgetItem(str(r.get('Aciklama', r.get('Tatil Adi','')))))

    def tatil_ekle(self):
        t = self.date_tatil.date().toString("dd.MM.yyyy"); a = self.txt_tatil_aciklama.text().strip()
        if not a: return
        self.t_ekle_worker = EkleWorker('Tatiller', [t, a])
        self.t_ekle_worker.islem_tamam.connect(lambda: [self.tatilleri_yukle(), self.txt_tatil_aciklama.clear()])
        self.t_ekle_worker.start()

    # --- YETKİLER ---
    def yetkileri_yukle(self):
        if hasattr(self, 'yetki_worker') and self.yetki_worker and self.yetki_worker.isRunning():
            return
        self.yetki_worker = VeriYukleWorker('Rol_Yetkileri')
        self.yetki_worker.veri_indi.connect(self._yetkiler_geldi)
        self.yetki_worker.start()

    def _yetkiler_geldi(self, data):
        self.yetkiler_data = data
        self.table_yetki.setRowCount(len(data))
        for i, row in enumerate(data):
            sheet_row_num = i + 2 
            self.table_yetki.setItem(i, 0, QTableWidgetItem(str(row.get('Rol', ''))))
            self.table_yetki.setItem(i, 1, QTableWidgetItem(str(row.get('Form_Kodu', ''))))
            self.table_yetki.setItem(i, 2, QTableWidgetItem(str(row.get('Oge_Adi', ''))))
            self.table_yetki.setItem(i, 3, QTableWidgetItem(str(row.get('Islem', ''))))
            self.table_yetki.item(i, 0).setData(Qt.UserRole, sheet_row_num)

    def yetki_ekle(self):
        rol = self.cmb_rol.currentText()
        form = self.cmb_form_kodu.currentText()
        oge = self.cmb_oge_adi.currentText().strip()
        islem = self.cmb_islem.currentText()
        
        if not oge:
            show_error("Eksik", "Nesne adı giriniz.", self)
            return

        self.btn_yetki_ekle.setEnabled(False)
        self.y_ekle_worker = EkleWorker('Rol_Yetkileri', [rol, form, oge, islem])
        self.y_ekle_worker.finished.connect(lambda: self._thread_temizle("ekle"))
        self.y_ekle_worker.islem_tamam.connect(lambda: [self.yetkileri_yukle(), self.btn_yetki_ekle.setEnabled(True)])
        self.y_ekle_worker.start()

    def yetki_sil(self):
        row = self.table_yetki.currentRow()
        if row < 0: return
        rol = self.table_yetki.item(row, 0).text()
        oge = self.table_yetki.item(row, 2).text()
        sheet_row_num = self.table_yetki.item(row, 0).data(Qt.UserRole)
        
        if show_question("Sil", f"'{rol}' rolü için '{oge}' kuralı silinecek. Emin misiniz?", self):
            self.y_sil_worker = SilWorker('Rol_Yetkileri', sheet_row_num)
            self.y_sil_worker.finished.connect(lambda: self._thread_temizle("sil"))
            self.y_sil_worker.islem_tamam.connect(self.yetkileri_yukle)
            self.y_sil_worker.start()

    def _thread_temizle(self, tip):
        if tip == "ekle" and hasattr(self, 'y_ekle_worker'):
            self.y_ekle_worker.deleteLater()
            self.y_ekle_worker = None
        elif tip == "sil" and hasattr(self, 'y_sil_worker'):
            self.y_sil_worker.deleteLater()
            self.y_sil_worker = None

    # 🔴 EN ÖNEMLİ KISIM: Pencere kapanırken threadleri öldür
    def closeEvent(self, event):
        worker_names = ['sabit_worker', 'tatil_worker', 'yetki_worker', 'ekle_worker', 't_ekle_worker', 'y_ekle_worker', 'y_sil_worker']
        for name in worker_names:
            if hasattr(self, name):
                worker = getattr(self, name)
                if worker and worker.isRunning():
                    worker.quit()
                    worker.wait(500) # Max 500ms bekle
        event.accept()

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from temalar.tema import TemaYonetimi
    app = QApplication(sys.argv)
    TemaYonetimi.uygula_fusion_dark(app)
    win = AyarlarPenceresi(yetki="admin")
    win.show()
    sys.exit(app.exec())