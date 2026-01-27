# -*- coding: utf-8 -*-
import sys
import os
import logging
import uuid
from datetime import datetime, timedelta

# PySide6 Kütüphaneleri
from PySide6.QtCore import Qt, QDate, QThread, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, 
    QDateEdit, QSpinBox, QFrame, QAbstractItemView, QMessageBox,
    QGroupBox, QScrollArea, QSplitter, QLineEdit, QAbstractSpinBox, 
    QProgressBar, QGridLayout, QApplication, QMenu
)

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# --- PROJE MODÜLLERİ ---
try:
    from araclar.yetki_yonetimi import YetkiYoneticisi
    from temalar.tema import TemaYonetimi
    from google_baglanti import veritabani_getir, InternetBaglantiHatasi, KimlikDogrulamaHatasi
    from araclar.ortak_araclar import (
        pencereyi_kapat, show_info, show_error, show_question,
        create_group_box, create_form_layout, kayitlari_getir, 
        add_combo_box, add_date_edit, satir_ekle
    )
except ImportError as e:
    print(f"KRİTİK HATA: Modüller yüklenemedi! {e}")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("IzinGiris")

# =============================================================================
# YARDIMCI SINIF: TARİH SIRALAMASI
# =============================================================================
class DateTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        try:
            return self._parse(self.text()) < self._parse(other.text())
        except:
            return super().__lt__(other)
    
    def _parse(self, t):
        for f in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try: return datetime.strptime(t, f)
            except: continue
        return datetime.min

# =============================================================================
# WORKER: VERİLERİ YÜKLE
# =============================================================================
class VeriYukleyici(QThread):
    veri_hazir = Signal(dict)
    hata_olustu = Signal(str) 
    
    def run(self):
        data = {
            'hizmet_siniflari': [],
            'izin_tipleri': [],
            'personel': [], 
            'izinler': [],
            'izin_bilgi': []
        }
        try:
            # 1. SABİTLER
            sabitler = kayitlari_getir(veritabani_getir, 'sabit', 'Sabitler')
            h_siniflari = set()
            i_tipleri = set()
            
            if sabitler:
                for s in sabitler:
                    kod = str(s.get('Kod', '')).strip()
                    eleman = str(s.get('MenuEleman', '')).strip()
                    if kod == 'Hizmet_Sinifi': h_siniflari.add(eleman)
                    elif kod in ['İzin_Tipi', 'Izin_Tipi']: i_tipleri.add(eleman)
            
            data['hizmet_siniflari'] = sorted(list(h_siniflari))
            data['hizmet_siniflari'].insert(0, "Seçiniz...")
            data['izin_tipleri'] = sorted(list(i_tipleri))
            data['izin_tipleri'].insert(0, "Seçiniz...")

            # 2. PERSONEL
            personeller = kayitlari_getir(veritabani_getir, 'personel', 'Personel')
            pers_list = []
            if personeller:
                for p in personeller:
                    tc = str(p.get('Kimlik_No', '')).strip()
                    ad = str(p.get('Ad_Soyad', '')).strip()
                    sinif = str(p.get('Hizmet_Sinifi', '')).strip()
                    if ad: pers_list.append({'ad': ad, 'tc': tc, 'sinif': sinif})
            data['personel'] = pers_list

            # 3. İZİN GEÇMİŞİ
            tum_izinler = kayitlari_getir(veritabani_getir, 'personel', 'izin_giris')
            data['izinler'] = tum_izinler if tum_izinler else []

            # 4. BAKİYE BİLGİSİ
            bakiye = kayitlari_getir(veritabani_getir, 'personel', 'izin_bilgi')
            data['izin_bilgi'] = bakiye if bakiye else []
            
            self.veri_hazir.emit(data)

        except Exception as e:
            self.hata_olustu.emit(f"Veri yükleme hatası: {str(e)}")

