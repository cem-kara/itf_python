# -*- coding: utf-8 -*-
import sys
import os
import logging
import random
import re
import urllib.request

# PySide6 Kütüphaneleri
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QAction, QIcon, QPixmap, QColor, QFont, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QTableWidgetItem, QCheckBox, QMenu, QInputDialog, 
    QApplication, QFrame, QProgressBar, QFileDialog, QPushButton, QGroupBox,
    QHeaderView, QMessageBox
)

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
    
    # 🚀 YENİ: Service Katmanı
    from services.personel_service import PersonelService

    # Diğer formlar (Opsiyonel)
    try:
        from formlar.personel_detay import PersonelDetayPenceresi
        from formlar.personel_ekle import PersonelEklePenceresi
        from formlar.izin_takip import IzinTakipPenceresi 
    except ImportError:
        pass

except ImportError as e:
    print(f"KRİTİK HATA: Modüller yüklenemedi! {e}")
    PersonelService = None

# Excel Kütüphanesi
try: import openpyxl
except ImportError: openpyxl = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PersonelListesi")

# =============================================================================
# WORKER: AVATAR YÜKLEYİCİ (MEVCUT YAPI KORUNDU)
# =============================================================================
class AvatarWorker(QThread):
    resim_hazir = Signal(int, QPixmap) 

    def __init__(self, veri_listesi, temp_dir):
        super().__init__()
        self.veri = veri_listesi 
        self.temp_dir = temp_dir
        self.calisiyor = True

    def run(self):
        if not os.path.exists(self.temp_dir):
            try: os.makedirs(self.temp_dir)
            except: pass

        for row_idx, link, tc in self.veri:
            if not self.calisiyor: break
            if not link: continue

            local_path = os.path.join(self.temp_dir, f"{tc}_avatar.jpg")
            pixmap = QPixmap()

            # 1. Local Cache Kontrolü
            if os.path.exists(local_path):
                pixmap.load(local_path)
            else:
                # 2. İndirme
                try:
                    file_id = self._get_id(link)
                    if file_id:
                        dl_url = f"https://drive.google.com/uc?export=download&id={file_id}"
                        data = urllib.request.urlopen(dl_url, timeout=5).read()
                        pixmap.loadFromData(data)
                        if not pixmap.isNull():
                            # Resmi küçültüp kaydet (Performans için)
                            pixmap = pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            pixmap.save(local_path, "JPG")
                except:
                    continue 

            if not pixmap.isNull():
                final_pix = pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.resim_hazir.emit(row_idx, final_pix)

    def _get_id(self, link):
        try:
            match = re.search(r'/d/([-\w]+)', link)
            if match: return match.group(1)
            match = re.search(r'[?&]id=([-\w]+)', link)
            if match: return match.group(1)
        except: pass
        return None

    def durdur(self):
        self.calisiyor = False

# =============================================================================
# WORKER: VERİ İŞLEMLERİ (SERVICE ENTEGRELİ)
# =============================================================================
class VeriYukleWorker(QThread):
    """Personel listesini Service üzerinden çeker (Cache destekli)."""
    veri_indi = Signal(list)
    hata_olustu = Signal(str)
    
    def __init__(self, service):
        super().__init__()
        self.service = service

    def run(self):
        try:
            if not self.service:
                raise Exception("Personel Servisi başlatılamadı.")
                
            # Service'den veriyi liste formatında (List[Dict] veya List[List]) al
            # Burada mevcut UI yapınız List[List] (satır satır) beklediği için dönüşüm gerekebilir
            # Ancak PersonelService'i buna göre güncellediğimiz varsayılıyor veya
            # Service dict dönüyorsa burada listeye çevireceğiz.
            
            ham_veri = self.service.personel_listesi_getir(force_refresh=False)
            
            # Eğer Service List[Dict] dönüyorsa (yeni yapı), bunu List[List]'e çevir (eski yapı uyumu)
            # Not: Bu, geçiş sürecinde UI kodunu kırmamak içindir.
            if ham_veri and isinstance(ham_veri[0], dict):
                # Header oluştur
                headers = list(ham_veri[0].keys())
                liste_veri = [headers]
                for row_dict in ham_veri:
                    liste_veri.append(list(row_dict.values()))
                self.veri_indi.emit(liste_veri)
            else:
                # Zaten liste ise direkt gönder
                self.veri_indi.emit(ham_veri)
                
        except Exception as e:
            self.hata_olustu.emit(f"Veri yükleme hatası: {str(e)}")

