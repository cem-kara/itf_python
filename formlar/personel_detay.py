# -*- coding: utf-8 -*-
import sys
import os
import logging
import urllib.request
import traceback
import re 

# PySide6 Kütüphaneleri
from PySide6.QtCore import Qt, QDate, QThread, Signal
from PySide6.QtGui import QPixmap, QDesktopServices, QAction, QIntValidator, QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFileDialog, QTabWidget, QProgressBar, QFrame,
    QComboBox, QLineEdit, QDateEdit, QFormLayout, QApplication, QGroupBox, QCompleter, QGridLayout, QMessageBox
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
    from gspread.cell import Cell
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
# WORKER: İZİN BİLGİLERİNİ GETİR
# =============================================================================
class IzinGetirWorker(QThread):
    veri_hazir = Signal(dict)
    
    def __init__(self, tc_kimlik):
        super().__init__()
        self.tc = str(tc_kimlik).strip()

    def run(self):
        izin_data = {}
        try:
            ws = veritabani_getir('personel', 'izin_bilgi')
            if ws:
                tum_veri = ws.get_all_records()
                hedef = next((item for item in tum_veri if str(item.get('TC_Kimlik', '')).strip() == self.tc), None)
                if hedef: izin_data = hedef
                else: izin_data = {"Hata": "Kayıt Bulunamadı"}
        except Exception as e:
            izin_data = {"Hata": str(e)}
        self.veri_hazir.emit(izin_data)

