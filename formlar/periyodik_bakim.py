# -*- coding: utf-8 -*-
import sys
import os
import datetime
import calendar
import time
import logging
from dateutil.relativedelta import relativedelta 

from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                               QTableWidget, QTableWidgetItem, QHeaderView, 
                               QLineEdit, QPushButton, QLabel, QMessageBox, 
                               QComboBox, QDateEdit, QTextEdit, QFileDialog, 
                               QProgressBar, QFrame, QGraphicsDropShadowEffect, 
                               QCompleter, QAbstractItemView, QGroupBox, QSizePolicy)
from PySide6.QtCore import Qt, QDate, QUrl, QThread, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont

# --- LOGLAMA ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PeriyodikBakim")

# --- AYARLAR ---
DRIVE_KLASOR_ID = "1KIYRhomNGppMZCXbqyngT2kH0X8c-GEK" 

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# --- İMPORTLAR ---
try:
    from araclar.yetki_yonetimi import YetkiYoneticisi
    from temalar.tema import TemaYonetimi
    from google_baglanti import veritabani_getir, GoogleDriveService
    from araclar.ortak_araclar import show_info, show_error, pencereyi_kapat
except ImportError as e:
    print(f"Modül Hatası: {e}")
    # Fallback
    def veritabani_getir(vt, sayfa): return None
    def show_info(t, m, p): print(m)
    def show_error(t, m, p): print(m)
    def pencereyi_kapat(w): w.close()
    class GoogleDriveService:
        def upload_file(self, a, b): return None
    class TemaYonetimi:
        @staticmethod
        def uygula_fusion_dark(app): pass

# --- YARDIMCI FONKSİYONLAR ---
def ay_ekle(kaynak_tarih, ay_sayisi):
    return kaynak_tarih + relativedelta(months=ay_sayisi)

# =============================================================================
# 1. THREAD SINIFLARI
# =============================================================================
class VeriYukleyici(QThread):
    veri_hazir = Signal(list, dict, list, dict)
    hata_olustu = Signal(str)
    
    def run(self):
        cihaz_listesi_combo = [] 
        cihaz_dict = {}          
        bakimlar = []
        header_map = {}
        
        try:
            # 1. CİHAZLARI ÇEK
            ws_cihaz = veritabani_getir('cihaz', 'Cihazlar')
            if ws_cihaz:
                raw_cihaz = ws_cihaz.get_all_values()
                if len(raw_cihaz) > 1:
                    headers = [str(h).strip() for h in raw_cihaz[0]]
                    idx_id = -1; idx_marka = -1; idx_model = -1
                    
                    for i, h in enumerate(headers):
                        if h in ["cihaz_id", "CihazID", "kayit_no"]: idx_id = i
                        elif h == "Marka": idx_marka = i
                        elif h == "Model": idx_model = i
                    
                    if idx_id != -1:
                        for row in raw_cihaz[1:]:
                            if len(row) > idx_id:
                                c_id = str(row[idx_id]).strip()
                                c_marka = str(row[idx_marka]).strip() if idx_marka != -1 and len(row) > idx_marka else ""
                                c_model = str(row[idx_model]).strip() if idx_model != -1 and len(row) > idx_model else ""
                                
                                if c_id:
                                    guzel_isim = f"{c_id} | {c_marka} {c_model}"
                                    cihaz_listesi_combo.append(guzel_isim)
                                    cihaz_dict[c_id] = f"{c_marka} {c_model}"

            # 2. BAKIMLARI ÇEK
            ws_bakim = veritabani_getir('cihaz', 'Periyodik_Bakim')
            if ws_bakim:
                raw_bakim = ws_bakim.get_all_values()
                if len(raw_bakim) > 0:
                    headers = [str(h).strip() for h in raw_bakim[0]]
                    for i, h in enumerate(headers):
                        header_map[h] = i
                    if len(raw_bakim) > 1:
                        bakimlar = raw_bakim[1:]
                    
        except Exception as e:
            logger.error(f"Veri yükleme hatası: {e}")
            self.hata_olustu.emit(str(e))
        
        self.veri_hazir.emit(sorted(cihaz_listesi_combo), cihaz_dict, bakimlar, header_map)

