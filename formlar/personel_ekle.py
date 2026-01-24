# -*- coding: utf-8 -*-
import sys
import os
import logging
from typing import Optional

# PySide6 Kütüphaneleri
from PySide6.QtCore import Qt, QDate, QThread, Signal
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFileDialog, QTabWidget, QProgressBar, QFrame,
    QComboBox, QCompleter, QLineEdit, QDateEdit, QFormLayout, QApplication
)

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from araclar.yetki_yonetimi import YetkiYoneticisi

# --- MODÜLLER ---
try:
    # Veritabanı ve Drive bağlantısı
    from google_baglanti import veritabani_getir
    try:
        from google_baglanti import GoogleDriveService, InternetBaglantiHatasi, KimlikDogrulamaHatasi
    except ImportError:
        GoogleDriveService = None
        InternetBaglantiHatasi = Exception
        KimlikDogrulamaHatasi = Exception
        print("UYARI: GoogleDriveService veya Hata Sınıfları bulunamadı.")

    # Ortak Araçlar (Yeni Sınıf Yapısı)
    from araclar.ortak_araclar import (
        OrtakAraclar, pencereyi_kapat, show_info, show_error, 
        validate_required_fields, kayitlari_getir, satir_ekle
    )
except ImportError as e:
    print(f"KRİTİK HATA: Modüller yüklenemedi! {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PersonelEkle")

# =============================================================================
# 1. BAŞLANGIÇ YÜKLEYİCİ (MANTIK AYNEN KORUNDU)
# =============================================================================
class BaslangicYukleyici(QThread):
    """
    Sabitler tablosundan ComboBox verilerini ve Drive Klasör ID'lerini çeker.
    Personel tablosundan Auto-Complete (Şehir, Okul vb.) verilerini çeker.
    """
    veri_hazir = Signal(dict)
    
    def run(self):
        sonuc_dict = {
            'Drive_Klasor': {} 
        }
        try:
            # --- A. SABİTLER TABLOSU ---
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
            
            # --- B. PERSONEL AUTO-COMPLETE ---
            tum_personel = kayitlari_getir(veritabani_getir, 'personel', 'Personel')
            sehirler, okullar, bolumler = set(), set(), set()
            
            if tum_personel:
                for p in tum_personel:
                    if p.get('Dogum_Yeri'): sehirler.add(p.get('Dogum_Yeri').strip())
                    
                    okul1 = p.get('Mezun_Olunan_Okul')
                    okul2 = p.get('Mezun_Olunan_Okul_2')
                    if okul1: okullar.add(okul1.strip())
                    if okul2: okullar.add(okul2.strip())
                    
                    fak1 = p.get('Mezun_Olunan_Fakülte')
                    fak2 = p.get('Mezun_Olunan_Fakülte_/_Bolüm_2')
                    if fak1: bolumler.add(fak1.strip())
                    if fak2: bolumler.add(fak2.strip())

            # --- C. SIRALAMA ---
            for k in sonuc_dict:
                if isinstance(sonuc_dict[k], list):
                    sonuc_dict[k].sort()
                    # "Seçiniz" ifadesini UI tarafında eklemek daha temiz, burada data saf kalsın
            
            sonuc_dict['Sehirler'] = sorted(list(sehirler))
            sonuc_dict['Okullar'] = sorted(list(okullar))
            sonuc_dict['Bolumler'] = sorted(list(bolumler))

        except Exception as e:
            logger.error(f"Başlangıç yükleme hatası: {e}")
        
        self.veri_hazir.emit(sonuc_dict)