# =============================================================================
# WORKER: GÜNCELLEME VE ARŞİVLEME
# =============================================================================
class GuncelleWorker(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)
    
    def __init__(self, tc_kimlik, yeni_veri_dict, dosya_yollari, mevcut_linkler, drive_ids, pasife_al=False):
        super().__init__()
        self.tc = tc_kimlik
        self.data = yeni_veri_dict
        self.files = dosya_yollari 
        self.links = mevcut_linkler 
        self.drive_ids = drive_ids
        self.pasife_al = pasife_al # Yeni parametre: İşten çıkış mı?

    def run(self):
        temp_files_to_delete = [] 
        try:
            drive = None
            if GoogleDriveService:
                try: drive = GoogleDriveService()
                except: pass

            # ---------------------------------------------------------
            # 1. RESİM HAZIRLIĞI
            # ---------------------------------------------------------
            resim_yolu_for_word = None
            if self.files.get("Resim") and os.path.exists(self.files["Resim"]):
                resim_yolu_for_word = self.files["Resim"]
            elif self.links.get("Resim"):
                try:
                    url = self.links["Resim"]
                    fid = self._get_file_id_from_link(url)
                    if fid:
                        temp_dl_path = os.path.join(current_dir, f"temp_dl_{self.tc}.jpg")
                        dl_url = f"https://drive.google.com/uc?export=download&id={fid}"
                        try:
                            urllib.request.urlretrieve(dl_url, temp_dl_path)
                            resim_yolu_for_word = temp_dl_path
                            temp_files_to_delete.append(temp_dl_path)
                        except: pass
                except: pass

            if resim_yolu_for_word and Image:
                try:
                    img = Image.open(resim_yolu_for_word)
                    if img.mode in ("RGBA", "P", "CMYK"): img = img.convert("RGB")
                    safe_resim_path = os.path.join(current_dir, f"temp_safe_{self.tc}.jpg")
                    img.save(safe_resim_path, "JPEG", quality=95)
                    temp_files_to_delete.append(safe_resim_path)
                    resim_yolu_for_word = safe_resim_path 
                    if self.files.get("Resim"): self.files["Resim"] = safe_resim_path
                except: pass

            # ---------------------------------------------------------
            # 2. DOSYA YÜKLEME (YENİLER İÇİN ESKİLERİ SİLEREK)
            # ---------------------------------------------------------
            if drive:
                id_resim = self.drive_ids.get("Personel_Resim", "")
                id_diploma = self.drive_ids.get("Personel_Diploma", "")
                
                for key, path in self.files.items():
                    if path and os.path.exists(path):
                        # Eskiyi Sil
                        eski_link = self.links.get(key)
                        if eski_link:
                            try:
                                old_fid = self._get_file_id_from_link(eski_link)
                                if old_fid and hasattr(drive, 'service'):
                                    try: drive.service.files().delete(fileId=old_fid, supportsAllDrives=True).execute()
                                    except: pass
                            except: pass

                        # Yeniyi Yükle
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
                            except Exception as e: print(f"Upload hatası: {e}")

            # ---------------------------------------------------------
            # 3. WORD OLUŞTURMA
            # ---------------------------------------------------------
            try:
                # Eski Word'ü Sil
                eski_ozluk_link = self.links.get("OzlukDosyasi")
                if drive and eski_ozluk_link and hasattr(drive, 'service'):
                    try:
                        old_fid = self._get_file_id_from_link(eski_ozluk_link)
                        if old_fid:
                            try: drive.service.files().delete(fileId=old_fid, supportsAllDrives=True).execute()
                            except: pass
                    except: pass

                # Yeni Word'ü Oluştur
                sablon_klasoru = os.path.join(root_dir, "sablonlar")
                rapor_araci = RaporYoneticisi(sablon_klasoru)
                context = self.data.copy() # Form verilerini kopyala
                context['Kimlik_No'] = self.tc
                context['Olusturma_Tarihi'] = QDate.currentDate().toString("dd.MM.yyyy")
                
                resimler = {}
                if resim_yolu_for_word: resimler['Resim'] = resim_yolu_for_word
                
                cikti_yolu = os.path.join(current_dir, f"{self.tc}_ozluk_guncel.docx")
                basari_word = rapor_araci.word_olustur("personel_ozluk_sablon.docx", context, cikti_yolu, resimler)
                
                if basari_word and drive:
                    id_dosyalar = self.drive_ids.get("Personel_Dosyalari", "") or self.drive_ids.get("Personel_Resim", "")
                    if id_dosyalar:
                        try:
                            link = drive.upload_file(cikti_yolu, id_dosyalar, custom_name=f"{self.tc}_{self.data.get('ad_soyad')}_Ozluk.docx")
                            if link: self.links["OzlukDosyasi"] = link
                        except: pass
                    if os.path.exists(cikti_yolu): os.remove(cikti_yolu)
            except: traceback.print_exc()

            # ---------------------------------------------------------
            # 4. PASİFE ALMA İŞLEMLERİ (DRIVE TAŞIMA & İZİN SIFIRLAMA)
            # ---------------------------------------------------------
            durum_text = "Aktif"
            if self.pasife_al:
                durum_text = "Pasif"
                # A) İzin Sıfırlama
                try:
                    ws_izin = veritabani_getir('personel', 'izin_bilgi')
                    cell = ws_izin.find(self.tc)
                    if cell:
                        # K Sütunu (11. Sütun) = Sua_Cari_Yil_Kazanim -> 0 yap
                        # Eğer sütun yapısı değişirse burası patlayabilir, header kontrolü eklenebilir.
                        # Şimdilik standart yapıya (K sütunu) göre işlem yapıyoruz.
                        ws_izin.update_cell(cell.row, 11, 0) 
                        print("Pasif personel cari izin kazanımı sıfırlandı.")
                except Exception as e: print(f"İzin sıfırlama hatası: {e}")

                # B) Dosya Taşıma (Eski_Personeller Klasörüne)
                if drive and hasattr(drive, 'service'):
                    arsiv_id = self.drive_ids.get("Eski_Personeller", "")
                    if arsiv_id:
                        for k, link in self.links.items():
                            if not link: continue
                            try:
                                fid = self._get_file_id_from_link(link)
                                if fid:
                                    # Mevcut parentları bul
                                    f = drive.service.files().get(fileId=fid, fields='parents').execute()
                                    prev_parents = ",".join(f.get('parents'))
                                    # Taşı
                                    drive.service.files().update(
                                        fileId=fid, 
                                        addParents=arsiv_id, 
                                        removeParents=prev_parents,
                                        supportsAllDrives=True
                                    ).execute()
                                    print(f"{k} dosyası arşive taşındı.")
                            except Exception as e: print(f"Dosya taşıma hatası ({k}): {e}")

            # ---------------------------------------------------------
            # 5. VERİTABANI GÜNCELLEME (PERSONEL SAYFASI)
            # ---------------------------------------------------------
            ws = veritabani_getir('personel', 'Personel')
            cell = ws.find(self.tc)
            if not cell: raise Exception("Personel bulunamadı.")
            
            # Veri listesini oluştur (Sütun sırasına dikkat!)
            # 0:TC ... 23:Durum, 24:AyrilisTarihi, 25:AyrilisNedeni
            guncel_satir = [
                self.tc, self.data.get('ad_soyad', ''),
                self.data.get('dogum_yeri', ''), self.data.get('dogum_tarihi', ''),
                self.data.get('hizmet_sinifi', ''), self.data.get('kadro_unvani', ''),
                self.data.get('gorev_yeri', ''), self.data.get('sicil_no', ''),
                self.data.get('baslama_tarihi', ''), self.data.get('cep_tel', ''),
                self.data.get('eposta', ''), self.data.get('okul1', ''),
                self.data.get('fakulte1', ''), self.data.get('mezun_tarihi1', ''),
                self.data.get('diploma_no1', ''), self.data.get('okul2', ''),
                self.data.get('fakulte2', ''), self.data.get('mezun_tarihi2', ''),
                self.data.get('diploma_no2', ''), 
                self.links.get('Resim', ''), self.links.get('Diploma1', ''), 
                self.links.get('Diploma2', ''), self.links.get('OzlukDosyasi', ''), 
                durum_text, # Sütun 24 (X) -> Durum
                self.data.get('ayrilis_tarihi', ''), # Sütun 25 (Y) -> Ayrılış Tarihi
                self.data.get('ayrilma_nedeni', '')  # Sütun 26 (Z) -> Ayrılma Nedeni
            ]
            
            # Satırı güncelle (A'dan Z'ye kadar, 26 Sütun)
            ws.update(f"A{cell.row}:Z{cell.row}", [guncel_satir])
            self.islem_tamam.emit()

        except Exception as e: self.hata_olustu.emit(f"Hata: {str(e)}")
        finally:
            for p in temp_files_to_delete:
                if os.path.exists(p):
                    try: os.remove(p)
                    except: pass

    def _get_file_id_from_link(self, link):
        if not link: return None
        try:
            match = re.search(r'/d/([-\w]+)', link)
            if match: return match.group(1)
            match = re.search(r'[?&]id=([-\w]+)', link)
            if match: return match.group(1)
        except: pass
        return None