class IslemKaydedici(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)

    def __init__(self, islem_tipi, veri):
        super().__init__()
        self.tip = islem_tipi 
        self.veri = veri 

    def run(self):
        try:
            ws_bakim = veritabani_getir('cihaz', 'Periyodik_Bakim')
            if not ws_bakim: raise Exception("Veritabanı bağlantısı yok")

            if self.tip == "INSERT":
                ws_bakim.append_rows(self.veri)
            elif self.tip == "UPDATE":
                satir_no = self.veri[0]
                yeni_degerler = self.veri[1]
                # A'dan başlayıp veri uzunluğu kadar git
                baslangic_col = "A"
                bitis_col = chr(ord('A') + len(yeni_degerler) - 1)
                # Eğer Z'yi geçerse bu mantık patlar ama şimdilik yeterli (13 sütun var)
                range_adresi = f"{baslangic_col}{satir_no}:{bitis_col}{satir_no}"
                ws_bakim.update(range_name=range_adresi, values=[yeni_degerler])

            self.islem_tamam.emit()
        except Exception as e:
            self.hata_olustu.emit(str(e))

class DosyaYukleyici(QThread):
    yuklendi = Signal(str)
    
    def __init__(self, yerel_yol):
        super().__init__()
        self.yol = yerel_yol

    def run(self):
        try:
            drive = GoogleDriveService()
            if not drive: 
                self.yuklendi.emit("-")
                return
            link = drive.upload_file(self.yol, DRIVE_KLASOR_ID)
            self.yuklendi.emit(link if link else "-")
        except:
            self.yuklendi.emit("-")

# =============================================================================
# 2. UI BİLEŞENLERİ
# =============================================================================
class ModernInputGroup(QWidget):
    def __init__(self, label_text, widget, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(4)
        
        self.lbl = QLabel(label_text)
        self.lbl.setStyleSheet("color: #b0b0b0; font-size: 11px; font-weight: bold; text-transform: uppercase;")
        
        self.widget = widget
        self.widget.setMinimumHeight(40)
        self.widget.setMinimumWidth(150)
        
        # Manuel stiller kaldırıldı, TemaYonetimi yönetecek
        if isinstance(widget, QTextEdit):
            self.widget.setMinimumHeight(80)
        
        layout.addWidget(self.lbl)
        layout.addWidget(self.widget)

class InfoCard(QGroupBox):
    """
    Görsel gruplama sağlayan kart bileşeni (QGroupBox).
    """
    def __init__(self, title, parent=None, color="#4dabf7"):
        super().__init__(title, parent)
        
        self.setStyleSheet(f"""
            QGroupBox {{
                background-color: #2d2d2d;
                border: 1px solid #444;
                border-radius: 8px;
                margin-top: 20px; 
                font-weight: bold;
                color: {color}; 
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 10px;
                left: 10px;
            }}
        """)
        
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 100))
        self.setGraphicsEffect(shadow)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 20, 15, 15)
        self.layout.setSpacing(15)

    def add_widget(self, widget): self.layout.addWidget(widget)
    def add_layout(self, layout): self.layout.addLayout(layout)