class DurumGuncelleWorker(QThread):
    """Personel durumunu günceller."""
    islem_tamam = Signal()
    hata_olustu = Signal(str)
    
    def __init__(self, service, tc_no, yeni_durum):
        super().__init__()
        self.service = service
        self.tc_no = tc_no
        self.yeni_durum = yeni_durum

    def run(self):
        try:
            # Service üzerinden güncelleme (Bu metod service'e eklenmeli)
            # Eğer service'de yoksa repo üzerinden de yapılabilir ama doğrusu service.
            basari, msg = self.service.personel_durum_guncelle(self.tc_no, self.yeni_durum)
            
            if basari:
                self.islem_tamam.emit()
            else:
                self.hata_olustu.emit(msg)
        except Exception as e:
            self.hata_olustu.emit(f"Güncelleme hatası: {str(e)}")

class SabitlerWorker(QThread):
    """Filtreleme için sabit verileri çeker."""
    veri_indi = Signal(list, list) # Gorev Yeri Listesi, Hizmet Sınıfı Listesi
    
    def __init__(self, service):
        super().__init__()
        self.service = service

    def run(self):
        try:
            # Service metodlarını kullan
            l_gorev = self.service.sabit_degerleri_getir('Gorev_Yeri')
            l_hizmet = self.service.sabit_degerleri_getir('Hizmet_Sinifi')
            
            # UI için "Tümü" seçeneği ekle
            l_gorev.insert(0, "Tüm Birimler")
            l_hizmet.insert(0, "Tüm Sınıflar")
            
            self.veri_indi.emit(l_gorev, l_hizmet)
        except:
            self.veri_indi.emit(["Tüm Birimler"], ["Tüm Sınıflar"])

