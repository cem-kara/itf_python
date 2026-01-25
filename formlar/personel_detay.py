# -*- coding: utf-8 -*-
import sys
import os
import logging
import urllib.request 

# PySide6 Kütüphaneleri
from PySide6.QtCore import Qt, QDate, QThread, Signal
from PySide6.QtGui import QPixmap, QDesktopServices, QAction
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFileDialog, QTabWidget, QProgressBar, QFrame,
    QComboBox, QLineEdit, QDateEdit, QFormLayout, QApplication
)

# --- YOL AYARLARI ---
# Dosyanın 'formlar' klasöründe olduğu varsayılarak proje kök dizini eklenir
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# --- PROJE MODÜLLERİ ---
try:
    # Yetki ve Araçlar
    from araclar.yetki_yonetimi import YetkiYoneticisi
    from araclar.ortak_araclar import (
        OrtakAraclar, pencereyi_kapat, show_info, show_error, show_question,
        validate_required_fields, kayitlari_getir
    )
    # Tema Yöneticisi
    from temalar.tema import TemaYonetimi

    # Google Servisleri
    from google_baglanti import veritabani_getir, InternetBaglantiHatasi, KimlikDogrulamaHatasi
    try:
        from google_baglanti import GoogleDriveService
    except ImportError:
        GoogleDriveService = None
        
except ImportError as e:
    print(f"KRİTİK HATA: Modüller yüklenemedi! {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PersonelDetay")

# =============================================================================
# WORKER: GÜNCELLEME İŞLEMİ (MANTIK KORUNDU)
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
        try:
            # 1. DOSYA YÜKLEME
            if GoogleDriveService and any(self.files.values()):
                drive = GoogleDriveService()
                
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
                            
                            link = drive.upload_file(path, hedef_id, custom_name=yeni_isim)
                            if link:
                                self.links[key] = link

            # 2. VERİTABANI GÜNCELLEME
            ws = veritabani_getir('personel', 'Personel')
            cell = ws.find(self.tc)
            
            if not cell:
                raise Exception("Personel veritabanında bulunamadı (TC değişmiş olabilir).")
                
            mevcut_satir = ws.row_values(cell.row)
            durum = mevcut_satir[-1] if mevcut_satir else "Aktif" 
            
            guncel_satir = [
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
                self.links.get('Resim', ''),
                self.links.get('Diploma1', ''),
                self.links.get('Diploma2', ''),
                durum
            ]
            
            ws.update(f"A{cell.row}:W{cell.row}", [guncel_satir])
            self.islem_tamam.emit()

        except InternetBaglantiHatasi:
            self.hata_olustu.emit("İnternet bağlantısı yok.")
        except Exception as e:
            self.hata_olustu.emit(f"Güncelleme hatası: {str(e)}")

