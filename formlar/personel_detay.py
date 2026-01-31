# -*- coding: utf-8 -*-
import sys
import os
import logging
from PySide6.QtCore import Qt, QDate, QThread, Signal, QUrl
from PySide6.QtGui import QPixmap, QDesktopServices, QIntValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFileDialog, QTabWidget, QProgressBar, QFrame,
    QComboBox, QLineEdit, QDateEdit, QFormLayout, QApplication, 
    QGroupBox, QMessageBox, QGridLayout
)

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# --- MODÜLLER ---
try:
    from araclar.yetki_yonetimi import YetkiYoneticisi
    from araclar.ortak_araclar import OrtakAraclar, show_info, show_error, show_question
    from temalar.tema import TemaYonetimi
    from services.personel_service import PersonelService
    from araclar.validators import Validator
    from PIL import Image
    import urllib.request
except ImportError as e:
    print(f"Modül Hatası: {e}")
    PersonelService = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PersonelDetay")

# =============================================================================
# WORKER: DETAY GÜNCELLEME
# =============================================================================
class GuncelleWorker(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)
    
    def __init__(self, service, tc, veri, dosyalar, linkler, kullanici):
        super().__init__()
        self.service = service
        self.tc = tc
        self.veri = veri
        self.dosyalar = dosyalar
        self.linkler = linkler
        self.kullanici = kullanici

    def run(self):
        try:
            # 1. Resim İşleme (Varsa)
            if self.dosyalar.get("Resim") and os.path.exists(self.dosyalar["Resim"]):
                try:
                    img = Image.open(self.dosyalar["Resim"])
                    if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                    temp_path = os.path.join(current_dir, f"temp_{self.tc}.jpg")
                    img.save(temp_path, "JPEG", quality=90)
                    self.dosyalar["Resim"] = temp_path
                except: pass

            # 2. Service Üzerinden Güncelleme
            # NOT: Service katmanında 'personel_guncelle' metodu olmalı.
            # Şimdilik repo.update mantığı simüle ediliyor.
            basari = self.service.repo.update(self.tc, self.veri)
            
            # TODO: Link güncelleme ve dosya yükleme işlemleri Service katmanına taşınmalı.
            
            if basari: self.islem_tamam.emit()
            else: self.hata_olustu.emit("Güncelleme başarısız.")
            
        except Exception as e:
            self.hata_olustu.emit(str(e))

# =============================================================================
# WORKER: SABİT VERİLERİ YÜKLE
# =============================================================================
class VeriYukleyici(QThread):
    veri_hazir = Signal(dict)
    def __init__(self, service): super().__init__(); self.service = service
    def run(self):
        d = {}
        try:
            if self.service:
                d['Hizmet_Sinifi'] = self.service.sabit_degerleri_getir('Hizmet_Sinifi')
                d['Kadro_Unvani'] = self.service.sabit_degerleri_getir('Kadro_Unvani')
                d['Gorev_Yeri'] = self.service.sabit_degerleri_getir('Gorev_Yeri')
                d['Sehirler'] = self.service.benzersiz_degerleri_getir('Dogum_Yeri')
                d['Okullar'] = self.service.benzersiz_degerleri_getir('Mezun_Olunan_Okul')
                d['Bolumler'] = self.service.benzersiz_degerleri_getir('Mezun_Olunan_Fakülte')
        except: pass
        self.veri_hazir.emit(d)