# =============================================================================
# 3. ANA PENCERE
# =============================================================================
class PeriyodikBakimPenceresi(QWidget):
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.setWindowTitle("Periyodik Bakım Yönetimi")
        self.resize(1300, 800)
        
        self.inputs = {}
        self.control_buttons = {} 
        self.cihaz_sozlugu = {}   
        self.tum_bakimlar = []    
        self.header_map = {}      
        
        self.secilen_plan_id = None
        self.secilen_dosya = None
        self.mevcut_link = None
        
        self.setup_ui()
        
        # Tema Uygulama
        try:
            TemaYonetimi.tema_uygula(self)
        except AttributeError: pass
        
        # Yetki Uygulama
        YetkiYoneticisi.uygula(self, "periyodik_bakim")
        
        self.verileri_yukle()

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(20)
        
        # --- SOL PANEL ---
        sol_panel = QVBoxLayout()
        sol_panel.setSpacing(15)
        
        # Kart 1: Planlama
        card_plan = InfoCard("Bakım Planlama", color="#4CAF50")
        
        self.add_modern_input(card_plan, "Cihaz Seçimi", "Cihaz", "combo")
        self.inputs["Cihaz"].setEditable(True)
        self.inputs["Cihaz"].setPlaceholderText("ID veya Marka ile arayın...")
        self.inputs["Cihaz"].completer().setCompletionMode(QCompleter.PopupCompletion)
        
        row1 = QHBoxLayout(); row1.setSpacing(10)
        self.add_modern_input(row1, "Bakım Periyodu", "BakimPeriyodu", "combo")
        self.inputs["BakimPeriyodu"].addItems(["3 Ay", "6 Ay", "1 Yıl", "Tek Seferlik"])
        
        self.add_modern_input(row1, "Planlanan Tarih", "PlanlananTarih", "date")
        card_plan.add_layout(row1)
        
        sol_panel.addWidget(card_plan)
        
        # Kart 2: İşlem Sonucu
        card_islem = InfoCard("İşlem Sonucu", color="#FF9800")
        
        self.add_modern_input(card_islem, "Bakım Durumu", "Durum", "combo")
        self.inputs["Durum"].addItems(["Planlandı", "Yapıldı", "Gecikti", "İptal"])
        self.inputs["Durum"].currentTextChanged.connect(self.durum_kontrol)
        
        # İşlem Tarihi
        self.add_modern_input(card_islem, "İşlem / Yapılma Tarihi", "IslemTarihi", "date")
        
        self.add_modern_input(card_islem, "Teknisyen", "Teknisyen")
        # 🟢 OTOMATİK DOLDURMA
        if self.kullanici_adi:
            self.inputs["Teknisyen"].setText(str(self.kullanici_adi))
        
        txt_not = QTextEdit()
        txt_not.setPlaceholderText("Yapılan işlemler, ölçümler...")
        grp_not = ModernInputGroup("Yapılan İşlemler", txt_not)
        card_islem.add_widget(grp_not)
        self.inputs["YapilanIslem"] = txt_not
        
        self.add_modern_input(card_islem, "Not / Açıklama", "Açiklama")

        self.create_file_manager(card_islem, "Bakım Raporu", "Dosya")
        
        sol_panel.addWidget(card_islem)
        
        # Butonlar
        self.btn_yeni = QPushButton("Temizle / Yeni Plan")
        self.btn_yeni.setObjectName("btn_yeni") # Yetki için
        self.btn_yeni.setCursor(Qt.PointingHandCursor)
        self.btn_yeni.setStyleSheet("background: transparent; border: 1px dashed #666; color: #aaa; padding: 10px; border-radius: 6px;")
        self.btn_yeni.clicked.connect(self.formu_temizle)
        sol_panel.addWidget(self.btn_yeni)
        
        self.btn_kaydet = QPushButton("🗓️ Planı Oluştur")
        self.btn_kaydet.setObjectName("btn_kaydet") # Yetki için
        self.btn_kaydet.setCursor(Qt.PointingHandCursor)
        self.btn_kaydet.setMinimumHeight(50)
        # Özel yeşil stil (Tema dışı)
        self.btn_kaydet.setStyleSheet("""
            QPushButton { background-color: #2e7d32; color: white; border-radius: 8px; font-weight: bold; font-size: 14px; }
            QPushButton:hover { background-color: #388e3c; }
            QPushButton:disabled { background-color: #444; color: #888; }
        """)
        self.btn_kaydet.clicked.connect(self.kaydet_baslat)
        sol_panel.addWidget(self.btn_kaydet)
        
        sol_panel.addStretch()
        
        sol_widget = QWidget()
        sol_widget.setLayout(sol_panel)
        sol_widget.setFixedWidth(420)
        main_layout.addWidget(sol_widget)
        
        # --- SAĞ PANEL (LİSTE) ---
        sag_panel = QVBoxLayout()
        
        # HEADER (GroupBox ile)
        grp_filtre = QGroupBox("Bakım Takvimi")
        grp_filtre.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        grp_filtre.setStyleSheet("QGroupBox { font-size: 14px; font-weight: bold; color: #4dabf7; margin-top: 10px; }")
        
        filter_layout = QHBoxLayout(grp_filtre)
        
        self.cmb_filtre_ay = QComboBox()
        self.cmb_filtre_ay.addItems(["Tüm Aylar"] + list(calendar.month_name)[1:])
        self.cmb_filtre_ay.setFixedWidth(150)
        # Stil temaya bırakıldı
        self.cmb_filtre_ay.currentIndexChanged.connect(self.tabloyu_guncelle)
        
        btn_yenile = QPushButton("⟳")
        btn_yenile.setFixedSize(35, 35)
        btn_yenile.clicked.connect(self.verileri_yukle)
        # Stil temaya bırakıldı
        
        filter_layout.addStretch()
        filter_layout.addWidget(QLabel("Ay Filtresi:"))
        filter_layout.addWidget(self.cmb_filtre_ay)
        filter_layout.addWidget(btn_yenile)
        sag_panel.addWidget(grp_filtre)
        
        self.tablo = QTableWidget()
        self.tablo.setColumnCount(6)
        self.tablo.setHorizontalHeaderLabels(["PlanID", "Cihaz", "Tarih", "Periyot", "Durum", "Açıklama"])
        self.tablo.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tablo.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tablo.verticalHeader().setVisible(False)
        # Manuel stil kaldırıldı, tema.py yönetecek
        self.tablo.doubleClicked.connect(self.satir_tiklandi)
        sag_panel.addWidget(self.tablo)
        
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setStyleSheet("background: transparent; border: none; QProgressBar::chunk { background: #4dabf7; }")
        sag_panel.addWidget(self.progress)
        
        main_layout.addLayout(sag_panel)

    # --- UI YARDIMCILARI (MODERN) ---
    def add_modern_input(self, parent, label, key, tip="text"):
        widget = None
        if tip == "text": widget = QLineEdit()
        elif tip == "combo": widget = QComboBox()
        elif tip == "date": 
            widget = QDateEdit(); widget.setCalendarPopup(True); widget.setDisplayFormat("yyyy-MM-dd")
            widget.setDate(QDate.currentDate())
            
        grp = ModernInputGroup(label, widget)
        
        # 🟢 HATA DÜZELTME: Layout/Widget ekleme kontrolü
        if isinstance(parent, InfoCard):
            parent.add_widget(grp)
        elif hasattr(parent, "addWidget"): # QVBoxLayout, QHBoxLayout vb.
            parent.addWidget(grp)
        elif hasattr(parent, "addLayout"): # Yedek (QBoxLayout türevi)
            parent.addWidget(grp) # Layout'a widget eklenir
            
        self.inputs[key] = widget
        return widget

    def create_file_manager(self, card, label, key):
        container = QWidget()
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0,0,0,0)
        
        self.lbl_dosya = QLabel("Rapor Yok")
        self.lbl_dosya.setStyleSheet("color: #666; font-style: italic;")
        
        self.btn_dosya_ac = QPushButton("📄 Aç")
        self.btn_dosya_ac.setVisible(False)
        self.btn_dosya_ac.setFixedSize(50, 35)
        self.btn_dosya_ac.setStyleSheet("background: #1565c0; border-radius: 4px; color: white;")
        self.btn_dosya_ac.clicked.connect(self.dosyayi_ac)
        
        btn_yukle = QPushButton("📂 Yükle")
        btn_yukle.setFixedSize(60, 35)
        btn_yukle.setStyleSheet("background: #333; border: 1px solid #444; border-radius: 4px; color: white;")
        btn_yukle.clicked.connect(self.dosya_sec)
        
        lay.addWidget(self.lbl_dosya)
        lay.addStretch()
        lay.addWidget(self.btn_dosya_ac)
        lay.addWidget(btn_yukle)
        
        grp = ModernInputGroup(label, container)
        container.setStyleSheet("background: transparent;")
        card.add_widget(grp)
        
        self.control_buttons[key] = {
            "upload": btn_yukle,
            "view": self.btn_dosya_ac,
            "label": self.lbl_dosya
        }

    # --- MANTIK ---
    def durum_kontrol(self):
        durum = self.inputs["Durum"].currentText()
        if durum == "Yapıldı":
            self.lbl_dosya.setText("Rapor Yükleyiniz")
            self.inputs["Açiklama"].setPlaceholderText("Mutlaka giriniz")
        else:
            self.lbl_dosya.setText("Rapor Gerekmiyor")

    def dosya_sec(self):
        yol, _ = QFileDialog.getOpenFileName(self, "Rapor Seç", "", "PDF ve Resim (*.pdf *.jpg *.png)")
        if yol:
            self.secilen_dosya = yol
            self.lbl_dosya.setText(os.path.basename(yol))
            self.lbl_dosya.setStyleSheet("color: #FF9800;")

    def dosyayi_ac(self):
        if self.mevcut_link:
            QDesktopServices.openUrl(QUrl(self.mevcut_link))

    def verileri_yukle(self):
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.loader = VeriYukleyici()
        self.loader.veri_hazir.connect(self.veriler_geldi)
        self.loader.hata_olustu.connect(lambda e: self.progress.setVisible(False))
        self.loader.start()

    def veriler_geldi(self, cihazlar_combo, cihaz_dict, bakimlar, header_map):
        self.progress.setVisible(False)
        self.cihaz_sozlugu = cihaz_dict
        self.tum_bakimlar = bakimlar
        self.header_map = header_map
        
        self.inputs["Cihaz"].clear()
        self.inputs["Cihaz"].addItem("") 
        self.inputs["Cihaz"].addItems(cihazlar_combo)
        self.inputs["Cihaz"].setEnabled(True)
            
        self.tabloyu_guncelle()

    def get_val(self, row, header_name, default=""):
        if header_name in self.header_map:
            idx = self.header_map[header_name]
            if idx < len(row): return str(row[idx])
        return default

    def tabloyu_guncelle(self):
        self.tablo.setRowCount(0)
        ay_idx = self.cmb_filtre_ay.currentIndex()
        
        for row in reversed(self.tum_bakimlar):
            tarih = self.get_val(row, "PlanlananTarih", "")
            
            if ay_idx > 0:
                try:
                    dt = datetime.datetime.strptime(tarih, "%Y-%m-%d")
                    if dt.month != ay_idx: continue
                except: continue
            
            r = self.tablo.rowCount()
            self.tablo.insertRow(r)
            
            p_id = self.get_val(row, "PlanID", "")
            c_id = self.get_val(row, "cihaz_id", "")
            c_ad = self.cihaz_sozlugu.get(c_id, c_id)
            
            periyot = self.get_val(row, "BakimPeriyodu", "")
            durum = self.get_val(row, "Durum", "")
            aciklama = self.get_val(row, "Açiklama", "")
            
            self.tablo.setItem(r, 0, QTableWidgetItem(p_id))
            self.tablo.setItem(r, 1, QTableWidgetItem(c_ad))
            self.tablo.setItem(r, 2, QTableWidgetItem(tarih))
            self.tablo.setItem(r, 3, QTableWidgetItem(periyot))
            
            item_durum = QTableWidgetItem(durum)
            if durum == "Yapıldı": item_durum.setForeground(QColor("#4caf50"))
            elif durum == "Gecikti": item_durum.setForeground(QColor("#f44336"))
            else: item_durum.setForeground(QColor("#ffeb3b"))
            self.tablo.setItem(r, 4, item_durum)
            
            self.tablo.setItem(r, 5, QTableWidgetItem(aciklama))
            
            self.tablo.item(r, 0).setData(Qt.UserRole, row)

    def satir_tiklandi(self, index):
        row = index.row()
        row_data = self.tablo.item(row, 0).data(Qt.UserRole)
        if not row_data: return
        
        self.secilen_plan_id = self.get_val(row_data, "PlanID", "")
        self.btn_kaydet.setText("Değişiklikleri Kaydet")
        
        # --- ZORUNLU PASİF ALANLAR (Düzenleme Modunda) ---
        self.inputs["Cihaz"].setEnabled(False)
        self.inputs["BakimPeriyodu"].setEnabled(False)
        self.inputs["PlanlananTarih"].setEnabled(False)
        
        # Formu doldur
        c_id = self.get_val(row_data, "cihaz_id", "")
        idx = self.inputs["Cihaz"].findText(c_id, Qt.MatchContains)
        if idx >= 0: self.inputs["Cihaz"].setCurrentIndex(idx)
        
        self.inputs["BakimPeriyodu"].setCurrentText(self.get_val(row_data, "BakimPeriyodu", ""))
        
        tarih_str = self.get_val(row_data, "PlanlananTarih", "")
        if tarih_str: self.inputs["PlanlananTarih"].setDate(QDate.fromString(tarih_str, "yyyy-MM-dd"))
        
        # Yapılan Tarih (Varsa doldur, yoksa bugünü koy)
        yapilan_t_str = self.get_val(row_data, "BakimTarihi", "")
        if yapilan_t_str: 
            self.inputs["IslemTarihi"].setDate(QDate.fromString(yapilan_t_str, "yyyy-MM-dd"))
        else:
            self.inputs["IslemTarihi"].setDate(QDate.currentDate())

        durum = self.get_val(row_data, "Durum", "")
        self.inputs["Durum"].setCurrentText(durum)
        
        self.inputs["Açiklama"].setText(self.get_val(row_data, "Açiklama", ""))
        self.inputs["YapilanIslem"].setText(self.get_val(row_data, "YapilanIslemler", ""))
        self.inputs["Teknisyen"].setText(self.get_val(row_data, "Teknisyen", ""))
        
        link = self.get_val(row_data, "Rapor", "")
        if link and "http" in link:
            self.mevcut_link = link
            self.control_buttons["Dosya"]["view"].setVisible(True)
            self.control_buttons["Dosya"]["label"].setText("Rapor Mevcut")
            self.control_buttons["Dosya"]["label"].setStyleSheet("color: #4CAF50;")
        else:
            self.mevcut_link = None
            self.control_buttons["Dosya"]["view"].setVisible(False)
            self.control_buttons["Dosya"]["label"].setText("Rapor Yok")

        # KİLİTLEME KONTROLÜ
        if durum == "Yapıldı":
            self.kilit_yonet(True)
        else:
            self.kilit_yonet(False)

    def kilit_yonet(self, tamamlandi_mi):
        # Eğer tamamlandıysa Durum bile değişmesin
        self.inputs["Durum"].setEnabled(not tamamlandi_mi) 
        self.inputs["Teknisyen"].setReadOnly(tamamlandi_mi)
        
        # HER ZAMAN AÇIK KALACAKLAR (Güncelleme için)
        self.inputs["IslemTarihi"].setEnabled(True)
        self.inputs["Açiklama"].setReadOnly(False)
        self.inputs["YapilanIslem"].setReadOnly(False)
        if "Dosya" in self.control_buttons:
            self.control_buttons["Dosya"]["upload"].setEnabled(True)
        
        if tamamlandi_mi:
            self.btn_kaydet.setText("💾 Notları/Dosyayı Güncelle")
            self.btn_kaydet.setEnabled(True)
            self.btn_kaydet.setStyleSheet("background-color: #F57C00; color: white;")
        else:
            self.btn_kaydet.setText("Değişiklikleri Kaydet")
            self.btn_kaydet.setEnabled(True)
            self.btn_kaydet.setStyleSheet("background-color: #2e7d32; color: white;")

    def formu_temizle(self):
        self.secilen_plan_id = None
        self.btn_kaydet.setText("🗓️ Planı Oluştur")
        self.btn_kaydet.setEnabled(True)
        self.btn_kaydet.setStyleSheet("background-color: #2e7d32; color: white;")
        
        self.inputs["YapilanIslem"].clear()
        self.inputs["Açiklama"].clear()
        self.inputs["Teknisyen"].clear()
        # Otomatik Doldurma Tekrar
        if self.kullanici_adi:
            self.inputs["Teknisyen"].setText(str(self.kullanici_adi))
            
        self.inputs["Durum"].setCurrentIndex(0)
        self.secilen_dosya = None
        self.inputs["IslemTarihi"].setDate(QDate.currentDate())
        
        self.control_buttons["Dosya"]["label"].setText("Rapor Yok")
        self.control_buttons["Dosya"]["view"].setVisible(False)
        
        # YENİ KAYIT MODU: Her şey açık
        self.inputs["Cihaz"].setEnabled(True)
        self.inputs["Cihaz"].setCurrentIndex(0)
        self.inputs["BakimPeriyodu"].setEnabled(True)
        self.inputs["PlanlananTarih"].setEnabled(True)
        self.inputs["Durum"].setEnabled(True)
        self.inputs["Teknisyen"].setReadOnly(False)
        self.inputs["Açiklama"].setReadOnly(False)
        self.inputs["YapilanIslem"].setReadOnly(False)

    def kaydet_baslat(self):
        cihaz_text = self.inputs["Cihaz"].currentText()
        if not cihaz_text:
            show_info("Hata", "Cihaz seçmelisiniz.", self)
            return
            
        cihaz_id = cihaz_text.split('|')[0].strip()

        self.btn_kaydet.setText("İşleniyor...")
        self.btn_kaydet.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        
        if self.secilen_dosya:
            self.uploader = DosyaYukleyici(self.secilen_dosya)
            self.uploader.yuklendi.connect(lambda l: self.kaydet_devam(l, cihaz_id))
            self.uploader.start()
        else:
            self.kaydet_devam("-", cihaz_id)

    def kaydet_devam(self, dosya_link, cihaz_id):
        if dosya_link == "-" and self.mevcut_link: dosya_link = self.mevcut_link
        
        periyot = self.inputs["BakimPeriyodu"].currentText()
        tarih = self.inputs["PlanlananTarih"].date().toPython()
        tarih_str = tarih.strftime("%Y-%m-%d")
        
        durum = self.inputs["Durum"].currentText()
        yapilan = self.inputs["YapilanIslem"].toPlainText()
        aciklama = self.inputs["Açiklama"].text()
        teknisyen = self.inputs["Teknisyen"].text()
        
        # İşlem Tarihi (Gerçekleşen)
        islem_tarih_str = ""
        if durum == "Yapıldı":
            islem_tarih_str = self.inputs["IslemTarihi"].date().toString("yyyy-MM-dd")
        
        # UPDATE
        if self.secilen_plan_id:
            satir_no = -1
            mevcut_data = []
            for i, row in enumerate(self.tum_bakimlar):
                curr_id = self.get_val(row, "PlanID", "")
                if str(curr_id) == str(self.secilen_plan_id):
                    satir_no = i + 2 
                    mevcut_data = row
                    break
            
            if satir_no > 0:
                sira = self.get_val(mevcut_data, "BakimSirasi", "1. Bakım")
                
                yeni_veri = [
                    self.secilen_plan_id, cihaz_id, periyot, sira, tarih_str,
                    "Periyodik", durum, islem_tarih_str, "Periyodik", yapilan, aciklama, teknisyen, dosya_link
                ]
                
                self.saver = IslemKaydedici("UPDATE", [satir_no, yeni_veri])
                self.saver.islem_tamam.connect(self.islem_bitti)
                self.saver.hata_olustu.connect(self.hata_goster)
                self.saver.start()
                return

        # INSERT
        tekrar = 1
        ay_artis = 0
        if "3 Ay" in periyot: tekrar, ay_artis = 4, 3
        elif "6 Ay" in periyot: tekrar, ay_artis = 2, 6
        elif "1 Yıl" in periyot: tekrar, ay_artis = 1, 12
        
        base_id = int(time.time())
        satirlar = []
        
        for i in range(tekrar):
            yeni_tarih = ay_ekle(tarih, i * ay_artis)
            t_str = yeni_tarih.strftime("%Y-%m-%d")
            
            s_durum = durum if i == 0 else "Planlandı"
            s_dosya = dosya_link if i == 0 else "-"
            s_yapilan = yapilan if i == 0 else "-"
            s_aciklama = aciklama if i == 0 else "-"
            s_tek = teknisyen if i == 0 else "-"
            
            # İlk kayıt ve Yapıldı ise işlem tarihini koy
            s_bakim_t = islem_tarih_str if (i == 0 and s_durum == "Yapıldı") else ""
            
            row = [
                f"P-{base_id + i}", cihaz_id, periyot, f"{i+1}. Bakım",
                t_str, "Periyodik", s_durum, s_bakim_t, 
                "Periyodik", s_yapilan, s_aciklama, s_tek, s_dosya
            ]
            satirlar.append(row)
            
        self.saver = IslemKaydedici("INSERT", satirlar)
        self.saver.islem_tamam.connect(self.islem_bitti)
        self.saver.hata_olustu.connect(self.hata_goster)
        self.saver.start()

    def islem_bitti(self):
        self.progress.setVisible(False)
        self.btn_kaydet.setEnabled(True)
        self.btn_kaydet.setText("🗓️ Planı Oluştur")
        show_info("Başarılı", "İşlem kaydedildi.", self)
        self.formu_temizle()
        self.verileri_yukle()

    def hata_goster(self, msg):
        self.progress.setVisible(False)
        self.btn_kaydet.setEnabled(True)
        self.btn_kaydet.setText("HATA!")
        show_error("Hata", msg, self)

    # 🟢 DEĞİŞİKLİK 3: Thread Güvenliği
    def closeEvent(self, event):
        if hasattr(self, 'loader') and self.loader.isRunning():
            self.loader.quit()
            self.loader.wait(500)
        if hasattr(self, 'saver') and self.saver.isRunning():
            self.saver.quit()
            self.saver.wait(500)
        if hasattr(self, 'uploader') and self.uploader.isRunning():
            self.uploader.quit()
            self.uploader.wait(500)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Tema uygulaması eklendi
    try:
        from temalar.tema import TemaYonetimi
        TemaYonetimi.uygula_fusion_dark(app)
    except Exception as e:
        print(f"Tema uygulanamadı: {e}")
        app.setStyle("Fusion")
        
    win = PeriyodikBakimPenceresi()
    win.show()
    sys.exit(app.exec())