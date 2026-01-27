# -*- coding: utf-8 -*-
import sys
import os
import logging
import random

# PySide6 Kütüphaneleri
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QTableWidgetItem, QCheckBox, QMenu, QInputDialog, 
    QApplication, QFrame, QProgressBar, QFileDialog
)

# Excel Kütüphanesi Kontrolü
try:
    import openpyxl
except ImportError:
    openpyxl = None

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# --- PROJE MODÜLLERİ ---
try:
    from araclar.yetki_yonetimi import YetkiYoneticisi
    from araclar.guvenlik import GuvenlikAraclari
    from araclar.ortak_araclar import (
        OrtakAraclar, show_info, show_error, show_question, pencereyi_kapat
    )
    from temalar.tema import TemaYonetimi
    
    from google_baglanti import (
        veritabani_getir, InternetBaglantiHatasi, 
        KimlikDogrulamaHatasi, VeritabaniBulunamadiHatasi
    )

    try:
        from formlar.personel_detay import PersonelDetayPenceresi
        from formlar.personel_ekle import PersonelEklePenceresi
        # 👇 BU SATIRI EKLEYİN 👇
        from formlar.izin_takip import IzinTakipPenceresi 
    except ImportError:
        pass

except ImportError as e:
    print(f"KRİTİK HATA: Modüller yüklenemedi! {e}")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PersonelListesi")

# =============================================================================
# WORKER SINIFLARI
# =============================================================================

class VeriYukleWorker(QThread):
    """Personel listesini çeker."""
    veri_indi = Signal(list)
    hata_olustu = Signal(str)

    def run(self):
        try:
            ws = veritabani_getir('personel', 'Personel')
            self.veri_indi.emit(ws.get_all_values())
        except InternetBaglantiHatasi:
            self.hata_olustu.emit("İnternet bağlantısı yok. Lütfen kontrol edin.")
        except KimlikDogrulamaHatasi:
            self.hata_olustu.emit("Google oturum süresi doldu. Giriş yenilenmeli.")
        except Exception as e:
            self.hata_olustu.emit(f"Veri çekme hatası: {str(e)}")

class DurumGuncelleWorker(QThread):
    """Personel durumunu günceller."""
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
                try: durum_col_idx = basliklar.index("Durum") + 1
                except ValueError: durum_col_idx = len(basliklar) + 1
                
                ws.update_cell(cell.row, durum_col_idx, self.yeni_durum)
                self.islem_tamam.emit()
            else:
                self.hata_olustu.emit("Personel veritabanında bulunamadı.")
        except Exception as e:
            self.hata_olustu.emit(f"Güncelleme hatası: {str(e)}")

class SabitlerWorker(QThread):
    """Filtreleme için Hizmet Sınıflarını çeker."""
    veri_indi = Signal(list) 
    
    def run(self):
        try:
            ws = veritabani_getir('sabit', 'Sabitler')
            hizmet_siniflari = set()
            
            if ws:
                records = ws.get_all_records()
                for satir in records:
                    kod = str(satir.get('Kod', '')).strip()
                    eleman = str(satir.get('MenuEleman', '')).strip()
                    
                    if kod == "Hizmet_Sinifi":
                        hizmet_siniflari.add(eleman)
            
            sirali_liste = sorted(list(hizmet_siniflari))
            sirali_liste.insert(0, "Tümü")
            
            self.veri_indi.emit(sirali_liste)
        except Exception as e: 
            print(f"Sabitler hatası: {e}")
            self.veri_indi.emit(["Tümü"]) 

class KullaniciEkleWorker(QThread):
    """Personeli sisteme kullanıcı olarak ekler."""
    sonuc = Signal(bool, str)
    
    def __init__(self, kimlik, ad_soyad, rol):
        super().__init__()
        self.kimlik = kimlik
        self.ad_soyad = ad_soyad
        self.rol = rol

    def run(self):
        try:
            ws = veritabani_getir('user', 'user_login')
            tum_kullanicilar = ws.get_all_records()
            for u in tum_kullanicilar:
                if str(u.get('username')) == self.kimlik:
                    self.sonuc.emit(False, "Bu personel zaten kullanıcı olarak tanımlı.")
                    return

            user_id = random.randint(10000, 99999)
            sifreli_pass = GuvenlikAraclari.sifrele("12345")
            ws.append_row([user_id, self.kimlik, sifreli_pass, self.rol, "", "EVET"])
            self.sonuc.emit(True, f"{self.ad_soyad} sisteme eklendi.\nVarsayılan Şifre: 12345")
        except Exception as e:
            self.sonuc.emit(False, f"Kullanıcı ekleme hatası: {str(e)}")

