# -*- coding: utf-8 -*-
import logging
import os
import sys
import traceback
from typing import Optional

# PySide6 Kütüphaneleri
from PySide6.QtCore import Qt, QDate, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFileDialog, QTabWidget, QProgressBar, QFrame,
    QComboBox, QCompleter, QLineEdit, QDateEdit, QFormLayout, QApplication, QGroupBox
)
from PySide6.QtGui import QIntValidator

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
        OrtakAraclar, pencereyi_kapat, show_info, show_error, 
        validate_required_fields, kayitlari_getir, satir_ekle
    )
    from temalar.tema import TemaYonetimi 
    from araclar.rapor_yoneticisi import RaporYoneticisi 
    
    from google_baglanti import (
        veritabani_getir, GoogleDriveService, 
        InternetBaglantiHatasi, KimlikDogrulamaHatasi
    )
    
    # 🟢 RESİM İŞLEME İÇİN EKLENDİ
    from PIL import Image
    
except ImportError as e:
    print(f"KRİTİK HATA: Modüller yüklenemedi! {e}")
    print("Lütfen 'pip install Pillow' komutunu çalıştırın.")
    GoogleDriveService = None
    InternetBaglantiHatasi = Exception
    KimlikDogrulamaHatasi = Exception
    Image = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PersonelEkle")

# =============================================================================
# 1. BAŞLANGIÇ YÜKLEYİCİ
# =============================================================================
class BaslangicYukleyici(QThread):
    veri_hazir = Signal(dict)
    
    def run(self):
        sonuc_dict = {'Drive_Klasor': {}}
        try:
            tum_sabitler = kayitlari_getir(veritabani_getir, 'sabit', 'Sabitler')
            if tum_sabitler:
                for satir in tum_sabitler:
                    kod = str(satir.get('Kod', '')).strip()
                    eleman = str(satir.get('MenuEleman', '')).strip()
                    aciklama = str(satir.get('Aciklama', '')).strip() 
                    
                    if kod and eleman:
                        if kod == "Drive_Klasor":
                            sonuc_dict['Drive_Klasor'][eleman] = aciklama
                        else:
                            if kod not in sonuc_dict: sonuc_dict[kod] = []
                            sonuc_dict[kod].append(eleman)
            
            tum_personel = kayitlari_getir(veritabani_getir, 'personel', 'Personel')
            sehirler, okullar, bolumler = set(), set(), set()
            
            if tum_personel:
                for p in tum_personel:
                    dy = p.get('Dogum_Yeri')
                    if dy: sehirler.add(str(dy).strip())
                    
                    okul = p.get('Mezun_Olunan_Okul')
                    if okul: okullar.add(str(okul).strip())
                    
                    fak = p.get('Mezun_Olunan_Fakülte')
                    if fak: bolumler.add(str(fak).strip())

            for k in sonuc_dict:
                if isinstance(sonuc_dict[k], list): sonuc_dict[k].sort()
            
            sonuc_dict['Sehirler'] = sorted(list(sehirler))
            sonuc_dict['Okullar'] = sorted(list(okullar))
            sonuc_dict['Bolumler'] = sorted(list(bolumler))

        except Exception as e:
            logger.error(f"Başlangıç yükleme hatası: {e}")
            traceback.print_exc()
        
        self.veri_hazir.emit(sonuc_dict)

