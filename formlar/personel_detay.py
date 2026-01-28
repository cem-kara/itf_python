# -*- coding: utf-8 -*-
import sys
import os
import logging
import urllib.request
import traceback 

# PySide6 Kütüphaneleri
from PySide6.QtCore import Qt, QDate, QThread, Signal
from PySide6.QtGui import QPixmap, QDesktopServices, QAction, QIntValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFileDialog, QTabWidget, QProgressBar, QFrame,
    QComboBox, QLineEdit, QDateEdit, QFormLayout, QApplication, QGroupBox, QCompleter
)

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# --- PROJE MODÜLLERİ ---
try:
    from araclar.yetki_yonetimi import YetkiYoneticisi
    from araclar.ortak_araclar import (
        OrtakAraclar, pencereyi_kapat, show_info, show_error, show_question,
        validate_required_fields, kayitlari_getir
    )
    from temalar.tema import TemaYonetimi
    from araclar.rapor_yoneticisi import RaporYoneticisi
    
    from google_baglanti import veritabani_getir, InternetBaglantiHatasi, KimlikDogrulamaHatasi
    try:
        from google_baglanti import GoogleDriveService
    except ImportError:
        GoogleDriveService = None
    
    from PIL import Image

except ImportError as e:
    print(f"KRİTİK HATA: Modüller yüklenemedi! {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PersonelDetay")