# =============================================================================
# ANA FORM
# =============================================================================
class PersonelDetayPenceresi(QWidget):
    veri_guncellendi = Signal() # Liste ekranını yenilemek için

    def __init__(self, personel_data_row, yetki='viewer', kullanici_adi="Sistem"):
        super().__init__()
        self.p_data = personel_data_row # Liste'den gelen ham veri
        self.tc = str(self.p_data[0])
        self.ad_soyad = str(self.p_data[1])
        
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        self.service = PersonelService()
        
        self.duzenleme_modu = False
        self.dosya_yollari = {"Resim": None, "Diploma1": None, "Diploma2": None}
        self.ui = {}
        
        # Linkler (Sütun indekslerine dikkat! Listeden gelen sıraya göre)
        try:
            self.linkler = {
                "Resim": self.p_data[19] if len(self.p_data)>19 else "",
                "Diploma1": self.p_data[20] if len(self.p_data)>20 else "",
                "Diploma2": self.p_data[21] if len(self.p_data)>21 else "",
                "Ozluk": self.p_data[22] if len(self.p_data)>22 else ""
            }
        except: self.linkler = {}

        self.setWindowTitle(f"Personel Detay: {self.ad_soyad}")
        self.resize(1100, 800)
        
        self._setup_ui()
        self._baslangic_yukle()
        self._verileri_doldur() # Formu doldur
        self._mod_ayarla(False) # Başlangıçta salt okunur
        
        try: YetkiYoneticisi.uygula(self, "personel_detay")
        except: pass

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        
        # --- ÜST BAR (Başlık ve Butonlar) ---
        top_bar = QHBoxLayout()
        self.lbl_baslik = QLabel(f"👤 {self.ad_soyad}")
        self.lbl_baslik.setStyleSheet("font-size: 20px; font-weight: bold; color: #4dabf7;")
        
        self.btn_duzenle = QPushButton("✏️ Düzenle")
        self.btn_duzenle.clicked.connect(lambda: self._mod_ayarla(True))
        
        self.btn_kaydet = QPushButton("💾 Kaydet")
        self.btn_kaydet.clicked.connect(self._kaydet)
        self.btn_kaydet.setStyleSheet("background-color: #2e7d32; color: white;")
        
        self.btn_iptal = QPushButton("❌ İptal")
        self.btn_iptal.clicked.connect(lambda: self._mod_ayarla(False))
        self.btn_iptal.setStyleSheet("background-color: #c62828; color: white;")
        
        top_bar.addWidget(self.lbl_baslik)
        top_bar.addStretch()
        top_bar.addWidget(self.btn_duzenle)
        top_bar.addWidget(self.btn_kaydet)
        top_bar.addWidget(self.btn_iptal)
        main_layout.addLayout(top_bar)

        # --- SEKME YAPISI ---
        self.tabs = QTabWidget()
        
        # TAB 1: KİMLİK & KURUMSAL
        self.tab_bilgi = QWidget()
        self._setup_bilgi_tab(self.tab_bilgi)
        self.tabs.addTab(self.tab_bilgi, "📋 Personel Bilgileri")
        
        # TAB 2: İZİN DURUMU
        self.tab_izin = QWidget()
        self._setup_izin_tab(self.tab_izin)
        self.tabs.addTab(self.tab_izin, "🏖️ İzin Durumu")
        
        main_layout.addWidget(self.tabs)
        
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        main_layout.addWidget(self.progress)

    def _setup_bilgi_tab(self, parent):
        layout = QVBoxLayout(parent)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        content = QWidget()
        c_layout = QVBoxLayout(content)
        c_layout.setSpacing(20)
        
        # --- BÖLÜM 1: ÜST (FOTO | KİMLİK | İLETİŞİM) ---
        top_box = QWidget()
        top_lay = QHBoxLayout(top_box)
        top_lay.setContentsMargins(0,0,0,0)
        
        # Fotoğraf
        grp_foto = QGroupBox("Fotoğraf")
        v_foto = QVBoxLayout(grp_foto); v_foto.setAlignment(Qt.AlignCenter)
        self.lbl_resim = QLabel("Yükleniyor...")
        self.lbl_resim.setFixedSize(130, 150)
        self.lbl_resim.setScaledContents(True)
        self.lbl_resim.setStyleSheet("border: 2px dashed #555;")
        self.btn_resim = QPushButton("Değiştir"); self.btn_resim.clicked.connect(lambda: self._dosya_sec("Resim"))
        v_foto.addWidget(self.lbl_resim); v_foto.addWidget(self.btn_resim)
        
        # Kimlik
        grp_kimlik = QGroupBox("Kimlik Bilgileri")
        f_kimlik = QFormLayout(grp_kimlik)
        self.ui['tc'] = QLineEdit(); self.ui['tc'].setReadOnly(True) # TC Değişemez
        self.ui['ad_soyad'] = QLineEdit()
        self.ui['dogum_yeri'] = self._create_combo(True)
        self.ui['dogum_tarihi'] = QDateEdit(); self.ui['dogum_tarihi'].setDisplayFormat("dd.MM.yyyy")
        f_kimlik.addRow("TC Kimlik:", self.ui['tc'])
        f_kimlik.addRow("Ad Soyad:", self.ui['ad_soyad'])
        f_kimlik.addRow("Doğum Yeri:", self.ui['dogum_yeri'])
        f_kimlik.addRow("Doğum Tar:", self.ui['dogum_tarihi'])
        
        # İletişim
        grp_iletisim = QGroupBox("İletişim")
        f_iletisim = QFormLayout(grp_iletisim)
        self.ui['cep_tel'] = QLineEdit()
        self.ui['eposta'] = QLineEdit()
        f_iletisim.addRow("Cep Tel:", self.ui['cep_tel'])
        f_iletisim.addRow("E-Posta:", self.ui['eposta'])
        
        top_lay.addWidget(grp_foto)
        top_lay.addWidget(grp_kimlik, stretch=1)
        top_lay.addWidget(grp_iletisim, stretch=1)
        c_layout.addWidget(top_box)
        
        # --- BÖLÜM 2: KURUMSAL (50:50 BÖLÜNMÜŞ) ---
        grp_kurum = QGroupBox("Kurumsal Bilgiler")
        
        # Ana yatay layout
        h_kurum = QHBoxLayout(grp_kurum)
        h_kurum.setSpacing(20) # İki sütun arası boşluk
        h_kurum.setContentsMargins(15, 25, 15, 15)

        # 1. SOL SÜTUN KONTEYNERİ (Sol %50)
        left_container = QWidget()
        v_k1 = QFormLayout(left_container) # Form layout container'ın içinde
        v_k1.setContentsMargins(0, 0, 0, 0)
        
        self.ui['hizmet_sinifi'] = self._create_combo()
        self.ui['kadro_unvani'] = self._create_combo()
        self.ui['gorev_yeri'] = self._create_combo()
        
        v_k1.addRow("Hizmet Sınıfı:", self.ui['hizmet_sinifi'])
        v_k1.addRow("Kadro Ünvanı:", self.ui['kadro_unvani'])
        v_k1.addRow("Görev Yeri:", self.ui['gorev_yeri'])

        # 2. SAĞ SÜTUN KONTEYNERİ (Sağ %50)
        right_container = QWidget()
        v_k2 = QFormLayout(right_container)
        v_k2.setContentsMargins(0, 0, 0, 0)

        self.ui['sicil_no'] = QLineEdit()
        self.ui['baslama_tarihi'] = QDateEdit()
        self.ui['baslama_tarihi'].setDisplayFormat("dd.MM.yyyy")
       
        v_k2.addRow("Sicil No:", self.ui['sicil_no'])
        v_k2.addRow("Başlama Tar:", self.ui['baslama_tarihi'])
        

        # 3. LAYOUTA EKLEME (STRETCH = 1 ile eşit paylaşım)
        h_kurum.addWidget(left_container, 1) # Stretch 1
        h_kurum.addWidget(right_container, 1) # Stretch 1
        
        c_layout.addWidget(grp_kurum)
        
        # --- BÖLÜM 3: EĞİTİM ---
        grp_egitim = QGroupBox("Eğitim Bilgileri")
        h_egitim = QHBoxLayout(grp_egitim)
        
        # Okul 1
        v_e1 = QFormLayout()
        self.ui['okul1'] = self._create_combo(True)
        self.ui['fakulte1'] = self._create_combo(True)
        self.ui['mezun_tarihi1'] = QLineEdit()
        self.ui['diploma_no1'] = QLineEdit()
        self.btn_dip1_gor = QPushButton("👁️"); self.btn_dip1_gor.clicked.connect(lambda: self._dosya_ac("Diploma1"))
        self.btn_dip1_yuk = QPushButton("📤"); self.btn_dip1_yuk.clicked.connect(lambda: self._dosya_sec("Diploma1"))
        
        h_btns1 = QHBoxLayout(); h_btns1.addWidget(self.btn_dip1_gor); h_btns1.addWidget(self.btn_dip1_yuk)
        v_e1.addRow(QLabel("<b>1. Okul</b>"))
        v_e1.addRow("Okul:", self.ui['okul1'])
        v_e1.addRow("Bölüm:", self.ui['fakulte1'])
        v_e1.addRow("Dip. No:", self.ui['diploma_no1'])
        v_e1.addRow("Dosya:", h_btns1)
        
        # Okul 2
        v_e2 = QFormLayout()
        self.ui['okul2'] = self._create_combo(True)
        self.ui['fakulte2'] = self._create_combo(True)
        self.ui['mezun_tarihi2'] = QLineEdit()
        self.ui['diploma_no2'] = QLineEdit()
        self.btn_dip2_gor = QPushButton("👁️"); self.btn_dip2_gor.clicked.connect(lambda: self._dosya_ac("Diploma2"))
        self.btn_dip2_yuk = QPushButton("📤"); self.btn_dip2_yuk.clicked.connect(lambda: self._dosya_sec("Diploma2"))
        
        h_btns2 = QHBoxLayout(); h_btns2.addWidget(self.btn_dip2_gor); h_btns2.addWidget(self.btn_dip2_yuk)
        v_e2.addRow(QLabel("<b>2. Okul</b>"))
        v_e2.addRow("Okul:", self.ui['okul2'])
        v_e2.addRow("Bölüm:", self.ui['fakulte2'])
        v_e2.addRow("Dip. No:", self.ui['diploma_no2'])
        v_e2.addRow("Dosya:", h_btns2)
        
        h_egitim.addLayout(v_e1); h_egitim.addLayout(v_e2)
        c_layout.addWidget(grp_egitim)
        
        scroll.setWidget(content)
        layout.addWidget(scroll)

    def _setup_izin_tab(self, parent):
        l = QVBoxLayout(parent)
        self.lbl_izin_info = QLabel("İzin bilgileri yükleniyor...")
        self.lbl_izin_info.setAlignment(Qt.AlignCenter)
        l.addWidget(self.lbl_izin_info)

    # --- FONKSİYONLAR ---
    def _create_combo(self, editable=False):
        c = QComboBox()
        c.setEditable(editable)
        return c

    def _mod_ayarla(self, duzenleme_aktif):
        self.duzenleme_modu = duzenleme_aktif
        self.btn_duzenle.setVisible(not duzenleme_aktif)
        self.btn_kaydet.setVisible(duzenleme_aktif)
        self.btn_iptal.setVisible(duzenleme_aktif)
        self.btn_resim.setVisible(duzenleme_aktif)
        self.btn_dip1_yuk.setVisible(duzenleme_aktif)
        self.btn_dip2_yuk.setVisible(duzenleme_aktif)
        
        # Alanları kilitle/aç
        # Not: findChildren tuple desteklemediği için manuel döngü
        all_widgets = self.findChildren(QWidget)
        for w in all_widgets:
            if isinstance(w, (QLineEdit, QComboBox, QDateEdit)):
                if w == self.ui['tc']: continue 
                w.setEnabled(duzenleme_aktif)
                if isinstance(w, QLineEdit): w.setReadOnly(not duzenleme_aktif)

    def _baslangic_yukle(self):
        self.loader = VeriYukleyici(self.service)
        self.loader.veri_hazir.connect(self._sabitler_yuklendi)
        self.loader.start()
        
        if self.linkler.get("Resim"):
            self._resim_indir(self.linkler["Resim"])

    def _sabitler_yuklendi(self, d):
        self.ui['hizmet_sinifi'].addItems(d.get('Hizmet_Sinifi', []))
        self.ui['kadro_unvani'].addItems(d.get('Kadro_Unvani', []))
        self.ui['gorev_yeri'].addItems(d.get('Gorev_Yeri', []))
        # ... diğerleri

    def _verileri_doldur(self):
        # Listeden gelen veriyi UI'ya dağıt
        try:
            self.ui['tc'].setText(str(self.p_data[0]))
            self.ui['ad_soyad'].setText(str(self.p_data[1]))
            self.ui['dogum_yeri'].setCurrentText(str(self.p_data[2]))
            # self.ui['dogum_tarihi'].setDate(...) # Tarih formatı dönüşümü gerekebilir
            self.ui['hizmet_sinifi'].setCurrentText(str(self.p_data[4]))
            self.ui['kadro_unvani'].setCurrentText(str(self.p_data[5]))
            self.ui['gorev_yeri'].setCurrentText(str(self.p_data[6]))
            self.ui['sicil_no'].setText(str(self.p_data[7]))
            # Baslama tarihi p_data[8]
            self.ui['cep_tel'].setText(str(self.p_data[9]))
            # Durum p_data[23] civarı olabilir, kontrol edilmeli
        except Exception as e: print(f"Veri doldurma hatası: {e}")

    def _resim_indir(self, url):
        pass # Worker ile indirilmeli

    def _dosya_sec(self, tip):
        p, _ = QFileDialog.getOpenFileName(self, "Seç", "", "Dosya (*.jpg *.pdf)")
        if p:
            self.dosya_yollari[tip] = p
            if tip == "Resim": 
                self.lbl_resim.setPixmap(QPixmap(p).scaled(130, 150))

    def _dosya_ac(self, tip):
        url = self.linkler.get(tip)
        if url: QDesktopServices.openUrl(QUrl(url))
        else: show_info("Bilgi", "Dosya bulunamadı.", self)

    def _kaydet(self):
        veri = {
            'Ad_Soyad': self.ui['ad_soyad'].text(),
            'Cep_Telefonu': self.ui['cep_tel'].text(),
            # ... diğer tüm alanlar
        }
        
        self.worker = GuncelleWorker(self.service, self.tc, veri, self.dosya_yollari, self.linkler, self.kullanici_adi)
        self.worker.islem_tamam.connect(self._kayit_basarili)
        self.worker.hata_olustu.connect(lambda e: show_error("Hata", e, self))
        self.worker.start()
        self.progress.setVisible(True)
        self.btn_kaydet.setEnabled(False)

    def _kayit_basarili(self):
        self.progress.setVisible(False)
        self.btn_kaydet.setEnabled(True)
        show_info("Başarılı", "Güncelleme tamamlandı.", self)
        self._mod_ayarla(False)
        self.veri_guncellendi.emit()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    try: TemaYonetimi.uygula_fusion_dark(app)
    except: pass
    win = PersonelDetayPenceresi(["Test Personel"]*30)
    win.show()
    sys.exit(app.exec())