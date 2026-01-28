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
    QHeaderView
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
        from formlar.izin_takip import IzinTakipPenceresi 
    except ImportError:
        pass

except ImportError as e:
    print(f"KRİTİK HATA: Modüller yüklenemedi! {e}")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PersonelListesi")

# =============================================================================
# WORKER: AVATAR YÜKLEYİCİ (ASENKRON & CACHED)
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

            if os.path.exists(local_path):
                pixmap.load(local_path)
            else:
                try:
                    file_id = self._get_id(link)
                    if file_id:
                        dl_url = f"https://drive.google.com/uc?export=download&id={file_id}"
                        data = urllib.request.urlopen(dl_url, timeout=5).read()
                        pixmap.loadFromData(data)
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
# WORKER: VERİ İŞLEMLERİ
# =============================================================================
class VeriYukleWorker(QThread):
    veri_indi = Signal(list)
    hata_olustu = Signal(str)

    def run(self):
        try:
            ws = veritabani_getir('personel', 'Personel')
            self.veri_indi.emit(ws.get_all_values())
        except Exception as e:
            self.hata_olustu.emit(f"Veri hatası: {str(e)}")

class DurumGuncelleWorker(QThread):
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
                headers = ws.row_values(1)
                try: col = headers.index("Durum") + 1
                except: 
                    # Durum sütunu bulunamazsa varsayılan olarak 24. sütun (X)
                    col = 24 
                
                ws.update_cell(cell.row, col, self.yeni_durum)
                self.islem_tamam.emit()
            else:
                self.hata_olustu.emit("Personel bulunamadı.")
        except Exception as e:
            self.hata_olustu.emit(f"Hata: {str(e)}")

class SabitlerWorker(QThread):
    veri_indi = Signal(list, list) # Gorev Yeri Listesi, Hizmet Sınıfı Listesi

    def run(self):
        try:
            ws = veritabani_getir('sabit', 'Sabitler')
            gorev_yerleri = set()
            hizmet_siniflari = set()
            
            if ws:
                for r in ws.get_all_records():
                    kod = str(r.get('Kod')).strip()
                    val = str(r.get('MenuEleman')).strip()
                    if kod == "Gorev_Yeri":
                        gorev_yerleri.add(val)
                    elif kod == "Hizmet_Sinifi":
                        hizmet_siniflari.add(val)
            
            l_gorev = sorted(list(gorev_yerleri))
            l_gorev.insert(0, "Tüm Birimler")
            
            l_hizmet = sorted(list(hizmet_siniflari))
            l_hizmet.insert(0, "Tüm Sınıflar")
            
            self.veri_indi.emit(l_gorev, l_hizmet)
        except:
            self.veri_indi.emit(["Tüm Birimler"], ["Tüm Sınıflar"])

class KullaniciEkleWorker(QThread):
    sonuc = Signal(bool, str)
    def __init__(self, kimlik, ad, rol): super().__init__(); self.k, self.a, self.r = kimlik, ad, rol
    def run(self):
        try:
            ws = veritabani_getir('user', 'user_login')
            for u in ws.get_all_records():
                if str(u.get('username')) == self.k:
                    self.sonuc.emit(False, "Zaten kullanıcı."); return
            uid = random.randint(10000, 99999)
            pw = GuvenlikAraclari.sifrele("12345")
            ws.append_row([uid, self.k, pw, self.r, "", "EVET"])
            self.sonuc.emit(True, f"Eklendi.\nŞifre: 12345")
        except Exception as e: self.sonuc.emit(False, str(e))