# =============================================================================
# WORKER: RESİM İNDİRME (MANTIK KORUNDU)
# =============================================================================
class ResimIndirWorker(QThread):
    resim_indi = Signal(QPixmap)
    
    def __init__(self, url):
        super().__init__()
        self.url = url
        
    def run(self):
        try:
            if not self.url: return
            file_id = None
            if "id=" in self.url: file_id = self.url.split("id=")[1].split("&")[0]
            elif "/d/" in self.url: file_id = self.url.split("/d/")[1].split("/")[0]
            
            if file_id:
                download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
                data = urllib.request.urlopen(download_url).read()
                pixmap = QPixmap()
                pixmap.loadFromData(data)
                self.resim_indi.emit(pixmap)
        except Exception as e:
            print(f"Resim indirme hatası: {e}")

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
        self.resize(1100, 800)
        
        # State
        self.duzenleme_modu = False
        self.ui = {}
        self.dosya_yollari = {"Resim": None, "Diploma1": None, "Diploma2": None}
        self.mevcut_linkler = {
            "Resim": self.personel_data[19] if len(self.personel_data)>19 else "",
            "Diploma1": self.personel_data[20] if len(self.personel_data)>20 else "",
            "Diploma2": self.personel_data[21] if len(self.personel_data)>21 else ""
        }
        
        self.drive_config = {} 

        self._setup_ui()
        self._sabitleri_yukle()
        self._verileri_forma_yaz()
        self._mod_degistir(False) 
        
        # Yetki Kontrolü
        YetkiYoneticisi.uygula(self, "personel_detay")
        
        # Profil resmini yükle
        if self.mevcut_linkler["Resim"]:
            self.resim_worker = ResimIndirWorker(self.mevcut_linkler["Resim"])
            self.resim_worker.resim_indi.connect(lambda p: self.lbl_resim.setPixmap(p.scaled(150, 170, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            self.resim_worker.start()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        
        # --- ÜST BAR (Başlık ve Butonlar) ---
        top_bar = QHBoxLayout()
        
        self.lbl_baslik = QLabel(f"👤 {self.personel_data[1]}")
        # Başlık için tema uyumlu ancak belirgin bir stil bırakılabilir veya temaya devredilebilir.
        # Burada sadece font ayarı bırakıp rengi temadan almasını sağlıyoruz.
        self.lbl_baslik.setStyleSheet("font-size: 18px; font-weight: bold;")
        
        # Manuel renkler kaldırıldı, ID'ler korundu.
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
        
        # --- İÇERİK (Scroll) ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content_widget = QWidget()
        
        layout_cols = QHBoxLayout(content_widget)
        
        # SOL KOLON (Resim + Kimlik)
        left_lay = QVBoxLayout()
        left_lay.setAlignment(Qt.AlignTop)
        
        # Resim Alanı
        grp_resim = OrtakAraclar.create_group_box(content_widget, "Fotoğraf")
        v_res = QVBoxLayout(grp_resim)
        v_res.setAlignment(Qt.AlignCenter)
        self.lbl_resim = QLabel("Fotoğraf Yok")
        self.lbl_resim.setFixedSize(150, 170)
        # Resim çerçevesi özel olduğu için korunabilir
        self.lbl_resim.setStyleSheet("border: 2px dashed #555; background: #2b2b2b; border-radius: 8px;")
        self.lbl_resim.setScaledContents(True)
        self.btn_resim_degis = OrtakAraclar.create_button(grp_resim, "Değiştir...", lambda: self._dosya_sec("Resim"))
        self.btn_resim_degis.setVisible(False)
        v_res.addWidget(self.lbl_resim)
        v_res.addWidget(self.btn_resim_degis)
        left_lay.addWidget(grp_resim)
        
        # Kimlik Grubu
        grp_kimlik = OrtakAraclar.create_group_box(content_widget, "Kimlik Bilgileri")
        f_kimlik = QFormLayout(grp_kimlik)
        self.ui['tc'] = OrtakAraclar.create_line_edit(grp_kimlik); self.ui['tc'].setReadOnly(True)
        self.ui['ad_soyad'] = OrtakAraclar.create_line_edit(grp_kimlik)
        self.ui['dogum_yeri'] = OrtakAraclar.create_line_edit(grp_kimlik)
        self.ui['dogum_tarihi'] = OrtakAraclar.create_line_edit(grp_kimlik) 
        f_kimlik.addRow("TC No:", self.ui['tc'])
        f_kimlik.addRow("Ad Soyad:", self.ui['ad_soyad'])
        f_kimlik.addRow("Doğum Yeri:", self.ui['dogum_yeri'])
        f_kimlik.addRow("Doğum Tarihi:", self.ui['dogum_tarihi'])
        left_lay.addWidget(grp_kimlik)
        
        # İletişim
        grp_iletisim = OrtakAraclar.create_group_box(content_widget, "İletişim")
        f_ilet = QFormLayout(grp_iletisim)
        self.ui['cep_tel'] = OrtakAraclar.create_line_edit(grp_iletisim)
        self.ui['eposta'] = OrtakAraclar.create_line_edit(grp_iletisim)
        f_ilet.addRow("Telefon:", self.ui['cep_tel'])
        f_ilet.addRow("E-Posta:", self.ui['eposta'])
        left_lay.addWidget(grp_iletisim)
        
        layout_cols.addLayout(left_lay, 1)
        
        # SAĞ KOLON (Kurumsal + Eğitim)
        right_lay = QVBoxLayout()
        right_lay.setAlignment(Qt.AlignTop)
        
        # Kurumsal
        grp_kurum = OrtakAraclar.create_group_box(content_widget, "Kurumsal Bilgiler")
        grp_kurum.setFixedHeight(250)
        f_kurum = QFormLayout(grp_kurum)
        self.ui['hizmet_sinifi'] = OrtakAraclar.create_combo_box(grp_kurum)
        self.ui['kadro_unvani'] = OrtakAraclar.create_combo_box(grp_kurum)
        self.ui['gorev_yeri'] = OrtakAraclar.create_combo_box(grp_kurum)
        self.ui['sicil_no'] = OrtakAraclar.create_line_edit(grp_kurum)
        self.ui['baslama_tarihi'] = OrtakAraclar.create_line_edit(grp_kurum)
        
        f_kurum.addRow("Hizmet Sınıfı:", self.ui['hizmet_sinifi'])
        f_kurum.addRow("Kadro Ünvanı:", self.ui['kadro_unvani'])
        f_kurum.addRow("Görev Yeri:", self.ui['gorev_yeri'])
        f_kurum.addRow("Sicil No:", self.ui['sicil_no'])
        f_kurum.addRow("Başlama Tarihi:", self.ui['baslama_tarihi'])
        right_lay.addWidget(grp_kurum)
        
        # Eğitim Tabları
        grp_egitim = OrtakAraclar.create_group_box(content_widget, "Eğitim Bilgileri")
        grp_egitim.setFixedHeight(300)
        v_egitim = QVBoxLayout(grp_egitim)
        self.tab_egitim = QTabWidget()
        
        # Tab 1
        p1 = QWidget()
        fl1 = QFormLayout(p1)
        self.ui['okul1'] = OrtakAraclar.create_line_edit(p1)
        self.ui['fakulte1'] = OrtakAraclar.create_line_edit(p1)
        self.ui['mezun_tarihi1'] = OrtakAraclar.create_line_edit(p1)
        self.ui['diploma_no1'] = OrtakAraclar.create_line_edit(p1)
        
        h_d1 = QHBoxLayout()
        self.btn_view_dip1 = OrtakAraclar.create_button(p1, "👁️ Görüntüle", lambda: self._dosya_ac("Diploma1"))
        self.btn_up_dip1 = OrtakAraclar.create_button(p1, "📤 Yükle", lambda: self._dosya_sec("Diploma1"))
        h_d1.addWidget(self.btn_view_dip1); h_d1.addWidget(self.btn_up_dip1)
        
        fl1.addRow("Okul:", self.ui['okul1'])
        fl1.addRow("Bölüm:", self.ui['fakulte1'])
        fl1.addRow("Mezuniyet:", self.ui['mezun_tarihi1'])
        fl1.addRow("Diploma No:", self.ui['diploma_no1'])
        fl1.addRow("Dosya:", h_d1)
        self.tab_egitim.addTab(p1, "1. Üniversite")
        
        # Tab 2
        p2 = QWidget()
        fl2 = QFormLayout(p2)
        self.ui['okul2'] = OrtakAraclar.create_line_edit(p2)
        self.ui['fakulte2'] = OrtakAraclar.create_line_edit(p2)
        self.ui['mezun_tarihi2'] = OrtakAraclar.create_line_edit(p2)
        self.ui['diploma_no2'] = OrtakAraclar.create_line_edit(p2)
        
        h_d2 = QHBoxLayout()
        self.btn_view_dip2 = OrtakAraclar.create_button(p2, "👁️ Görüntüle", lambda: self._dosya_ac("Diploma2"))
        self.btn_up_dip2 = OrtakAraclar.create_button(p2, "📤 Yükle", lambda: self._dosya_sec("Diploma2"))
        h_d2.addWidget(self.btn_view_dip2); h_d2.addWidget(self.btn_up_dip2)
        
        fl2.addRow("Okul:", self.ui['okul2'])
        fl2.addRow("Bölüm:", self.ui['fakulte2'])
        fl2.addRow("Mezuniyet:", self.ui['mezun_tarihi2'])
        fl2.addRow("Diploma No:", self.ui['diploma_no2'])
        fl2.addRow("Dosya:", h_d2)
        self.tab_egitim.addTab(p2, "2. Üniversite")
        
        v_egitim.addWidget(self.tab_egitim)
        right_lay.addWidget(grp_egitim)
        
        layout_cols.addLayout(right_lay, 2)
        
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)
        
        # Progress Bar
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        main_layout.addWidget(self.progress)

    # --- VERİ YÖNETİMİ ---
    def _sabitleri_yukle(self):
        try:
            sabitler = kayitlari_getir(veritabani_getir, 'sabit', 'Sabitler')
            hizmet = set()
            unvan = set()
            gorev = set()
            
            for row in sabitler:
                kod = str(row.get('Kod', '')).strip()
                val = str(row.get('MenuEleman', '')).strip()
                desc = str(row.get('Aciklama', '')).strip()
                
                if kod == 'Drive_Klasor':
                    self.drive_config[val] = desc
                elif kod == 'Hizmet_Sinifi': hizmet.add(val)
                elif kod == 'Kadro_Unvani': unvan.add(val)
                elif kod == 'Gorev_Yeri': gorev.add(val)
            
            self.ui['hizmet_sinifi'].addItems(sorted(list(hizmet)))
            self.ui['kadro_unvani'].addItems(sorted(list(unvan)))
            self.ui['gorev_yeri'].addItems(sorted(list(gorev)))
            
        except Exception as e:
            print(f"Sabit yükleme hatası: {e}")

    def _verileri_forma_yaz(self):
        mapping = {
            'tc': 0, 'ad_soyad': 1, 'dogum_yeri': 2, 'dogum_tarihi': 3,
            'sicil_no': 7, 'baslama_tarihi': 8, 'cep_tel': 9, 'eposta': 10,
            'okul1': 11, 'fakulte1': 12, 'mezun_tarihi1': 13, 'diploma_no1': 14,
            'okul2': 15, 'fakulte2': 16, 'mezun_tarihi2': 17, 'diploma_no2': 18
        }
        
        for key, idx in mapping.items():
            val = str(self.personel_data[idx]) if len(self.personel_data) > idx else ""
            if isinstance(self.ui[key], QLineEdit):
                self.ui[key].setText(val)
        
        def set_combo(key, idx):
            val = str(self.personel_data[idx]) if len(self.personel_data) > idx else ""
            cb = self.ui[key]
            index = cb.findText(val)
            if index >= 0: cb.setCurrentIndex(index)
            else: cb.addItem(val); cb.setCurrentText(val)
            
        set_combo('hizmet_sinifi', 4)
        set_combo('kadro_unvani', 5)
        set_combo('gorev_yeri', 6)

    def _mod_degistir(self, duzenlenebilir):
        self.duzenleme_modu = duzenlenebilir
        
        self.btn_duzenle.setVisible(not duzenlenebilir)
        self.btn_kaydet.setVisible(duzenlenebilir)
        self.btn_iptal.setVisible(duzenlenebilir)
        
        self.btn_resim_degis.setVisible(duzenlenebilir)
        self.btn_up_dip1.setVisible(duzenlenebilir)
        self.btn_up_dip2.setVisible(duzenlenebilir)
        
        for key, widget in self.ui.items():
            if key == 'tc': continue 
            
            if isinstance(widget, QLineEdit):
                widget.setReadOnly(not duzenlenebilir)
                # Manuel stil kaldırıldı, tema.py readOnly durumunu yönetiyor
            elif isinstance(widget, QComboBox):
                widget.setEnabled(duzenlenebilir)

    def _duzenle_tiklandi(self):
        self._mod_degistir(True)

    def _iptal_tiklandi(self):
        if show_question("İptal", "Değişiklikleri iptal etmek istiyor musunuz?", self):
            self._verileri_forma_yaz()
            self.dosya_yollari = {k:None for k in self.dosya_yollari}
            self._mod_degistir(False)

    def _dosya_sec(self, key):
        file_filter = "Resim (*.jpg *.png)" if key == "Resim" else "Belge (*.pdf *.jpg)"
        path, _ = QFileDialog.getOpenFileName(self, "Dosya Seç", "", file_filter)
        if path:
            self.dosya_yollari[key] = path
            show_info("Seçildi", f"{key} için dosya seçildi:\n{os.path.basename(path)}", self)
            
            if key == "Resim": 
                self.lbl_resim.setPixmap(QPixmap(path).scaled(150, 170, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _dosya_ac(self, key):
        link = self.mevcut_linkler.get(key)
        if link:
            QDesktopServices.openUrl(link)
        else:
            show_info("Bulunamadı", "Sistemde yüklü dosya yok.", self)

    def _kaydet_baslat(self):
        if not validate_required_fields([self.ui['ad_soyad'], self.ui['hizmet_sinifi']]):
            return
            
        self.btn_kaydet.setEnabled(False)
        self.progress.setVisible(True); self.progress.setRange(0, 0)
        
        data = {}
        for k, v in self.ui.items():
            if isinstance(v, QComboBox): data[k] = v.currentText()
            elif isinstance(v, QLineEdit): data[k] = v.text()
            else: data[k] = ""
        
        self.worker = GuncelleWorker(
            self.ui['tc'].text(), 
            data, 
            self.dosya_yollari, 
            self.mevcut_linkler, 
            self.drive_config
        )
        self.worker.islem_tamam.connect(self._on_success)
        self.worker.hata_olustu.connect(self._on_error)
        self.worker.start()

    def _on_success(self):
        self.progress.setVisible(False)
        self.btn_kaydet.setEnabled(True)
        show_info("Başarılı", "Personel bilgileri güncellendi.", self)
        self._mod_degistir(False)
        self.veri_guncellendi.emit()

    def _on_error(self, err):
        self.progress.setVisible(False)
        self.btn_kaydet.setEnabled(True)
        show_error("Hata", err, self)

    def closeEvent(self, event):
        if hasattr(self, 'resim_worker') and self.resim_worker.isRunning():
            self.resim_worker.quit()
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.quit()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    try:
        TemaYonetimi.uygula_fusion_dark(app)
    except Exception as e:
        print(f"Tema uygulanamadı: {e}")
    dummy_data = ["12345678901", "Test Personel", "İst", "01.01.1990", "İdari", "Uzman", "Merkez", "101", "01.01.2020", "555", "a@a.com"] + [""]*15
    win = PersonelDetayPenceresi(dummy_data)
    win.show()
    sys.exit(app.exec())