# =============================================================================
# PERSONEL LİSTESİ FORMU
# =============================================================================
class PersonelListesiPenceresi(QWidget):
    def __init__(self, yetki='viewer', kullanici_adi="Sistem"):
        super().__init__()
        self.setWindowTitle("Personel Yönetim Paneli")
        self.resize(1300, 800)
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        # 🚀 Service Başlatma
        self.service = PersonelService()
        
        self.ham_veri = []
        self.basliklar = []
        self.avatar_thread = None
        self.temp_avatar_dir = os.path.join(root_dir, "temp", "avatars")
        
        # Varsayılan Filtre
        self.secili_durum_filtresi = "Aktif" 
        self.idx_durum = -1 
        
        self._setup_ui()
        
        try: YetkiYoneticisi.uygula(self, "personel_listesi")
        except: pass
            
        self._sabitleri_yukle()
        self._verileri_yenile()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        # --- 1. ÜST FİLTRE PANELİ ---
        filter_frame = QFrame()
        filter_frame.setObjectName("filter_frame")
        filter_frame.setStyleSheet("""
            QFrame#filter_frame { background-color: #2b2b2b; border-radius: 8px; border: 1px solid #3e3e3e; }
            QPushButton { padding: 6px 15px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #444; }
        """)
        h_filter = QHBoxLayout(filter_frame)
        h_filter.setContentsMargins(10, 10, 10, 10)
        
        # Durum Butonları
        self.btn_aktif = self._create_filter_btn("Aktifler", "#28a745", lambda: self._durum_filtre_degistir("Aktif"))
        self.btn_pasif = self._create_filter_btn("Pasifler", "#dc3545", lambda: self._durum_filtre_degistir("Pasif"))
        self.btn_izinli = self._create_filter_btn("İzinliler", "#ffc107", lambda: self._durum_filtre_degistir("İzinli"), text_color="black")
        self.btn_tumu = self._create_filter_btn("Tümü", "#6c757d", lambda: self._durum_filtre_degistir("Tümü"))
        
        h_filter.addWidget(self.btn_aktif)
        h_filter.addWidget(self.btn_pasif)
        h_filter.addWidget(self.btn_izinli)
        h_filter.addWidget(self.btn_tumu)
        h_filter.addSpacing(20) 
        
        # Filtre Kutuları
        self.cmb_gorev_yeri = OrtakAraclar.create_combo_box(self)
        self.cmb_gorev_yeri.setFixedWidth(220)
        self.cmb_gorev_yeri.currentIndexChanged.connect(self._filtrele_tetikle)
        h_filter.addWidget(QLabel("Birim:"))
        h_filter.addWidget(self.cmb_gorev_yeri)

        self.cmb_hizmet_filtre = OrtakAraclar.create_combo_box(self)
        self.cmb_hizmet_filtre.setFixedWidth(180)
        self.cmb_hizmet_filtre.currentIndexChanged.connect(self._filtrele_tetikle)
        h_filter.addWidget(self.cmb_hizmet_filtre)
        
        h_filter.addStretch()
        
        # İşlem Butonları
        self.btn_yeni = OrtakAraclar.create_button(self, " + Yeni", self._yeni_personel_ac)
        self.btn_yeni.setFixedWidth(80)
        
        self.btn_yenile = OrtakAraclar.create_button(self, "⟳ Yenile", self._verileri_yenile)
        self.btn_yenile.setFixedWidth(80)
        
        h_filter.addWidget(self.btn_yeni)
        h_filter.addWidget(self.btn_yenile)
        main_layout.addWidget(filter_frame)

        # --- 2. TABLO ---
        # Tablo başlıkları (Ekranda görünecekler)
        headers = ["Foto", "TC Kimlik", "Ad Soyad", "Hizmet Sınıfı", "Ünvan", "Görev Yeri", "Cep Tel", "Durum"]
        self.table = OrtakAraclar.create_table(self, headers)
        self.table.setIconSize(QSize(32, 32)) 
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 50) 
        
        self.table.cellDoubleClicked.connect(self._detay_ac)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._sag_tik_menu)
        
        main_layout.addWidget(self.table)

        # --- 3. FOOTER ---
        footer = QHBoxLayout()
        self.lbl_info = QLabel("Hazır")
        self.progress = QProgressBar(); self.progress.setVisible(False); self.progress.setFixedWidth(200)
        self.btn_excel = OrtakAraclar.create_button(self, "Excel", self._listeyi_yazdir)
        self.btn_excel.setFixedSize(80, 30)
        
        footer.addWidget(self.lbl_info)
        footer.addStretch()
        footer.addWidget(self.progress)
        footer.addWidget(self.btn_excel)
        main_layout.addLayout(footer)

    def _create_filter_btn(self, text, color, func, text_color="white"):
        btn = QPushButton(text)
        btn.setStyleSheet(f"background-color: {color}; color: {text_color}; border: none;")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(func)
        return btn

    # --- İŞLEMLER ---
    
    def _durum_filtre_degistir(self, durum):
        self.secili_durum_filtresi = durum
        self._filtrele_tetikle()

    def _sabitleri_yukle(self):
        self.sabit_worker = SabitlerWorker(self.service)
        self.sabit_worker.veri_indi.connect(self._sabitler_geldi)
        self.sabit_worker.start()

    def _sabitler_geldi(self, birimler, siniflar):
        self.cmb_gorev_yeri.clear()
        self.cmb_gorev_yeri.addItems(birimler)
        self.cmb_hizmet_filtre.clear()
        self.cmb_hizmet_filtre.addItems(siniflar)

    def _verileri_yenile(self):
        self.progress.setVisible(True); self.progress.setRange(0, 0)
        self.btn_yenile.setEnabled(False)
        self.worker = VeriYukleWorker(self.service)
        self.worker.veri_indi.connect(self._veri_geldi)
        self.worker.hata_olustu.connect(lambda m: (self.progress.setVisible(False), show_error("Hata", m, self)))
        self.worker.start()

    def _veri_geldi(self, veri_listesi):
        self.progress.setVisible(False)
        self.btn_yenile.setEnabled(True)
        if not veri_listesi: return
        
        self.basliklar = veri_listesi[0]
        self.ham_veri = veri_listesi[1:] 
        
        # Durum sütunu bulma (Sheet'teki kolon ismi 'Durum' olmalı)
        try:
            self.idx_durum = self.basliklar.index("Durum")
        except ValueError:
            self.idx_durum = 23 # Fallback
            
        self._filtrele_tetikle() 

    def _filtrele_tetikle(self):
        if not self.ham_veri: return
        
        hedef_durum = self.secili_durum_filtresi
        hedef_birim = self.cmb_gorev_yeri.currentText()
        hedef_sinif = self.cmb_hizmet_filtre.currentText()
        
        if "Tüm" in hedef_birim: hedef_birim = ""
        if "Tüm" in hedef_sinif: hedef_sinif = ""
        
        # Sütun İndekslerini dinamik bulmaya çalışalım (Yoksa sabit)
        try: idx_sinif = self.basliklar.index("Hizmet_Sinifi")
        except: idx_sinif = 4
        
        try: idx_birim = self.basliklar.index("Gorev_Yeri")
        except: idx_birim = 6
        
        filtrelenmis = []
        for row in self.ham_veri:
            row_sinif = str(row[idx_sinif]).strip() if len(row) > idx_sinif else ""
            row_birim = str(row[idx_birim]).strip() if len(row) > idx_birim else ""
            row_durum = str(row[self.idx_durum]).strip() if len(row) > self.idx_durum else "Aktif"
            
            # Durum Filtresi
            if hedef_durum != "Tümü":
                if hedef_durum == "Aktif":
                    if row_durum == "Pasif": continue
                elif hedef_durum not in row_durum: continue
            
            # Birim ve Sınıf Filtresi
            if hedef_birim and hedef_birim != row_birim: continue
            if hedef_sinif and hedef_sinif != row_sinif: continue
            
            filtrelenmis.append(row)
            
        self._tabloyu_doldur(filtrelenmis)

    def _tabloyu_doldur(self, veri_seti):
        self.table.setRowCount(0)
        
        if self.avatar_thread and self.avatar_thread.isRunning():
            self.avatar_thread.durdur()
            self.avatar_thread.wait()
        
        self.table.setRowCount(len(veri_seti))
        self.lbl_info.setText(f"Kayıt Sayısı: {len(veri_seti)}")
        
        avatar_queue = [] 
        
        # Tabloda gösterilecek sütunların kaynak verideki indeksleri
        # [TC, Ad, Hizmet, Ünvan, Görev, Tel] -> Bunların indekslerini bulmak en iyisi
        # Şimdilik sabit: 0=TC, 1=Ad, 4=Hizmet, 5=Ünvan, 6=Görev, 9=Tel
        col_indices = [0, 1, 4, 5, 6, 9] 
        idx_resim = 19 # Resim URL'sinin olduğu sütun
        
        for i, row in enumerate(veri_seti):
            item_foto = QTableWidgetItem()
            item_foto.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, item_foto)
            
            # Resim Linki Varsa Kuyruğa Ekle
            resim_link = row[idx_resim] if len(row) > idx_resim else ""
            if resim_link: avatar_queue.append((i, resim_link, row[0]))
            
            # Diğer Sütunları Doldur
            for t_col, d_idx in enumerate(col_indices, 1): 
                val = row[d_idx] if len(row) > d_idx else ""
                item = QTableWidgetItem(str(val))
                self.table.setItem(i, t_col, item)
            
            # Durum Hücresi (Özel Renklendirme)
            durum_val = row[self.idx_durum] if len(row) > self.idx_durum else "Aktif"
            item_durum = QTableWidgetItem(durum_val)
            item_durum.setTextAlignment(Qt.AlignCenter)
            
            fg_color = Qt.white
            if "Aktif" in durum_val: fg_color = QColor("#4cd964") 
            elif "Pasif" in durum_val: fg_color = QColor("#ff3b30") 
            elif "İzin" in durum_val: fg_color = QColor("#ffcc00"); item_durum.setForeground(Qt.black)
            
            item_durum.setForeground(fg_color)
            item_durum.setFont(QFont("Segoe UI", 9, QFont.Bold))
            
            self.table.setItem(i, 7, item_durum)
            
            # Veriyi sakla (Detay ekranı için)
            self.table.item(i, 1).setData(Qt.UserRole, row)

        # Avatar yüklemeyi başlat
        if avatar_queue:
            self.avatar_thread = AvatarWorker(avatar_queue, self.temp_avatar_dir)
            self.avatar_thread.resim_hazir.connect(self._avatar_guncelle)
            self.avatar_thread.start()

    def _avatar_guncelle(self, row, pixmap):
        try:
            item = self.table.item(row, 0)
            if item: item.setIcon(QIcon(pixmap))
        except: pass

    # --- MENU VE DİĞERLERİ ---
    def _sag_tik_menu(self, pos):
        menu = QMenu()
        r = self.table.currentRow()
        if r >= 0:
            item = self.table.item(r, 1) 
            if item:
                data = item.data(Qt.UserRole)
                tc = data[0]
                durum = data[self.idx_durum] if len(data) > self.idx_durum else "Aktif"
                
                menu.addAction("📝 Detay Görüntüle", lambda: self._detay_ac(r, 0))
                menu.addSeparator()
                menu.addAction("🏖️ İzin Giriş/Takip", lambda: self._izin_formu_ac(data))
                menu.addSeparator()
                
                # Durum Değiştirme
                yeni_durum = "Aktif" if durum == "Pasif" else "Pasif"
                icon = "♻️" if durum == "Pasif" else "🗑️"
                act_d = menu.addAction(f"{icon} {yeni_durum} Yap")
                act_d.triggered.connect(lambda: self._durum_degistir(tc, yeni_durum))
                
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _detay_ac(self, r, c):
        item = self.table.item(r, 1)
        if item:
            data = item.data(Qt.UserRole)
            if 'PersonelDetayPenceresi' in globals():
                self.win_detay = PersonelDetayPenceresi(data, self.yetki, self.kullanici_adi)
                self.win_detay.veri_guncellendi.connect(self._verileri_yenile)
                OrtakAraclar.mdi_pencere_ac(self, self.win_detay, f"Detay: {data[1]}")

    def _izin_formu_ac(self, data):
        if 'IzinTakipPenceresi' in globals():
            self.win_izin = IzinTakipPenceresi(data, self.yetki, self.kullanici_adi)
            OrtakAraclar.mdi_pencere_ac(self, self.win_izin, f"İzin: {data[1]}")

    def _yeni_personel_ac(self):
        if 'PersonelEklePenceresi' in globals():
            self.win_ekle = PersonelEklePenceresi(self.yetki, self.kullanici_adi)
            OrtakAraclar.mdi_pencere_ac(self, self.win_ekle, "Personel Ekle")

    def _durum_degistir(self, tc, d):
        if show_question("Onay", f"Personel durumu '{d}' olarak güncellensin mi?", self):
            self.progress.setVisible(True)
            self.d_worker = DurumGuncelleWorker(self.service, tc, d)
            self.d_worker.islem_tamam.connect(lambda: (show_info("Başarılı", "Durum güncellendi.", self), self._verileri_yenile()))
            self.d_worker.hata_olustu.connect(lambda m: show_error("Hata", m, self))
            self.d_worker.start()

    def _listeyi_yazdir(self):
        if not openpyxl: return show_error("Eksik Modül", "Excel işlemleri için 'openpyxl' gerekli.", self)
        path, _ = QFileDialog.getSaveFileName(self, "Kaydet", "Personel_Listesi.xlsx", "Excel (*.xlsx)")
        if path:
            try:
                wb = openpyxl.Workbook(); ws = wb.active
                # Başlıkları Yaz
                ws.append(["TC Kimlik", "Ad Soyad", "Hizmet Sınıfı", "Ünvan", "Görev Yeri", "Cep Tel", "Durum"])
                # Verileri Yaz
                for r in range(self.table.rowCount()):
                    row_data = []
                    for c in range(1, 8): # 0. sütun resim olduğu için atlıyoruz
                        item = self.table.item(r, c)
                        row_data.append(item.text() if item else "")
                    ws.append(row_data)
                wb.save(path)
                show_info("Başarılı", "Liste Excel olarak kaydedildi.", self)
            except Exception as e: show_error("Hata", str(e), self)

    def closeEvent(self, e):
        if self.avatar_thread: self.avatar_thread.durdur()
        # Çalışan workerları temizle
        if hasattr(self, 'worker') and self.worker.isRunning(): self.worker.quit()
        if hasattr(self, 'sabit_worker') and self.sabit_worker.isRunning(): self.sabit_worker.quit()
        e.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    try: TemaYonetimi.uygula_fusion_dark(app)
    except: pass
    win = PersonelListesiPenceresi()
    win.show()
    sys.exit(app.exec())