# =============================================================================
# PERSONEL LİSTESİ FORMU
# =============================================================================
class PersonelListesiPenceresi(QWidget):
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.setWindowTitle("Personel Yönetim Paneli")
        self.resize(1300, 800)
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.ham_veri = []
        self.basliklar = []
        self.avatar_thread = None
        self.temp_avatar_dir = os.path.join(root_dir, "temp", "avatars")
        
        # 🟢 Varsayılan Filtre
        self.secili_durum_filtresi = "Aktif" 
        
        # 🟢 Durum Sütunu İndeksi (Otomatik bulunacak)
        self.idx_durum = -1 
        
        self._setup_ui()
        YetkiYoneticisi.uygula(self, "personel_listesi")
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
        
        # A. Durum Butonları
        self.btn_aktif = self._create_filter_btn("Aktifler", "#28a745", lambda: self._durum_filtre_degistir("Aktif"))
        self.btn_pasif = self._create_filter_btn("Pasifler", "#dc3545", lambda: self._durum_filtre_degistir("Pasif"))
        self.btn_izinli = self._create_filter_btn("İzinliler", "#ffc107", lambda: self._durum_filtre_degistir("İzinli"), text_color="black")
        self.btn_tumu = self._create_filter_btn("Tümü", "#6c757d", lambda: self._durum_filtre_degistir("Tümü"))
        
        h_filter.addWidget(self.btn_aktif)
        h_filter.addWidget(self.btn_pasif)
        h_filter.addWidget(self.btn_izinli)
        h_filter.addWidget(self.btn_tumu)
        
        h_filter.addSpacing(20) 
        
        # B. Görev Yeri Filtresi
        self.cmb_gorev_yeri = OrtakAraclar.create_combo_box(self)
        self.cmb_gorev_yeri.addItem("Birimler Yükleniyor...")
        self.cmb_gorev_yeri.setFixedWidth(220)
        self.cmb_gorev_yeri.currentIndexChanged.connect(self._filtrele_tetikle)
        h_filter.addWidget(QLabel("Birim:"))
        h_filter.addWidget(self.cmb_gorev_yeri)

        # C. Hizmet Sınıfı Filtresi
        self.cmb_hizmet_filtre = OrtakAraclar.create_combo_box(self)
        self.cmb_hizmet_filtre.addItem("Sınıflar Yükleniyor...")
        self.cmb_hizmet_filtre.setFixedWidth(180)
        self.cmb_hizmet_filtre.currentIndexChanged.connect(self._filtrele_tetikle)
        h_filter.addWidget(self.cmb_hizmet_filtre)
        
        h_filter.addStretch()
        
        # D. İşlem Butonları
        self.btn_yeni = OrtakAraclar.create_button(self, " + Yeni", self._yeni_personel_ac)
        self.btn_yeni.setFixedWidth(80)
        
        self.btn_yenile = OrtakAraclar.create_button(self, "⟳ Yenile", self._verileri_yenile)
        self.btn_yenile.setFixedWidth(80)
        
        h_filter.addWidget(self.btn_yeni)
        h_filter.addWidget(self.btn_yenile)
        
        main_layout.addWidget(filter_frame)

        # --- 2. TABLO ---
        headers = ["Foto", "TC Kimlik", "Ad Soyad", "Hizmet Sınıfı", "Ünvan", "Görev Yeri", "Cep Tel", "Durum"]
        self.table = OrtakAraclar.create_table(self, headers)
        self.table.setIconSize(QSize(32, 32)) 
        
        # Sütun Genişlik Ayarı (Resim Sabit, Diğerleri Yayıl)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch) # Varsayılan: Yayıl
        header.setSectionResizeMode(0, QHeaderView.Fixed) # İstisna: Resim Sabit
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
        self.sabit_worker = SabitlerWorker()
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
        self.worker = VeriYukleWorker()
        self.worker.veri_indi.connect(self._veri_geldi)
        self.worker.hata_olustu.connect(lambda m: (self.progress.setVisible(False), show_error("Hata", m, self)))
        self.worker.start()

    def _veri_geldi(self, veri_listesi):
        self.progress.setVisible(False)
        self.btn_yenile.setEnabled(True)
        if not veri_listesi: return
        
        self.basliklar = veri_listesi[0]
        self.ham_veri = veri_listesi[1:] 
        
        # 🟢 Durum Sütununu Otomatik Bul (Hata Çözümü)
        try:
            self.idx_durum = self.basliklar.index("Durum")
        except ValueError:
            # Bulamazsa varsayılan 23 (X sütunu)
            self.idx_durum = 23
            
        self._filtrele_tetikle() 

    def _filtrele_tetikle(self):
        if not self.ham_veri: return
        
        hedef_durum = self.secili_durum_filtresi
        hedef_birim = self.cmb_gorev_yeri.currentText()
        hedef_sinif = self.cmb_hizmet_filtre.currentText()
        
        if "Tüm" in hedef_birim: hedef_birim = ""
        if "Tüm" in hedef_sinif: hedef_sinif = ""
        
        # Sütun İndeksleri
        idx_sinif = 4
        idx_birim = 6
        # idx_durum artık dinamik bulunuyor (self.idx_durum)
        
        filtrelenmis = []
        for row in self.ham_veri:
            row_sinif = str(row[idx_sinif]).strip() if len(row) > idx_sinif else ""
            row_birim = str(row[idx_birim]).strip() if len(row) > idx_birim else ""
            
            # Durum verisini doğru sütundan çek
            row_durum = str(row[self.idx_durum]).strip() if len(row) > self.idx_durum else "Aktif"
            
            # 1. Durum Filtresi
            if hedef_durum != "Tümü":
                if hedef_durum == "Aktif":
                    # "Aktif", "İzinli", "Raporlu" hepsi Aktif kategorisindedir
                    if row_durum == "Pasif": continue
                elif hedef_durum not in row_durum: continue
            
            # 2. Birim Filtresi
            if hedef_birim and hedef_birim != row_birim: continue
            
            # 3. Sınıf Filtresi
            if hedef_sinif and hedef_sinif != row_sinif: continue
            
            filtrelenmis.append(row)
            
        self._tabloyu_doldur(filtrelenmis)

    def _tabloyu_doldur(self, veri_seti):
        self.table.setRowCount(0)
        
        if self.avatar_thread and self.avatar_thread.isRunning():
            self.avatar_thread.durdur()
            self.avatar_thread.wait()
        
        self.table.setRowCount(len(veri_seti))
        self.lbl_info.setText(f"Gösterilen: {len(veri_seti)} | Filtre: {self.secili_durum_filtresi}")
        
        avatar_queue = [] 
        
        col_map = [0, 1, 4, 5, 6, 9] 
        idx_resim = 19
        
        for i, row in enumerate(veri_seti):
            item_foto = QTableWidgetItem()
            item_foto.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, item_foto)
            
            resim_link = row[idx_resim] if len(row) > idx_resim else ""
            if resim_link: avatar_queue.append((i, resim_link, row[0]))
            
            for t_col, d_idx in enumerate(col_map, 1): 
                val = row[d_idx] if len(row) > d_idx else ""
                item = QTableWidgetItem(str(val))
                self.table.setItem(i, t_col, item)
            
            # Durum Hücresi
            durum_val = row[self.idx_durum] if len(row) > self.idx_durum else "Aktif"
            item_durum = QTableWidgetItem(durum_val)
            item_durum.setTextAlignment(Qt.AlignCenter)
            
            bg_color = None
            fg_color = Qt.white
            
            if "Aktif" in durum_val: fg_color = QColor("#4cd964") 
            elif "Pasif" in durum_val: fg_color = QColor("#ff3b30") 
            elif "İzin" in durum_val: fg_color = QColor("#ffcc00"); item_durum.setForeground(Qt.black)
            elif "Rapor" in durum_val: bg_color = QColor("#ff3b30")
            
            item_durum.setForeground(fg_color)
            if bg_color: item_durum.setBackground(bg_color)
            item_durum.setFont(QFont("Segoe UI", 9, QFont.Bold))
            
            self.table.setItem(i, 7, item_durum)
            self.table.item(i, 1).setData(Qt.UserRole, row)

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
                tc, ad = data[0], data[1]
                
                # Durumu self.idx_durum ile doğru çek
                durum = data[self.idx_durum] if len(data) > self.idx_durum else "Aktif"
                
                menu.addAction("📝 Detay Görüntüle", lambda: self._detay_ac(r, 0))
                menu.addSeparator()
                menu.addAction("🏖️ İzin Giriş/Takip", lambda: self._izin_formu_ac(data))
                menu.addSeparator()
                menu.addAction("🔑 Kullanıcı Yap", lambda: self._kullanici_yap(tc, ad))
                act_d = menu.addAction(f"{'♻️ Aktif Yap' if durum=='Pasif' else '🗑️ Pasife Al'}")
                act_d.triggered.connect(lambda: self._durum_degistir(tc, "Aktif" if durum=="Pasif" else "Pasif"))
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

    def _kullanici_yap(self, tc, ad):
        rol, ok = QInputDialog.getItem(self, "Yetki", f"{ad} yetkisi:", ["viewer","user","admin","admin_mudur"], 0, False)
        if ok:
            if show_question("Onay", "Kullanıcı eklensin mi?", self):
                self.u_worker = KullaniciEkleWorker(tc, ad, rol)
                self.u_worker.sonuc.connect(lambda b, m: show_info("Bilgi", m, self) if b else show_error("Hata", m, self))
                self.u_worker.start()

    def _durum_degistir(self, tc, d):
        if show_question("Onay", f"Durum '{d}' yapılacak?", self):
            self.progress.setVisible(True)
            self.d_worker = DurumGuncelleWorker(tc, d)
            self.d_worker.islem_tamam.connect(lambda: (show_info("Tamam", "Güncellendi", self), self._verileri_yenile()))
            self.d_worker.hata_olustu.connect(lambda m: show_error("Hata", m, self))
            self.d_worker.start()

    def _listeyi_yazdir(self):
        if not openpyxl: return show_error("Hata", "openpyxl modülü yok.", self)
        path, _ = QFileDialog.getSaveFileName(self, "Kaydet", "Liste.xlsx", "Excel (*.xlsx)")
        if path:
            try:
                wb = openpyxl.Workbook(); ws = wb.active; ws.append(["TC", "Ad", "Birim", "Durum"])
                for r in range(self.table.rowCount()):
                    ws.append([self.table.item(r,1).text(), self.table.item(r,2).text(), self.table.item(r,5).text(), self.table.item(r,7).text()])
                wb.save(path); show_info("Tamam", "Kaydedildi.", self)
            except Exception as e: show_error("Hata", str(e), self)

    def closeEvent(self, e):
        if self.avatar_thread: self.avatar_thread.durdur()
        for w in ['worker', 'sabit_worker', 'u_worker', 'd_worker']:
            if hasattr(self, w) and getattr(self, w).isRunning(): getattr(self, w).quit()
        e.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    try: TemaYonetimi.uygula_fusion_dark(app)
    except: pass
    win = PersonelListesiPenceresi()
    win.show()
    sys.exit(app.exec())