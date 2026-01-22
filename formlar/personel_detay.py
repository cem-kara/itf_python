# -*- coding: utf-8 -*-
import sys
import os
import logging
import re
import urllib.request 

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

# Yetki Yöneticisi
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
        pencereyi_kapat, show_info, show_error, show_question,
        validate_required_fields, create_group_box, 
        create_form_layout, add_line_edit, add_combo_box, 
        add_date_edit, kayitlari_getir
    )
except ImportError as e:
    print(f"KRİTİK HATA: Modüller yüklenemedi! {e}")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PersonelDetay")

# =============================================================================
# 1. BAŞLANGIÇ YÜKLEYİCİ (SABİTLER VE DRIVE ID'LERİ)
# =============================================================================
class BaslangicYukleyici(QThread):
    veri_hazir = Signal(dict)
    
    def run(self):
        sonuc_dict = {'Drive_Klasor': {}}
        try:
            # A. SABİTLER
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
            
            # B. PERSONEL AUTO-COMPLETE
            tum_personel = kayitlari_getir(veritabani_getir, 'personel', 'Personel')
            sehirler, okullar, bolumler = set(), set(), set()
            if tum_personel:
                for p in tum_personel:
                    if p.get('Dogum_Yeri'): sehirler.add(p.get('Dogum_Yeri').strip())
                    if p.get('Mezun_Olunan_Okul'): okullar.add(p.get('Mezun_Olunan_Okul').strip())
                    if p.get('Mezun_Olunan_Okul_2'): okullar.add(p.get('Mezun_Olunan_Okul_2').strip())
                    if p.get('Mezun_Olunan_Fakülte'): bolumler.add(p.get('Mezun_Olunan_Fakülte').strip())
                    if p.get('Mezun_Olunan_Fakülte_/_Bolüm_2'): bolumler.add(p.get('Mezun_Olunan_Fakülte_/_Bolüm_2').strip())

            for k in sonuc_dict:
                if isinstance(sonuc_dict[k], list):
                    sonuc_dict[k].sort()
                    sonuc_dict[k].insert(0, "Seçiniz...")
            
            sonuc_dict['Sehirler'] = sorted(list(sehirler))
            sonuc_dict['Okullar'] = sorted(list(okullar))
            sonuc_dict['Bolumler'] = sorted(list(bolumler))

        except Exception as e:
            logger.error(f"Başlangıç yükleme hatası: {e}")
        
        self.veri_hazir.emit(sonuc_dict)

# =============================================================================
# 2. RESİM İNDİRME İŞÇİSİ
# =============================================================================
class ResimIndirWorker(QThread):
    resim_indi = Signal(QPixmap)
    hata = Signal()

    def __init__(self, drive_url):
        super().__init__()
        self.url = drive_url

    def run(self):
        try:
            match = re.search(r'/d/([a-zA-Z0-9_-]+)', self.url)
            if match:
                file_id = match.group(1)
                direct_url = f"https://drive.google.com/uc?export=view&id={file_id}"
                data = urllib.request.urlopen(direct_url).read()
                pixmap = QPixmap()
                pixmap.loadFromData(data)
                if not pixmap.isNull():
                    self.resim_indi.emit(pixmap)
                else:
                    self.hata.emit()
            else:
                self.hata.emit()
        except Exception:
            self.hata.emit()