class ResimIndirWorker(QThread):
    resim_indi = Signal(QPixmap)
    def __init__(self, url): super().__init__(); self.url = url
    def run(self):
        try:
            if not self.url: return
            file_id = None
            match = re.search(r'/d/([-\w]+)', self.url)
            if match: file_id = match.group(1)
            elif "id=" in self.url: file_id = self.url.split("id=")[1].split("&")[0]
            if file_id:
                dl_url = f"https://drive.google.com/uc?export=download&id={file_id}"
                data = urllib.request.urlopen(dl_url).read()
                pix = QPixmap(); pix.loadFromData(data)
                self.resim_indi.emit(pix)
        except: pass

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
        
        # Linkleri Çek
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
        self._izin_verilerini_yukle()
        
        YetkiYoneticisi.uygula(self, "personel_detay")
        if self.mevcut_linkler["Resim"]:
            self.resim_worker = ResimIndirWorker(self.mevcut_linkler["Resim"])
            self.resim_worker.resim_indi.connect(lambda p: self.lbl_resim.setPixmap(p.scaled(140, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            self.resim_worker.start()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        
        # ÜST BAR
        top_bar = QHBoxLayout()
        self.lbl_baslik = QLabel(f"👤 {self.personel_data[1]}")
        self.lbl_baslik.setStyleSheet("font-size: 20px; font-weight: bold; color: #4dabf7;")
        self.btn_duzenle = OrtakAraclar.create_button(self, "✏️ Düzenle", self._duzenle_tiklandi)
        self.btn_kaydet = OrtakAraclar.create_button(self, "💾 Kaydet", self._kaydet_baslat); self.btn_kaydet.setVisible(False)
        self.btn_iptal = OrtakAraclar.create_button(self, "❌ İptal", self._iptal_tiklandi); self.btn_iptal.setVisible(False)
        top_bar.addWidget(self.lbl_baslik); top_bar.addStretch()
        top_bar.addWidget(self.btn_duzenle); top_bar.addWidget(self.btn_kaydet); top_bar.addWidget(self.btn_iptal)
        main_layout.addLayout(top_bar)
        
        # TABS
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #3e3e3e; border-radius: 5px; }
            QTabBar::tab { background: #2b2b2b; color: #aaa; padding: 10px 20px; }
            QTabBar::tab:selected { background: #3e3e3e; color: #fff; font-weight: bold; border-bottom: 2px solid #4dabf7; }
        """)
        self.tab_personel = QWidget(); self._setup_personel_tab(self.tab_personel)
        self.tabs.addTab(self.tab_personel, "📋 Personel Bilgileri")
        self.tab_izin = QWidget(); self._setup_izin_tab(self.tab_izin)
        self.tabs.addTab(self.tab_izin, "🏖️ İzin Durumu")
        main_layout.addWidget(self.tabs)
        
        self.progress = QProgressBar(); self.progress.setVisible(False)
        main_layout.addWidget(self.progress)

    def _setup_personel_tab(self, parent_widget):
        # Ana Layout
        layout = QVBoxLayout(parent_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        content_widget = QWidget()
        # İki sütunlu ana yapı (Sol: Kimlik, Sağ: Detaylar)
        main_h_layout = QHBoxLayout(content_widget)
        main_h_layout.setSpacing(20)
        main_h_layout.setContentsMargins(10, 10, 10, 10)
        
        # =========================================================
        # SOL SÜTUN: KİMLİK KARTI (DÜZELTİLDİ)
        # =========================================================
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setAlignment(Qt.AlignTop)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        grp_kimlik = OrtakAraclar.create_group_box(content_widget, "Kimlik Bilgileri")
        grp_kimlik.setStyleSheet("QGroupBox{font-weight:bold; border:1px solid #444; border-radius:8px; margin-top:10px;} QGroupBox::title{subcontrol-origin: margin; left: 10px; color:#4dabf7;}")
        
        v_kimlik = QVBoxLayout(grp_kimlik)
        v_kimlik.setSpacing(15)
        v_kimlik.setContentsMargins(15, 25, 15, 15)
        
        # 1. Fotoğraf Alanı (Yatayda ve Dikeyde Ortalı)
        img_layout_wrapper = QHBoxLayout()
        img_layout_wrapper.addStretch()
        
        v_img_inner = QVBoxLayout()
        v_img_inner.setSpacing(8)
        
        self.lbl_resim = QLabel("Fotoğraf Yok")
        self.lbl_resim.setFixedSize(150, 170)
        self.lbl_resim.setStyleSheet("border: 2px solid #555; background: #222; border-radius: 8px;")
        self.lbl_resim.setAlignment(Qt.AlignCenter)
        self.lbl_resim.setScaledContents(True)
        
        self.btn_resim_degis = OrtakAraclar.create_button(grp_kimlik, "📷 Değiştir", lambda: self._dosya_sec("Resim"))
        self.btn_resim_degis.setFixedWidth(150)
        self.btn_resim_degis.setStyleSheet("background-color: #333; font-size: 11px; padding: 4px;")
        
        v_img_inner.addWidget(self.lbl_resim)
        v_img_inner.addWidget(self.btn_resim_degis)
        
        img_layout_wrapper.addLayout(v_img_inner)
        img_layout_wrapper.addStretch()
        
        v_kimlik.addLayout(img_layout_wrapper)
        
        # Ayırıcı
        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken); line.setStyleSheet("background-color: #444;")
        v_kimlik.addWidget(line)

        # 2. Temel Bilgiler
        self.ui['tc'] = self._create_input_with_label(grp_kimlik, "TC Kimlik No:")
        self.ui['tc'].setReadOnly(True)
        self.ui['tc'].setStyleSheet("color: #aaa; background-color: #2b2b2b; font-weight: bold;")
        v_kimlik.addWidget(self.ui['tc'].parentWidget())

        self.ui['ad_soyad'] = self._create_input_with_label(grp_kimlik, "Adı Soyadı:")
        self.ui['ad_soyad'].setStyleSheet("font-weight: bold; font-size: 13px;")
        v_kimlik.addWidget(self.ui['ad_soyad'].parentWidget())
        
        # 3. Doğum Bilgileri (Yan Yana)
        h_dogum = QHBoxLayout()
        h_dogum.setSpacing(10)
        
        self.ui['dogum_yeri'] = self._create_editable_combo(grp_kimlik)
        self.ui['dogum_tarihi'] = QDateEdit()
        self.ui['dogum_tarihi'].setCalendarPopup(True)
        self.ui['dogum_tarihi'].setDisplayFormat("dd.MM.yyyy")
        self.ui['dogum_tarihi'].setMinimumHeight(30)
        
        h_dogum.addWidget(self._wrap_label_widget("Doğum Yeri:", self.ui['dogum_yeri']))
        h_dogum.addWidget(self._wrap_label_widget("Doğum Tarihi:", self.ui['dogum_tarihi']))
        
        v_kimlik.addLayout(h_dogum)
        
        v_kimlik.addStretch() # Aşağıyı boş bırak
        left_layout.addWidget(grp_kimlik)
        main_h_layout.addWidget(left_container, 3)

        # =========================================================
        # SAĞ SÜTUN: DETAYLAR (İLETİŞİM, KADRO, EĞİTİM, ÇIKIŞ)
        # =========================================================
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setAlignment(Qt.AlignTop)
        right_layout.setSpacing(15)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # 1. İLETİŞİM
        grp_iletisim = OrtakAraclar.create_group_box(content_widget, "İletişim Bilgileri")
        h_iletisim = QHBoxLayout(grp_iletisim); h_iletisim.setSpacing(15); h_iletisim.setContentsMargins(15, 25, 15, 15)
        self.ui['cep_tel'] = self._create_input_with_label(grp_iletisim, "Cep Telefonu:")
        self.ui['eposta'] = self._create_input_with_label(grp_iletisim, "E-Posta Adresi:")
        h_iletisim.addWidget(self.ui['cep_tel'].parentWidget())
        h_iletisim.addWidget(self.ui['eposta'].parentWidget())
        right_layout.addWidget(grp_iletisim)

        # 2. KADRO
        grp_kadro = OrtakAraclar.create_group_box(content_widget, "Kadro ve Kurumsal Bilgiler")
        v_kadro = QVBoxLayout(grp_kadro); v_kadro.setSpacing(15); v_kadro.setContentsMargins(15, 25, 15, 15)
        
        row_k1 = QHBoxLayout()
        self.ui['hizmet_sinifi'] = self._create_combo_no_label(grp_kadro)
        self.ui['kadro_unvani'] = self._create_combo_no_label(grp_kadro)
        row_k1.addWidget(self._wrap_label_widget("Hizmet Sınıfı:", self.ui['hizmet_sinifi']))
        row_k1.addWidget(self._wrap_label_widget("Kadro Ünvanı:", self.ui['kadro_unvani']))
        v_kadro.addLayout(row_k1)
        
        row_k2 = QHBoxLayout()
        self.ui['sicil_no'] = OrtakAraclar.create_line_edit(grp_kadro)
        self.ui['baslama_tarihi'] = QDateEdit(); self.ui['baslama_tarihi'].setCalendarPopup(True); self.ui['baslama_tarihi'].setDisplayFormat("dd.MM.yyyy")
        self.ui['gorev_yeri'] = self._create_combo_no_label(grp_kadro)
        row_k2.addWidget(self._wrap_label_widget("Kurum Sicil No:", self.ui['sicil_no']), 1)
        row_k2.addWidget(self._wrap_label_widget("Başlama Tarihi:", self.ui['baslama_tarihi']), 1)
        row_k2.addWidget(self._wrap_label_widget("Görev Yeri:", self.ui['gorev_yeri']), 2)
        v_kadro.addLayout(row_k2)
        right_layout.addWidget(grp_kadro)

        # 3. EĞİTİM (YAN YANA DÜZEN)
        grp_egitim = OrtakAraclar.create_group_box(content_widget, "Eğitim ve Belgeler")
        h_egitim_main = QHBoxLayout(grp_egitim)
        h_egitim_main.setSpacing(20)
        h_egitim_main.setContentsMargins(15, 25, 15, 15)
        
        # --- SOL EĞİTİM SÜTUNU ---
        v_edu1 = QVBoxLayout(); v_edu1.setSpacing(10)
        lbl_edu1 = QLabel("1. Mezuniyet / Eğitim"); lbl_edu1.setStyleSheet("color:#4dabf7; font-weight:bold; border-bottom:1px solid #444; padding-bottom:3px;")
        v_edu1.addWidget(lbl_edu1)
        self.ui['okul1'] = self._create_editable_combo(grp_egitim); v_edu1.addWidget(self._wrap_label_widget("Okul:", self.ui['okul1']))
        self.ui['fakulte1'] = self._create_editable_combo(grp_egitim); v_edu1.addWidget(self._wrap_label_widget("Bölüm / Fakülte:", self.ui['fakulte1']))
        h_dip1 = QHBoxLayout()
        self.ui['mezun_tarihi1'] = OrtakAraclar.create_line_edit(grp_egitim); self.ui['mezun_tarihi1'].setInputMask("99.99.9999")
        self.ui['diploma_no1'] = OrtakAraclar.create_line_edit(grp_egitim)
        h_dip1.addWidget(self._wrap_label_widget("Mez. Tar:", self.ui['mezun_tarihi1']))
        h_dip1.addWidget(self._wrap_label_widget("Dip. No:", self.ui['diploma_no1']))
        v_edu1.addLayout(h_dip1)
        h_btn1 = QHBoxLayout()
        self.btn_view_dip1 = OrtakAraclar.create_button(grp_egitim, "👁️ Görüntüle", lambda: self._dosya_ac("Diploma1"))
        self.btn_up_dip1 = OrtakAraclar.create_button(grp_egitim, "📤 Yükle", lambda: self._dosya_sec("Diploma1"))
        h_btn1.addWidget(self.btn_view_dip1); h_btn1.addWidget(self.btn_up_dip1)
        v_edu1.addLayout(h_btn1); v_edu1.addStretch()
        h_egitim_main.addLayout(v_edu1)
        
        # --- DİKEY AYRAÇ ---
        line_v = QFrame(); line_v.setFrameShape(QFrame.VLine); line_v.setStyleSheet("background-color: #444;"); h_egitim_main.addWidget(line_v)
        
        # --- SAĞ EĞİTİM SÜTUNU ---
        v_edu2 = QVBoxLayout(); v_edu2.setSpacing(10)
        lbl_edu2 = QLabel("2. Mezuniyet / Eğitim"); lbl_edu2.setStyleSheet("color:#4dabf7; font-weight:bold; border-bottom:1px solid #444; padding-bottom:3px;")
        v_edu2.addWidget(lbl_edu2)
        self.ui['okul2'] = self._create_editable_combo(grp_egitim); v_edu2.addWidget(self._wrap_label_widget("Okul:", self.ui['okul2']))
        self.ui['fakulte2'] = self._create_editable_combo(grp_egitim); v_edu2.addWidget(self._wrap_label_widget("Bölüm / Fakülte:", self.ui['fakulte2']))
        h_dip2 = QHBoxLayout()
        self.ui['mezun_tarihi2'] = OrtakAraclar.create_line_edit(grp_egitim); self.ui['mezun_tarihi2'].setInputMask("99.99.9999")
        self.ui['diploma_no2'] = OrtakAraclar.create_line_edit(grp_egitim)
        h_dip2.addWidget(self._wrap_label_widget("Mez. Tar:", self.ui['mezun_tarihi2']))
        h_dip2.addWidget(self._wrap_label_widget("Dip. No:", self.ui['diploma_no2']))
        v_edu2.addLayout(h_dip2)
        h_btn2 = QHBoxLayout()
        self.btn_view_dip2 = OrtakAraclar.create_button(grp_egitim, "👁️ Görüntüle", lambda: self._dosya_ac("Diploma2"))
        self.btn_up_dip2 = OrtakAraclar.create_button(grp_egitim, "📤 Yükle", lambda: self._dosya_sec("Diploma2"))
        h_btn2.addWidget(self.btn_view_dip2); h_btn2.addWidget(self.btn_up_dip2)
        v_edu2.addLayout(h_btn2); v_edu2.addStretch()
        h_egitim_main.addLayout(v_edu2)

        right_layout.addWidget(grp_egitim)

        # 4. İŞTEN ÇIKIŞ PANELİ
        grp_cikis = QGroupBox("⚠️ İşten Çıkış İşlemleri")
        grp_cikis.setStyleSheet("QGroupBox{border:1px solid #ff6b6b; border-radius:8px; margin-top:10px; background-color:#2b1b1b;} QGroupBox::title{color:#ff6b6b; font-weight:bold;}")
        h_cikis = QHBoxLayout(grp_cikis); h_cikis.setSpacing(15); h_cikis.setContentsMargins(15, 20, 15, 15)
        
        self.ui['ayrilis_tarihi'] = QDateEdit(); self.ui['ayrilis_tarihi'].setCalendarPopup(True); self.ui['ayrilis_tarihi'].setDisplayFormat("dd.MM.yyyy")
        self.ui['ayrilis_tarihi'].setDate(QDate.currentDate())
        self.ui['ayrilma_nedeni'] = OrtakAraclar.create_line_edit(grp_cikis, "Örn: İstifa, Tayin...")
        
        self.btn_pasif = QPushButton("Personeli Pasife Al")
        self.btn_pasif.setStyleSheet("background-color:#c92a2a; color:white; font-weight:bold; padding:8px; border-radius:4px;")
        self.btn_pasif.setCursor(Qt.PointingHandCursor)
        self.btn_pasif.clicked.connect(self._isten_cikar_tiklandi)
        self.btn_pasif.setVisible(False) 
        self.ui['btn_pasif'] = self.btn_pasif 

        h_cikis.addWidget(self._wrap_label_widget("Ayrılış Tarihi:", self.ui['ayrilis_tarihi']))
        h_cikis.addWidget(self._wrap_label_widget("Ayrılma Nedeni:", self.ui['ayrilma_nedeni']))
        h_cikis.addWidget(self.btn_pasif)
        right_layout.addWidget(grp_cikis)

        right_layout.addStretch() # Sağ tarafı yukarı itele
        
        main_h_layout.addWidget(right_container, 7)
        
        scroll.setWidget(content_widget)
        layout.addWidget(scroll)

    def _setup_izin_tab(self, parent_widget):
        layout = QVBoxLayout(parent_widget)
        self.lbl_izin_yukleniyor = QLabel("Veriler yükleniyor..."); self.lbl_izin_yukleniyor.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_izin_yukleniyor)
        self.izin_content = QWidget(); self.izin_content.setVisible(False)
        grid = QGridLayout(self.izin_content); grid.setSpacing(20)
        
        grp_yillik = QGroupBox("📅 Yıllık İzin"); grp_yillik.setStyleSheet("border:1px solid #555; border-radius:8px;")
        v_yillik = QVBoxLayout(grp_yillik)
        self.lbl_yillik_devir = self._create_info_row(v_yillik, "Devir:")
        self.lbl_yillik_hakedis = self._create_info_row(v_yillik, "Hak Edilen:")
        self.lbl_yillik_toplam = self._create_info_row(v_yillik, "Toplam:", bold=True)
        self.lbl_yillik_kullanilan = self._create_info_row(v_yillik, "Kullanılan:", color="#ff6b6b")
        self.lbl_yillik_kalan = self._create_info_row(v_yillik, "KALAN:", bold=True, size=16, color="#69db7c")
        grid.addWidget(grp_yillik, 0, 0)
        
        grp_sua = QGroupBox("☢️ Şua İzni"); grp_sua.setStyleSheet("border:1px solid #555; border-radius:8px;")
        v_sua = QVBoxLayout(grp_sua)
        self.lbl_sua_hak = self._create_info_row(v_sua, "Hak:")
        self.lbl_sua_kul = self._create_info_row(v_sua, "Kullanılan:", color="#ff6b6b")
        self.lbl_sua_kalan = self._create_info_row(v_sua, "KALAN:", bold=True, size=16, color="#69db7c")
        self.lbl_sua_cari = QLabel("0"); v_sua.addWidget(self.lbl_sua_cari)
        grid.addWidget(grp_sua, 0, 1)
        
        grp_diger = QGroupBox("⚠️ Diğer"); grp_diger.setStyleSheet("border:1px solid #555; border-radius:8px;")
        v_diger = QVBoxLayout(grp_diger); self.lbl_rapor_toplam = self._create_info_row(v_diger, "Toplam Rapor:")
        grid.addWidget(grp_diger, 1, 0, 1, 2)
        
        layout.addWidget(self.izin_content); layout.addStretch()

    def _create_info_row(self, layout, title, bold=False, size=12, color="#e9ecef"):
        row = QHBoxLayout(); lbl_title = QLabel(title); lbl_val = QLabel("...")
        style = f"font-size: {size}px; color: {color};"; 
        if bold: style += " font-weight: bold;"
        lbl_val.setStyleSheet(style); lbl_val.setAlignment(Qt.AlignRight)
        row.addWidget(lbl_title); row.addWidget(lbl_val); layout.addLayout(row)
        return lbl_val

    def _izin_verilerini_yukle(self):
        self.izin_worker = IzinGetirWorker(self.ui['tc'].text())
        self.izin_worker.veri_hazir.connect(self._on_izin_yuklendi)
        self.izin_worker.start()

    def _on_izin_yuklendi(self, data):
        self.lbl_izin_yukleniyor.setVisible(False); self.izin_content.setVisible(True)
        if "Hata" in data: return
        self.lbl_yillik_devir.setText(str(data.get('Yillik_Devir', 0)))
        self.lbl_yillik_hakedis.setText(str(data.get('Yillik_Hakedis', 0)))
        self.lbl_yillik_toplam.setText(str(data.get('Yillik_Toplam_Hak', 0)))
        self.lbl_yillik_kullanilan.setText(str(data.get('Yillik_Kullanilan', 0)))
        self.lbl_yillik_kalan.setText(f"{data.get('Yillik_Kalan', 0)} Gün")
        self.lbl_sua_hak.setText(str(data.get('Sua_Kullanilabilir_Hak', 0)))
        self.lbl_sua_kul.setText(str(data.get('Sua_Kullanilan', 0)))
        self.lbl_sua_kalan.setText(f"{data.get('Sua_Kalan', 0)} Gün")
        self.lbl_rapor_toplam.setText(str(data.get('Rapor_Mazeret_Top', 0)))

    # --- STANDART UI METODLARI ---
    def _create_input_with_label(self, p, t, ph=""): c=QWidget(p); l=QVBoxLayout(c); l.setContentsMargins(0,0,0,0); l.setSpacing(5); lb=QLabel(t); lb.setStyleSheet("color:#b0b0b0; font-size:11px; font-weight:bold;"); i=OrtakAraclar.create_line_edit(c, ph); l.addWidget(lb); l.addWidget(i); return i
    def _wrap_label_widget(self, t, w): c=QWidget(); l=QVBoxLayout(c); l.setContentsMargins(0,0,0,0); l.setSpacing(5); lb=QLabel(t); lb.setStyleSheet("color:#b0b0b0; font-size:11px; font-weight:bold;"); l.addWidget(lb); l.addWidget(w); return c
    def _create_editable_combo(self, p): c=OrtakAraclar.create_combo_box(p); c.setEditable(True); c.completer().setCompletionMode(QCompleter.PopupCompletion); return c
    def _create_combo_no_label(self, p): return QComboBox(p)

    def _sabitleri_yukle(self):
        try:
            s = kayitlari_getir(veritabani_getir, 'sabit', 'Sabitler')
            h, u, g = set(), set(), set(); se, ok, bo = set(), set(), set()
            for r in s:
                k, v = str(r.get('Kod','')), str(r.get('MenuEleman',''))
                if k=='Drive_Klasor': self.drive_config[v]=str(r.get('Aciklama',''))
                elif k=='Hizmet_Sinifi': h.add(v)
                elif k=='Kadro_Unvani': u.add(v)
                elif k=='Gorev_Yeri': g.add(v)
            tp = kayitlari_getir(veritabani_getir, 'personel', 'Personel')
            for p in tp:
                if p.get('Dogum_Yeri'): se.add(p.get('Dogum_Yeri'))
                if p.get('Mezun_Olunan_Okul'): ok.add(p.get('Mezun_Olunan_Okul'))
                if p.get('Mezun_Olunan_Fakülte'): bo.add(p.get('Mezun_Olunan_Fakülte'))
            self.ui['hizmet_sinifi'].addItems(sorted(list(h))); self.ui['kadro_unvani'].addItems(sorted(list(u))); self.ui['gorev_yeri'].addItems(sorted(list(g)))
            for f, l in [('dogum_yeri', se), ('okul1', ok), ('okul2', ok), ('fakulte1', bo), ('fakulte2', bo)]: self.ui[f].addItems(sorted(list(l)))
        except: pass

    def _verileri_forma_yaz(self):
        m = {'tc':0, 'ad_soyad':1, 'dogum_yeri':2, 'dogum_tarihi':3, 'sicil_no':7, 'baslama_tarihi':8, 'cep_tel':9, 'eposta':10, 'okul1':11, 'fakulte1':12, 'mezun_tarihi1':13, 'diploma_no1':14, 'okul2':15, 'fakulte2':16, 'mezun_tarihi2':17, 'diploma_no2':18, 'ayrilis_tarihi':24, 'ayrilma_nedeni':25}
        for k, i in m.items():
            val = str(self.personel_data[i]) if len(self.personel_data)>i else ""
            if isinstance(self.ui[k], QLineEdit): self.ui[k].setText(val)
            elif isinstance(self.ui[k], QDateEdit): 
                try: self.ui[k].setDate(QDate.fromString(val, "dd.MM.yyyy"))
                except: pass
        def sc(k, i):
            val = str(self.personel_data[i]) if len(self.personel_data)>i else ""
            cb = self.ui[k]; idx = cb.findText(val)
            if idx>=0: cb.setCurrentIndex(idx)
            else: cb.addItem(val); cb.setCurrentText(val)
        sc('hizmet_sinifi',4); sc('kadro_unvani',5); sc('gorev_yeri',6); sc('dogum_yeri',2); sc('okul1',11); sc('fakulte1',12); sc('okul2',15); sc('fakulte2',16)

    def _mod_degistir(self, d):
        self.duzenleme_modu = d
        self.btn_duzenle.setVisible(not d); self.btn_kaydet.setVisible(d); self.btn_iptal.setVisible(d)
        self.btn_resim_degis.setVisible(d); self.btn_up_dip1.setVisible(d); self.btn_up_dip2.setVisible(d); self.btn_view_dip1.setVisible(not d); self.btn_view_dip2.setVisible(not d)
        self.ui['btn_pasif'].setVisible(d) # Pasife Al Butonu
        for k, w in self.ui.items():
            if k in ['tc', 'btn_pasif']: continue
            if isinstance(w, (QLineEdit, QComboBox, QDateEdit)): 
                if isinstance(w, QLineEdit): w.setReadOnly(not d)
                else: w.setEnabled(d)

    def _duzenle_tiklandi(self): self._mod_degistir(True)
    def _iptal_tiklandi(self): 
        if show_question("İptal", "İptal edilsin mi?", self): self._verileri_forma_yaz(); self._mod_degistir(False)
    
    def _isten_cikar_tiklandi(self):
        neden = self.ui['ayrilma_nedeni'].text()
        tarih = self.ui['ayrilis_tarihi'].text()
        if not neden: show_error("Hata", "Lütfen ayrılma nedeni giriniz.", self); return
        
        msg = f"DİKKAT! {self.ui['ad_soyad'].text()} personeli PASİFE alınacak.\n\n" \
              f"- Dosyaları 'Eski_Personeller' klasörüne taşınacak.\n" \
              f"- Kalan izin hakları dondurulacak.\n\n" \
              f"Tarih: {tarih}\nNeden: {neden}\n\nOnaylıyor musunuz?"
        
        if show_question("Onay", msg, self):
            self._kaydet_baslat(pasife_al=True)

    def _dosya_sec(self, k):
        f = "Resim (*.jpg *.png)" if k=="Resim" else "Belge (*.pdf *.jpg)"
        p, _ = QFileDialog.getOpenFileName(self, "Seç", "", f)
        if p:
            self.dosya_yollari[k] = p
            show_info("Seçildi", os.path.basename(p), self)
            if k=="Resim": self.lbl_resim.setPixmap(QPixmap(p).scaled(140, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _dosya_ac(self, k):
        l = self.mevcut_linkler.get(k)
        if l: QDesktopServices.openUrl(l)
        else: show_info("Yok", "Dosya yok.", self)

    def _kaydet_baslat(self, pasife_al=False):
        if not validate_required_fields([self.ui['ad_soyad'], self.ui['hizmet_sinifi']]): return
        self.btn_kaydet.setEnabled(False); self.progress.setVisible(True); self.progress.setRange(0, 0)
        d = {}
        for k, v in self.ui.items():
            if isinstance(v, QComboBox): d[k] = v.currentText()
            elif isinstance(v, QLineEdit): d[k] = v.text()
            elif isinstance(v, QDateEdit): d[k] = v.date().toString("dd.MM.yyyy")
            else: d[k] = ""
        self.worker = GuncelleWorker(self.ui['tc'].text(), d, self.dosya_yollari, self.mevcut_linkler, self.drive_config, pasife_al)
        self.worker.islem_tamam.connect(self._on_success); self.worker.hata_olustu.connect(self._on_error); self.worker.start()

    def _on_success(self):
        self.progress.setVisible(False); self.btn_kaydet.setEnabled(True)
        show_info("Başarılı", "İşlem Tamamlandı.", self); self._mod_degistir(False); self.veri_guncellendi.emit()

    def _on_error(self, e):
        self.progress.setVisible(False); self.btn_kaydet.setEnabled(True); show_error("Hata", e, self)

    def closeEvent(self, e):
        if hasattr(self, 'resim_worker') and self.resim_worker.isRunning(): self.resim_worker.quit()
        if hasattr(self, 'worker') and self.worker.isRunning(): self.worker.quit()
        if hasattr(self, 'izin_worker') and self.izin_worker.isRunning(): self.izin_worker.quit()
        e.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    try: TemaYonetimi.uygula_fusion_dark(app)
    except: pass
    win = PersonelDetayPenceresi(["1"]*30)
    win.show()
    sys.exit(app.exec())