# =============================================================================
# WORKER: GÜNCELLEME VE RAPORLAMA (SİLME SORUNU GİDERİLDİ)
# =============================================================================
class GuncelleWorker(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)
    
    def __init__(self, tc_kimlik, yeni_veri_dict, dosya_yollari, mevcut_linkler, drive_ids):
        super().__init__()
        self.tc = tc_kimlik
        self.data = yeni_veri_dict
        self.files = dosya_yollari 
        self.links = mevcut_linkler 
        self.drive_ids = drive_ids

    def run(self):
        temp_files_to_delete = [] 
        try:
            drive = None
            if GoogleDriveService:
                try: drive = GoogleDriveService()
                except: pass

            # ---------------------------------------------------------
            # 1. RESİM HAZIRLIĞI (WORD İÇİN)
            # ---------------------------------------------------------
            resim_yolu_for_word = None
            
            # A) Yeni Resim
            if self.files.get("Resim") and os.path.exists(self.files["Resim"]):
                resim_yolu_for_word = self.files["Resim"]
            
            # B) Mevcut Resim (İndirme)
            elif self.links.get("Resim"):
                try:
                    url = self.links["Resim"]
                    fid = self._get_file_id_from_link(url)
                    
                    if fid:
                        temp_dl_path = os.path.join(current_dir, f"temp_dl_{self.tc}.jpg")
                        # Google Drive indirme linki (yetki gerektirmeyen durumlar için)
                        # Eğer dosya özelse bu basit urlretrieve çalışmayabilir, 
                        # o durumda drive.service.files().get_media kullanmak gerekir.
                        # Şimdilik mevcut yapıyı koruyoruz.
                        dl_url = f"https://drive.google.com/uc?export=download&id={fid}"
                        try:
                            urllib.request.urlretrieve(dl_url, temp_dl_path)
                            resim_yolu_for_word = temp_dl_path
                            temp_files_to_delete.append(temp_dl_path)
                        except:
                            print("Resim indirme başarısız (Erişim izni gerekebilir).")
                except Exception as e:
                    print(f"Mevcut resim indirme hatası: {e}")

            # 🟢 RESİM FORMATLAMA (Pillow)
            if resim_yolu_for_word and Image:
                try:
                    img = Image.open(resim_yolu_for_word)
                    if img.mode in ("RGBA", "P", "CMYK"):
                        img = img.convert("RGB")
                    
                    safe_resim_path = os.path.join(current_dir, f"temp_safe_{self.tc}.jpg")
                    img.save(safe_resim_path, "JPEG", quality=95)
                    
                    temp_files_to_delete.append(safe_resim_path)
                    resim_yolu_for_word = safe_resim_path 
                    
                    if self.files.get("Resim"):
                        self.files["Resim"] = safe_resim_path
                except Exception as e:
                    print(f"Resim işleme hatası: {e}")

            # ---------------------------------------------------------
            # 2. DOSYA YÜKLEME (DRIVE - Sadece Yeni Seçilenler)
            # ---------------------------------------------------------
            if drive:
                id_resim = self.drive_ids.get("Personel_Resim", "")
                id_diploma = self.drive_ids.get("Personel_Diploma", "")
                
                for key, path in self.files.items():
                    if path and os.path.exists(path):
                        hedef_id = id_resim if key == "Resim" else id_diploma
                        if hedef_id:
                            _, uzanti = os.path.splitext(path)
                            if key == "Resim": yeni_isim = f"{self.tc}_profil_resim{uzanti}"
                            elif key == "Diploma1": yeni_isim = f"{self.tc}_diploma_1{uzanti}"
                            elif key == "Diploma2": yeni_isim = f"{self.tc}_diploma_2{uzanti}"
                            else: yeni_isim = os.path.basename(path)
                            
                            try:
                                link = drive.upload_file(path, hedef_id, custom_name=yeni_isim)
                                if link: self.links[key] = link
                            except Exception as e:
                                print(f"Dosya yükleme hatası ({key}): {e}")

            # ---------------------------------------------------------
            # 3. ESKİ ÖZLÜK DOSYASINI SİLME (DÜZELTİLDİ: supportsAllDrives)
            # ---------------------------------------------------------
            eski_ozluk_link = self.links.get("OzlukDosyasi")
            
            if drive and eski_ozluk_link and hasattr(drive, 'service'):
                try:
                    old_fid = self._get_file_id_from_link(eski_ozluk_link)
                    print(f"Silinecek Dosya ID: {old_fid}")

                    if old_fid:
                        try:
                            # 🟢 KRİTİK DÜZELTME: supportsAllDrives=True
                            drive.service.files().delete(
                                fileId=old_fid, 
                                supportsAllDrives=True
                            ).execute()
                            print("Eski özlük dosyası silindi.")
                        except Exception as delete_error:
                            # Dosya zaten yoksa (404) hata sayma
                            if "404" in str(delete_error) or "not found" in str(delete_error).lower():
                                print("Eski dosya zaten silinmiş (404).")
                            else:
                                print(f"Dosya silinemedi: {delete_error}")
                except Exception as e:
                    print(f"Silme işleminde genel hata: {e}")

            # ---------------------------------------------------------
            # 4. WORD OLUŞTURMA VE YÜKLEME
            # ---------------------------------------------------------
            try:
                sablon_klasoru = os.path.join(root_dir, "sablonlar")
                rapor_araci = RaporYoneticisi(sablon_klasoru)
                
                context = {
                    'AD_SOYAD': self.data.get('ad_soyad', ''),
                    'Kimlik_No': self.tc,
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

                resimler = {}
                if resim_yolu_for_word:
                    resimler['Resim'] = resim_yolu_for_word
                
                cikti_yolu = os.path.join(current_dir, f"{self.tc}_ozluk_guncel.docx")
                
                basari_word = rapor_araci.word_olustur("personel_ozluk_sablon.docx", context, cikti_yolu, resimler)
                
                if basari_word and drive:
                    id_dosyalar = self.drive_ids.get("Personel_Dosyalari", "") or self.drive_ids.get("Personel_Resim", "")
                    if id_dosyalar:
                        try:
                            # Yeni dosyayı yükle
                            link = drive.upload_file(cikti_yolu, id_dosyalar, custom_name=f"{self.tc}_{self.data.get('ad_soyad')}_Ozluk.docx")
                            if link: self.links["OzlukDosyasi"] = link
                        except Exception as e:
                            print(f"Word Drive yükleme hatası: {e}")
                    
                    if os.path.exists(cikti_yolu): os.remove(cikti_yolu)

            except Exception as e:
                print("Word oluşturma hatası:")
                traceback.print_exc()

            # ---------------------------------------------------------
            # 5. VERİTABANI GÜNCELLEME
            # ---------------------------------------------------------
            ws = veritabani_getir('personel', 'Personel')
            cell = ws.find(self.tc)
            if not cell: raise Exception("Personel veritabanında bulunamadı.")
                
            mevcut_satir = ws.row_values(cell.row)
            durum = mevcut_satir[-1] if len(mevcut_satir) > 23 else "Aktif"
            
            guncel_satir = [
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
                self.links.get('Resim', ''),
                self.links.get('Diploma1', ''), 
                self.links.get('Diploma2', ''), 
                self.links.get('OzlukDosyasi', ''), 
                durum
            ]
            
            ws.update(f"A{cell.row}:X{cell.row}", [guncel_satir])
            self.islem_tamam.emit()

        except Exception as e:
            self.hata_olustu.emit(f"Güncelleme hatası: {str(e)}")
        
        finally:
            for p in temp_files_to_delete:
                if os.path.exists(p):
                    try: os.remove(p)
                    except: pass

    # 🟢 YARDIMCI: LINKTEN ID ÇIKARMA
    def _get_file_id_from_link(self, link):
        if not link: return None
        try:
            if "id=" in link: return link.split("id=")[1].split("&")[0]
            if "/d/" in link: return link.split("/d/")[1].split("/")[0]
        except: pass
        return None

class ResimIndirWorker(QThread):
    resim_indi = Signal(QPixmap)
    def __init__(self, url): super().__init__(); self.url = url
    def run(self):
        try:
            if not self.url: return
            file_id = None
            if "id=" in self.url: file_id = self.url.split("id=")[1].split("&")[0]
            elif "/d/" in self.url: file_id = self.url.split("/d/")[1].split("/")[0]
            if file_id:
                dl_url = f"https://drive.google.com/uc?export=download&id={file_id}"
                data = urllib.request.urlopen(dl_url).read()
                pix = QPixmap(); pix.loadFromData(data)
                self.resim_indi.emit(pix)
        except Exception: pass

# =============================================================================
# ANA FORM
# =============================================================================
class PersonelDetayPenceresi(QWidget):
    veri_guncellendi = Signal() 

    def __init__(self, personel_data_row, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.personel_data = personel_data_row 
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.setWindowTitle(f"Personel Detay: {self.personel_data[1]}") 
        self.resize(1300, 850)
        
        self.duzenleme_modu = False
        self.ui = {}
        self.dosya_yollari = {"Resim": None, "Diploma1": None, "Diploma2": None}
        
        # Linkleri Çek (Index Kontrolü ile)
        self.mevcut_linkler = {
            "Resim": self.personel_data[19] if len(self.personel_data)>19 else "",
            "Diploma1": self.personel_data[20] if len(self.personel_data)>20 else "",
            "Diploma2": self.personel_data[21] if len(self.personel_data)>21 else "",
            "OzlukDosyasi": self.personel_data[22] if len(self.personel_data)>22 else ""
        }
        self.drive_config = {} 

        self._setup_ui()
        self._sabitleri_yukle()
        self._verileri_forma_yaz()
        self._mod_degistir(False) 
        
        YetkiYoneticisi.uygula(self, "personel_detay")
        
        if self.mevcut_linkler["Resim"]:
            self.resim_worker = ResimIndirWorker(self.mevcut_linkler["Resim"])
            self.resim_worker.resim_indi.connect(lambda p: self.lbl_resim.setPixmap(p.scaled(140, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            self.resim_worker.start()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        
        top_bar = QHBoxLayout()
        self.lbl_baslik = QLabel(f"👤 {self.personel_data[1]}")
        self.lbl_baslik.setStyleSheet("font-size: 18px; font-weight: bold;")
        
        self.btn_duzenle = OrtakAraclar.create_button(self, "✏️ Düzenle", self._duzenle_tiklandi)
        self.btn_duzenle.setObjectName("btn_duzenle")
        
        self.btn_kaydet = OrtakAraclar.create_button(self, "💾 Kaydet", self._kaydet_baslat)
        self.btn_kaydet.setObjectName("btn_kaydet")
        self.btn_kaydet.setVisible(False)
        
        self.btn_iptal = OrtakAraclar.create_button(self, "❌ İptal", self._iptal_tiklandi)
        self.btn_iptal.setObjectName("btn_iptal")
        self.btn_iptal.setVisible(False)

        top_bar.addWidget(self.lbl_baslik)
        top_bar.addStretch()
        top_bar.addWidget(self.btn_duzenle)
        top_bar.addWidget(self.btn_kaydet)
        top_bar.addWidget(self.btn_iptal)
        main_layout.addLayout(top_bar)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        content_widget = QWidget()
        columns_layout = QHBoxLayout(content_widget)
        columns_layout.setSpacing(20)
        columns_layout.setContentsMargins(10, 10, 10, 10)
        
        left_layout = QVBoxLayout()
        left_layout.setAlignment(Qt.AlignTop)
        left_layout.setSpacing(20)
        
        grp_kimlik = OrtakAraclar.create_group_box(content_widget, "Kimlik ve Fotoğraf Bilgileri")
        v_kimlik = QVBoxLayout(grp_kimlik)
        v_kimlik.setSpacing(15)
        
        h_resim = QVBoxLayout() 
        h_resim.setAlignment(Qt.AlignCenter)
        self.lbl_resim = QLabel("Fotoğraf Yok")
        self.lbl_resim.setFixedSize(140, 160)
        self.lbl_resim.setStyleSheet("border: 2px dashed #555; background: #2b2b2b; color: #aaa; border-radius: 8px;")
        self.lbl_resim.setAlignment(Qt.AlignCenter)
        self.lbl_resim.setScaledContents(True)
        self.btn_resim_degis = OrtakAraclar.create_button(grp_kimlik, "📷 Değiştir...", lambda: self._dosya_sec("Resim"))
        self.btn_resim_degis.setFixedWidth(140)
        h_resim.addWidget(self.lbl_resim)
        h_resim.addWidget(self.btn_resim_degis)
        v_kimlik.addLayout(h_resim)
        v_kimlik.addSpacing(10)

        self.ui['tc'] = self._create_input_with_label(grp_kimlik, "TC Kimlik No:", "11 Haneli TC")
        self.ui['tc'].setMaxLength(11); self.ui['tc'].setReadOnly(True)
        self.ui['tc'].setValidator(QIntValidator())
        v_kimlik.addWidget(self.ui['tc'].parentWidget())

        self.ui['ad_soyad'] = self._create_input_with_label(grp_kimlik, "Adı Soyadı:")
        v_kimlik.addWidget(self.ui['ad_soyad'].parentWidget())

        row_dogum = QHBoxLayout()
        self.ui['dogum_yeri'] = self._create_editable_combo(grp_kimlik) 
        self.ui['dogum_tarihi'] = QDateEdit(); self.ui['dogum_tarihi'].setCalendarPopup(True); self.ui['dogum_tarihi'].setDisplayFormat("dd.MM.yyyy"); self.ui['dogum_tarihi'].setMinimumHeight(40)
        row_dogum.addWidget(self._wrap_label_widget("Doğum Yeri:", self.ui['dogum_yeri']))
        row_dogum.addWidget(self._wrap_label_widget("Doğum Tarihi:", self.ui['dogum_tarihi']))
        v_kimlik.addLayout(row_dogum)
        
        left_layout.addWidget(grp_kimlik)
        left_layout.addStretch()
        columns_layout.addLayout(left_layout, 4)

        right_layout = QVBoxLayout()
        right_layout.setAlignment(Qt.AlignTop)
        right_layout.setSpacing(20)

        grp_iletisim = OrtakAraclar.create_group_box(content_widget, "İletişim Bilgileri")
        h_iletisim = QHBoxLayout(grp_iletisim)
        h_iletisim.setSpacing(15)
        
        self.ui['cep_tel'] = self._create_input_with_label(grp_iletisim, "Cep Telefonu:", "05XX...")
        self.ui['cep_tel'].setMaxLength(11); self.ui['cep_tel'].setValidator(QIntValidator())
        h_iletisim.addWidget(self.ui['cep_tel'].parentWidget())
        
        self.ui['eposta'] = self._create_input_with_label(grp_iletisim, "E-Posta Adresi:")
        h_iletisim.addWidget(self.ui['eposta'].parentWidget())
        
        right_layout.addWidget(grp_iletisim)

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
        self.ui['baslama_tarihi'] = QDateEdit(); self.ui['baslama_tarihi'].setCalendarPopup(True); self.ui['baslama_tarihi'].setDisplayFormat("dd.MM.yyyy"); self.ui['baslama_tarihi'].setMinimumHeight(40)
        self.ui['gorev_yeri'] = self._create_combo_no_label(grp_kadro)
        
        row_k2.addWidget(self._wrap_label_widget("Kurum Sicil No:", self.ui['sicil_no']), 1)
        row_k2.addWidget(self._wrap_label_widget("Başlama Tarihi:", self.ui['baslama_tarihi']), 0)
        row_k2.addWidget(self._wrap_label_widget("Görev Yeri:", self.ui['gorev_yeri']), 1)
        v_kadro.addLayout(row_k2)
        right_layout.addWidget(grp_kadro)

        grp_egitim_ana = OrtakAraclar.create_group_box(content_widget, "Eğitim Bilgileri")
        layout_egitim_ana = QHBoxLayout(grp_egitim_ana)
        layout_egitim_ana.setContentsMargins(10, 25, 10, 10)
        layout_egitim_ana.setSpacing(20)
        
        grp_uni1 = QGroupBox("Lise / Lisans / Önlisans")
        grp_uni1.setStyleSheet("QGroupBox { border: 1px solid #444; border-radius: 6px; margin-top: 10px; font-weight: bold; } QGroupBox::title { color: #4dabf7; top: -4px; left: 10px; }")
        l_uni1 = QVBoxLayout(grp_uni1)

        self.ui['okul1'] = self._create_editable_combo(grp_uni1)
        self.ui['fakulte1'] = self._create_editable_combo(grp_uni1)
        l_uni1.addWidget(self._wrap_label_widget("Okul:", self.ui['okul1']))
        l_uni1.addWidget(self._wrap_label_widget("Bölüm/Fakülte:", self.ui['fakulte1']))
        
        row_u1_2 = QHBoxLayout()
        self.ui['mezun_tarihi1'] = OrtakAraclar.create_line_edit(grp_uni1); self.ui['mezun_tarihi1'].setInputMask("99.99.9999")
        self.ui['diploma_no1'] = OrtakAraclar.create_line_edit(grp_uni1)
        row_u1_2.addWidget(self._wrap_label_widget("Mezuniyet Tarihi:", self.ui['mezun_tarihi1']))
        row_u1_2.addWidget(self._wrap_label_widget("Diploma No:", self.ui['diploma_no1']))
        l_uni1.addLayout(row_u1_2)
        
        h_d1 = QHBoxLayout()
        self.btn_view_dip1 = OrtakAraclar.create_button(grp_uni1, "👁️ Aç", lambda: self._dosya_ac("Diploma1"))
        self.btn_up_dip1 = OrtakAraclar.create_button(grp_uni1, "📤 Yükle", lambda: self._dosya_sec("Diploma1"))
        h_d1.addWidget(self.btn_view_dip1); h_d1.addWidget(self.btn_up_dip1)
        l_uni1.addLayout(h_d1)
        layout_egitim_ana.addWidget(grp_uni1)

        grp_uni2 = QGroupBox("Önlisans / Yüksek Lisans / Lisans Tamamlama")
        grp_uni2.setStyleSheet("QGroupBox { border: 1px solid #444; border-radius: 6px; margin-top: 10px; font-weight: bold; } QGroupBox::title { color: #4dabf7; top: -4px; left: 10px; }")
        l_uni2 = QVBoxLayout(grp_uni2)

        self.ui['okul2'] = self._create_editable_combo(grp_uni2)
        self.ui['fakulte2'] = self._create_editable_combo(grp_uni2)
        l_uni2.addWidget(self._wrap_label_widget("Okul:", self.ui['okul2']))
        l_uni2.addWidget(self._wrap_label_widget("Bölüm/Fakülte:", self.ui['fakulte2']))
        
        row_u2_2 = QHBoxLayout()
        self.ui['mezun_tarihi2'] = OrtakAraclar.create_line_edit(grp_uni2); self.ui['mezun_tarihi2'].setInputMask("99.99.9999")
        self.ui['diploma_no2'] = OrtakAraclar.create_line_edit(grp_uni2)
        row_u2_2.addWidget(self._wrap_label_widget("Mezuniyet Tarihi:", self.ui['mezun_tarihi2']))
        row_u2_2.addWidget(self._wrap_label_widget("Diploma No:", self.ui['diploma_no2']))
        l_uni2.addLayout(row_u2_2)
        
        h_d2 = QHBoxLayout()
        self.btn_view_dip2 = OrtakAraclar.create_button(grp_uni2, "👁️ Aç", lambda: self._dosya_ac("Diploma2"))
        self.btn_up_dip2 = OrtakAraclar.create_button(grp_uni2, "📤 Yükle", lambda: self._dosya_sec("Diploma2"))
        h_d2.addWidget(self.btn_view_dip2); h_d2.addWidget(self.btn_up_dip2)
        l_uni2.addLayout(h_d2)
        layout_egitim_ana.addWidget(grp_uni2)

        right_layout.addWidget(grp_egitim_ana)
        right_layout.addStretch()
        columns_layout.addLayout(right_layout, 6)

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)
        
        self.progress = QProgressBar(); self.progress.setVisible(False)
        main_layout.addWidget(self.progress)

    # --- YARDIMCI METODLAR ---
    def _create_input_with_label(self, parent, label_text, placeholder=""):
        container = QWidget(parent) 
        lay = QVBoxLayout(container); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(5)
        lbl = QLabel(label_text); lbl.setStyleSheet("color: #b0b0b0; font-size: 11px; font-weight: bold; text-transform: uppercase;")
        inp = OrtakAraclar.create_line_edit(container, placeholder)
        lay.addWidget(lbl); lay.addWidget(inp)
        return inp 

    def _wrap_label_widget(self, label_text, widget):
        container = QWidget(); lay = QVBoxLayout(container); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(5)
        lbl = QLabel(label_text); lbl.setStyleSheet("color: #b0b0b0; font-size: 11px; font-weight: bold; text-transform: uppercase;")
        lay.addWidget(lbl); lay.addWidget(widget)
        return container

    def _create_editable_combo(self, parent):
        combo = OrtakAraclar.create_combo_box(parent); combo.setEditable(True); combo.completer().setCompletionMode(QCompleter.PopupCompletion)
        return combo
        
    def _create_combo_no_label(self, parent): return QComboBox(parent)

    def _sabitleri_yukle(self):
        try:
            sabitler = kayitlari_getir(veritabani_getir, 'sabit', 'Sabitler')
            hizmet, unvan, gorev = set(), set(), set()
            sehir, okul, bolum = set(), set(), set()
            
            for row in sabitler:
                kod, val = str(row.get('Kod','')), str(row.get('MenuEleman',''))
                if kod == 'Drive_Klasor': self.drive_config[val] = str(row.get('Aciklama',''))
                elif kod == 'Hizmet_Sinifi': hizmet.add(val)
                elif kod == 'Kadro_Unvani': unvan.add(val)
                elif kod == 'Gorev_Yeri': gorev.add(val)
            
            tum_personel = kayitlari_getir(veritabani_getir, 'personel', 'Personel')
            for p in tum_personel:
                if p.get('Dogum_Yeri'): sehir.add(p.get('Dogum_Yeri'))
                if p.get('Mezun_Olunan_Okul'): okul.add(p.get('Mezun_Olunan_Okul'))
                if p.get('Mezun_Olunan_Fakülte'): bolum.add(p.get('Mezun_Olunan_Fakülte'))

            self.ui['hizmet_sinifi'].addItems(sorted(list(hizmet)))
            self.ui['kadro_unvani'].addItems(sorted(list(unvan)))
            self.ui['gorev_yeri'].addItems(sorted(list(gorev)))
            
            for f, l in [('dogum_yeri', sehir), ('okul1', okul), ('okul2', okul), ('fakulte1', bolum), ('fakulte2', bolum)]:
                self.ui[f].addItems(sorted(list(l)))
                
        except Exception as e: print(f"Hata: {e}")

    def _verileri_forma_yaz(self):
        mapping = {
            'tc': 0, 'ad_soyad': 1, 'dogum_yeri': 2, 'dogum_tarihi': 3,
            'sicil_no': 7, 'baslama_tarihi': 8, 'cep_tel': 9, 'eposta': 10,
            'okul1': 11, 'fakulte1': 12, 'mezun_tarihi1': 13, 'diploma_no1': 14,
            'okul2': 15, 'fakulte2': 16, 'mezun_tarihi2': 17, 'diploma_no2': 18
        }
        for key, idx in mapping.items():
            val = str(self.personel_data[idx]) if len(self.personel_data) > idx else ""
            if isinstance(self.ui[key], QLineEdit): self.ui[key].setText(val)
            elif isinstance(self.ui[key], QDateEdit): 
                try: self.ui[key].setDate(QDate.fromString(val, "dd.MM.yyyy"))
                except: pass
        
        def set_combo(key, idx):
            val = str(self.personel_data[idx]) if len(self.personel_data) > idx else ""
            cb = self.ui[key]; idx = cb.findText(val)
            if idx >= 0: cb.setCurrentIndex(idx)
            else: cb.addItem(val); cb.setCurrentText(val)
            
        set_combo('hizmet_sinifi', 4); set_combo('kadro_unvani', 5); set_combo('gorev_yeri', 6)
        set_combo('dogum_yeri', 2); set_combo('okul1', 11); set_combo('fakulte1', 12)
        set_combo('okul2', 15); set_combo('fakulte2', 16)

    def _mod_degistir(self, duzenlenebilir):
        self.duzenleme_modu = duzenlenebilir
        self.btn_duzenle.setVisible(not duzenlenebilir)
        self.btn_kaydet.setVisible(duzenlenebilir); self.btn_iptal.setVisible(duzenlenebilir)
        self.btn_resim_degis.setVisible(duzenlenebilir)
        self.btn_up_dip1.setVisible(duzenlenebilir); self.btn_up_dip2.setVisible(duzenlenebilir)
        self.btn_view_dip1.setVisible(not duzenlenebilir); self.btn_view_dip2.setVisible(not duzenlenebilir)
        
        for key, widget in self.ui.items():
            if key == 'tc': continue
            if isinstance(widget, QLineEdit): widget.setReadOnly(not duzenlenebilir)
            elif isinstance(widget, QComboBox) or isinstance(widget, QDateEdit): widget.setEnabled(duzenlenebilir)

    def _duzenle_tiklandi(self): self._mod_degistir(True)
    def _iptal_tiklandi(self): 
        if show_question("İptal", "Değişiklikleri iptal et?", self): self._verileri_forma_yaz(); self._mod_degistir(False)

    def _dosya_sec(self, key):
        f = "Resim (*.jpg *.png)" if key == "Resim" else "Belge (*.pdf *.jpg)"
        p, _ = QFileDialog.getOpenFileName(self, "Seç", "", f)
        if p:
            self.dosya_yollari[key] = p
            show_info("Seçildi", os.path.basename(p), self)
            if key == "Resim": self.lbl_resim.setPixmap(QPixmap(p).scaled(140, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _dosya_ac(self, key):
        l = self.mevcut_linkler.get(key)
        if l: QDesktopServices.openUrl(l)
        else: show_info("Yok", "Dosya yok.", self)

    def _kaydet_baslat(self):
        if not validate_required_fields([self.ui['ad_soyad'], self.ui['hizmet_sinifi']]): return
        self.btn_kaydet.setEnabled(False); self.progress.setVisible(True); self.progress.setRange(0, 0)
        data = {}
        for k, v in self.ui.items():
            if isinstance(v, QComboBox): data[k] = v.currentText()
            elif isinstance(v, QLineEdit): data[k] = v.text()
            elif isinstance(v, QDateEdit): data[k] = v.date().toString("dd.MM.yyyy")
            else: data[k] = ""
        self.worker = GuncelleWorker(self.ui['tc'].text(), data, self.dosya_yollari, self.mevcut_linkler, self.drive_config)
        self.worker.islem_tamam.connect(self._on_success); self.worker.hata_olustu.connect(self._on_error); self.worker.start()

    def _on_success(self):
        self.progress.setVisible(False); self.btn_kaydet.setEnabled(True)
        show_info("Başarılı", "Güncellendi.", self); self._mod_degistir(False); self.veri_guncellendi.emit()

    def _on_error(self, err):
        self.progress.setVisible(False); self.btn_kaydet.setEnabled(True); show_error("Hata", err, self)

    def closeEvent(self, event):
        if hasattr(self, 'resim_worker') and self.resim_worker.isRunning(): self.resim_worker.quit()
        if hasattr(self, 'worker') and self.worker.isRunning(): self.worker.quit()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    try: TemaYonetimi.uygula_fusion_dark(app)
    except: pass
    win = PersonelDetayPenceresi(["1"]*24)
    win.show()
    sys.exit(app.exec())