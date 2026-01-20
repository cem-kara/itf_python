# -*- coding: utf-8 -*-
import sys
import os
import logging
import uuid
from datetime import datetime, timedelta

# PySide6 Kütüphaneleri
from PySide6.QtCore import Qt, QDate, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, 
    QDateEdit, QSpinBox, QFrame, QAbstractItemView, QMessageBox,
    QGroupBox, QScrollArea, QSplitter, QLineEdit, QAbstractSpinBox, QProgressBar, QGridLayout
)

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# --- MODÜLLER ---
try:
    from google_baglanti import veritabani_getir
    from araclar.ortak_araclar import (
        pencereyi_kapat, show_info, show_error, show_question,
        create_group_box, create_form_layout, kayitlari_getir, 
        add_combo_box, add_date_edit, satir_ekle
    )
except ImportError as e:
    print(f"Modül Hatası: {e}")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("IzinGiris")

# =============================================================================
# WORKER: VERİLERİ YÜKLE
# =============================================================================
class VeriYukleyici(QThread):
    veri_hazir = Signal(dict)
    
    def run(self):
        data = {
            'hizmet_siniflari': [],
            'izin_tipleri': [],
            'personel': [], 
            'izinler': [],
            'izin_bilgi': [] # Bakiye Bilgisi
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
                    
                    if kod == 'Hizmet_Sinifi' and eleman:
                        h_siniflari.add(eleman)
                    elif kod in ['İzin_Tipi', 'Izin_Tipi'] and eleman:
                        i_tipleri.add(eleman)
            
            data['hizmet_siniflari'] = sorted(list(h_siniflari))
            data['hizmet_siniflari'].insert(0, "Seçiniz...")
            
            data['izin_tipleri'] = sorted(list(i_tipleri))
            data['izin_tipleri'].insert(0, "Seçiniz...")

            # 2. PERSONEL LİSTESİ
            personeller = kayitlari_getir(veritabani_getir, 'personel', 'Personel')
            pers_list = []
            if personeller:
                for p in personeller:
                    tc = str(p.get('Kimlik_No', '')).strip()
                    ad = str(p.get('Ad_Soyad', '')).strip()
                    sinif = str(p.get('Hizmet_Sinifi', '')).strip()
                    
                    if ad:
                        pers_list.append({'ad': ad, 'tc': tc, 'sinif': sinif})
            
            data['personel'] = pers_list

            # 3. İZİN GEÇMİŞİ
            tum_izinler = kayitlari_getir(veritabani_getir, 'personel', 'izin_giris')
            data['izinler'] = tum_izinler if tum_izinler else []

            # 4. İZİN BİLGİ (BAKİYE) - YENİ SÜTUN YAPISI
            # No, Kimlik_No, Ad_Soyad, Hak_Edilen, Devir, ToplamKullanilan, Kalan, Hak_Edilen_sua, Kullanilan_sua
            bakiye = kayitlari_getir(veritabani_getir, 'personel', 'izin_bilgi')
            data['izin_bilgi'] = bakiye if bakiye else []

        except Exception as e:
            logger.error(f"Veri yükleme hatası: {e}")
        
        self.veri_hazir.emit(data)

# =============================================================================
# WORKER: KAYIT / GÜNCELLEME (HESAPLAMA MANTIĞI GÜNCELLENDİ)
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
            # A. İzin Giriş Tablosuna Kayıt
            ws_giris = veritabani_getir('personel', 'izin_giris')
            if not ws_giris: raise Exception("izin_giris tablosuna erişilemedi.")

            row_giris = [
                self.data.get('Id'),
                self.data.get('Hizmet_Sinifi'),
                self.data.get('personel_id'), # TC
                self.data.get('Ad_Soyad'),    # İsim
                self.data.get('izin_tipi'),
                self.data.get('Baslama_Tarihi'),
                self.data.get('Gun'),
                self.data.get('Bitis_Tarihi')
            ]

            if self.tip == "yeni":
                ws_giris.append_row(row_giris)
            elif self.tip == "guncelle":
                cell = ws_giris.find(self.data.get('Id'))
                if cell:
                    ws_giris.update(f"A{cell.row}", [row_giris])
                else:
                    raise Exception("Güncellenecek kayıt bulunamadı.")

            # B. İzin Bilgi (Bakiye) Güncelleme (Sadece Yeni Kayıtta)
            if self.tip == "yeni":
                ws_bilgi = veritabani_getir('personel', 'izin_bilgi')
                tc_kimlik = str(self.data.get('personel_id')).strip()
                izin_tipi = str(self.data.get('izin_tipi')).strip().upper()
                gun_sayisi = int(self.data.get('Gun', 0))

                # Kişiyi Bul (Kimlik_No ile)
                cell_personel = ws_bilgi.find(tc_kimlik)
                
                if cell_personel:
                    row_idx = cell_personel.row
                    
                    # Sütun İndeksleri (1-tabanlı):
                    # 1:No, 2:Kimlik_No, 3:Ad_Soyad, 4:Hak_Edilen, 5:Devir, 
                    # 6:ToplamKullanilan, 7:Kalan, 8:Hak_Edilen_sua, 9:Kullanilan_sua
                    
                    def get_int(idx):
                        val = ws_bilgi.cell(row_idx, idx).value
                        return int(val) if val and str(val).isdigit() else 0

                    if izin_tipi == "YILLIK İZİN":
                        hak_edilen = get_int(4)
                        devir = get_int(5)
                        kullanilan = get_int(6)
                        
                        # Kullanılanı artır
                        yeni_kullanilan = kullanilan + gun_sayisi
                        
                        # Düşme Mantığı: Önce Devirden, Sonra Haktan
                        kalan_dusulecek = gun_sayisi
                        
                        if devir >= kalan_dusulecek:
                            devir -= kalan_dusulecek
                            kalan_dusulecek = 0
                        else:
                            kalan_dusulecek -= devir
                            devir = 0
                        
                        # Devir bittiyse haktan düş
                        hak_edilen -= kalan_dusulecek
                        
                        # Kalanı Hesapla (Yeni Hak + Yeni Devir)
                        yeni_kalan = hak_edilen + devir
                        
                        # Veritabanına Yaz
                        ws_bilgi.update_cell(row_idx, 4, hak_edilen) # Hak_Edilen
                        ws_bilgi.update_cell(row_idx, 5, devir)      # Devir
                        ws_bilgi.update_cell(row_idx, 6, yeni_kullanilan) # ToplamKullanilan
                        ws_bilgi.update_cell(row_idx, 7, yeni_kalan) # Kalan

                    elif "ŞUA" in izin_tipi:
                        # Sadece Kullanilan_sua (9. Sütun) artırılır
                        kul_sua = get_int(9)
                        ws_bilgi.update_cell(row_idx, 9, kul_sua + gun_sayisi)

            self.islem_tamam.emit()

        except Exception as e:
            self.hata_olustu.emit(str(e))

# =============================================================================
# ANA FORM
# =============================================================================
class IzinGirisPenceresi(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Personel İzin İşlemleri")
        self.resize(1350, 850)
        
        self.tum_personel = []
        self.tum_izinler = []
        self.tum_bakiye = []
        self.duzenleme_modu = False
        self.ui = {}

        self._setup_ui()
        self._verileri_yukle()

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        
        # --- SOL TARA ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0,0,0,0)

        # 1. GİRİŞ KUTUSU
        grp_giris = create_group_box("İzin Giriş / Düzenleme")
        form_layout = create_form_layout()

        self.txt_id = QLineEdit()
        self.txt_id.setVisible(False)

        # Hizmet Sınıfı
        self.ui['sinif'] = add_combo_box(form_layout, "Hizmet Sınıfı:", items=["Yükleniyor..."])
        self.ui['sinif'].currentIndexChanged.connect(self._on_sinif_changed)

        # Personel Listesi
        self.ui['personel'] = add_combo_box(form_layout, "Personel:", items=[])
        self.ui['personel'].setEditable(True)
        self.ui['personel'].currentIndexChanged.connect(self._on_personel_changed)

        # İzin Tipi
        self.ui['izin_tipi'] = add_combo_box(form_layout, "İzin Tipi:", items=["Yükleniyor..."])

        # Tarih ve Gün
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

        # Bitiş Tarihi
        self.ui['bitis'] = QDateEdit()
        self.ui['bitis'].setReadOnly(True)
        self.ui['bitis'].setDisplayFormat("dd.MM.yyyy")
        self.ui['bitis'].setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.ui['bitis'].setStyleSheet("background-color: #2b2b2b; color: #aaa; border: 1px solid #444;")
        self.ui['bitis'].setFixedHeight(35)
        form_layout.addRow("Bitiş Tarihi:", self.ui['bitis'])

        # Butonlar
        h_btn = QHBoxLayout()
        self.btn_temizle = QPushButton("Yeni Kayıt")
        self.btn_temizle.setFixedHeight(40)
        self.btn_temizle.clicked.connect(self._formu_temizle)
        
        self.btn_kaydet = QPushButton("KAYDET")
        self.btn_kaydet.setFixedHeight(40)
        self.btn_kaydet.setStyleSheet("background-color: #0067c0; color: white; font-weight: bold;")
        self.btn_kaydet.clicked.connect(self._kaydet_baslat)

        h_btn.addWidget(self.btn_temizle)
        h_btn.addWidget(self.btn_kaydet)
        form_layout.addRow(h_btn)

        grp_giris.setLayout(form_layout)
        left_layout.addWidget(grp_giris)

        # 2. BİLGİ PANELİ
        grp_bilgi = create_group_box("Personel İzin Durumu")
        bilgi_layout = QGridLayout()
        bilgi_layout.setSpacing(10)

        self.lbl_devir = QLabel("-")
        self.lbl_hakedilen = QLabel("-")
        self.lbl_kullanilan = QLabel("-")
        self.lbl_kalan = QLabel("-")
        self.lbl_hak_sua = QLabel("-")
        self.lbl_kul_sua = QLabel("-")

        val_style = "font-weight: bold; color: #4caf50; font-size: 13px;"
        
        bilgi_layout.addWidget(QLabel("Devreden İzin:"), 0, 0)
        self.lbl_devir.setStyleSheet(val_style)
        bilgi_layout.addWidget(self.lbl_devir, 0, 1)

        bilgi_layout.addWidget(QLabel("Hak Edilen İzin:"), 1, 0)
        self.lbl_hakedilen.setStyleSheet(val_style)
        bilgi_layout.addWidget(self.lbl_hakedilen, 1, 1)

        bilgi_layout.addWidget(QLabel("Kullanılan İzin:"), 2, 0)
        self.lbl_kullanilan.setStyleSheet(val_style)
        bilgi_layout.addWidget(self.lbl_kullanilan, 2, 1)

        bilgi_layout.addWidget(QLabel("KALAN İZİN:"), 3, 0)
        self.lbl_kalan.setStyleSheet("font-weight: bold; color: #2196f3; font-size: 15px;")
        bilgi_layout.addWidget(self.lbl_kalan, 3, 1)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        bilgi_layout.addWidget(line, 4, 0, 1, 2)

        bilgi_layout.addWidget(QLabel("Hak Edilen Şua:"), 5, 0)
        self.lbl_hak_sua.setStyleSheet(val_style)
        bilgi_layout.addWidget(self.lbl_hak_sua, 5, 1)
        
        bilgi_layout.addWidget(QLabel("Kullanılan Şua:"), 6, 0)
        self.lbl_kul_sua.setStyleSheet(val_style)
        bilgi_layout.addWidget(self.lbl_kul_sua, 6, 1)

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
        self.table_genel.setColumnCount(6)
        self.table_genel.setHorizontalHeaderLabels(["TC Kimlik", "Personel Adı", "İzin Tip", "Başlama", "Gün", "Bitiş"])
        self.table_genel.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_genel.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_genel.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_genel.cellDoubleClicked.connect(self._satir_secildi)
        
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

        # Bilgi Paneli Doldurma
        kayit_bulundu = False
        for row in self.tum_bakiye:
            if str(row.get('Kimlik_No', '')).strip() == str(secilen_tc):
                # Yeni Sütun İsimleri: Hak_Edilen, Devir, ToplamKullanilan, Kalan
                self.lbl_devir.setText(str(row.get('Devir', '-')))
                self.lbl_hakedilen.setText(str(row.get('Hak_Edilen', '-')))
                self.lbl_kullanilan.setText(str(row.get('ToplamKullanilan', '-')))
                self.lbl_kalan.setText(str(row.get('Kalan', '-')))
                self.lbl_hak_sua.setText(str(row.get('Hak_Edilen_sua', '-')))
                self.lbl_kul_sua.setText(str(row.get('Kullanilan_sua', '-')))
                kayit_bulundu = True
                break
        
        if not kayit_bulundu:
            self._bilgi_paneli_sifirla()

    def _bilgi_paneli_sifirla(self):
        for lbl in [self.lbl_devir, self.lbl_hakedilen, self.lbl_kullanilan, 
                    self.lbl_kalan, self.lbl_hak_sua, self.lbl_kul_sua]:
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
            self.table_genel.setItem(i, 0, QTableWidgetItem(str(tc_no))) 
            self.table_genel.setItem(i, 1, QTableWidgetItem(str(ad_soyad))) 
            self.table_genel.setItem(i, 2, QTableWidgetItem(str(row.get('izin_tipi'))))
            self.table_genel.setItem(i, 3, QTableWidgetItem(str(row.get('Başlama_Tarihi'))))
            self.table_genel.setItem(i, 4, QTableWidgetItem(str(row.get('Gun'))))
            self.table_genel.setItem(i, 5, QTableWidgetItem(str(row.get('Bitiş_Tarihi'))))
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

    def _formu_temizle(self):
        self.duzenleme_modu = False
        self.btn_kaydet.setText("KAYDET")
        self.btn_kaydet.setStyleSheet("background-color: #0067c0; color: white; font-weight: bold;")
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
                if p['ad'] == ad_soyad:
                    tc_kimlik = p['tc']
                    break
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

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from temalar.tema import TemaYonetimi
    app = QApplication(sys.argv)
    TemaYonetimi.uygula_fusion_dark(app)
    win = IzinGirisPenceresi()
    win.show()
    sys.exit(app.exec())