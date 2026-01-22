# -*- coding: utf-8 -*-
import sys
import os
import logging

# PySide6 Kütüphaneleri
from PySide6.QtCore import Qt, QDate, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFileDialog, QTabWidget, QProgressBar, QFrame,
    QComboBox, QCompleter, QMessageBox, QLineEdit, QDateEdit
)

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from araclar.yetki_yonetimi import YetkiYoneticisi

# --- MODÜLLER ---
try:
    from google_baglanti import veritabani_getir
    try:
        from google_baglanti import GoogleDriveService
    except ImportError:
        GoogleDriveService = None
        print("UYARI: GoogleDriveService bulunamadı.")

    from araclar.ortak_araclar import (
        pencereyi_kapat, show_info, show_error, 
        validate_required_fields, create_group_box, 
        create_form_layout, add_line_edit, add_combo_box, 
        add_date_edit, kayitlari_getir, satir_ekle
    )
except ImportError as e:
    print(f"KRİTİK HATA: Modüller yüklenemedi! {e}")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PersonelEkle")

# =============================================================================
# 1. BAŞLANGIÇ YÜKLEYİCİ (SABİTLER VE DRIVE ID'LERİ)
# =============================================================================
class BaslangicYukleyici(QThread):
    """
    1. Sabitler tablosundan ComboBox verilerini VE Drive Klasör ID'lerini çeker.
    2. Personel tablosundan Auto-Complete verilerini çeker.
    """
    veri_hazir = Signal(dict)
    
    def run(self):
        sonuc_dict = {
            'Drive_Klasor': {} # Drive ID'lerini saklayacağımız yer
        }
        try:
            # --- A. SABİTLER TABLOSU ---
            tum_sabitler = kayitlari_getir(veritabani_getir, 'sabit', 'Sabitler')
            
            if tum_sabitler:
                for satir in tum_sabitler:
                    kod = str(satir.get('Kod', '')).strip()
                    eleman = str(satir.get('MenuEleman', '')).strip()
                    # ID'ler 'Aciklama' sütununda tutuluyor
                    aciklama = str(satir.get('Aciklama', '')).strip() 

                    if kod and eleman:
                        # 1. Drive Klasör ID'lerini Ayıkla
                        if kod == "Drive_Klasor":
                            # Örn: Drive_Klasor -> Personel_Resim : ID_STR
                            sonuc_dict['Drive_Klasor'][eleman] = aciklama
                        
                        # 2. Diğer Sabitleri Listeye Ekle
                        else:
                            if kod not in sonuc_dict: sonuc_dict[kod] = []
                            sonuc_dict[kod].append(eleman)
            
            # --- B. PERSONEL AUTO-COMPLETE ---
            tum_personel = kayitlari_getir(veritabani_getir, 'personel', 'Personel')
            sehirler, okullar, bolumler = set(), set(), set()
            
            if tum_personel:
                for p in tum_personel:
                    if p.get('Dogum_Yeri'): sehirler.add(p.get('Dogum_Yeri').strip())
                    
                    if p.get('Mezun_Olunan_Okul'): okullar.add(p.get('Mezun_Olunan_Okul').strip())
                    if p.get('Mezun_Olunan_Okul_2'): okullar.add(p.get('Mezun_Olunan_Okul_2').strip())
                    
                    if p.get('Mezun_Olunan_Fakülte'): bolumler.add(p.get('Mezun_Olunan_Fakülte').strip())
                    if p.get('Mezun_Olunan_Fakülte_/_Bolüm_2'): bolumler.add(p.get('Mezun_Olunan_Fakülte_/_Bolüm_2').strip())

            # --- C. SIRALAMA VE DÜZENLEME ---
            for k in sonuc_dict:
                if isinstance(sonuc_dict[k], list): # Sadece listeleri sırala
                    sonuc_dict[k].sort()
                    sonuc_dict[k].insert(0, "Seçiniz...")
            
            sonuc_dict['Sehirler'] = sorted(list(sehirler))
            sonuc_dict['Okullar'] = sorted(list(okullar))
            sonuc_dict['Bolumler'] = sorted(list(bolumler))

        except Exception as e:
            logger.error(f"Başlangıç yükleme hatası: {e}")
        
        self.veri_hazir.emit(sonuc_dict)

