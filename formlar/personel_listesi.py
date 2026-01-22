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
    QProgressBar, QFrame, QAbstractItemView, QMessageBox, 
    QComboBox, QCheckBox, QMenu, QInputDialog
)

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from araclar.yetki_yonetimi import YetkiYoneticisi
from araclar.guvenlik import GuvenlikAraclari
# --- MODÜLLER ---
try:
    from google_baglanti import veritabani_getir
    from araclar.ortak_araclar import (
        pencereyi_kapat, show_info, show_error, create_group_box, 
        mdi_pencere_ac, show_question 
    )
    # Modüller henüz hazır değilse hata vermemesi için try blokları içinde import edilebilir
    try:
        from formlar.personel_detay import PersonelDetayPenceresi
        from formlar.personel_ekle import PersonelEklePenceresi
    except ImportError:
        pass

except ImportError as e:
    print(f"Modül Hatası: {e}")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PersonelListesi")

# =============================================================================
# WORKER SINIFLARI
# =============================================================================

class VeriYukleWorker(QThread):
    veri_indi = Signal(list)
    hata_olustu = Signal(str)
    def run(self):
        try:
            ws = veritabani_getir('personel', 'Personel')
            if ws: self.veri_indi.emit(ws.get_all_values())
            else: self.hata_olustu.emit("Veritabanına bağlanılamadı.")
        except Exception as e: self.hata_olustu.emit(str(e))

class DurumGuncelleWorker(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)
    
    def __init__(self, tc_no, yeni_durum):
        super().__init__()
        self.tc_no = tc_no
        self.yeni_durum = yeni_durum

    def run(self):
        try:
            ws = veritabani_getir('personel', 'Personel')
            cell = ws.find(self.tc_no)
            if cell:
                basliklar = ws.row_values(1)
                try:
                    durum_col_idx = basliklar.index("Durum") + 1
                except ValueError:
                    durum_col_idx = len(basliklar) + 1
                
                ws.update_cell(cell.row, durum_col_idx, self.yeni_durum)
                self.islem_tamam.emit()
            else:
                self.hata_olustu.emit("Personel bulunamadı.")
        except Exception as e:
            self.hata_olustu.emit(str(e))

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

class KullaniciEkleWorker(QThread):
    sonuc = Signal(bool, str)
    def __init__(self, kimlik, ad_soyad, rol):
        super().__init__()
        self.kimlik = kimlik
        self.ad_soyad = ad_soyad
        self.rol = rol

    def run(self):
        try:
            ws = veritabani_getir('user', 'user_login')
            if not ws:
                self.sonuc.emit(False, "User veritabanına erişilemedi.")
                return
            
            # ... (Mükerrer kontrolü aynı kalacak) ...

            import random
            user_id = random.randint(10000, 99999)
            
            # ŞİFRELEME BURADA YAPILIYOR
            # Varsayılan şifre: 12345
            sifreli_pass = GuvenlikAraclari.sifrele("12345")
            
            # password sütununa artık '12345' değil, hashlenmiş hali gidiyor
            ws.append_row([user_id, self.kimlik, sifreli_pass, self.rol, "", "EVET"])
            
            self.sonuc.emit(True, f"{self.ad_soyad} sisteme kullanıcı olarak eklendi.\nŞifre: 12345")
        except Exception as e:
            self.sonuc.emit(False, str(e))