# =============================================================================
# 3. GÜNCELLEME İŞÇİSİ
# =============================================================================
class GuncelleWorker(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)
    
    def __init__(self, eski_tc, yeni_veri, dosya_yollari, eski_linkler, drive_ids):
        super().__init__()
        self.eski_tc = eski_tc
        self.data = yeni_veri
        self.files = dosya_yollari
        self.old_links = eski_linkler
        self.drive_ids = drive_ids

    def run(self):
        try:
            final_links = self.old_links.copy()
            tc_no = self.data.get('tc', '00000000000')

            if GoogleDriveService:
                drive = GoogleDriveService()
                id_resim = self.drive_ids.get("Personel_Resim", "")
                id_diploma = self.drive_ids.get("Personel_Diploma", "")

                for key, path in self.files.items():
                    if path and os.path.exists(path):
                        try:
                            hedef_id = id_resim if key == "Resim" else id_diploma
                            if hedef_id:
                                _, uzanti = os.path.splitext(path)
                                if key == "Resim": yeni_isim = f"{tc_no}_profil_resim{uzanti}"
                                elif key == "Diploma1": yeni_isim = f"{tc_no}_diploma_1{uzanti}"
                                elif key == "Diploma2": yeni_isim = f"{tc_no}_diploma_2{uzanti}"
                                else: yeni_isim = os.path.basename(path)

                                link = drive.upload_file(path, hedef_id, custom_name=yeni_isim)
                                if link: final_links[key] = link
                        except Exception as e:
                            print(f"{key} yükleme hatası: {e}")

            row_data = [
                self.data.get('tc'), self.data.get('ad_soyad'), self.data.get('dogum_yeri'),
                self.data.get('dogum_tarihi'), self.data.get('hizmet_sinifi'), self.data.get('kadro_unvani'),
                self.data.get('gorev_yeri'), self.data.get('sicil_no'), self.data.get('baslama_tarihi'),
                self.data.get('cep_tel'), self.data.get('eposta'), self.data.get('okul1'),
                self.data.get('fakulte1'), self.data.get('mezun_tarihi1'), self.data.get('diploma_no1'),
                self.data.get('okul2'), self.data.get('fakulte2'), self.data.get('mezun_tarihi2'),
                self.data.get('diploma_no2'),
                final_links.get('Resim', ''),
                final_links.get('Diploma1', ''),
                final_links.get('Diploma2', '')
            ]

            ws = veritabani_getir('personel', 'Personel')
            if ws:
                cell = ws.find(self.eski_tc)
                if cell:
                    ws.update(f"A{cell.row}", [row_data]) 
                    self.islem_tamam.emit()
                else:
                    self.hata_olustu.emit("Kayıt bulunamadı (TC değişmiş olabilir).")
            else:
                self.hata_olustu.emit("Veritabanı bağlantısı yok.")

        except Exception as e:
            self.hata_olustu.emit(str(e))

# =============================================================================
# 4. SİLME İŞÇİSİ
# =============================================================================
class SilWorker(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)
    def __init__(self, tc_no):
        super().__init__()
        self.tc_no = tc_no
    def run(self):
        try:
            ws = veritabani_getir('personel', 'Personel')
            if ws:
                cell = ws.find(self.tc_no)
                if cell:
                    ws.delete_rows(cell.row)
                    self.islem_tamam.emit()
                else: self.hata_olustu.emit("Kayıt bulunamadı.")
            else: self.hata_olustu.emit("Bağlantı yok.")
        except Exception as e: self.hata_olustu.emit(str(e))