# =============================================================================
# 2. KAYIT İŞÇİSİ (MANTIK AYNEN KORUNDU + YENİ HATA YÖNETİMİ)
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
        try:
            drive_links = {"Resim": "", "Diploma1": "", "Diploma2": ""}
            tc_no = self.data.get('tc', '00000000000')
            
            # --- 1. DOSYA YÜKLEME ---
            if GoogleDriveService:
                drive = GoogleDriveService()
                
                # ID'leri sözlükten al
                id_resim = self.drive_ids.get("Personel_Resim", "") 
                id_diploma = self.drive_ids.get("Personel_Diploma", "")

                for key, path in self.files.items():
                    if path and os.path.exists(path):
                        hedef_id = id_resim if key == "Resim" else id_diploma
                        
                        if hedef_id:
                            _, uzanti = os.path.splitext(path)
                            
                            # İsimlendirme Mantığı (Senin dosyadaki gibi)
                            if key == "Resim":
                                yeni_isim = f"{tc_no}_profil_resim{uzanti}"
                            elif key == "Diploma1":
                                yeni_isim = f"{tc_no}_diploma_1{uzanti}"
                            elif key == "Diploma2":
                                yeni_isim = f"{tc_no}_diploma_2{uzanti}"
                            else:
                                yeni_isim = os.path.basename(path)

                            # Yükleme (OrtakAraclar hatayı fırlatacak şekilde ayarlandıysa try-except dışarıda yakalar)
                            link = drive.upload_file(path, hedef_id, custom_name=yeni_isim)
                            if link:
                                drive_links[key] = link
                        else:
                            logger.warning(f"{key} için Klasör ID bulunamadı.")
            
            # --- 2. VERİ HAZIRLAMA (Liste Sırası Önemli) ---
            # Veritabanı sütun sırasına tam uyumlu olmalı
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
            # satir_ekle fonksiyonu artık boolean dönüyor
            basari = satir_ekle(veritabani_getir, 'personel', 'Personel', row)
            
            if basari:
                self.islem_tamam.emit()
            else:
                raise Exception("Veritabanına kayıt yapılamadı (API Hatası).")

        except InternetBaglantiHatasi:
            self.hata_olustu.emit("İnternet bağlantısı kesildi.")
        except KimlikDogrulamaHatasi:
            self.hata_olustu.emit("Google oturumu zaman aşımına uğradı. Programı yeniden başlatın.")
        except Exception as e:
            self.hata_olustu.emit(f"Beklenmeyen Hata: {str(e)}")