# =============================================================================
# 2. KAYIT İŞÇİSİ (RESİM DÜZELTME ÖZELLİKLİ)
# =============================================================================
class KayitWorker(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)
    
    def __init__(self, veri_sozlugu, dosya_yollari, drive_ids):
        super().__init__()
        self.data = veri_sozlugu
        self.files = dosya_yollari
        self.drive_ids = drive_ids 

    def run(self):
        temp_resim_path = None # Geçici dosya takibi için
        
        try:
            drive_links = {"Resim": "", "Diploma1": "", "Diploma2": "", "OzlukDosyasi": ""}
            tc_no = self.data.get('tc', '00000000000')
            ad_soyad = self.data.get('ad_soyad', 'Isimsiz')
            
            # 🟢 ADIM 0: RESİM FORMATINI STANDARTLAŞTIRMA (Hata Önleyici)
            if self.files.get("Resim") and Image:
                try:
                    orj_yol = self.files["Resim"]
                    if os.path.exists(orj_yol):
                        # Resmi aç ve RGB'ye çevir (Word ve Drive için en güvenli format)
                        img = Image.open(orj_yol)
                        if img.mode in ("RGBA", "P", "CMYK"):
                            img = img.convert("RGB")
                        
                        # Geçici olarak JPG kaydet
                        temp_resim_path = os.path.join(current_dir, f"temp_resim_{tc_no}.jpg")
                        img.save(temp_resim_path, "JPEG", quality=90)
                        
                        # Dosya yolunu güncelle (Artık işlemler bu temiz dosyayla yapılacak)
                        self.files["Resim"] = temp_resim_path
                except Exception as e:
                    print(f"Resim formatlama uyarısı: {e} (Orijinal dosya kullanılacak)")

            # --- 1. SÜRÜCÜYE BAĞLAN ---
            drive = None
            if GoogleDriveService:
                try:
                    drive = GoogleDriveService()
                except Exception as e:
                    print(f"Drive bağlantı hatası: {e}")

            # --- 2. DOSYA YÜKLEME ---
            if drive:
                id_resim = self.drive_ids.get("Personel_Resim", "") 
                id_diploma = self.drive_ids.get("Personel_Diploma", "")

                for key, path in self.files.items():
                    if path and os.path.exists(path):
                        hedef_id = id_resim if key == "Resim" else id_diploma
                        if hedef_id:
                            _, uzanti = os.path.splitext(path)
                            if key == "Resim": yeni_isim = f"{tc_no}_profil{uzanti}"
                            elif key == "Diploma1": yeni_isim = f"{tc_no}_diploma_1{uzanti}"
                            elif key == "Diploma2": yeni_isim = f"{tc_no}_diploma_2{uzanti}"
                            else: yeni_isim = os.path.basename(path)

                            try:
                                link = drive.upload_file(path, hedef_id, custom_name=yeni_isim)
                                if link: drive_links[key] = link
                            except Exception as e:
                                print(f"Dosya yükleme hatası ({key}): {e}")

            # --- 3. WORD OLUŞTURMA ---
            try:
                sablon_klasoru = os.path.join(root_dir, "sablonlar")
                rapor_araci = RaporYoneticisi(sablon_klasoru)
                
                context = {
                    'Ad_Soyad': ad_soyad,
                    'Kimlik_No': tc_no,
                    'Hizmet_sinifi': self.data.get('hizmet_sinifi'),
                    'Kadro_Unvani': self.data.get('kadro_unvani'),
                    'Memuriyete_Baslama_Tarihi': self.data.get('baslama_tarihi'),
                    'Kurum_Sicil_No': self.data.get('sicil_no'),
                    'Gorev_Yeri': self.data.get('gorev_yeri'),
                    'Dogum_Yeri': self.data.get('dogum_yeri'),
                    'Dogum_Tarihi': self.data.get('dogum_tarihi'),
                    'Cep_Telefon': self.data.get('cep_tel'),
                    'E_posta': self.data.get('eposta'),
                    'Mezun_Olunan_Okul': self.data.get('okul1'),
                    'Mezun_Olunan_Fakülte': self.data.get('fakulte1'),
                    'Mezuniyet_Tarihi': self.data.get('mezun_tarihi1'),
                    'Diploma_No': self.data.get('diploma_no1'),
                    'Mezun_Olunan_Okul_2': self.data.get('okul2'),
                    'Mezun_Olunan_Fakülte_Bolum_2': self.data.get('fakulte2'),
                    'Mezuniyet_Tarihi_2': self.data.get('mezun_tarihi2'),
                    'Diploma_No_2': self.data.get('diploma_no2'),
                    'Olusturma_Tarihi': QDate.currentDate().toString("dd.MM.yyyy")
                }

                resim_yolu = self.files.get("Resim")
                resimler = {}
                if resim_yolu and os.path.exists(resim_yolu):
                    resimler['Resim'] = os.path.abspath(resim_yolu)
                
                cikti_yolu = os.path.join(current_dir, f"{tc_no}_ozluk.docx")

                basari_word = rapor_araci.word_olustur("personel_ozluk_sablon.docx", context, cikti_yolu, resimler)
                
                if basari_word and drive:
                    id_dosyalar = self.drive_ids.get("Personel_Dosyalari", "") or self.drive_ids.get("Personel_Resim", "")
                    if id_dosyalar:
                        try:
                            link = drive.upload_file(cikti_yolu, id_dosyalar, custom_name=f"{tc_no}_{ad_soyad}_Ozluk.docx")
                            if link: drive_links["OzlukDosyasi"] = link
                        except Exception as e:
                            print(f"Word Drive hatası: {e}")
                    
                    if os.path.exists(cikti_yolu): os.remove(cikti_yolu)

            except Exception as e:
                print("--- WORD HATASI ---")
                traceback.print_exc()

            # --- 4. VERİTABANI KAYIT ---
            row_personel = [
                self.data.get('tc', ''), self.data.get('ad_soyad', ''),
                self.data.get('dogum_yeri', ''), self.data.get('dogum_tarihi', ''),
                self.data.get('hizmet_sinifi', ''), self.data.get('kadro_unvani', ''),
                self.data.get('gorev_yeri', ''), self.data.get('sicil_no', ''),
                self.data.get('baslama_tarihi', ''), self.data.get('cep_tel', ''),
                self.data.get('eposta', ''), self.data.get('okul1', ''),
                self.data.get('fakulte1', ''), self.data.get('mezun_tarihi1', ''),
                self.data.get('diploma_no1', ''), self.data.get('okul2', ''),
                self.data.get('fakulte2', ''), self.data.get('mezun_tarihi2', ''),
                self.data.get('diploma_no2', ''), 
                drive_links.get('Resim', ''),
                drive_links.get('Diploma1', ''), 
                drive_links.get('Diploma2', ''),
                drive_links.get('OzlukDosyasi', '') 
            ]

            basari_vt = satir_ekle(veritabani_getir, 'personel', 'Personel', row_personel)
            
            if basari_vt: 
                try:
                    row_izin = [
                        self.data.get('tc', ''), self.data.get('ad_soyad', ''),
                        0, 0, 0, 0, 0, 0, 0, 0, 0, 0
                    ]
                    satir_ekle(veritabani_getir, 'personel', 'izin_bilgi', row_izin)
                except Exception as ex:
                    print(f"İzin bilgisi hatası: {ex}")

                self.islem_tamam.emit()
            else: 
                raise Exception("Veritabanına kayıt yapılamadı.")

        except InternetBaglantiHatasi: self.hata_olustu.emit("İnternet bağlantısı kesildi.")
        except KimlikDogrulamaHatasi: self.hata_olustu.emit("Oturum zaman aşımı.")
        except Exception as e: 
            traceback.print_exc()
            self.hata_olustu.emit(f"Hata: {str(e)}")
        
        finally:
            # 🟢 TEMİZLİK: Geçici oluşturulan resim dosyasını sil
            if temp_resim_path and os.path.exists(temp_resim_path):
                try: os.remove(temp_resim_path)
                except: pass

