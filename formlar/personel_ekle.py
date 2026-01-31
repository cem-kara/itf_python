# -*- coding: utf-8 -*-
import logging
import os
import sys
import traceback
from typing import Optional

# PySide6 Kütüphaneleri
from PySide6.QtCore import Qt, QDate, QThread, Signal, QRegularExpression
from PySide6.QtGui import QPixmap, QIntValidator, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFileDialog, QProgressBar, QFrame,
    QComboBox, QCompleter, QLineEdit, QDateEdit, 
    QApplication, QGroupBox, QMessageBox, QFormLayout
)

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# --- PROJE MODÜLLERİ ---
try:
    from araclar.log_yonetimi import LogYoneticisi
    from araclar.yetki_yonetimi import YetkiYoneticisi
    from araclar.ortak_araclar import (
        OrtakAraclar, pencereyi_kapat, show_info, show_error
    )
    from temalar.tema import TemaYonetimi 
    from araclar.rapor_yoneticisi import RaporYoneticisi 
    from services.personel_service import PersonelService
    
    # Validator Modülü
    try:
        from araclar.validators import Validator
    except ImportError:
        class Validator:
            @staticmethod
            def validate_tc(x): return len(str(x))==11, "TC 11 hane olmalı"
            @staticmethod
            def validate_phone(x): return True, ""
            @staticmethod
            def validate_email(x): return True, ""

    from PIL import Image
    
except ImportError as e:
    print(f"KRİTİK HATA: Modüller yüklenemedi! {e}")
    PersonelService = None
    Image = None
    Validator = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PersonelEkle")

# =============================================================================
# 1. BAŞLANGIÇ YÜKLEYİCİ
# =============================================================================
class BaslangicYukleyici(QThread):
    veri_hazir = Signal(dict)
    def __init__(self, service):
        super().__init__()
        self.service = service

    def run(self):
        sonuc_dict = {}
        try:
            if not self.service: return
            sonuc_dict['Hizmet_Sinifi'] = self.service.sabit_degerleri_getir('Hizmet_Sinifi')
            sonuc_dict['Kadro_Unvani'] = self.service.sabit_degerleri_getir('Kadro_Unvani')
            sonuc_dict['Gorev_Yeri'] = self.service.sabit_degerleri_getir('Gorev_Yeri')
            sonuc_dict['Sehirler'] = self.service.benzersiz_degerleri_getir('Dogum_Yeri')
            sonuc_dict['Okullar'] = self.service.benzersiz_degerleri_getir('Mezun_Olunan_Okul')
            sonuc_dict['Bolumler'] = self.service.benzersiz_degerleri_getir('Mezun_Olunan_Fakülte')
        except Exception: pass
        self.veri_hazir.emit(sonuc_dict)

# =============================================================================
# 2. KAYIT İŞÇİSİ
# =============================================================================
class KayitWorker(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)
    
    def __init__(self, service, veri_sozlugu, dosya_yollari, kullanici_adi):
        super().__init__()
        self.service = service
        self.data = veri_sozlugu
        self.files = dosya_yollari
        self.kullanici_adi = kullanici_adi

    def run(self):
        temp_files = [] 
        try:
            # Resim İşleme
            if self.files.get("Resim") and Image:
                try:
                    orj_yol = self.files["Resim"]
                    if os.path.exists(orj_yol):
                        img = Image.open(orj_yol)
                        if img.mode in ("RGBA", "P", "CMYK"): img = img.convert("RGB")
                        tc_no = self.data.get('Kimlik_No', 'temp')
                        temp_resim_path = os.path.join(current_dir, f"temp_resim_{tc_no}.jpg")
                        img.save(temp_resim_path, "JPEG", quality=90)
                        self.files["Resim"] = temp_resim_path
                        temp_files.append(temp_resim_path)
                except Exception as e: logger.warning(f"Resim hatası: {e}")

            # Word Oluşturma
            try:
                sablon_klasoru = os.path.join(root_dir, "sablonlar")
                rapor_araci = RaporYoneticisi(sablon_klasoru)
                context = {k: v for k, v in self.data.items()}
                context['Olusturma_Tarihi'] = QDate.currentDate().toString("dd.MM.yyyy")
                resimler = {}
                if self.files.get("Resim") and os.path.exists(self.files["Resim"]):
                    resimler['Resim'] = os.path.abspath(self.files["Resim"])
                
                tc_no = self.data.get('Kimlik_No', '000')
                word_path = os.path.join(current_dir, f"{tc_no}_ozluk.docx")
                
                if rapor_araci.word_olustur("personel_ozluk_sablon.docx", context, word_path, resimler):
                    self.files['Ozluk_Dosyasi'] = word_path
                    temp_files.append(word_path)
            except Exception as e: logger.error(f"Word hatası: {e}")

            # Servis Kaydı
            basari, mesaj = self.service.personel_ekle(self.data, self.files, self.kullanici_adi)
            if basari: self.islem_tamam.emit()
            else: self.hata_olustu.emit(mesaj)
        
        except Exception as e:
            self.hata_olustu.emit(f"Kritik Hata: {str(e)}")
        finally:
            for path in temp_files:
                if os.path.exists(path):
                    try: os.remove(path)
                    except: pass