# =============================================================================
# PERSONEL LİSTESİ FORMU
# =============================================================================
class PersonelListesiPenceresi(QWidget):
    # DÜZELTME 1: Main.py uyumu için 'kullanici_adi' parametresi
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.setWindowTitle("Personel Listesi")
        self.resize(1200, 700)
        
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.ham_veri = []
        self.basliklar = []
        
        self._setup_ui()
        
        # 🟢 YETKİ KONTROLÜ (UI Kurulduktan Sonra)
        # Bu, statik butonları (btn_yeni vb.) gizler
        YetkiYoneticisi.uygula(self, "personel_listesi")
        
        self._sabitleri_yukle()
        self._verileri_yenile()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # ÜST BAR
        top_bar = QHBoxLayout()
        self.txt_ara = QLineEdit()
        self.txt_ara.setPlaceholderText("🔍 İsim, TC veya Birim ara...")
        self.txt_ara.setFixedHeight(40)
        self.txt_ara.setStyleSheet("QLineEdit { border: 1px solid #555; border-radius: 8px; padding-left: 15px; background-color: #2b2b2b; color: white; }")
        self.txt_ara.textChanged.connect(self._filtrele_tetikle)

        self.cmb_hizmet_filtre = QComboBox()
        self.cmb_hizmet_filtre.setPlaceholderText("Hizmet Sınıfı")
        self.cmb_hizmet_filtre.setFixedHeight(40)
        self.cmb_hizmet_filtre.setMinimumWidth(180)
        self.cmb_hizmet_filtre.currentIndexChanged.connect(self._filtrele_tetikle)

        self.chk_pasif_goster = QCheckBox("Eski Personelleri Göster")
        self.chk_pasif_goster.setStyleSheet("color: #ccc; font-weight: bold;")
        self.chk_pasif_goster.stateChanged.connect(self._filtrele_tetikle)

        # 🟢 BUTON İSİMLENDİRME (Yetki için)
        self.btn_yeni = QPushButton(" + Yeni Personel")
        self.btn_yeni.setObjectName("btn_yeni") # YetkiYoneticisi bunu kullanacak
        self.btn_yeni.setFixedHeight(40)
        self.btn_yeni.setStyleSheet("QPushButton { background-color: #28a745; color: white; border-radius: 6px; font-weight: bold; } QPushButton:hover { background-color: #218838; }")
        self.btn_yeni.clicked.connect(self._yeni_personel_ac)

        self.btn_yenile = QPushButton(" Yenile")
        self.btn_yenile.setObjectName("btn_yenile")
        self.btn_yenile.setFixedHeight(40)
        self.btn_yenile.setStyleSheet("QPushButton { background-color: #0067c0; color: white; border-radius: 6px; font-weight: bold; }")
        self.btn_yenile.clicked.connect(self._verileri_yenile)

        top_bar.addWidget(self.txt_ara, 1)
        top_bar.addWidget(self.cmb_hizmet_filtre)
        top_bar.addWidget(self.chk_pasif_goster) 
        top_bar.addWidget(self.btn_yeni)
        top_bar.addWidget(self.btn_yenile)
        main_layout.addLayout(top_bar)

        # TABLO
        self.table = QTableWidget()
        self.table.setColumnCount(7) 
        self.table.setHorizontalHeaderLabels(["TC Kimlik", "Ad Soyad", "Hizmet Sınıfı", "Ünvan", "Görev Yeri", "Cep Telefonu", "Durum"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.cellDoubleClicked.connect(self._detay_ac)
        
        # Sağ Tık Menüsü
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._sag_tik_menu)
        
        main_layout.addWidget(self.table)

        # FOOTER
        bottom_layout = QHBoxLayout()
        self.lbl_kayit_sayisi = QLabel("Toplam Kayıt: 0")
        self.progress = QProgressBar(); self.progress.setVisible(False)
        self.progress.setStyleSheet("QProgressBar { max-height: 4px; border: none; background: #333; } QProgressBar::chunk { background: #0078d4; }")
        bottom_layout.addWidget(self.lbl_kayit_sayisi)
        bottom_layout.addWidget(self.progress)
        main_layout.addLayout(bottom_layout)

    # --- SİNYALLER VE İŞLEMLER ---
    def _sag_tik_menu(self, position):
        menu = QMenu()
        menu.setStyleSheet("QMenu { background-color: #2d2d30; color: white; border: 1px solid #555; } QMenu::item:selected { background-color: #0078d4; }")
        
        secili_satir = self.table.currentRow()
        if secili_satir >= 0:
            item = self.table.item(secili_satir, 0)
            item_ad = self.table.item(secili_satir, 1)
            
            if item:
                tc_no = item.text()
                ad_soyad = item_ad.text()
                data = item.data(Qt.UserRole)
                durum = str(data[-1]).strip() if data and len(data) > 0 else "Aktif"
                
                # 🟢 YETKİ UYARLAMA: Action'ları 'self'e atıyoruz ki yönetici bulabilsin
                self.action_detay = QAction("📝 Detay Görüntüle", self)
                self.action_detay.setObjectName("action_detay") # İsimlendirme önemli
                self.action_detay.triggered.connect(lambda: self._detay_ac(secili_satir, 0))
                menu.addAction(self.action_detay)
                
                menu.addSeparator()

                self.action_user = QAction("🔑 Sisteme Kullanıcı Olarak Ekle", self)
                self.action_user.setObjectName("action_user")
                self.action_user.triggered.connect(lambda: self._kullanici_yap(tc_no, ad_soyad))
                menu.addAction(self.action_user)
                
                menu.addSeparator()
                
                self.action_sil = QAction("Durum Değiştir", self) # Geçici isim
                self.action_sil.setObjectName("action_sil")
                
                if durum == "Pasif":
                    self.action_sil.setText("♻️ Aktif Yap")
                    self.action_sil.triggered.connect(lambda: self._durum_degistir(tc_no, "Aktif"))
                else:
                    self.action_sil.setText("🗑️ Pasife Al")
                    self.action_sil.triggered.connect(lambda: self._durum_degistir(tc_no, "Pasif"))
                
                menu.addAction(self.action_sil)

                # 🟢 DİNAMİK YETKİ KONTROLÜ
                # Menü açılmadan hemen önce, bu yeni oluşturulan action'lar için kuralları uygula
                YetkiYoneticisi.uygula(self, "personel_listesi")

        menu.exec(self.table.viewport().mapToGlobal(position))

    def _kullanici_yap(self, tc, ad):
        roller = ["user", "admin", "viewer"]
        rol, ok = QInputDialog.getItem(self, "Yetki Seçimi", f"{ad} için yetki düzeyi seçiniz:", roller, 0, False)
        
        if ok and rol:
            if show_question("Onay", f"{ad} sisteme '{rol}' yetkisiyle eklenecek.\nVarsayılan Şifre: 12345\nOnaylıyor musunuz?", self):
                self.progress.setVisible(True)
                self.user_worker = KullaniciEkleWorker(tc, ad, rol)
                self.user_worker.sonuc.connect(self._kullanici_ekleme_bitti)
                self.user_worker.start()

    def _kullanici_ekleme_bitti(self, basari, mesaj):
        self.progress.setVisible(False)
        if basari: show_info("İşlem Başarılı", mesaj, self)
        else: show_error("Hata", mesaj, self)

    def _durum_degistir(self, tc, yeni_durum):
        if show_question("Onay", f"Personel durumu '{yeni_durum}' olarak değiştirilecek. Emin misiniz?", self):
            self.progress.setVisible(True); self.progress.setRange(0, 0)
            self.d_worker = DurumGuncelleWorker(tc, yeni_durum)
            self.d_worker.islem_tamam.connect(self._islem_tamamlandi)
            self.d_worker.hata_olustu.connect(lambda m: show_error(self, "Hata", m))
            self.d_worker.start()

    def _islem_tamamlandi(self):
        self.progress.setVisible(False)
        show_info("Başarılı", "Personel durumu güncellendi.", self)
        self._verileri_yenile()

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
        
        try: self.idx_durum = self.basliklar.index("Durum")
        except ValueError: self.idx_durum = -1
            
        self.ham_veri = veri_listesi[1:] 
        self._filtrele_tetikle()

    def _filtrele_tetikle(self):
        text = self.txt_ara.text().lower().strip()
        secilen_sinif = self.cmb_hizmet_filtre.currentText()
        pasifleri_goster = self.chk_pasif_goster.isChecked()
        
        if not secilen_sinif: secilen_sinif = "Tümü"
        
        filtrelenmis_veri = []
        
        for satir in self.ham_veri:
            satir_str = " ".join([str(x).lower() for x in satir])
            sinif_degeri = satir[4] if len(satir) > 4 else ""
            
            durum_degeri = "Aktif"
            if self.idx_durum != -1 and len(satir) > self.idx_durum:
                durum_degeri = str(satir[self.idx_durum]).strip()
            
            if not pasifleri_goster and durum_degeri == "Pasif":
                continue

            if (text in satir_str) and ((secilen_sinif == "Tümü") or (sinif_degeri == secilen_sinif)):
                filtrelenmis_veri.append(satir)
                
        self._tabloyu_doldur(filtrelenmis_veri)

    def _tabloyu_doldur(self, veri_seti):
        self.table.setRowCount(len(veri_seti))
        self.lbl_kayit_sayisi.setText(f"Görüntülenen Kayıt: {len(veri_seti)}")
        
        for i, row in enumerate(veri_seti):
            durum_val = row[self.idx_durum] if self.idx_durum != -1 and len(row) > self.idx_durum else "Aktif"
            
            # Gösterilecek Sütunlar
            gosterilecek = [0, 1, 4, 5, 6, 9]
            col_idx = 0
            for idx in gosterilecek:
                val = row[idx] if len(row) > idx else ""
                self.table.setItem(i, col_idx, QTableWidgetItem(str(val)))
                col_idx += 1
            
            # Durum Sütunu
            item_durum = QTableWidgetItem(str(durum_val))
            if durum_val == "Pasif": item_durum.setForeground(Qt.red)
            else: item_durum.setForeground(Qt.green)
            self.table.setItem(i, col_idx, item_durum)

            self.table.item(i, 0).setData(Qt.UserRole, row)
            
    def _detay_ac(self, row, column):
        item = self.table.item(row, 0)
        if item:
            personel_data = item.data(Qt.UserRole)
            self.detay_penceresi = PersonelDetayPenceresi(personel_data, self.yetki, self.kullanici_adi)
            self.detay_penceresi.veri_guncellendi.connect(self._verileri_yenile)
            mdi_pencere_ac(self, self.detay_penceresi, "Personel Detay Kartı")

    def _yeni_personel_ac(self):
        # Yetki ve kullanıcı adını ilet
        self.ekle_penceresi = PersonelEklePenceresi(self.yetki, self.kullanici_adi)
        mdi_pencere_ac(self, self.ekle_penceresi, "Yeni Personel Ekle")

    # 🟢 DÜZELTME 3: Çökme Önleyici Kapanış Olayı
    def closeEvent(self, event):
        worker_names = ['worker', 'sabit_worker', 'user_worker', 'd_worker']
        for name in worker_names:
            if hasattr(self, name):
                worker = getattr(self, name)
                if worker and worker.isRunning():
                    worker.quit()
                    worker.wait(500)
        event.accept()

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from temalar.tema import TemaYonetimi
    app = QApplication(sys.argv)
    TemaYonetimi.uygula_fusion_dark(app)
    win = PersonelListesiPenceresi()
    win.show()
    sys.exit(app.exec())