# =============================================================================
# PERSONEL LİSTESİ FORMU
# =============================================================================
class PersonelListesiPenceresi(QWidget):
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.setWindowTitle("Personel Listesi")
        self.resize(1200, 750)
        
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.ham_veri = []
        self.basliklar = []
        self.idx_durum = -1
        
        self._setup_ui()
        YetkiYoneticisi.uygula(self, "personel_listesi")
        self._sabitleri_yukle()
        self._verileri_yenile()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # --- ÜST BAR ---
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        # 1. Arama
        self.txt_ara = OrtakAraclar.create_line_edit(self, placeholder="🔍 İsim, TC veya Birim ara...")
        self.txt_ara.setMinimumWidth(250)
        self.txt_ara.textChanged.connect(self._filtrele_tetikle)

        # 2. Filtre
        self.cmb_hizmet_filtre = OrtakAraclar.create_combo_box(self)
        self.cmb_hizmet_filtre.addItem("Hizmet Sınıfı (Yükleniyor...)")
        self.cmb_hizmet_filtre.setMinimumWidth(250)
        self.cmb_hizmet_filtre.currentIndexChanged.connect(self._filtrele_tetikle)

        # 3. Checkbox
        self.chk_pasif_goster = QCheckBox("Eski Personelleri Göster")
        self.chk_pasif_goster.stateChanged.connect(self._filtrele_tetikle)

        # 4. Butonlar
        self.btn_yeni = OrtakAraclar.create_button(self, " + Yeni Personel", self._yeni_personel_ac)
        self.btn_yeni.setObjectName("btn_yeni") 
        
        self.btn_yazdir = OrtakAraclar.create_button(self, "🖨️ Excel'e Aktar", self._listeyi_yazdir)
        self.btn_yazdir.setStyleSheet("background-color: #2e7d32; color: white;") 
        
        self.btn_yenile = OrtakAraclar.create_button(self, " Yenile", self._verileri_yenile)
        self.btn_yenile.setObjectName("btn_yenile")

        top_bar.addWidget(self.txt_ara)
        top_bar.addWidget(self.cmb_hizmet_filtre)
        top_bar.addWidget(self.chk_pasif_goster)
        top_bar.addStretch() 
        top_bar.addWidget(self.btn_yeni)
        top_bar.addWidget(self.btn_yazdir)
        top_bar.addWidget(self.btn_yenile)
        
        main_layout.addLayout(top_bar)

        # --- TABLO ---
        headers = ["TC Kimlik", "Ad Soyad", "Hizmet Sınıfı", "Ünvan", "Görev Yeri", "Cep Telefonu", "Durum"]
        self.table = OrtakAraclar.create_table(self, headers)
        self.table.cellDoubleClicked.connect(self._detay_ac)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._sag_tik_menu)
        main_layout.addWidget(self.table)

        # --- FOOTER ---
        bottom_layout = QHBoxLayout()
        self.lbl_kayit_sayisi = QLabel("Toplam Kayıt: 0")
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setFixedHeight(10)
        
        bottom_layout.addWidget(self.lbl_kayit_sayisi)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.progress)
        main_layout.addLayout(bottom_layout)

    # --- İŞLEMLER ---

    def _sabitleri_yukle(self):
        self.sabit_worker = SabitlerWorker()
        self.sabit_worker.veri_indi.connect(self._sabitler_geldi)
        self.sabit_worker.start()

    def _sabitler_geldi(self, liste):
        self.cmb_hizmet_filtre.clear()
        self.cmb_hizmet_filtre.addItems(liste)

    def _verileri_yenile(self):
        self.progress.setVisible(True); self.progress.setRange(0, 0)
        self.btn_yenile.setEnabled(False)
        self.worker = VeriYukleWorker()
        self.worker.veri_indi.connect(self._veri_geldi)
        self.worker.hata_olustu.connect(self._hata_goster)
        self.worker.start()

    def _veri_geldi(self, veri_listesi):
        self.progress.setVisible(False)
        self.btn_yenile.setEnabled(True)
        if not veri_listesi: return
        
        self.basliklar = veri_listesi[0]
        self.ham_veri = veri_listesi[1:] 
        
        # Sütun İndekslerini Bul
        try: self.idx_durum = self.basliklar.index("Durum")
        except ValueError: self.idx_durum = -1
            
        self._filtrele_tetikle()

    def _hata_goster(self, mesaj):
        self.progress.setVisible(False)
        self.btn_yenile.setEnabled(True)
        show_error("Hata", mesaj, self)

    def _filtrele_tetikle(self):
        text = self.txt_ara.text().lower().strip()
        secilen_sinif = self.cmb_hizmet_filtre.currentText()
        pasifleri_goster = self.chk_pasif_goster.isChecked()
        idx_hizmet = 4 
        filtrelenmis_veri = []
        
        for satir in self.ham_veri:
            satir_str = " ".join([str(x).lower() for x in satir])
            sinif_degeri = satir[idx_hizmet] if len(satir) > idx_hizmet else ""
            durum_degeri = "Aktif"
            if self.idx_durum != -1 and len(satir) > self.idx_durum:
                durum_degeri = str(satir[self.idx_durum]).strip()
            
            if not pasifleri_goster and durum_degeri == "Pasif": continue

            if (text in satir_str) and ((secilen_sinif == "Tümü" or "Yükleniyor" in secilen_sinif) or (sinif_degeri == secilen_sinif)):
                filtrelenmis_veri.append(satir)
        self._tabloyu_doldur(filtrelenmis_veri)

    def _tabloyu_doldur(self, veri_seti):
        self.table.setRowCount(0)
        self.table.setRowCount(len(veri_seti))
        self.lbl_kayit_sayisi.setText(f"Görüntülenen Kayıt: {len(veri_seti)}")
        
        gosterilecek_indexler = [0, 1, 4, 5, 6, 9] 
        for i, row in enumerate(veri_seti):
            durum_val = row[self.idx_durum] if self.idx_durum != -1 and len(row) > self.idx_durum else "Aktif"
            col_counter = 0
            for idx in gosterilecek_indexler:
                val = row[idx] if len(row) > idx else ""
                item = QTableWidgetItem(str(val))
                self.table.setItem(i, col_counter, item)
                col_counter += 1
            
            item_durum = QTableWidgetItem(str(durum_val))
            if durum_val == "Pasif": item_durum.setForeground(Qt.red)
            else: item_durum.setForeground(Qt.green)
            self.table.setItem(i, col_counter, item_durum)
            self.table.item(i, 0).setData(Qt.UserRole, row)

    # 🟢 TEMİZLENMİŞ EXCEL YAZDIRMA
    def _listeyi_yazdir(self):
        if openpyxl is None:
            show_error("Kütüphane Hatası", "Excel yazdırma işlemi için 'openpyxl' modülü gereklidir.", self)
            return

        dosya_yolu, _ = QFileDialog.getSaveFileName(self, "Excel Olarak Kaydet", "Personel_Listesi.xlsx", "Excel Dosyası (*.xlsx)")
        if not dosya_yolu: return

        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Personel Listesi"
            
            # Başlıklar
            ws.append(["TC Kimlik", "Ad Soyad", "Hizmet Sınıfı", "Görev Yeri"])
            
            row_count = self.table.rowCount()
            for row in range(row_count):
                tc = self.table.item(row, 0).text()
                ad = self.table.item(row, 1).text()
                hizmet = self.table.item(row, 2).text()
                gorev_yeri = self.table.item(row, 4).text()
                
                ws.append([tc, ad, hizmet, gorev_yeri])
            
            for col in ws.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_length: max_length = len(cell.value)
                    except: pass
                ws.column_dimensions[column].width = (max_length + 2)

            wb.save(dosya_yolu)
            show_info("Başarılı", f"Liste başarıyla kaydedildi:\n{dosya_yolu}", self)
            
        except Exception as e:
            show_error("Yazdırma Hatası", f"Excel dosyası oluşturulamadı:\n{str(e)}", self)

    def _sag_tik_menu(self, position):
        menu = QMenu()
        secili_satir = self.table.currentRow()
        if secili_satir >= 0:
            item_tc = self.table.item(secili_satir, 0)
            item_ad = self.table.item(secili_satir, 1)
            if item_tc:
                tc_no = item_tc.text()
                ad_soyad = item_ad.text()
                row_data = item_tc.data(Qt.UserRole)
                durum = row_data[self.idx_durum] if self.idx_durum != -1 else "Aktif"
                
                act_detay = QAction("📝 Detay Görüntüle", self)
                act_detay.triggered.connect(lambda: self._detay_ac(secili_satir, 0))
                menu.addAction(act_detay)
                menu.addSeparator()
                
                # 🟢 YENİ: İzin Menüsü
                act_izin = QAction("🏖️ İzin Giriş / Takip", self)
                act_izin.triggered.connect(lambda: self._izin_formu_ac(row_data))
                menu.addAction(act_izin)
                menu.addSeparator() # Ayırıcı çizgi
                act_user = QAction("🔑 Kullanıcı Yetkilendirme", self)
                act_user.triggered.connect(lambda: self._kullanici_yap(tc_no, ad_soyad))
                menu.addAction(act_user)
                menu.addSeparator()
                act_durum = QAction(f"{'♻️ Aktif Yap' if durum == 'Pasif' else '🗑️ Pasife Al'}", self)
                act_durum.triggered.connect(lambda: self._durum_degistir(tc_no, "Aktif" if durum == "Pasif" else "Pasif"))
                menu.addAction(act_durum)
                menu.addSeparator()
                                               
        menu.exec(self.table.viewport().mapToGlobal(position))

    def _detay_ac(self, row, column):
        item = self.table.item(row, 0)
        if item:
            personel_data = item.data(Qt.UserRole)
            if 'PersonelDetayPenceresi' in globals():
                self.detay_win = PersonelDetayPenceresi(personel_data, self.yetki, self.kullanici_adi)
                self.detay_win.veri_guncellendi.connect(self._verileri_yenile)
                OrtakAraclar.mdi_pencere_ac(self, self.detay_win, f"Detay: {personel_data[1]}")
            else: show_info("Bilgi", "Detay modülü henüz yüklenmedi.", self)
            
    def _izin_formu_ac(self, personel_data):
        """Seçili personel için izin takip penceresini açar."""
        if 'IzinTakipPenceresi' in globals():
            self.izin_win = IzinTakipPenceresi(personel_data, self.yetki, self.kullanici_adi)
            OrtakAraclar.mdi_pencere_ac(self, self.izin_win, f"İzin: {personel_data[1]}")
        else:
            show_info("Bilgi", "İzin modülü henüz yüklenmedi veya dosyası eksik.", self)

    def _yeni_personel_ac(self):
        if 'PersonelEklePenceresi' in globals():
            self.ekle_win = PersonelEklePenceresi(self.yetki, self.kullanici_adi)
            OrtakAraclar.mdi_pencere_ac(self, self.ekle_win, "Yeni Personel Ekle")
        else: show_info("Bilgi", "Personel Ekleme modülü henüz yüklenmedi.", self)

    def _kullanici_yap(self, tc, ad):
        roller = ["viewer", "user", "admin", "admin_mudur"]
        rol, ok = QInputDialog.getItem(self, "Yetki Seçimi", f"{ad} için yetki düzeyi:", roller, 0, False)
        if ok and rol:
            if show_question("Onay", f"{ad} sisteme '{rol}' yetkisiyle eklenecek.\nOnaylıyor musunuz?", self):
                self.progress.setVisible(True)
                self.u_worker = KullaniciEkleWorker(tc, ad, rol)
                self.u_worker.sonuc.connect(lambda b, m: (self.progress.setVisible(False), show_info("Bilgi", m, self) if b else show_error("Hata", m, self)))
                self.u_worker.start()

    def _durum_degistir(self, tc, yeni_durum):
        if show_question("Durum Değişikliği", f"Personel durumu '{yeni_durum}' yapılacak. Emin misiniz?", self):
            self.progress.setVisible(True)
            self.d_worker = DurumGuncelleWorker(tc, yeni_durum)
            self.d_worker.islem_tamam.connect(lambda: (show_info("Başarılı", "Güncellendi", self), self._verileri_yenile()))
            self.d_worker.hata_olustu.connect(lambda m: self._hata_goster(m))
            self.d_worker.start()

    def closeEvent(self, event):
        for attr in ['worker', 'sabit_worker', 'u_worker', 'd_worker']:
            if hasattr(self, attr):
                w = getattr(self, attr)
                if w and w.isRunning(): w.quit(); w.wait(500)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    try: TemaYonetimi.uygula_fusion_dark(app)
    except Exception as e: print(f"Tema uygulanamadı: {e}")
    win = PersonelListesiPenceresi()
    win.show()
    sys.exit(app.exec())