# =============================================================================
# WORKER: KAYIT (YENİ SÜTUN YAPISINA GÖRE)
# =============================================================================
class KayitWorker(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)

    def __init__(self, veri_sozlugu, islem_tipi="yeni"):
        super().__init__()
        self.data = veri_sozlugu
        self.tip = islem_tipi

    def run(self):
        try:
            hedef_tc = str(self.data.get('personel_id', '')).strip()
            
            try:
                yeni_bas = datetime.strptime(self.data.get('Baslama_Tarihi'), "%d.%m.%Y")
                yeni_bit = datetime.strptime(self.data.get('Bitis_Tarihi'), "%d.%m.%Y")
            except ValueError:
                raise Exception("Tarih formatı hatalı.")

            islem_id = str(self.data.get('Id', '')).strip()

            # --- 1. MÜKERRERLİK KONTROLÜ ---
            tum_izinler = kayitlari_getir(veritabani_getir, 'personel', 'izin_giris')
            if tum_izinler:
                for kayit in tum_izinler:
                    durum = str(kayit.get('Durum', '')).strip()
                    if durum == "İptal Edildi": continue

                    vt_tc = str(kayit.get('personel_id', '')).strip()
                    if vt_tc != hedef_tc: continue

                    vt_id = str(kayit.get('Id', '')).strip()
                    if self.tip == "guncelle" and vt_id == islem_id: continue

                    try:
                        vt_bas = datetime.strptime(str(kayit.get('Başlama_Tarihi')), "%d.%m.%Y")
                        vt_bit = datetime.strptime(str(kayit.get('Bitis_Tarihi')), "%d.%m.%Y")
                        if (yeni_bas <= vt_bit) and (yeni_bit >= vt_bas):
                            raise Exception(f"Bu tarihlerde ({vt_bas.strftime('%d.%m')} - {vt_bit.strftime('%d.%m')}) zaten izinli!")
                    except: continue

            # --- 2. KAYIT İŞLEMİ ---
            ws_giris = veritabani_getir('personel', 'izin_giris')
            
            row_giris = [
                self.data.get('Id'),
                self.data.get('Hizmet_Sinifi'),
                self.data.get('personel_id'),
                self.data.get('Ad_Soyad'),
                self.data.get('izin_tipi'),
                self.data.get('Baslama_Tarihi'),
                self.data.get('Gun'),
                self.data.get('Bitis_Tarihi'),
                "İşlendi"
            ]

            if self.tip == "yeni":
                ws_giris.append_row(row_giris)
                # Yeni kayıtta bakiyeden düş
                self._bakiye_guncelle(hedef_tc, self.data.get('izin_tipi'), int(self.data.get('Gun', 0)), islem="dus")
            
            elif self.tip == "guncelle":
                cell = ws_giris.find(self.data.get('Id'))
                if cell: ws_giris.update(f"A{cell.row}:I{cell.row}", [row_giris])
                else: raise Exception("Güncellenecek kayıt bulunamadı.")

            self.islem_tamam.emit()

        except Exception as e:
            self.hata_olustu.emit(f"Kayıt hatası: {str(e)}")

    def _bakiye_guncelle(self, tc, izin_tipi, gun, islem="dus"):
        """
        Yeni Yapıya Göre Bakiye Güncelleme:
        - Yıllık İzin: Yillik_Kullanilan ARTAR, Yillik_Kalan (Toplam-Kullanilan) HESAPLANIR.
        - Şua: Sua_Kullanilan ARTAR, Sua_Kalan HESAPLANIR.
        """
        try:
            ws_bilgi = veritabani_getir('personel', 'izin_bilgi')
            if not ws_bilgi: return

            tum_tc = ws_bilgi.col_values(1) # TC_Kimlik 1. sütun varsayımı (veya başlık kontrolü)
            
            # TC sütununu dinamik bulalım
            headers = ws_bilgi.row_values(1)
            try: c_tc = headers.index("TC_Kimlik") + 1
            except: c_tc = 2 # Varsayılan
            
            tum_tc = ws_bilgi.col_values(c_tc)
            try: row_idx = tum_tc.index(tc) + 1
            except: return # Personel bakiye tablosunda yok

            # Sütun İndekslerini Bul
            def get_col(name): return headers.index(name) + 1

            katsayi = 1 if islem == "dus" else -1
            tip_str = str(izin_tipi).lower()

            def safe_int(v):
                try: return int(v)
                except: return 0

            # --- YILLIK İZİN ---
            if "yıllık" in tip_str:
                c_kullanilan = get_col("Yillik_Kullanilan")
                c_toplam_hak = get_col("Yillik_Toplam_Hak")
                c_kalan = get_col("Yillik_Kalan")
                
                # Mevcut değerleri oku
                mevcut_kullanilan = safe_int(ws_bilgi.cell(row_idx, c_kullanilan).value)
                toplam_hak = safe_int(ws_bilgi.cell(row_idx, c_toplam_hak).value)
                
                # Yeni değerler
                yeni_kullanilan = max(0, mevcut_kullanilan + (gun * katsayi))
                yeni_kalan = toplam_hak - yeni_kullanilan
                
                # Güncelle
                ws_bilgi.update_cell(row_idx, c_kullanilan, yeni_kullanilan)
                ws_bilgi.update_cell(row_idx, c_kalan, yeni_kalan)

            # --- ŞUA İZNİ ---
            elif "şua" in tip_str or "sua" in tip_str:
                c_kullanilan = get_col("Sua_Kullanilan")
                c_hakedis = get_col("Sua_Hakedis")
                c_kalan = get_col("Sua_Kalan")
                
                mevcut_kul = safe_int(ws_bilgi.cell(row_idx, c_kullanilan).value)
                hakedis = safe_int(ws_bilgi.cell(row_idx, c_hakedis).value)
                
                yeni_kul = max(0, mevcut_kul + (gun * katsayi))
                yeni_kal = hakedis - yeni_kul
                
                ws_bilgi.update_cell(row_idx, c_kullanilan, yeni_kul)
                ws_bilgi.update_cell(row_idx, c_kalan, yeni_kal)
            
            # --- DİĞER İZİNLER ---
            else:
                try:
                    c_diger = get_col("Rapor_Mazeret_Top")
                    mevcut = safe_int(ws_bilgi.cell(row_idx, c_diger).value)
                    ws_bilgi.update_cell(row_idx, c_diger, max(0, mevcut + (gun * katsayi)))
                except: pass

        except Exception as e:
            print(f"Bakiye hatası: {e}")