# =============================================================================
# 2. KAYIT İŞÇİSİ
# =============================================================================
class KayitWorker(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)
    
    def __init__(self, veri_sozlugu, dosya_yollari, drive_ids):
        super().__init__()
        self.data = veri_sozlugu
        self.files = dosya_yollari
        self.drive_ids = drive_ids # Veritabanından gelen ID sözlüğü

    def run(self):
        try:
            drive_links = {"Resim": "", "Diploma1": "", "Diploma2": ""}
            tc_no = self.data.get('tc', '00000000000')
            
            # --- 1. DOSYA YÜKLEME ---
            if GoogleDriveService:
                drive = GoogleDriveService()
                
                # ID'leri sözlükten al (Sabitler tablosunda bu isimlerle kayıtlı olmalı)
                id_resim = self.drive_ids.get("Personel_Resim", "") 
                id_diploma = self.drive_ids.get("Personel_Diploma", "")

                for key, path in self.files.items():
                    if path and os.path.exists(path):
                        try:
                            # Hangi klasöre gidecek?
                            hedef_id = id_resim if key == "Resim" else id_diploma
                            
                            if hedef_id:
                                # Dosya Uzantısını Al
                                _, uzanti = os.path.splitext(path)
                                
                                # Yeni İsmi Belirle
                                if key == "Resim":
                                    yeni_isim = f"{tc_no}_profil_resim{uzanti}"
                                elif key == "Diploma1":
                                    yeni_isim = f"{tc_no}_diploma_1{uzanti}"
                                elif key == "Diploma2":
                                    yeni_isim = f"{tc_no}_diploma_2{uzanti}"
                                else:
                                    yeni_isim = os.path.basename(path)

                                # Yükleme
                                link = drive.upload_file(path, hedef_id, custom_name=yeni_isim)
                                
                                if link:
                                    drive_links[key] = link
                            else:
                                print(f"HATA: {key} için veritabanında klasör ID bulunamadı.")
                                
                        except Exception as e:
                            print(f"{key} yükleme hatası: {e}")
            
            # --- 2. VERİ HAZIRLAMA ---
            row = [
                self.data.get('tc', ''),
                self.data.get('ad_soyad', ''),
                self.data.get('dogum_yeri', ''),
                self.data.get('dogum_tarihi', ''),
                self.data.get('hizmet_sinifi', ''),
                self.data.get('kadro_unvani', ''),
                self.data.get('gorev_yeri', ''),
                self.data.get('sicil_no', ''),
                self.data.get('baslama_tarihi', ''),
                self.data.get('cep_tel', ''),
                self.data.get('eposta', ''),
                self.data.get('okul1', ''),
                self.data.get('fakulte1', ''),
                self.data.get('mezun_tarihi1', ''),
                self.data.get('diploma_no1', ''),
                self.data.get('okul2', ''),
                self.data.get('fakulte2', ''),
                self.data.get('mezun_tarihi2', ''),
                self.data.get('diploma_no2', ''),
                drive_links.get('Resim', ''),
                drive_links.get('Diploma1', ''),
                drive_links.get('Diploma2', '')
            ]

            # --- 3. KAYIT ---
            basari = satir_ekle(veritabani_getir, 'personel', 'Personel', row)
            
            if basari:
                self.islem_tamam.emit()
            else:
                raise Exception("Veritabanına kayıt sırasında hata oluştu.")

        except Exception as e:
            self.hata_olustu.emit(str(e))