# =============================================================================
# 3. ANA FORM
# =============================================================================
class PersonelEklePenceresi(QWidget):
    def __init__(self, yetki='viewer', kullanici_adi=None): 
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi 
        
        self.setWindowTitle("Yeni Personel Ekle")
        self.resize(1300, 850)
        
        self.dosya_yollari = {"Resim": None, "Diploma1": None, "Diploma2": None}
        self.drive_config = {} 
        self.ui = {} 

        self._setup_ui()
        YetkiYoneticisi.uygula(self, "personel_ekle")
        self._baslangic_yukle()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        content_widget = QWidget()
        columns_layout = QHBoxLayout(content_widget)
        columns_layout.setSpacing(20)
        columns_layout.setContentsMargins(10, 10, 10, 10)

        # ================= SOL SÜTUN =================
        left_layout = QVBoxLayout()
        left_layout.setAlignment(Qt.AlignTop)
        left_layout.setSpacing(20)

        # 1. KİMLİK VE FOTOĞRAF
        grp_kimlik = OrtakAraclar.create_group_box(content_widget, "Kimlik ve Fotoğraf Bilgileri")
        v_kimlik = QVBoxLayout(grp_kimlik)
        v_kimlik.setSpacing(15)
        
        # A) Fotoğraf Alanı
        h_resim = QVBoxLayout() 
        h_resim.setAlignment(Qt.AlignCenter)
        self.lbl_resim_onizleme = QLabel("Fotoğraf Yok")
        self.lbl_resim_onizleme.setFixedSize(140, 160)
        self.lbl_resim_onizleme.setStyleSheet("border: 2px dashed #555; background: #2b2b2b; color: #aaa; border-radius: 8px;")
        self.lbl_resim_onizleme.setAlignment(Qt.AlignCenter)
        self.lbl_resim_onizleme.setScaledContents(True)
        btn_resim_sec = OrtakAraclar.create_button(grp_kimlik, "📷 Fotoğraf Seç", self._resim_sec)
        btn_resim_sec.setFixedWidth(140)
        h_resim.addWidget(self.lbl_resim_onizleme)
        h_resim.addWidget(btn_resim_sec)
        v_kimlik.addLayout(h_resim)
        
        v_kimlik.addSpacing(10)

        # B) Kimlik Inputları
        self.ui['tc'] = self._create_input_with_label(grp_kimlik, "TC Kimlik No:", "11 Haneli TC")
        self.ui['tc'].setMaxLength(11)
        self.ui['tc'].setValidator(QIntValidator())
        v_kimlik.addWidget(self.ui['tc'].parentWidget()) 

        self.ui['ad_soyad'] = self._create_input_with_label(grp_kimlik, "Adı Soyadı:")
        v_kimlik.addWidget(self.ui['ad_soyad'].parentWidget())

        # C) Doğum Yeri ve Tarihi
        row_dogum = QHBoxLayout()
        self.ui['dogum_yeri'] = self._create_editable_combo(grp_kimlik)
        self.ui['dogum_tarihi'] = QDateEdit()
        self.ui['dogum_tarihi'].setCalendarPopup(True)
        self.ui['dogum_tarihi'].setDisplayFormat("dd.MM.yyyy")
        self.ui['dogum_tarihi'].setMinimumHeight(40) 
        
        row_dogum.addWidget(self._wrap_label_widget("Doğum Yeri:", self.ui['dogum_yeri']))
        row_dogum.addWidget(self._wrap_label_widget("Doğum Tarihi:", self.ui['dogum_tarihi']))
        v_kimlik.addLayout(row_dogum)

        left_layout.addWidget(grp_kimlik)
        columns_layout.addLayout(left_layout, 4) 

        # ================= SAĞ SÜTUN =================
        right_layout = QVBoxLayout()
        right_layout.setAlignment(Qt.AlignTop)
        right_layout.setSpacing(20)

        # 2. İLETİŞİM
        grp_iletisim = OrtakAraclar.create_group_box(content_widget, "İletişim Bilgileri")
        h_iletisim = QHBoxLayout(grp_iletisim)
        h_iletisim.setSpacing(15)
        
        self.ui['cep_tel'] = self._create_input_with_label(grp_iletisim, "Cep Telefonu:", "05XX...")
        self.ui['cep_tel'].setMaxLength(11)
        self.ui['cep_tel'].setValidator(QIntValidator())
        h_iletisim.addWidget(self.ui['cep_tel'].parentWidget())
        
        self.ui['eposta'] = self._create_input_with_label(grp_iletisim, "E-Posta Adresi:")
        h_iletisim.addWidget(self.ui['eposta'].parentWidget())
        
        right_layout.addWidget(grp_iletisim)

        # 3. KADRO
        grp_kadro = OrtakAraclar.create_group_box(content_widget, "Kadro ve Kurumsal Bilgiler")
        v_kadro = QVBoxLayout(grp_kadro)
        v_kadro.setSpacing(15)
        
        row_k1 = QHBoxLayout()
        self.ui['hizmet_sinifi'] = self._create_combo_no_label(grp_kadro)
        self.ui['kadro_unvani'] = self._create_combo_no_label(grp_kadro)
        row_k1.addWidget(self._wrap_label_widget("Hizmet Sınıfı:", self.ui['hizmet_sinifi']))
        row_k1.addWidget(self._wrap_label_widget("Kadro Ünvanı:", self.ui['kadro_unvani']))
        v_kadro.addLayout(row_k1)
        
        row_k2 = QHBoxLayout()
        self.ui['sicil_no'] = OrtakAraclar.create_line_edit(grp_kadro)
        self.ui['baslama_tarihi'] = QDateEdit()
        self.ui['baslama_tarihi'].setCalendarPopup(True)
        self.ui['baslama_tarihi'].setDisplayFormat("dd.MM.yyyy")
        self.ui['baslama_tarihi'].setDate(QDate.currentDate())
        self.ui['baslama_tarihi'].setMinimumHeight(40)
        self.ui['gorev_yeri'] = self._create_combo_no_label(grp_kadro)
        
        row_k2.addWidget(self._wrap_label_widget("Kurum Sicil No:", self.ui['sicil_no']), 1)
        row_k2.addWidget(self._wrap_label_widget("Başlama Tarihi:", self.ui['baslama_tarihi']), 0)
        row_k2.addWidget(self._wrap_label_widget("Görev Yeri:", self.ui['gorev_yeri']), 1)
        v_kadro.addLayout(row_k2)
        
        right_layout.addWidget(grp_kadro)

        # 4. EĞİTİM
        grp_egitim_ana = OrtakAraclar.create_group_box(content_widget, "Eğitim Bilgileri")
        layout_egitim_ana = QHBoxLayout(grp_egitim_ana)
        layout_egitim_ana.setContentsMargins(10, 25, 10, 10)
        layout_egitim_ana.setSpacing(20)
        
        # Üniversite 1
        grp_uni1 = QGroupBox("Lise / Lisans / Önlisans")
        grp_uni1.setStyleSheet("QGroupBox { border: 1px solid #444; border-radius: 6px; margin-top: 10px; font-weight: bold; } QGroupBox::title { color: #4dabf7; top: -4px; left: 10px; }")
        l_uni1 = QVBoxLayout(grp_uni1)
        self.ui['okul1'] = self._create_editable_combo(grp_uni1)
        self.ui['fakulte1'] = self._create_editable_combo(grp_uni1)
        l_uni1.addWidget(self._wrap_label_widget("Okul:", self.ui['okul1']))
        l_uni1.addWidget(self._wrap_label_widget("Bölüm/Fakülte:", self.ui['fakulte1']))
        
        row_u1_2 = QHBoxLayout()
        self.ui['mezun_tarihi1'] = OrtakAraclar.create_line_edit(grp_uni1)
        self.ui['mezun_tarihi1'].setInputMask("99.99.9999")
        self.ui['mezun_tarihi1'].setPlaceholderText("GG.AA.YYYY")
        self.ui['diploma_no1'] = OrtakAraclar.create_line_edit(grp_uni1)
        row_u1_2.addWidget(self._wrap_label_widget("Mezuniyet Tarihi:", self.ui['mezun_tarihi1']))
        row_u1_2.addWidget(self._wrap_label_widget("Diploma No:", self.ui['diploma_no1']))
        l_uni1.addLayout(row_u1_2)
        
        self.btn_dip1 = OrtakAraclar.create_button(grp_uni1, "📄 Diploma Dosyası Seç", lambda: self._dosya_sec("Diploma1", self.btn_dip1))
        l_uni1.addWidget(self.btn_dip1)
        layout_egitim_ana.addWidget(grp_uni1)

        # Üniversite 2
        grp_uni2 = QGroupBox("Önlisans / Yüksek Lisans / Lisans Tamamlama")
        grp_uni2.setStyleSheet("QGroupBox { border: 1px solid #444; border-radius: 6px; margin-top: 10px; font-weight: bold; } QGroupBox::title { color: #4dabf7; top: -4px; left: 10px; }")
        l_uni2 = QVBoxLayout(grp_uni2)
        self.ui['okul2'] = self._create_editable_combo(grp_uni2)
        self.ui['fakulte2'] = self._create_editable_combo(grp_uni2)
        l_uni2.addWidget(self._wrap_label_widget("Okul:", self.ui['okul2']))
        l_uni2.addWidget(self._wrap_label_widget("Bölüm/Fakülte:", self.ui['fakulte2']))
        
        row_u2_2 = QHBoxLayout()
        self.ui['mezun_tarihi2'] = OrtakAraclar.create_line_edit(grp_uni2)
        self.ui['mezun_tarihi2'].setInputMask("99.99.9999")
        self.ui['mezun_tarihi2'].setPlaceholderText("GG.AA.YYYY")
        self.ui['diploma_no2'] = OrtakAraclar.create_line_edit(grp_uni2)
        row_u2_2.addWidget(self._wrap_label_widget("Mezuniyet Tarihi:", self.ui['mezun_tarihi2']))
        row_u2_2.addWidget(self._wrap_label_widget("Diploma No:", self.ui['diploma_no2']))
        l_uni2.addLayout(row_u2_2)
        
        self.btn_dip2 = OrtakAraclar.create_button(grp_uni2, "📄 Diploma Dosyası Seç", lambda: self._dosya_sec("Diploma2", self.btn_dip2))
        l_uni2.addWidget(self.btn_dip2)
        layout_egitim_ana.addWidget(grp_uni2)

        right_layout.addWidget(grp_egitim_ana)
        right_layout.addStretch()
        columns_layout.addLayout(right_layout, 6) 

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        # Footer
        footer = QHBoxLayout()
        footer.setContentsMargins(10, 10, 10, 10)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        
        btn_iptal = QPushButton("İptal")
        btn_iptal.setObjectName("btn_iptal") 
        btn_iptal.setFixedSize(120, 45)
        btn_iptal.clicked.connect(lambda: pencereyi_kapat(self))
        
        self.btn_kaydet = OrtakAraclar.create_button(self, "✅ Personel Kaydet", self._kaydet_baslat)
        self.btn_kaydet.setObjectName("btn_kaydet") 
        self.btn_kaydet.setFixedSize(180, 45)
        
        footer.addWidget(self.progress)
        footer.addStretch()
        footer.addWidget(btn_iptal)
        footer.addWidget(self.btn_kaydet)
        main_layout.addLayout(footer)
        
    # --- YARDIMCI UI METODLARI ---
    def _create_input_with_label(self, parent, label_text, placeholder=""):
        container = QWidget(parent) 
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        lbl = QLabel(label_text)
        lbl.setStyleSheet("color: #b0b0b0; font-size: 11px; font-weight: bold; text-transform: uppercase;")
        inp = OrtakAraclar.create_line_edit(container, placeholder)
        lay.addWidget(lbl)
        lay.addWidget(inp)
        return inp 

    def _wrap_label_widget(self, label_text, widget):
        container = QWidget() 
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        lbl = QLabel(label_text)
        lbl.setStyleSheet("color: #b0b0b0; font-size: 11px; font-weight: bold; text-transform: uppercase;")
        lay.addWidget(lbl)
        lay.addWidget(widget)
        return container

    def _create_editable_combo(self, parent):
        combo = OrtakAraclar.create_combo_box(parent)
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.completer().setCompletionMode(QCompleter.PopupCompletion)
        return combo
        
    def _create_combo_no_label(self, parent):
        combo = QComboBox(parent)
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
            self.ui[field].clear(); self.ui[field].addItems(veriler.get(key, []))
            self.ui[field].setCurrentIndex(-1); self.ui[field].setPlaceholderText("Seçiniz veya yazınız...")
        self.drive_config = veriler.get('Drive_Klasor', {})

    def _resim_sec(self):
        d, _ = QFileDialog.getOpenFileName(self, "Fotoğraf Seç", "", "Resim (*.jpg *.png *.jpeg)")
        if d: 
            self.dosya_yollari["Resim"] = d
            self.lbl_resim_onizleme.setPixmap(QPixmap(d).scaled(140, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _dosya_sec(self, key, btn):
        d, _ = QFileDialog.getOpenFileName(self, "Dosya Seç", "", "Dosya (*.pdf *.jpg *.png)")
        if d: 
            self.dosya_yollari[key] = d
            btn.setText(f"✅ Seçildi: {os.path.basename(d)[:15]}...")
            btn.setStyleSheet("background-color: #2e7d32; color: white;") 

    def _kaydet_baslat(self):
        if not validate_required_fields([self.ui['tc'], self.ui['ad_soyad'], self.ui['hizmet_sinifi']]): return
        self.btn_kaydet.setEnabled(False); self.btn_kaydet.setText("Kaydediliyor...")
        self.progress.setVisible(True); self.progress.setRange(0, 0) 
        
        data = {}
        for k, v in self.ui.items():
            if isinstance(v, QComboBox): data[k] = v.currentText()
            elif isinstance(v, QDateEdit): data[k] = v.date().toString("dd.MM.yyyy")
            elif isinstance(v, QLineEdit): data[k] = v.text()
            else: data[k] = ""
        self.worker = KayitWorker(data, self.dosya_yollari, self.drive_config)
        self.worker.islem_tamam.connect(self._on_success)
        self.worker.hata_olustu.connect(self._on_error)
        self.worker.start()

    def _on_success(self):
        self.progress.setRange(0, 100); self.progress.setValue(100)
        self.btn_kaydet.setText("Personel Kaydet"); self.btn_kaydet.setEnabled(True)
        show_info("Başarılı", "Kayıt Başarılı.", self); pencereyi_kapat(self)

    def _on_error(self, err):
        self.progress.setVisible(False); self.btn_kaydet.setEnabled(True)
        self.btn_kaydet.setText("Personel Kaydet"); show_error("Kayıt Hatası", err, self)

    def closeEvent(self, event):
        if hasattr(self, 'loader') and self.loader.isRunning(): self.loader.quit(); self.loader.wait(500)
        if hasattr(self, 'worker') and self.worker.isRunning(): self.worker.quit(); self.worker.wait(500)
        event.accept()

if __name__ == "__main__":
    app = QApplication([])
    try:
        TemaYonetimi.uygula_fusion_dark(app)
    except Exception as e:
        print(f"Tema uygulanamadı: {e}")
    win = PersonelEklePenceresi()
    win.show()
    app.exec()