# =============================================================================
# WORKER: İPTAL VE İADE (YENİ YAPİ)
# =============================================================================
class IptalWorker(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)
    
    def __init__(self, kayit_id):
        super().__init__()
        self.kid = kayit_id

    def run(self):
        try:
            ws_giris = veritabani_getir('personel', 'izin_giris')
            cell = ws_giris.find(str(self.kid))
            
            if cell:
                row_data = ws_giris.row_values(cell.row)
                basliklar = ws_giris.row_values(1)
                
                # Verileri al
                try:
                    idx_durum = basliklar.index("Durum") + 1
                    idx_tc = basliklar.index("personel_id")
                    idx_gun = basliklar.index("Gun")
                    idx_tip = basliklar.index("izin_tipi")
                    
                    tc = row_data[idx_tc]
                    gun = int(row_data[idx_gun])
                    tip = row_data[idx_tip]
                    durum = row_data[idx_durum-1]
                except:
                    # Yedek indeksler
                    tc = row_data[2]; tip = row_data[4]; gun = int(row_data[6]); durum = row_data[8]; idx_durum = 9

                if durum == "İptal Edildi": raise Exception("Zaten iptal edilmiş.")

                # 1. Durumu Güncelle
                ws_giris.update_cell(cell.row, idx_durum, "İptal Edildi")
                
                # 2. İade Yap (KayitWorker'daki mantığı tersine çalıştır)
                self._iade_et(tc, tip, gun)
                self.islem_tamam.emit()
            else:
                self.hata_olustu.emit("Kayıt bulunamadı.")
        except Exception as e: 
            self.hata_olustu.emit(f"İptal hatası: {str(e)}")

    def _iade_et(self, tc, tip, gun):
        """Bakiyeyi iade eder (KayitWorker mantığıyla aynı, sadece işlem tersi)."""
        # Burada KayitWorker'ın metodunu çağırmak yerine mantığı kopyalıyoruz (Thread safe)
        try:
            ws_bilgi = veritabani_getir('personel', 'izin_bilgi')
            headers = ws_bilgi.row_values(1)
            try: c_tc = headers.index("TC_Kimlik") + 1
            except: c_tc = 2
            
            tum_tc = ws_bilgi.col_values(c_tc)
            if tc not in tum_tc: return
            row_idx = tum_tc.index(tc) + 1
            
            def get_col(n): return headers.index(n) + 1
            def safe_int(v): 
                try: return int(v) 
                except: return 0

            tip_str = str(tip).lower()
            
            if "yıllık" in tip_str:
                c_kul = get_col("Yillik_Kullanilan")
                c_hak = get_col("Yillik_Toplam_Hak")
                c_kal = get_col("Yillik_Kalan")
                
                mevcut_kul = safe_int(ws_bilgi.cell(row_idx, c_kul).value)
                top_hak = safe_int(ws_bilgi.cell(row_idx, c_hak).value)
                
                yeni_kul = max(0, mevcut_kul - gun) # İade = Azalt
                ws_bilgi.update_cell(row_idx, c_kul, yeni_kul)
                ws_bilgi.update_cell(row_idx, c_kal, top_hak - yeni_kul)
                
            elif "şua" in tip_str or "sua" in tip_str:
                c_kul = get_col("Sua_Kullanilan")
                c_hak = get_col("Sua_Hakedis")
                c_kal = get_col("Sua_Kalan")
                
                mevcut_kul = safe_int(ws_bilgi.cell(row_idx, c_kul).value)
                top_hak = safe_int(ws_bilgi.cell(row_idx, c_hak).value)
                
                yeni_kul = max(0, mevcut_kul - gun)
                ws_bilgi.update_cell(row_idx, c_kul, yeni_kul)
                ws_bilgi.update_cell(row_idx, c_kal, top_hak - yeni_kul)
            else:
                c_diger = get_col("Rapor_Mazeret_Top")
                mevcut = safe_int(ws_bilgi.cell(row_idx, c_diger).value)
                ws_bilgi.update_cell(row_idx, c_diger, max(0, mevcut - gun))
        except: pass