# =============================================================================
# 3. ANA FORM (MODERN UI + ORİJİNAL KONTROLLER)
# =============================================================================
class PersonelEklePenceresi(QWidget):
    def __init__(self, yetki='viewer', kullanici_adi=None): 
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi 
        
        self.setWindowTitle("Yeni Personel Ekle")
        self.resize(1200, 850)
        
        self.dosya_yollari = {"Resim": None, "Diploma1": None, "Diploma2": None}
        self.drive_config = {} 
        self.ui = {} # Widget referanslarını burada tutacağız

        self._setup_ui()
        
        # Yetki Kontrolü
        YetkiYoneticisi.uygula(self, "personel_ekle")
        
        # Verileri Yükle
        self._baslangic_yukle()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        
        # Scroll Area (Responsive olması için)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content_widget = QWidget()
        
        # İçerik Layout (İki Kolonlu)
        columns_layout = QHBoxLayout(content_widget)
        columns_layout.setSpacing(20)

        # ---------------------------
        # SOL SÜTUN
        # ---------------------------
        left_layout = QVBoxLayout()
        left_layout.setAlignment(Qt.AlignTop)

        # 1. FOTOĞRAF ALANI
        grp_resim = OrtakAraclar.create_group_box(content_widget, "Personel Fotoğrafı")
        v_resim = QVBoxLayout(grp_resim)
        v_resim.setAlignment(Qt.AlignCenter)
        
        self.lbl_resim_onizleme = QLabel("Fotoğraf Yok")
        self.lbl_resim_onizleme.setFixedSize(150, 170)
        self.lbl_resim_onizleme.setStyleSheet("border: 2px dashed #555; background: #2b2b2b; color: #aaa; border-radius: 8px;")
        self.lbl_resim_onizleme.setAlignment(Qt.AlignCenter)
        self.lbl_resim_onizleme.setScaledContents(True)
        
        btn_resim_sec = OrtakAraclar.create_button(grp_resim, "📷 Fotoğraf Seç", self._resim_sec)
        
        v_resim.addWidget(self.lbl_resim_onizleme)
        v_resim.addSpacing(10)
        v_resim.addWidget(btn_resim_sec)
        left_layout.addWidget(grp_resim)

        # 2. KİMLİK BİLGİLERİ (Orijinal alanlar korundu)
        grp_kimlik = OrtakAraclar.create_group_box(content_widget, "Kimlik Bilgileri")
        form_kimlik = QFormLayout(grp_kimlik)
        form_kimlik.setSpacing(15)
        
        self.ui['tc'] = OrtakAraclar.create_line_edit(grp_kimlik, placeholder="11 Haneli TC")
        self.ui['tc'].setMaxLength(11) # TC sınırı
        # QIntValidator manuel eklenmeli çünkü OrtakAraclar standardında yoksa
        from PySide6.QtGui import QIntValidator
        self.ui['tc'].setValidator(QIntValidator())
        
        self.ui['ad_soyad'] = OrtakAraclar.create_line_edit(grp_kimlik)
        
        # Editable Combo (Doğum Yeri için)
        self.ui['dogum_yeri'] = self._create_editable_combo(grp_kimlik)
        
        # Date Edit
        self.ui['dogum_tarihi'] = QDateEdit()
        self.ui['dogum_tarihi'].setCalendarPopup(True)
        self.ui['dogum_tarihi'].setDisplayFormat("dd.MM.yyyy")
        # Stil (OrtakAraclar'dan gelen stil ile uyumlu olması için manuel veya sınıfa eklenebilir)
        self.ui['dogum_tarihi'].setStyleSheet("QDateEdit { padding: 5px; border: 1px solid #555; background-color: #2b2b2b; color: white; border-radius: 3px; }")
        
        form_kimlik.addRow("TC Kimlik No:", self.ui['tc'])
        form_kimlik.addRow("Adı Soyadı:", self.ui['ad_soyad'])
        form_kimlik.addRow("Doğum Yeri:", self.ui['dogum_yeri'])
        form_kimlik.addRow("Doğum Tarihi:", self.ui['dogum_tarihi'])
        left_layout.addWidget(grp_kimlik)

        # 3. İLETİŞİM BİLGİLERİ
        grp_iletisim = OrtakAraclar.create_group_box(content_widget, "İletişim Bilgileri")
        form_iletisim = QFormLayout(grp_iletisim)
        form_iletisim.setSpacing(15)
        
        self.ui['cep_tel'] = OrtakAraclar.create_line_edit(grp_iletisim, "05XX...")
        self.ui['cep_tel'].setMaxLength(11)
        self.ui['cep_tel'].setValidator(QIntValidator())
        
        self.ui['eposta'] = OrtakAraclar.create_line_edit(grp_iletisim)
        
        form_iletisim.addRow("Cep Telefonu:", self.ui['cep_tel'])
        form_iletisim.addRow("E-Posta Adresi:", self.ui['eposta'])
        left_layout.addWidget(grp_iletisim)
        
        columns_layout.addLayout(left_layout, 1)

        # ---------------------------
        # SAĞ SÜTUN
        # ---------------------------
        right_layout = QVBoxLayout()
        right_layout.setAlignment(Qt.AlignTop)

        # 4. KADRO VE KURUMSAL (Orijinal alanlar korundu)
        grp_kadro = OrtakAraclar.create_group_box(content_widget, "Kadro ve Kurumsal Bilgiler")
        form_kadro = QFormLayout(grp_kadro)
        form_kadro.setSpacing(15)
        
        self.ui['hizmet_sinifi'] = OrtakAraclar.create_combo_box(grp_kadro)
        self.ui['kadro_unvani'] = OrtakAraclar.create_combo_box(grp_kadro)
        self.ui['gorev_yeri'] = OrtakAraclar.create_combo_box(grp_kadro)
        self.ui['sicil_no'] = OrtakAraclar.create_line_edit(grp_kadro)
        
        self.ui['baslama_tarihi'] = QDateEdit()
        self.ui['baslama_tarihi'].setCalendarPopup(True)
        self.ui['baslama_tarihi'].setDisplayFormat("dd.MM.yyyy")
        self.ui['baslama_tarihi'].setDate(QDate.currentDate())
        self.ui['baslama_tarihi'].setStyleSheet("QDateEdit { padding: 5px; border: 1px solid #555; background-color: #2b2b2b; color: white; border-radius: 3px; }")

        form_kadro.addRow("Hizmet Sınıfı:", self.ui['hizmet_sinifi'])
        form_kadro.addRow("Kadro Ünvanı:", self.ui['kadro_unvani'])
        form_kadro.addRow("Görev Yeri:", self.ui['gorev_yeri'])
        form_kadro.addRow("Kurum Sicil No:", self.ui['sicil_no'])
        form_kadro.addRow("Başlama Tarihi:", self.ui['baslama_tarihi'])
        right_layout.addWidget(grp_kadro)

        # 5. EĞİTİM BİLGİLERİ (Tab Yapısı Korundu)
        grp_egitim = OrtakAraclar.create_group_box(content_widget, "Eğitim Bilgileri")
        v_egitim = QVBoxLayout(grp_egitim)
        
        self.tab_widget = QTabWidget()
        # Tab stil ayarı (tema.py yapmıyorsa)
        self.tab_widget.setStyleSheet("QTabWidget::pane { border: 1px solid #444; } QTabBar::tab { background: #333; color: #aaa; padding: 8px; } QTabBar::tab:selected { background: #555; color: white; }")
        
        # --- TAB 1 ---
        page1 = QWidget()
        f1 = QFormLayout(page1)
        self.ui['okul1'] = self._create_editable_combo(page1)
        self.ui['fakulte1'] = self._create_editable_combo(page1)
        self.ui['mezun_tarihi1'] = QDateEdit(); self.ui['mezun_tarihi1'].setDisplayFormat("dd.MM.yyyy")
        self.ui['diploma_no1'] = OrtakAraclar.create_line_edit(page1)
        
        h_d1 = QHBoxLayout()
        self.btn_dip1 = OrtakAraclar.create_button(page1, "📄 Diploma 1 Yükle", lambda: self._dosya_sec("Diploma1", self.btn_dip1))
        h_d1.addWidget(self.btn_dip1)
        
        f1.addRow("Okul:", self.ui['okul1'])
        f1.addRow("Bölüm/Fakülte:", self.ui['fakulte1'])
        f1.addRow("Mezuniyet Tarihi:", self.ui['mezun_tarihi1'])
        f1.addRow("Diploma No:", self.ui['diploma_no1'])
        f1.addRow("Dosya:", h_d1)
        self.tab_widget.addTab(page1, "1. Üniversite")

        # --- TAB 2 ---
        page2 = QWidget()
        f2 = QFormLayout(page2)
        self.ui['okul2'] = self._create_editable_combo(page2)
        self.ui['fakulte2'] = self._create_editable_combo(page2)
        self.ui['mezun_tarihi2'] = QDateEdit(); self.ui['mezun_tarihi2'].setDisplayFormat("dd.MM.yyyy")
        self.ui['diploma_no2'] = OrtakAraclar.create_line_edit(page2)
        
        h_d2 = QHBoxLayout()
        self.btn_dip2 = OrtakAraclar.create_button(page2, "📄 Diploma 2 Yükle", lambda: self._dosya_sec("Diploma2", self.btn_dip2))
        h_d2.addWidget(self.btn_dip2)
        
        f2.addRow("Okul:", self.ui['okul2'])
        f2.addRow("Bölüm/Fakülte:", self.ui['fakulte2'])
        f2.addRow("Mezuniyet Tarihi:", self.ui['mezun_tarihi2'])
        f2.addRow("Diploma No:", self.ui['diploma_no2'])
        f2.addRow("Dosya:", h_d2)
        self.tab_widget.addTab(page2, "2. Üniversite")
        
        v_egitim.addWidget(self.tab_widget)
        right_layout.addWidget(grp_egitim)
        
        columns_layout.addLayout(right_layout, 2)
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        # --- FOOTER ---
        footer = QHBoxLayout()
        footer.setContentsMargins(10, 10, 10, 10)
        
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setStyleSheet("QProgressBar { border: 1px solid #555; border-radius: 5px; text-align: center; } QProgressBar::chunk { background-color: #0d47a1; }")
        
        btn_iptal = QPushButton("İptal")
        btn_iptal.setStyleSheet("background-color: transparent; border: 1px solid #d32f2f; color: #d32f2f; padding: 8px 16px; border-radius: 4px;")
        btn_iptal.clicked.connect(lambda: pencereyi_kapat(self))
        
        self.btn_kaydet = OrtakAraclar.create_button(self, "✅ Personel Kaydet", self._kaydet_baslat)
        self.btn_kaydet.setObjectName("btn_kaydet") # Yetki yönetimi için ID
        
        footer.addWidget(self.progress)
        footer.addStretch()
        footer.addWidget(btn_iptal)
        footer.addWidget(self.btn_kaydet)
        
        main_layout.addLayout(footer)
        
    def _create_editable_combo(self, parent):
        """Auto-complete özellikli Combo Box oluşturur."""
        combo = OrtakAraclar.create_combo_box(parent)
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.completer().setCompletionMode(QCompleter.PopupCompletion)
        return combo

    def _baslangic_yukle(self):
        self.loader = BaslangicYukleyici()
        self.loader.veri_hazir.connect(self._verileri_doldur)
        self.loader.start()

    def _verileri_doldur(self, veriler):
        # Sabit Comboları Doldur
        self.ui['hizmet_sinifi'].clear(); self.ui['hizmet_sinifi'].addItems(veriler.get('Hizmet_Sinifi', []))
        self.ui['kadro_unvani'].clear(); self.ui['kadro_unvani'].addItems(veriler.get('Kadro_Unvani', []))
        self.ui['gorev_yeri'].clear(); self.ui['gorev_yeri'].addItems(veriler.get('Gorev_Yeri', []))
        
        # Auto-complete Comboları Doldur
        for field, key in [('dogum_yeri', 'Sehirler'), ('okul1', 'Okullar'), ('okul2', 'Okullar'), 
                           ('fakulte1', 'Bolumler'), ('fakulte2', 'Bolumler')]:
            self.ui[field].clear()
            self.ui[field].addItems(veriler.get(key, []))
            self.ui[field].setCurrentIndex(-1)
            self.ui[field].setPlaceholderText("Seçiniz veya yazınız...")

        # Drive ID'lerini sakla
        self.drive_config = veriler.get('Drive_Klasor', {})
        if not self.drive_config:
            logger.warning("Drive ID'leri veritabanından çekilemedi.")

    def _resim_sec(self):
        d, _ = QFileDialog.getOpenFileName(self, "Fotoğraf Seç", "", "Resim (*.jpg *.png *.jpeg)")
        if d: 
            self.dosya_yollari["Resim"] = d
            self.lbl_resim_onizleme.setPixmap(QPixmap(d).scaled(150, 170, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _dosya_sec(self, key, btn):
        d, _ = QFileDialog.getOpenFileName(self, "Dosya Seç", "", "Dosya (*.pdf *.jpg *.png)")
        if d: 
            self.dosya_yollari[key] = d
            btn.setText(f"✅ Seçildi: {os.path.basename(d)[:15]}...")
            btn.setStyleSheet("background-color: #2e7d32; color: white;") # Yeşil yap

    def _kaydet_baslat(self):
        # Zorunlu Alan Kontrolü (Liste halinde widget'ları gönderiyoruz)
        zorunlu_alanlar = [self.ui['tc'], self.ui['ad_soyad'], self.ui['hizmet_sinifi']]
        if not validate_required_fields(zorunlu_alanlar):
            return

        self.btn_kaydet.setEnabled(False)
        self.btn_kaydet.setText("Kaydediliyor...")
        self.progress.setVisible(True)
        self.progress.setRange(0, 0) # Sonsuz döngü
        
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

        # Worker'ı başlat
        self.worker = KayitWorker(data, self.dosya_yollari, self.drive_config)
        self.worker.islem_tamam.connect(self._on_success)
        self.worker.hata_olustu.connect(self._on_error)
        self.worker.start()

    def _on_success(self):
        self.progress.setRange(0, 100); self.progress.setValue(100)
        self.btn_kaydet.setText("Personel Kaydet")
        self.btn_kaydet.setEnabled(True)
        show_info("Başarılı", "Personel kaydı başarıyla oluşturuldu.", self)
        pencereyi_kapat(self)

    def _on_error(self, err):
        self.progress.setVisible(False)
        self.btn_kaydet.setEnabled(True)
        self.btn_kaydet.setText("Personel Kaydet")
        show_error("Kayıt Hatası", err, self)

    def closeEvent(self, event):
        """Pencere kapatılırken threadleri temizle"""
        if hasattr(self, 'loader') and self.loader.isRunning():
            self.loader.quit(); self.loader.wait(500)
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.quit(); self.worker.wait(500)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Test için
    win = PersonelEklePenceresi()
    win.show()
    sys.exit(app.exec())