# =============================================================================
# 5. DETAY FORMU (UI)
# =============================================================================
class PersonelDetayPenceresi(QWidget):
    veri_guncellendi = Signal() 

    def __init__(self, personel_data, yetki='viewer', giris_yapan_tc=None):
        super().__init__()
        self.setWindowTitle("Personel Detay ve Güncelleme")
        self.resize(1200, 800)
        
        # Değişkenleri Ata
        self.personel_data = personel_data if personel_data else []
        self.yetki = yetki
        self.giris_yapan_tc = str(giris_yapan_tc).strip()
        self.profil_tc = str(self.personel_data[0]).strip() if self.personel_data else ""

        self.ui = {}
        self.dosya_yollari = {"Resim": None, "Diploma1": None, "Diploma2": None}
        self.mevcut_linkler = {"Resim": "", "Diploma1": "", "Diploma2": ""}
        self.drive_config = {}

        # 1. Arayüzü Kur
        self._setup_ui() 

        # 2. Yetki Kontrolü (Hemen arayüzden sonra)
        # Eğer giriş yapan kişi, kendi profiline bakıyorsa kısıtlama uygulama!
        if self.giris_yapan_tc and self.profil_tc and self.giris_yapan_tc == self.profil_tc:
            pass # Kendi profili: Her şey serbest
        else:
            # Başkasının profili: Rol kısıtlamalarını uygula
            YetkiYoneticisi.uygula(self, "personel_detay")

        # 3. Verileri Arka Planda Yüklemeye Başla
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
        self.lbl_resim_onizleme = QLabel("Yükleniyor...")
        self.lbl_resim_onizleme.setFixedSize(150, 170)
        self.lbl_resim_onizleme.setStyleSheet("border: 2px dashed #666; background: #333; color: #aaa;")
        self.lbl_resim_onizleme.setScaledContents(True)
        self.lbl_resim_onizleme.setAlignment(Qt.AlignCenter)
        
        btn_resim_sec = QPushButton("Fotoğraf Değiştir...")
        btn_resim_sec.clicked.connect(self._resim_sec)
        v_resim.addWidget(self.lbl_resim_onizleme)
        v_resim.addWidget(btn_resim_sec)
        grp_resim.setLayout(v_resim)
        left_layout.addWidget(grp_resim)

        grp_kimlik = create_group_box("Kimlik")
        form_kimlik = create_form_layout()
        self.ui['tc'] = add_line_edit(form_kimlik, "TC No:", max_length=11, only_int=True)
        self.ui['tc'].setReadOnly(True) 
        self.ui['ad_soyad'] = add_line_edit(form_kimlik, "Ad Soyad:")
        self.ui['dogum_yeri'] = self._create_editable_combo(form_kimlik, "Doğum Yeri:")
        self.ui['dogum_tarihi'] = add_date_edit(form_kimlik, "Doğum Tarihi:")
        grp_kimlik.setLayout(form_kimlik)
        left_layout.addWidget(grp_kimlik)
        
        grp_iletisim = create_group_box("İletişim")
        form_iletisim = create_form_layout()
        self.ui['cep_tel'] = add_line_edit(form_iletisim, "Cep Tel:", placeholder="05XX...")
        self.ui['eposta'] = add_line_edit(form_iletisim, "E-Posta:")
        grp_iletisim.setLayout(form_iletisim)
        left_layout.addWidget(grp_iletisim)
        columns_layout.addLayout(left_layout, 1)

        # SAĞ SÜTUN
        right_layout = QVBoxLayout()
        grp_kadro = create_group_box("Kadro")
        form_kadro = create_form_layout()
        self.ui['hizmet_sinifi'] = add_combo_box(form_kadro, "Hizmet Sınıfı:", items=["Yükleniyor..."])
        self.ui['kadro_unvani'] = add_combo_box(form_kadro, "Kadro Ünvanı:", items=["Yükleniyor..."])
        self.ui['gorev_yeri'] = add_combo_box(form_kadro, "Görev Yeri:", items=["Yükleniyor..."])
        self.ui['sicil_no'] = add_line_edit(form_kadro, "Sicil No:")
        self.ui['baslama_tarihi'] = add_date_edit(form_kadro, "Başlama:")
        grp_kadro.setLayout(form_kadro)
        right_layout.addWidget(grp_kadro)
        
        grp_egitim = create_group_box("Eğitim")
        v_egitim = QVBoxLayout()
        tab_widget = QTabWidget()
        
        page1 = QWidget()
        f1 = create_form_layout()
        self.ui['okul1'] = self._create_editable_combo(f1, "Okul:")
        self.ui['fakulte1'] = self._create_editable_combo(f1, "Bölüm:")
        self.ui['mezun_tarihi1'] = add_date_edit(f1, "Tarih:")
        self.ui['diploma_no1'] = add_line_edit(f1, "Dip No:")
        h_d1 = QHBoxLayout()
        self.btn_dip1 = QPushButton("Diploma 1 (Değiştir)")
        self.btn_dip1.clicked.connect(lambda: self._dosya_sec("Diploma1", self.btn_dip1))
        h_d1.addWidget(self.btn_dip1); f1.addRow("Dosya:", h_d1)
        page1.setLayout(f1); tab_widget.addTab(page1, "1. Üni")

        page2 = QWidget()
        f2 = create_form_layout()
        self.ui['okul2'] = self._create_editable_combo(f2, "Okul:")
        self.ui['fakulte2'] = self._create_editable_combo(f2, "Bölüm:")
        self.ui['mezun_tarihi2'] = add_date_edit(f2, "Tarih:")
        self.ui['diploma_no2'] = add_line_edit(f2, "Dip No:")
        h_d2 = QHBoxLayout()
        self.btn_dip2 = QPushButton("Diploma 2 (Değiştir)")
        self.btn_dip2.clicked.connect(lambda: self._dosya_sec("Diploma2", self.btn_dip2))
        h_d2.addWidget(self.btn_dip2); f2.addRow("Dosya:", h_d2)
        page2.setLayout(f2); tab_widget.addTab(page2, "2. Üni")

        v_egitim.addWidget(tab_widget)
        grp_egitim.setLayout(v_egitim)
        right_layout.addWidget(grp_egitim)
        columns_layout.addLayout(right_layout, 2)
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        # BUTONLAR
        footer = QHBoxLayout()
        self.progress = QProgressBar(); self.progress.setVisible(False)
        self.btn_sil = QPushButton("Kaydı Sil"); self.btn_sil.setStyleSheet("background:#d32f2f;color:white;font-weight:bold;height:40px")
        self.btn_sil.clicked.connect(self._kayit_sil_onay)
        btn_iptal = QPushButton("Kapat"); btn_iptal.clicked.connect(lambda: pencereyi_kapat(self))
        self.btn_kaydet = QPushButton("Güncelle"); self.btn_kaydet.clicked.connect(self._guncelle_baslat)
        self.btn_kaydet.setStyleSheet("background:#0067c0;color:white;font-weight:bold;height:40px")
        
        footer.addWidget(self.btn_sil); footer.addWidget(self.progress); footer.addStretch()
        footer.addWidget(btn_iptal); footer.addWidget(self.btn_kaydet)
        main_layout.addLayout(footer)

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
        # 1. Sabitleri Doldur
        self.ui['hizmet_sinifi'].clear(); self.ui['hizmet_sinifi'].addItems(veriler.get('Hizmet_Sinifi', []))
        self.ui['kadro_unvani'].clear(); self.ui['kadro_unvani'].addItems(veriler.get('Kadro_Unvani', []))
        self.ui['gorev_yeri'].clear(); self.ui['gorev_yeri'].addItems(veriler.get('Gorev_Yeri', []))
        
        for field, key in [('dogum_yeri', 'Sehirler'), ('okul1', 'Okullar'), ('okul2', 'Okullar'), 
                           ('fakulte1', 'Bolumler'), ('fakulte2', 'Bolumler')]:
            self.ui[field].clear()
            self.ui[field].addItems(veriler.get(key, []))
            self.ui[field].setCurrentIndex(-1)

        self.drive_config = veriler.get('Drive_Klasor', {})

        # 2. Personel Verilerini Yerleştir
        if self.personel_data:
            self._personel_formunu_doldur()

    def _personel_formunu_doldur(self):
        try:
            d = self.personel_data
            self.ui['tc'].setText(str(d[0]))
            self.ui['ad_soyad'].setText(str(d[1]))
            self.ui['dogum_yeri'].setCurrentText(str(d[2]))
            self._tarih_set('dogum_tarihi', d[3])
            
            self.ui['hizmet_sinifi'].setCurrentText(str(d[4]))
            self.ui['kadro_unvani'].setCurrentText(str(d[5]))
            self.ui['gorev_yeri'].setCurrentText(str(d[6]))
            self.ui['sicil_no'].setText(str(d[7]))
            self._tarih_set('baslama_tarihi', d[8])
            self.ui['cep_tel'].setText(str(d[9]))
            self.ui['eposta'].setText(str(d[10]))
            
            self.ui['okul1'].setCurrentText(str(d[11]))
            self.ui['fakulte1'].setCurrentText(str(d[12]))
            self._tarih_set('mezun_tarihi1', d[13])
            self.ui['diploma_no1'].setText(str(d[14]))
            
            self.ui['okul2'].setCurrentText(str(d[15]))
            self.ui['fakulte2'].setCurrentText(str(d[16]))
            self._tarih_set('mezun_tarihi2', d[17])
            self.ui['diploma_no2'].setText(str(d[18]))
            
            if len(d) > 19: self.mevcut_linkler["Resim"] = str(d[19])
            if len(d) > 20: self.mevcut_linkler["Diploma1"] = str(d[20])
            if len(d) > 21: self.mevcut_linkler["Diploma2"] = str(d[21])
            
            if self.mevcut_linkler["Resim"]:
                self.lbl_resim_onizleme.setText("İndiriliyor...")
                self.resim_worker = ResimIndirWorker(self.mevcut_linkler["Resim"])
                self.resim_worker.resim_indi.connect(self._resim_goster)
                self.resim_worker.hata.connect(lambda: self.lbl_resim_onizleme.setText("Resim Hatalı"))
                self.resim_worker.start()
            else:
                self.lbl_resim_onizleme.setText("Fotoğraf Yok")
        except Exception as e:
            logger.error(f"Veri doldurma hatası: {e}")

    def _resim_goster(self, pixmap):
        self.lbl_resim_onizleme.setPixmap(pixmap)
        self.lbl_resim_onizleme.setStyleSheet("border: 2px solid #0067c0;")

    def _tarih_set(self, key, tarih_str):
        try:
            if tarih_str: self.ui[key].setDate(QDate.fromString(str(tarih_str), "dd.MM.yyyy"))
        except: pass

    def _resim_sec(self):
        d, _ = QFileDialog.getOpenFileName(self, "Seç", "", "Resim (*.jpg *.png)")
        if d: 
            self.dosya_yollari["Resim"] = d
            self.lbl_resim_onizleme.setPixmap(QPixmap(d))
            self.lbl_resim_onizleme.setStyleSheet("border: 2px solid #4caf50;")

    def _dosya_sec(self, key, btn):
        d, _ = QFileDialog.getOpenFileName(self, "Seç", "", "Dosya (*.pdf *.jpg)")
        if d: self.dosya_yollari[key] = d; btn.setText("Seçildi")

    def _kayit_sil_onay(self):
        if show_question(self, "Sil", "Kayıt silinsin mi?"):
            self.sil_worker = SilWorker(self.personel_data[0])
            self.sil_worker.islem_tamam.connect(self._on_sil)
            self.sil_worker.start()
    
    def _on_sil(self):
        show_info("Silindi", "Kayıt silindi.", self)
        self.veri_guncellendi.emit()
        pencereyi_kapat(self)

    def _guncelle_baslat(self):
        if not validate_required_fields([self.ui['ad_soyad']]): return
        self.btn_kaydet.setEnabled(False); self.progress.setVisible(True); self.progress.setRange(0,0)
        
        data = {}
        for k, v in self.ui.items():
            if isinstance(v, QComboBox): data[k] = v.currentText()
            elif isinstance(v, QDateEdit): data[k] = v.date().toString("dd.MM.yyyy")
            elif isinstance(v, QLineEdit): data[k] = v.text()
            else: data[k] = ""
        
        self.worker = GuncelleWorker(self.personel_data[0], data, self.dosya_yollari, self.mevcut_linkler, self.drive_config)
        self.worker.islem_tamam.connect(self._on_success)
        self.worker.hata_olustu.connect(self._on_error)
        self.worker.start()

    def _on_success(self):
        self.progress.setVisible(False); self.btn_kaydet.setEnabled(True)
        show_info("Tamam", "Güncelleme başarılı.", self)
        self.veri_guncellendi.emit()

    def _on_error(self, e):
        self.progress.setVisible(False); self.btn_kaydet.setEnabled(True)
        show_error("Hata", str(e), self)

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from temalar.tema import TemaYonetimi
    app = QApplication(sys.argv)
    TemaYonetimi.uygula_fusion_dark(app)
    # Test için boş bir data ile açılabilir
    win = PersonelDetayPenceresi(["11111111111", "Test Personel"])
    win.show()
    sys.exit(app.exec())