# =============================================================================
# ANA FORM
# =============================================================================
class IzinGirisPenceresi(QWidget):
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.setWindowTitle("Personel İzin İşlemleri")
        self.resize(1350, 850)
        
        self.tum_personel = []
        self.tum_izinler = []
        self.tum_bakiye = []
        self.duzenleme_modu = False
        self.ui = {}

        self._setup_ui()
        self._verileri_yukle()
        YetkiYoneticisi.uygula(self, "izin_giris")

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        
        # --- SOL TARAF ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0,0,0,0)

        # 1. GİRİŞ KUTUSU
        grp_giris = create_group_box("İzin Giriş / Düzenleme")
        form_layout = create_form_layout()

        self.txt_id = QLineEdit()
        self.txt_id.setVisible(False)

        self.ui['sinif'] = add_combo_box(form_layout, "Hizmet Sınıfı:", items=["Yükleniyor..."])
        self.ui['sinif'].currentIndexChanged.connect(self._on_sinif_changed)

        self.ui['personel'] = add_combo_box(form_layout, "Personel:", items=[])
        self.ui['personel'].setEditable(True)
        self.ui['personel'].currentIndexChanged.connect(self._on_personel_changed)

        self.ui['izin_tipi'] = add_combo_box(form_layout, "İzin Tipi:", items=["Yükleniyor..."])

        h_tarih = QHBoxLayout()
        self.ui['baslama'] = QDateEdit()
        self.ui['baslama'].setCalendarPopup(True)
        self.ui['baslama'].setDisplayFormat("dd.MM.yyyy")
        self.ui['baslama'].setDate(QDate.currentDate())
        self.ui['baslama'].setFixedHeight(35)
        self.ui['baslama'].dateChanged.connect(self._tarih_hesapla)
        
        self.ui['gun'] = QSpinBox()
        self.ui['gun'].setRange(1, 365)
        self.ui['gun'].setValue(1)
        self.ui['gun'].setFixedHeight(35)
        self.ui['gun'].valueChanged.connect(self._tarih_hesapla)
        
        h_tarih.addWidget(self.ui['baslama'])
        h_tarih.addWidget(QLabel("  Süre (Gün):"))
        h_tarih.addWidget(self.ui['gun'])
        form_layout.addRow("Başlama Tarihi:", h_tarih)

        self.ui['bitis'] = QDateEdit()
        self.ui['bitis'].setReadOnly(True)
        self.ui['bitis'].setDisplayFormat("dd.MM.yyyy")
        self.ui['bitis'].setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.ui['bitis'].setFixedHeight(35)
        form_layout.addRow("Bitiş Tarihi:", self.ui['bitis'])

        h_btn = QHBoxLayout()
        self.btn_temizle = QPushButton("Yeni Kayıt")
        self.btn_temizle.setObjectName("btn_temizle")
        self.btn_temizle.setFixedHeight(40)
        self.btn_temizle.clicked.connect(self._formu_temizle)
        
        self.btn_kaydet = QPushButton("KAYDET")
        self.btn_kaydet.setObjectName("btn_kaydet")
        self.btn_kaydet.setFixedHeight(40)
        self.btn_kaydet.clicked.connect(self._kaydet_baslat)

        h_btn.addWidget(self.btn_temizle)
        h_btn.addWidget(self.btn_kaydet)
        form_layout.addRow(h_btn)

        grp_giris.setLayout(form_layout)
        left_layout.addWidget(grp_giris)

        # 2. BİLGİ PANELİ (YENİ SÜTUNLARA GÖRE)
        grp_bilgi = create_group_box("Personel İzin Durumu")
        bilgi_layout = QGridLayout()
        bilgi_layout.setSpacing(10)

        self.lbl_yillik_devir = QLabel("-")
        self.lbl_yillik_hak = QLabel("-") # Toplam Hak
        self.lbl_yillik_kul = QLabel("-")
        self.lbl_yillik_kal = QLabel("-")
        
        self.lbl_sua_hak = QLabel("-")
        self.lbl_sua_kul = QLabel("-")
        self.lbl_sua_kal = QLabel("-")
        
        self.lbl_diger_top = QLabel("-")

        val_style = "font-weight: bold; color: #4caf50; font-size: 13px;"
        kalan_style = "font-weight: bold; color: #2196f3; font-size: 15px;"
        
        # Yıllık İzin Grubu
        bilgi_layout.addWidget(QLabel("<b>--- YILLIK İZİN ---</b>"), 0, 0, 1, 2)
        
        bilgi_layout.addWidget(QLabel("Devir:"), 1, 0)
        self.lbl_yillik_devir.setStyleSheet(val_style)
        bilgi_layout.addWidget(self.lbl_yillik_devir, 1, 1)

        bilgi_layout.addWidget(QLabel("Toplam Hak:"), 2, 0)
        self.lbl_yillik_hak.setStyleSheet(val_style)
        bilgi_layout.addWidget(self.lbl_yillik_hak, 2, 1)

        bilgi_layout.addWidget(QLabel("Kullanılan:"), 3, 0)
        self.lbl_yillik_kul.setStyleSheet(val_style)
        bilgi_layout.addWidget(self.lbl_yillik_kul, 3, 1)

        bilgi_layout.addWidget(QLabel("KALAN:"), 4, 0)
        self.lbl_yillik_kal.setStyleSheet(kalan_style)
        bilgi_layout.addWidget(self.lbl_yillik_kal, 4, 1)

        # Şua Grubu
        line = QFrame(); line.setFrameShape(QFrame.HLine)
        bilgi_layout.addWidget(line, 5, 0, 1, 2)
        bilgi_layout.addWidget(QLabel("<b>--- ŞUA İZNİ ---</b>"), 6, 0, 1, 2)

        bilgi_layout.addWidget(QLabel("Hakediş:"), 7, 0)
        self.lbl_sua_hak.setStyleSheet(val_style)
        bilgi_layout.addWidget(self.lbl_sua_hak, 7, 1)
        
        bilgi_layout.addWidget(QLabel("Kullanılan:"), 8, 0)
        self.lbl_sua_kul.setStyleSheet(val_style)
        bilgi_layout.addWidget(self.lbl_sua_kul, 8, 1)
        
        bilgi_layout.addWidget(QLabel("KALAN:"), 9, 0)
        self.lbl_sua_kal.setStyleSheet(kalan_style)
        bilgi_layout.addWidget(self.lbl_sua_kal, 9, 1)

        # Diğer
        line2 = QFrame(); line2.setFrameShape(QFrame.HLine)
        bilgi_layout.addWidget(line2, 10, 0, 1, 2)
        bilgi_layout.addWidget(QLabel("Diğer (Rapor/Mazeret):"), 11, 0)
        self.lbl_diger_top.setStyleSheet(val_style)
        bilgi_layout.addWidget(self.lbl_diger_top, 11, 1)

        grp_bilgi.setLayout(bilgi_layout)
        left_layout.addWidget(grp_bilgi)
        left_layout.addStretch()

        # --- SAĞ TARAF ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0,0,0,0)

        grp_genel = create_group_box("Tüm Personel İzin Listesi")
        v_genel = QVBoxLayout()

        self.txt_ara = QLineEdit()
        self.txt_ara.setPlaceholderText("🔍 TC veya Ad Soyad ile Ara...")
        self.txt_ara.setFixedHeight(35)
        self.txt_ara.textChanged.connect(self._genel_liste_filtrele)
        v_genel.addWidget(self.txt_ara)

        self.table_genel = QTableWidget()
        self.table_genel.setColumnCount(7)
        self.table_genel.setHorizontalHeaderLabels(["TC Kimlik", "Personel Adı", "İzin Tip", "Başlama", "Gün", "Bitiş", "Durum"])
        self.table_genel.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_genel.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_genel.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_genel.cellDoubleClicked.connect(self._satir_secildi)
        
        self.table_genel.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_genel.customContextMenuRequested.connect(self._sag_tik_menu)
        
        v_genel.addWidget(self.table_genel)
        grp_genel.setLayout(v_genel)
        right_layout.addWidget(grp_genel)

        # --- SPLITTER ---
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setHandleWidth(5)
        main_layout.addWidget(splitter)
        
        self.progress = QProgressBar(self)
        self.progress.setVisible(False)
        self.progress.setStyleSheet("QProgressBar { max-height: 5px; background: #333; border:none; } QProgressBar::chunk { background: #00ccff; }")
        self.progress.setGeometry(0, 0, self.width(), 5)

    # --- LOJİK İŞLEMLER ---
    def _verileri_yukle(self):
        self.progress.setVisible(True); self.progress.setRange(0,0)
        self.worker = VeriYukleyici()
        self.worker.veri_hazir.connect(self._veriler_geldi)
        self.worker.hata_olustu.connect(self._hata_goster)
        self.worker.start()

    def _veriler_geldi(self, data):
        self.progress.setVisible(False)
        self.ui['sinif'].clear()
        self.ui['sinif'].addItems(data.get('hizmet_siniflari', []))
        self.ui['izin_tipi'].clear()
        self.ui['izin_tipi'].addItems(data.get('izin_tipleri', []))
        self.tum_personel = data.get('personel', [])
        self._on_sinif_changed() 
        self.tum_izinler = data.get('izinler', [])
        self.tum_bakiye = data.get('izin_bilgi', [])
        self._genel_tabloyu_doldur(self.tum_izinler)
        self._tarih_hesapla()

    def _on_sinif_changed(self):
        secilen_sinif = self.ui['sinif'].currentText().strip()
        self.ui['personel'].blockSignals(True)
        self.ui['personel'].clear()
        self.ui['personel'].addItem("Seçiniz...")
        for p in self.tum_personel:
            p_sinif = str(p.get('sinif', '')).strip()
            if secilen_sinif == "Seçiniz..." or p_sinif == secilen_sinif:
                self.ui['personel'].addItem(p['ad'], p['tc'])
        self.ui['personel'].blockSignals(False)

    def _on_personel_changed(self):
        current_text = self.ui['personel'].currentText().strip()
        secilen_tc = self.ui['personel'].currentData()

        if not secilen_tc:
            for p in self.tum_personel:
                if p['ad'] == current_text:
                    secilen_tc = p['tc']
                    break
        
        self.txt_ara.blockSignals(True)
        self.txt_ara.clear()
        self.txt_ara.blockSignals(False)

        if not secilen_tc or current_text == "Seçiniz...":
            self._genel_tabloyu_doldur(self.tum_izinler)
            self._bilgi_paneli_sifirla()
            return

        filtrelenmis_liste = []
        for row in self.tum_izinler:
            vt_tc = str(row.get('personel_id', '')).strip()
            if vt_tc == str(secilen_tc):
                filtrelenmis_liste.append(row)
        self._genel_tabloyu_doldur(filtrelenmis_liste)

        # BAKİYE GÖSTERİMİ (YENİ SÜTUNLARA GÖRE)
        kayit_bulundu = False
        for row in self.tum_bakiye:
            if str(row.get('TC_Kimlik', '')).strip() == str(secilen_tc):
                self.lbl_yillik_devir.setText(str(row.get('Yillik_Devir', '-')))
                self.lbl_yillik_hak.setText(str(row.get('Yillik_Toplam_Hak', '-')))
                self.lbl_yillik_kul.setText(str(row.get('Yillik_Kullanilan', '-')))
                self.lbl_yillik_kal.setText(str(row.get('Yillik_Kalan', '-')))
                
                self.lbl_sua_hak.setText(str(row.get('Sua_Hakedis', '-')))
                self.lbl_sua_kul.setText(str(row.get('Sua_Kullanilan', '-')))
                self.lbl_sua_kal.setText(str(row.get('Sua_Kalan', '-')))
                
                self.lbl_diger_top.setText(str(row.get('Rapor_Mazeret_Top', '-')))
                
                kayit_bulundu = True
                break
        
        if not kayit_bulundu:
            self._bilgi_paneli_sifirla()

    def _bilgi_paneli_sifirla(self):
        for lbl in [self.lbl_yillik_devir, self.lbl_yillik_hak, self.lbl_yillik_kul, self.lbl_yillik_kal,
                    self.lbl_sua_hak, self.lbl_sua_kul, self.lbl_sua_kal, self.lbl_diger_top]:
            lbl.setText("-")

    def _tarih_hesapla(self):
        baslama = self.ui['baslama'].date()
        gun = self.ui['gun'].value()
        bitis = baslama.addDays(gun - 1)
        self.ui['bitis'].setDate(bitis)

    def _genel_tabloyu_doldur(self, veri_listesi):
        self.table_genel.setRowCount(len(veri_listesi))
        for i, row in enumerate(veri_listesi):
            tc_no = row.get('personel_id', '') 
            ad_soyad = row.get('Ad_Soyad', '') 
            durum = str(row.get('Durum', 'İşlendi'))

            self.table_genel.setItem(i, 0, QTableWidgetItem(str(tc_no))) 
            self.table_genel.setItem(i, 1, QTableWidgetItem(str(ad_soyad))) 
            self.table_genel.setItem(i, 2, QTableWidgetItem(str(row.get('izin_tipi'))))
            # Tarih sıralaması için özel öğe
            self.table_genel.setItem(i, 3, DateTableWidgetItem(str(row.get('Başlama_Tarihi'))))
            self.table_genel.setItem(i, 4, QTableWidgetItem(str(row.get('Gun'))))
            self.table_genel.setItem(i, 5, DateTableWidgetItem(str(row.get('Bitiş_Tarihi'))))
            
            item_durum = QTableWidgetItem(durum)
            self.table_genel.setItem(i, 6, item_durum)

            if durum == "İptal Edildi":
                for col in range(7):
                    item = self.table_genel.item(i, col)
                    item.setForeground(Qt.gray)
                item_durum.setForeground(Qt.red)
            else:
                item_durum.setForeground(Qt.green)

            self.table_genel.item(i, 0).setData(Qt.UserRole, row)

    def _genel_liste_filtrele(self, text):
        text = text.lower().strip()
        filtrelenmis = []
        for row in self.tum_izinler:
            tc = str(row.get('personel_id', '')).lower()
            isim = str(row.get('Ad_Soyad', '')).lower()
            if text in tc or text in isim:
                filtrelenmis.append(row)
        self._genel_tabloyu_doldur(filtrelenmis)

    def _satir_secildi(self, row, col):
        item = self.table_genel.item(row, 0)
        data = item.data(Qt.UserRole)
        
        if str(data.get('Durum', '')) == "İptal Edildi":
            show_error("Bilgi", "İptal edilmiş kayıtlar düzenlenemez.", self)
            return

        self.duzenleme_modu = True
        self.btn_kaydet.setText("GÜNCELLE")
        self.btn_kaydet.setStyleSheet("background-color: #f0ad4e; color: white; font-weight: bold;")
        
        self.txt_id.setText(str(data.get('Id')))
        self.ui['sinif'].setCurrentText(str(data.get('Hizmet_Sinifi')))
        tc_hedef = str(data.get('personel_id')) 
        idx = self.ui['personel'].findData(tc_hedef)
        if idx >= 0:
            self.ui['personel'].setCurrentIndex(idx)
        else:
            self.ui['personel'].setCurrentText(str(data.get('Ad_Soyad')))
        self.ui['izin_tipi'].setCurrentText(str(data.get('izin_tipi')))
        try:
            qdate_bas = QDate.fromString(str(data.get('Başlama_Tarihi')), "dd.MM.yyyy")
            if qdate_bas.isValid(): self.ui['baslama'].setDate(qdate_bas)
            self.ui['gun'].setValue(int(data.get('Gun', 1)))
        except: pass

    # 🟢 SAĞ TIK VE İPTAL
    def _sag_tik_menu(self, pos):
        row = self.table_genel.currentRow()
        if row < 0: return
        item_durum = self.table_genel.item(row, 6)
        durum = item_durum.text() if item_durum else ""
        
        menu = QMenu()
        if durum != "İptal Edildi":
            act_iptal = QAction("🚫 İzni İptal Et ve İade Yap", self)
            act_iptal.triggered.connect(lambda: self._iptal_et(row))
            menu.addAction(act_iptal)
        else:
            act = QAction("ℹ️ Kayıt iptal edilmiş.", self)
            act.setEnabled(False)
            menu.addAction(act)
        menu.exec(self.table_genel.viewport().mapToGlobal(pos))

    def _iptal_et(self, row):
        if show_question("Onay", "İzin iptal edilecek ve gün sayısı bakiyeye iade edilecek.\nEmin misiniz?", self):
            data = self.table_genel.item(row, 0).data(Qt.UserRole)
            kayit_id = str(data.get('Id', ''))
            
            self.progress.setVisible(True)
            self.iptal_worker = IptalWorker(kayit_id)
            self.iptal_worker.islem_tamam.connect(self._islem_basarili)
            self.iptal_worker.hata_olustu.connect(self._hata_goster)
            self.iptal_worker.start()

    def _formu_temizle(self):
        self.duzenleme_modu = False
        self.btn_kaydet.setText("KAYDET")
        self.btn_kaydet.setStyleSheet("") 
        self.txt_id.clear()
        self.ui['personel'].setCurrentIndex(0)
        self.ui['izin_tipi'].setCurrentIndex(0)
        self.ui['gun'].setValue(1)
        self.ui['baslama'].setDate(QDate.currentDate())
        self._genel_tabloyu_doldur(self.tum_izinler)
        self._bilgi_paneli_sifirla()

    def _kaydet_baslat(self):
        if self.ui['personel'].currentText() in ["", "Seçiniz..."]:
            show_error("Hata", "Lütfen personel seçiniz.", self)
            return
        if self.ui['izin_tipi'].currentText() in ["", "Seçiniz...", "Yükleniyor..."]:
            show_error("Hata", "Lütfen izin tipi seçiniz.", self)
            return

        self.btn_kaydet.setEnabled(False)
        self.progress.setVisible(True); self.progress.setRange(0,0)
        
        yeni_id = self.txt_id.text() if self.duzenleme_modu else str(uuid.uuid4())[:8]
        ad_soyad = self.ui['personel'].currentText().strip()
        tc_kimlik = self.ui['personel'].currentData()
        if not tc_kimlik:
            for p in self.tum_personel:
                if p['ad'] == ad_soyad: tc_kimlik = p['tc']; break
        if not tc_kimlik: tc_kimlik = ""

        veri = {
            'Id': yeni_id,
            'Hizmet_Sinifi': self.ui['sinif'].currentText(),
            'personel_id': str(tc_kimlik),
            'Ad_Soyad': str(ad_soyad),
            'izin_tipi': self.ui['izin_tipi'].currentText(),
            'Baslama_Tarihi': self.ui['baslama'].date().toString("dd.MM.yyyy"),
            'Gun': self.ui['gun'].value(),
            'Bitis_Tarihi': self.ui['bitis'].date().toString("dd.MM.yyyy")
        }
        tip = "guncelle" if self.duzenleme_modu else "yeni"
        self.k_worker = KayitWorker(veri, tip)
        self.k_worker.islem_tamam.connect(self._islem_basarili)
        self.k_worker.hata_olustu.connect(self._hata_goster)
        self.k_worker.start()

    def _islem_basarili(self):
        self.progress.setVisible(False)
        self.btn_kaydet.setEnabled(True)
        show_info("Başarılı", "İşlem başarıyla tamamlandı.", self)
        self._formu_temizle()
        self._verileri_yukle()

    def _hata_goster(self, err):
        self.progress.setVisible(False)
        self.btn_kaydet.setEnabled(True)
        show_error("Hata", str(err), self)

    def closeEvent(self, event):
        worker_names = ['worker', 'k_worker', 'iptal_worker']
        for name in worker_names:
            if hasattr(self, name):
                worker = getattr(self, name)
                if worker and worker.isRunning():
                    worker.quit()
                    worker.wait(500)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    try: TemaYonetimi.uygula_fusion_dark(app)
    except: pass
    win = IzinGirisPenceresi()
    win.show()
    sys.exit(app.exec())