# =============================================================================
# 3. ANA FORM
# =============================================================================
class PersonelEklePenceresi(QWidget):
    def __init__(self, yetki='viewer'): # Yetki alabilir hale getirin
        super().__init__()
        self.yetki = yetki
        self.setWindowTitle("Yeni Personel Ekle")
        self.resize(1200, 800)
        
        self.dosya_yollari = {"Resim": None, "Diploma1": None, "Diploma2": None}
        self.drive_config = {} # ID'ler burada saklanacak
        self.ui = {} 

        self._setup_ui()
        self._baslangic_yukle()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content_widget = QWidget()
        columns_layout = QHBoxLayout(content_widget)

        # SOL SÜTUN
        left_layout = QVBoxLayout()
        left_layout.setAlignment(Qt.AlignTop)

        grp_resim = create_group_box("Personel Fotoğrafı")
        v_resim = QVBoxLayout()
        v_resim.setAlignment(Qt.AlignCenter)
        self.lbl_resim_onizleme = QLabel("Fotoğraf Yok")
        self.lbl_resim_onizleme.setFixedSize(150, 170)
        self.lbl_resim_onizleme.setStyleSheet("border: 2px dashed #666; background: #333;")
        self.lbl_resim_onizleme.setScaledContents(True)
        btn_resim_sec = QPushButton("Fotoğraf Seç...")
        btn_resim_sec.clicked.connect(self._resim_sec)
        v_resim.addWidget(self.lbl_resim_onizleme)
        v_resim.addWidget(btn_resim_sec)
        grp_resim.setLayout(v_resim)
        left_layout.addWidget(grp_resim)

        grp_kimlik = create_group_box("Kimlik Bilgileri")
        form_kimlik = create_form_layout()
        self.ui['tc'] = add_line_edit(form_kimlik, "TC Kimlik No:", max_length=11, only_int=True)
        self.ui['ad_soyad'] = add_line_edit(form_kimlik, "Adı Soyadı:")
        self.ui['dogum_yeri'] = self._create_editable_combo(form_kimlik, "Doğum Yeri:")
        self.ui['dogum_tarihi'] = add_date_edit(form_kimlik, "Doğum Tarihi:")
        grp_kimlik.setLayout(form_kimlik)
        left_layout.addWidget(grp_kimlik)

        grp_iletisim = create_group_box("İletişim Bilgileri")
        form_iletisim = create_form_layout()
        self.ui['cep_tel'] = add_line_edit(form_iletisim, "Cep Telefonu:", placeholder="05XX...", max_length=11, only_int=True)
        self.ui['eposta'] = add_line_edit(form_iletisim, "E-Posta Adresi:")
        grp_iletisim.setLayout(form_iletisim)
        left_layout.addWidget(grp_iletisim)
        columns_layout.addLayout(left_layout, 1)

        # SAĞ SÜTUN
        right_layout = QVBoxLayout()
        right_layout.setAlignment(Qt.AlignTop)

        grp_kadro = create_group_box("Kadro ve Kurumsal Bilgiler")
        form_kadro = create_form_layout()
        self.ui['hizmet_sinifi'] = add_combo_box(form_kadro, "Hizmet Sınıfı:", items=["Yükleniyor..."])
        self.ui['kadro_unvani'] = add_combo_box(form_kadro, "Kadro Ünvanı:", items=["Yükleniyor..."])
        self.ui['gorev_yeri'] = add_combo_box(form_kadro, "Görev Yeri:", items=["Yükleniyor..."])
        self.ui['sicil_no'] = add_line_edit(form_kadro, "Kurum Sicil No:")
        self.ui['baslama_tarihi'] = add_date_edit(form_kadro, "Başlama Tarihi:", default_date=QDate.currentDate())
        grp_kadro.setLayout(form_kadro)
        right_layout.addWidget(grp_kadro)

        grp_egitim = create_group_box("Eğitim Bilgileri")
        v_egitim = QVBoxLayout()
        tab_widget = QTabWidget()
        
        # Tab 1
        page1 = QWidget()
        f1 = create_form_layout()
        self.ui['okul1'] = self._create_editable_combo(f1, "Okul:")
        self.ui['fakulte1'] = self._create_editable_combo(f1, "Bölüm/Fakülte:")
        self.ui['mezun_tarihi1'] = add_date_edit(f1, "Tarih:")
        self.ui['diploma_no1'] = add_line_edit(f1, "Dip No:")
        h_d1 = QHBoxLayout()
        self.btn_dip1 = QPushButton("Diploma 1 Yükle...")
        self.btn_dip1.clicked.connect(lambda: self._dosya_sec("Diploma1", self.btn_dip1))
        h_d1.addWidget(self.btn_dip1); f1.addRow("Dosya:", h_d1)
        page1.setLayout(f1); tab_widget.addTab(page1, "1. Üni")

        # Tab 2
        page2 = QWidget()
        f2 = create_form_layout()
        self.ui['okul2'] = self._create_editable_combo(f2, "Okul:")
        self.ui['fakulte2'] = self._create_editable_combo(f2, "Bölüm/Fakülte:")
        self.ui['mezun_tarihi2'] = add_date_edit(f2, "Tarih:")
        self.ui['diploma_no2'] = add_line_edit(f2, "Dip No:")
        h_d2 = QHBoxLayout()
        self.btn_dip2 = QPushButton("Diploma 2 Yükle...")
        self.btn_dip2.clicked.connect(lambda: self._dosya_sec("Diploma2", self.btn_dip2))
        h_d2.addWidget(self.btn_dip2); f2.addRow("Dosya:", h_d2)
        page2.setLayout(f2); tab_widget.addTab(page2, "2. Üni")
        
        v_egitim.addWidget(tab_widget)
        grp_egitim.setLayout(v_egitim)
        right_layout.addWidget(grp_egitim)
        
        columns_layout.addLayout(right_layout, 2)
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        footer = QHBoxLayout()
        self.progress = QProgressBar(); self.progress.setVisible(False)
        btn_iptal = QPushButton("İptal"); btn_iptal.clicked.connect(lambda: pencereyi_kapat(self))
        self.btn_kaydet = QPushButton("Personel Kaydet"); self.btn_kaydet.clicked.connect(self._kaydet_baslat)
        footer.addWidget(self.progress); footer.addStretch()
        footer.addWidget(btn_iptal); footer.addWidget(self.btn_kaydet)
        main_layout.addLayout(footer)
        YetkiYoneticisi.uygula(self, "personel_ekle")
        
    def _create_editable_combo(self, layout, label):
        combo = add_combo_box(layout, label, items=[])
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.completer().setCompletionMode(QCompleter.PopupCompletion)
        return combo

    def _baslangic_yukle(self):
        self.loader = BaslangicYukleyici()
        self.loader.veri_hazir.connect(self._verileri_doldur)
        self.loader.start()

    def _verileri_doldur(self, veriler):
        self.ui['hizmet_sinifi'].clear(); self.ui['hizmet_sinifi'].addItems(veriler.get('Hizmet_Sinifi', []))
        self.ui['kadro_unvani'].clear(); self.ui['kadro_unvani'].addItems(veriler.get('Kadro_Unvani', []))
        self.ui['gorev_yeri'].clear(); self.ui['gorev_yeri'].addItems(veriler.get('Gorev_Yeri', []))
        
        for field, key in [('dogum_yeri', 'Sehirler'), ('okul1', 'Okullar'), ('okul2', 'Okullar'), 
                           ('fakulte1', 'Bolumler'), ('fakulte2', 'Bolumler')]:
            self.ui[field].clear()
            self.ui[field].addItems(veriler.get(key, []))
            self.ui[field].setPlaceholderText("Seçiniz veya yazınız...")
            self.ui[field].setCurrentIndex(-1)

        # ID'leri çek ve sakla
        self.drive_config = veriler.get('Drive_Klasor', {})
        if not self.drive_config:
            print("UYARI: Drive ID'leri gelmedi. Sabitler tablosunu kontrol edin.")

    def _resim_sec(self):
        d, _ = QFileDialog.getOpenFileName(self, "Seç", "", "Resim (*.jpg *.png)")
        if d: self.dosya_yollari["Resim"] = d; self.lbl_resim_onizleme.setPixmap(QPixmap(d))

    def _dosya_sec(self, key, btn):
        d, _ = QFileDialog.getOpenFileName(self, "Seç", "", "Dosya (*.pdf *.jpg)")
        if d: self.dosya_yollari[key] = d; btn.setText("Seçildi")

    def _kaydet_baslat(self):
        if not validate_required_fields([self.ui['tc'], self.ui['ad_soyad']]):
            return

        self.btn_kaydet.setEnabled(False)
        self.btn_kaydet.setText("Kaydediliyor...")
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        
        # Verileri topla
        data = {}
        for k, v in self.ui.items():
            if isinstance(v, QComboBox):
                data[k] = v.currentText()
            elif isinstance(v, QDateEdit):
                data[k] = v.date().toString("dd.MM.yyyy")
            elif isinstance(v, QLineEdit):
                data[k] = v.text()
            else:
                data[k] = ""

        # DÜZELTİLDİ: drive_config parametresi eklendi
        self.worker = KayitWorker(data, self.dosya_yollari, self.drive_config)
        self.worker.islem_tamam.connect(self._on_success)
        self.worker.hata_olustu.connect(self._on_error)
        self.worker.start()

    def _on_success(self):
        self.progress.setRange(0, 100); self.progress.setValue(100)
        self.btn_kaydet.setText("Personel Kaydet")
        self.btn_kaydet.setEnabled(True)
        show_info("Başarılı", "Personel kaydı oluşturuldu.", self)
        pencereyi_kapat(self)

    def _on_error(self, err):
        self.progress.setVisible(False)
        self.btn_kaydet.setEnabled(True)
        self.btn_kaydet.setText("Personel Kaydet")
        show_error("Kayıt Hatası", err, self)

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from temalar.tema import TemaYonetimi
    app = QApplication(sys.argv)
    TemaYonetimi.uygula_fusion_dark(app)
    win = PersonelEklePenceresi()
    win.show()
    sys.exit(app.exec())