# =============================================================================
# 3. ANA FORM
# =============================================================================
class PersonelEklePenceresi(QWidget):
    def __init__(self, yetki='viewer', kullanici_adi="Sistem"): 
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi 
        
        self.service = PersonelService()
        self.dosya_yollari = {"Resim": None, "Diploma1": None, "Diploma2": None}
        self.ui = {} 

        self.setWindowTitle("Yeni Personel Ekle")
        self.resize(1200, 850)

        self._setup_ui()
        
        try: YetkiYoneticisi.uygula(self, "personel_ekle")
        except: pass
            
        self._baslangic_yukle()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(25)

        # ==========================================================
        # 1. BÖLÜM: ÜST ALAN (FOTO | KİMLİK | İLETİŞİM)
        # ==========================================================
        top_container = QWidget()
        top_layout = QHBoxLayout(top_container)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(20)

        # --- A. FOTOĞRAF (SOL) ---
        photo_grp = QGroupBox("Fotoğraf")
        photo_lay = QVBoxLayout(photo_grp)
        photo_lay.setAlignment(Qt.AlignCenter)
        
        self.lbl_resim_onizleme = QLabel("Fotoğraf\nYüklenmedi")
        self.lbl_resim_onizleme.setFixedSize(130, 150)
        self.lbl_resim_onizleme.setStyleSheet("border: 2px dashed #666; border-radius: 8px; color: #888;")
        self.lbl_resim_onizleme.setAlignment(Qt.AlignCenter)
        self.lbl_resim_onizleme.setScaledContents(True)
        
        btn_resim = QPushButton("Fotoğraf Seç")
        btn_resim.setCursor(Qt.PointingHandCursor)
        btn_resim.clicked.connect(self._resim_sec)
        
        photo_lay.addWidget(self.lbl_resim_onizleme)
        photo_lay.addWidget(btn_resim)
        
        # --- B. KİMLİK BİLGİLERİ (ORTA) ---
        id_grp = QGroupBox("Kimlik Bilgileri")
        id_lay = QVBoxLayout(id_grp)
        id_lay.setSpacing(15)
        id_lay.setContentsMargins(15, 25, 15, 15)

        # Satır 1: TC ve Ad Soyad
        row_id_1 = QHBoxLayout()
        self.ui['tc'] = QLineEdit()
        self.ui['tc'].setMaxLength(11)
        # DÜZELTME: QIntValidator yerine Regex Validator (Sadece rakam, sınır yok)
        self.ui['tc'].setValidator(QRegularExpressionValidator(QRegularExpression("[0-9]*"))) 
        
        self.ui['ad_soyad'] = QLineEdit()
        
        self._add_v_field(row_id_1, "TC Kimlik No (*)", self.ui['tc'])
        self._add_v_field(row_id_1, "Ad Soyad (*)", self.ui['ad_soyad'])
        id_lay.addLayout(row_id_1)

        # Satır 2: Doğum Yeri ve Tarihi
        row_id_2 = QHBoxLayout()
        self.ui['dogum_yeri'] = self._create_combo(editable=True)
        self.ui['dogum_tarihi'] = QDateEdit(); self.ui['dogum_tarihi'].setCalendarPopup(True); self.ui['dogum_tarihi'].setDisplayFormat("dd.MM.yyyy")
        
        self._add_v_field(row_id_2, "Doğum Yeri", self.ui['dogum_yeri'])
        self._add_v_field(row_id_2, "Doğum Tarihi", self.ui['dogum_tarihi'])
        id_lay.addLayout(row_id_2)
        
        id_lay.addStretch()

        # --- C. İLETİŞİM BİLGİLERİ (SAĞ) ---
        contact_grp = QGroupBox("İletişim Bilgileri")
        contact_lay = QVBoxLayout(contact_grp)
        contact_lay.setSpacing(15)
        contact_lay.setContentsMargins(15, 25, 15, 15)
        
        self.ui['cep_tel'] = QLineEdit()
        self.ui['cep_tel'].setPlaceholderText("05XX...")
        # DÜZELTME: Telefon için de Regex Validator
        self.ui['cep_tel'].setValidator(QRegularExpressionValidator(QRegularExpression("[0-9]*")))
        self.ui['cep_tel'].setMaxLength(11)
        
        self.ui['eposta'] = QLineEdit()
        
        self._add_v_field(contact_lay, "Cep Telefonu", self.ui['cep_tel'])
        self._add_v_field(contact_lay, "E-Posta Adresi", self.ui['eposta'])
        contact_lay.addStretch()

        top_layout.addWidget(photo_grp)
        top_layout.addWidget(id_grp, stretch=2)
        top_layout.addWidget(contact_grp, stretch=1)
        
        content_layout.addWidget(top_container)

        # ==========================================================
        # 2. BÖLÜM: KURUMSAL BİLGİLER
        # ==========================================================
        corp_grp = QGroupBox("Kurumsal Bilgiler")
        corp_lay = QVBoxLayout(corp_grp)
        corp_lay.setSpacing(15)
        corp_lay.setContentsMargins(15, 25, 15, 15)
        
        row_corp_1 = QHBoxLayout()
        self.ui['hizmet_sinifi'] = self._create_combo()
        self.ui['kadro_unvani'] = self._create_combo()
        self.ui['gorev_yeri'] = self._create_combo()
        
        self._add_v_field(row_corp_1, "Hizmet Sınıfı (*)", self.ui['hizmet_sinifi'])
        self._add_v_field(row_corp_1, "Kadro Ünvanı (*)", self.ui['kadro_unvani'])
        self._add_v_field(row_corp_1, "Görev Yeri", self.ui['gorev_yeri'])
        corp_lay.addLayout(row_corp_1)
        
        row_corp_2 = QHBoxLayout()
        self.ui['sicil_no'] = QLineEdit()
        self.ui['baslama_tarihi'] = QDateEdit(); self.ui['baslama_tarihi'].setCalendarPopup(True); self.ui['baslama_tarihi'].setDate(QDate.currentDate())
        
        self._add_v_field(row_corp_2, "Kurum Sicil No", self.ui['sicil_no'])
        self._add_v_field(row_corp_2, "Başlama Tarihi", self.ui['baslama_tarihi'])
        row_corp_2.addStretch() 
        corp_lay.addLayout(row_corp_2)
        
        content_layout.addWidget(corp_grp)

        # ==========================================================
        # 3. BÖLÜM: EĞİTİM BİLGİLERİ
        # ==========================================================
        edu_grp = QGroupBox("Eğitim Bilgileri")
        edu_main_lay = QHBoxLayout(edu_grp)
        edu_main_lay.setSpacing(20)
        
        # Okul 1
        edu_1_widget = QWidget()
        edu_1_lay = QVBoxLayout(edu_1_widget)
        edu_1_lay.setContentsMargins(0,0,0,0)
        
        self.ui['okul1'] = self._create_combo(editable=True)
        self.ui['fakulte1'] = self._create_combo(editable=True)
        self.ui['mezun_tarihi1'] = QLineEdit(); self.ui['mezun_tarihi1'].setPlaceholderText("GG.AA.YYYY")
        self.ui['diploma_no1'] = QLineEdit()
        self.btn_dip1 = QPushButton("Dosya Seç"); self.btn_dip1.clicked.connect(lambda: self._dosya_sec('Diploma1', self.btn_dip1))
        
        edu_1_lay.addWidget(QLabel("<b>1. Okul / Lisans</b>"))
        self._add_v_field(edu_1_lay, "Okul Adı", self.ui['okul1'])
        self._add_v_field(edu_1_lay, "Bölüm/Fakülte", self.ui['fakulte1'])
        
        row_edu_1 = QHBoxLayout()
        self._add_v_field(row_edu_1, "Mezuniyet Tar.", self.ui['mezun_tarihi1'])
        self._add_v_field(row_edu_1, "Diploma No", self.ui['diploma_no1'])
        edu_1_lay.addLayout(row_edu_1)
        self._add_v_field(edu_1_lay, "Diploma Dosyası", self.btn_dip1)
        
        # Okul 2
        edu_2_widget = QWidget()
        edu_2_lay = QVBoxLayout(edu_2_widget)
        edu_2_lay.setContentsMargins(0,0,0,0)
        
        self.ui['okul2'] = self._create_combo(editable=True)
        self.ui['fakulte2'] = self._create_combo(editable=True)
        self.ui['mezun_tarihi2'] = QLineEdit(); self.ui['mezun_tarihi2'].setPlaceholderText("GG.AA.YYYY")
        self.ui['diploma_no2'] = QLineEdit()
        self.btn_dip2 = QPushButton("Dosya Seç"); self.btn_dip2.clicked.connect(lambda: self._dosya_sec('Diploma2', self.btn_dip2))
        
        edu_2_lay.addWidget(QLabel("<b>2. Okul / Yüksek Lisans</b>"))
        self._add_v_field(edu_2_lay, "Okul Adı", self.ui['okul2'])
        self._add_v_field(edu_2_lay, "Bölüm/Fakülte", self.ui['fakulte2'])
        
        row_edu_2 = QHBoxLayout()
        self._add_v_field(row_edu_2, "Mezuniyet Tar.", self.ui['mezun_tarihi2'])
        self._add_v_field(row_edu_2, "Diploma No", self.ui['diploma_no2'])
        edu_2_lay.addLayout(row_edu_2)
        self._add_v_field(edu_2_lay, "Diploma Dosyası", self.btn_dip2)
        
        edu_main_lay.addWidget(edu_1_widget)
        edu_main_lay.addWidget(self._create_v_line())
        edu_main_lay.addWidget(edu_2_widget)
        
        content_layout.addWidget(edu_grp)

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        # Footer
        footer = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        
        self.btn_kaydet = QPushButton("✅ PERSONELİ KAYDET")
        self.btn_kaydet.setObjectName("btn_kaydet")
        self.btn_kaydet.setMinimumHeight(50)
        self.btn_kaydet.setMinimumWidth(200)
        self.btn_kaydet.clicked.connect(self._validasyon_ve_kaydet)
        
        btn_iptal = QPushButton("İPTAL")
        btn_iptal.setObjectName("btn_iptal")
        btn_iptal.setMinimumHeight(50)
        btn_iptal.clicked.connect(lambda: pencereyi_kapat(self))
        
        footer.addWidget(self.progress)
        footer.addStretch()
        footer.addWidget(btn_iptal)
        footer.addWidget(self.btn_kaydet)
        main_layout.addLayout(footer)

    # --- YARDIMCI METODLAR ---
    def _add_v_field(self, parent_layout, label_text, widget):
        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        
        lbl = QLabel(label_text)
        lbl.setStyleSheet("font-weight: bold; color: #aaa; font-size: 11px;")
        
        lay.addWidget(lbl)
        lay.addWidget(widget)
        parent_layout.addWidget(container)

    def _create_v_line(self):
        frame = QFrame()
        frame.setFrameShape(QFrame.VLine)
        frame.setFrameShadow(QFrame.Sunken)
        return frame

    def _create_combo(self, editable=False):
        c = QComboBox()
        c.setEditable(editable)
        if editable:
            c.setInsertPolicy(QComboBox.NoInsert)
            c.completer().setCompletionMode(QCompleter.PopupCompletion)
        return c

    def _baslangic_yukle(self):
        self.loader = BaslangicYukleyici(self.service)
        self.loader.veri_hazir.connect(self._verileri_doldur)
        self.loader.start()

    def _verileri_doldur(self, d):
        self.ui['hizmet_sinifi'].addItems(d.get('Hizmet_Sinifi', []))
        self.ui['kadro_unvani'].addItems(d.get('Kadro_Unvani', []))
        self.ui['gorev_yeri'].addItems(d.get('Gorev_Yeri', []))
        
        self.ui['dogum_yeri'].addItems(d.get('Sehirler', []))
        self.ui['okul1'].addItems(d.get('Okullar', []))
        self.ui['okul2'].addItems(d.get('Okullar', []))
        self.ui['fakulte1'].addItems(d.get('Bolumler', []))
        self.ui['fakulte2'].addItems(d.get('Bolumler', []))
        
        for k, v in self.ui.items():
            if isinstance(v, QComboBox): v.setCurrentIndex(-1)

    def _resim_sec(self):
        d, _ = QFileDialog.getOpenFileName(self, "Fotoğraf", "", "*.jpg *.png")
        if d: 
            self.dosya_yollari["Resim"] = d
            self.lbl_resim_onizleme.setPixmap(QPixmap(d).scaled(130, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _dosya_sec(self, key, btn):
        d, _ = QFileDialog.getOpenFileName(self, "Dosya", "", "*.pdf *.jpg")
        if d:
            self.dosya_yollari[key] = d
            btn.setText("✅ Seçildi")
            btn.setStyleSheet("color: #4CAF50; font-weight: bold;")

    def _validasyon_ve_kaydet(self):
        hatalar = []
        if not self.ui['tc'].text(): hatalar.append("TC Kimlik No zorunludur.")
        if not self.ui['ad_soyad'].text(): hatalar.append("Ad Soyad zorunludur.")
        if not self.ui['hizmet_sinifi'].currentText(): hatalar.append("Hizmet Sınıfı seçilmelidir.")
        
        tc_ok, tc_err = Validator.validate_tc(self.ui['tc'].text())
        if not tc_ok: hatalar.append(tc_err)
        
        tel_ok, tel_err = Validator.validate_phone(self.ui['cep_tel'].text())
        if not tel_ok: hatalar.append(tel_err)
        
        mail_ok, mail_err = Validator.validate_email(self.ui['eposta'].text())
        if not mail_ok: hatalar.append(mail_err)

        if hatalar:
            show_error("Giriş Hatası", "\n".join(hatalar), self)
            return

        self._kaydet_baslat()

    def _kaydet_baslat(self):
        self.btn_kaydet.setEnabled(False); self.btn_kaydet.setText("Kaydediliyor...")
        self.progress.setVisible(True); self.progress.setRange(0, 0)
        
        data = {
            'Kimlik_No': self.ui['tc'].text(),
            'Ad_Soyad': self.ui['ad_soyad'].text(),
            'Dogum_Yeri': self.ui['dogum_yeri'].currentText(),
            'Dogum_Tarihi': self.ui['dogum_tarihi'].text(),
            'Hizmet_Sinifi': self.ui['hizmet_sinifi'].currentText(),
            'Kadro_Unvani': self.ui['kadro_unvani'].currentText(),
            'Gorev_Yeri': self.ui['gorev_yeri'].currentText(),
            'Kurum_Sicil_No': self.ui['sicil_no'].text(),
            'Memuriyete_Baslama_Tarihi': self.ui['baslama_tarihi'].text(),
            'Cep_Telefonu': self.ui['cep_tel'].text(),
            'E_posta': self.ui['eposta'].text(),
            'Mezun_Olunan_Okul': self.ui['okul1'].currentText(),
            'Mezun_Olunan_Fakülte': self.ui['fakulte1'].currentText(),
            'Mezuniyet_Tarihi': self.ui['mezun_tarihi1'].text(),
            'Diploma_No': self.ui['diploma_no1'].text(),
            'Mezun_Olunan_Okul_2': self.ui['okul2'].currentText(),
            'Mezun_Olunan_Fakülte_2': self.ui['fakulte2'].currentText(),
            'Mezuniyet_Tarihi_2': self.ui['mezun_tarihi2'].text(),
            'Diploma_No_2': self.ui['diploma_no2'].text(),
            'Durum': 'Aktif'
        }
        
        self.worker = KayitWorker(self.service, data, self.dosya_yollari, self.kullanici_adi)
        self.worker.islem_tamam.connect(self._on_success)
        self.worker.hata_olustu.connect(self._on_error)
        self.worker.start()

    def _on_success(self):
        self.progress.setRange(0, 100); self.progress.setValue(100)
        self.btn_kaydet.setText("✅ PERSONELİ KAYDET"); self.btn_kaydet.setEnabled(True)
        show_info("Başarılı", "Personel başarıyla kaydedildi.", self)
        pencereyi_kapat(self)

    def _on_error(self, err):
        self.progress.setVisible(False); self.btn_kaydet.setEnabled(True)
        self.btn_kaydet.setText("✅ PERSONELİ KAYDET")
        show_error("Kayıt Hatası", err, self)

    def closeEvent(self, event):
        if hasattr(self, 'loader') and self.loader.isRunning(): self.loader.quit(); self.loader.wait(500)
        if hasattr(self, 'worker') and self.worker.isRunning(): self.worker.quit(); self.worker.wait(500)
        event.accept()

if __name__ == "__main__":
    app = QApplication([])
    try:
        from temalar.tema import TemaYonetimi
        TemaYonetimi.uygula_fusion_dark(app)
    except: pass
    win = PersonelEklePenceresi()
    win.show()
    app.exec()