# -*- coding: utf-8 -*-
import sys
import os
import datetime
import logging
from dateutil.relativedelta import relativedelta 

from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                               QTableWidget, QTableWidgetItem, QHeaderView, 
                               QLineEdit, QPushButton, QLabel, QMessageBox, 
                               QComboBox, QDateEdit, QTextEdit, QFileDialog, 
                               QProgressBar, QFrame, QGraphicsDropShadowEffect, 
                               QCompleter, QAbstractItemView, QGroupBox, QSizePolicy)
from PySide6.QtCore import Qt, QDate, QUrl, QThread, Signal
from PySide6.QtGui import QColor, QDesktopServices, QBrush, QFont

# --- LOGLAMA ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("KalibrasyonTakip")

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

# =============================================================================
# 1. THREAD SINIFLARI (VERİ VE İŞLEM YÖNETİMİ)
# =============================================================================

class VeriYukleyici(QThread):
    veri_hazir = Signal(list, dict, list, list) # CihazCombo, CihazDict, Firmalar, KalibrasyonListesi
    hata_olustu = Signal(str)
    
    def run(self):
        cihaz_listesi_combo = [] 
        cihaz_dict = {}          
        firmalar = []
        kalibrasyonlar = []
        
        try:
            ws_cihaz = veritabani_getir('cihaz', 'Cihazlar')
            if ws_cihaz:
                raw_cihaz = ws_cihaz.get_all_records()
                for row in raw_cihaz:
                    c_id = str(row.get('cihaz_id', '')).strip()
                    c_marka = str(row.get('Marka', '')).strip()
                    c_model = str(row.get('Model', '')).strip()
                    
                    if c_id:
                        guzel_isim = f"{c_id} | {c_marka} {c_model}"
                        cihaz_listesi_combo.append(guzel_isim)
                        cihaz_dict[c_id] = f"{c_marka} {c_model}"

            ws_firma = veritabani_getir('sabit', 'firmalar')
            if ws_firma:
                raw_firma = ws_firma.get_all_values()
                if len(raw_firma) > 1:
                    firmalar = sorted([str(r[0]).strip() for r in raw_firma[1:] if r])

            ws_kal = veritabani_getir('cihaz', 'Kalibrasyon')
            if ws_kal:
                raw_kal = ws_kal.get_all_values()
                if len(raw_kal) > 1:
                    kalibrasyonlar = raw_kal[1:] 
                    
            self.veri_hazir.emit(sorted(cihaz_listesi_combo), cihaz_dict, firmalar, kalibrasyonlar)
            
        except Exception as e:
            self.hata_olustu.emit(str(e))

class IslemKaydedici(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)

    def __init__(self, veri, mod="yeni", kayit_id=None):
        super().__init__()
        self.veri = veri 
        self.mod = mod
        self.kayit_id = kayit_id

    def run(self):
        try:
            ws = veritabani_getir('cihaz', 'Kalibrasyon')
            if not ws: raise Exception("Veritabanı bağlantısı yok")

            if self.mod == "yeni":
                # Yeni Kayıt Ekle
                ws.append_row(self.veri)
            
            elif self.mod == "guncelle":
                # Güncelleme
                cell = ws.find(self.kayit_id)
                if cell:
                    range_str = f"A{cell.row}:J{cell.row}"
                    ws.update(range_str, [self.veri])
                else:
                    raise Exception("Güncellenecek kayıt veritabanında bulunamadı.")

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
# 2. UI TASARIM BİLEŞENLERİ
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
    def __init__(self, title, parent=None, color="#42a5f5"):
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
# 3. ANA PENCERE (KALİBRASYON)
# =============================================================================

class KalibrasyonEklePenceresi(QWidget):
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        self.setWindowTitle("Kalibrasyon Yönetimi")
        self.resize(1300, 800)
        # Manuel arka plan kaldırıldı
        
        self.inputs = {}
        self.cihaz_sozlugu = {}
        self.tum_kalibrasyonlar = []
        
        self.secilen_dosya = None
        self.mevcut_link = "-"
        self.duzenleme_modu = False
        self.duzenlenen_id = None
        
        self.setup_ui()
        # Yetki
        YetkiYoneticisi.uygula(self, "kalibrasyon_ekle")
        self.verileri_yukle()

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(20)
        
        # --- SOL PANEL (VERİ GİRİŞ) ---
        sol_panel = QVBoxLayout()
        sol_panel.setSpacing(15)
        
        # Kart 1
        card_cihaz = InfoCard("Cihaz ve Firma Bilgisi", color="#42a5f5")
        
        self.add_modern_input(card_cihaz, "Cihaz Seçimi", "Cihaz", "combo")
        self.inputs["Cihaz"].setEditable(True)
        self.inputs["Cihaz"].setPlaceholderText("ID veya Model ara...")
        self.inputs["Cihaz"].completer().setCompletionMode(QCompleter.PopupCompletion)
        
        self.add_modern_input(card_cihaz, "Firma / Kurum", "Firma", "combo")
        self.inputs["Firma"].setEditable(True)
        
        sol_panel.addWidget(card_cihaz)

        # Kart 2
        card_tarih = InfoCard("Sertifika ve Süreç", color="#66bb6a")
        self.add_modern_input(card_tarih, "Sertifika No", "Sertifika")
        
        row_tarih = QHBoxLayout(); row_tarih.setSpacing(10)
        self.add_modern_input(row_tarih, "İşlem Tarihi", "YapilanTarih", "date")
        self.inputs["YapilanTarih"].dateChanged.connect(self.tarih_hesapla)
        
        self.add_modern_input(row_tarih, "Geçerlilik", "Gecerlilik", "combo")
        self.inputs["Gecerlilik"].addItems(["1 Yıl", "6 Ay", "2 Yıl", "3 Yıl", "Tek Seferlik"])
        self.inputs["Gecerlilik"].currentTextChanged.connect(self.tarih_hesapla)
        card_tarih.add_layout(row_tarih)
        
        self.add_modern_input(card_tarih, "Bitiş Tarihi (Hesaplanan)", "BitisTarihi", "date")
        sol_panel.addWidget(card_tarih)
        
        # Kart 3
        card_sonuc = InfoCard("Durum ve Belge", color="#ffa726")
        self.add_modern_input(card_sonuc, "Durum", "Durum", "combo")
        self.inputs["Durum"].addItems(["Planlandı", "Tamamlandı", "İptal"])
        self.inputs["Durum"].setCurrentText("Tamamlandı")
        
        self.create_file_manager(card_sonuc, "Sertifika / Rapor Dosyası", "Dosya")
        
        txt_aciklama = QTextEdit()
        txt_aciklama.setPlaceholderText("Varsa notlar...")
        grp_aciklama = ModernInputGroup("Açıklama", txt_aciklama)
        card_sonuc.add_widget(grp_aciklama)
        self.inputs["Aciklama"] = txt_aciklama
        sol_panel.addWidget(card_sonuc)
        
        # Butonlar
        self.btn_temizle = QPushButton("Yeni Kayıt / Temizle")
        self.btn_temizle.setObjectName("btn_temizle") # Yetki
        self.btn_temizle.setCursor(Qt.PointingHandCursor)
        self.btn_temizle.setStyleSheet("background: transparent; border: 1px dashed #666; color: #aaa; padding: 10px; border-radius: 6px;")
        self.btn_temizle.clicked.connect(self.formu_temizle)
        sol_panel.addWidget(self.btn_temizle)
        
        self.btn_kaydet = QPushButton("💾 KAYDET")
        self.btn_kaydet.setObjectName("btn_kaydet") # Yetki
        self.btn_kaydet.setCursor(Qt.PointingHandCursor)
        self.btn_kaydet.setMinimumHeight(50)
        self.btn_kaydet.setStyleSheet("""
            QPushButton { background-color: #2e7d32; color: white; border-radius: 8px; font-weight: bold; font-size: 14px; }
            QPushButton:hover { background-color: #388e3c; }
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
        grp_filtre = QGroupBox("Kalibrasyon Geçmişi")
        grp_filtre.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        grp_filtre.setStyleSheet("QGroupBox { font-size: 14px; font-weight: bold; color: #42a5f5; margin-top: 10px; }")
        
        filter_layout = QHBoxLayout(grp_filtre)
        
        self.txt_ara = QLineEdit()
        self.txt_ara.setPlaceholderText("Listede Ara...")
        # Stil temaya bırakıldı
        self.txt_ara.setFixedWidth(250)
        self.txt_ara.textChanged.connect(self.tabloyu_filtrele)
        
        btn_yenile = QPushButton("⟳")
        btn_yenile.setObjectName("btn_yenile")
        btn_yenile.setFixedSize(35, 35)
        btn_yenile.clicked.connect(self.verileri_yukle)
        # Stil temaya bırakıldı
        
        filter_layout.addStretch()
        filter_layout.addWidget(self.txt_ara)
        filter_layout.addWidget(btn_yenile)
        sag_panel.addWidget(grp_filtre)
        
        self.tablo = QTableWidget()
        self.tablo.setColumnCount(6)
        self.tablo.setHorizontalHeaderLabels(["ID", "Cihaz", "Firma", "Bitiş Tarihi", "Durum", "Belge"])
        self.tablo.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tablo.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tablo.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tablo.verticalHeader().setVisible(False)
        # Stil temaya bırakıldı
        self.tablo.cellClicked.connect(self.satir_secildi)
        
        sag_panel.addWidget(self.tablo)
        
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setStyleSheet("background: transparent; border: none; QProgressBar::chunk { background: #42a5f5; }")
        sag_panel.addWidget(self.progress)
        
        main_layout.addLayout(sag_panel)

    # --- UI HELPERS ---
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
        elif hasattr(parent, "addWidget"):
            parent.addWidget(grp)
        elif hasattr(parent, "addLayout"):
            parent.addWidget(grp)
            
        self.inputs[key] = widget
        return widget

    def create_file_manager(self, card, label, key):
        container = QWidget()
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0,0,0,0)
        
        self.lbl_dosya = QLabel("Dosya Seçilmedi")
        self.lbl_dosya.setStyleSheet("color: #666; font-style: italic;")
        
        btn_yukle = QPushButton("📂 Seç")
        btn_yukle.setFixedSize(60, 35)
        # Stil temaya bırakıldı
        btn_yukle.clicked.connect(self.dosya_sec)
        
        lay.addWidget(self.lbl_dosya)
        lay.addStretch()
        lay.addWidget(btn_yukle)
        
        grp = ModernInputGroup(label, container)
        container.setStyleSheet("background: transparent;")
        card.add_widget(grp)

    # --- MANTIK ---
    def tarih_hesapla(self):
        try:
            baslangic = self.inputs["YapilanTarih"].date().toPython()
            secim = self.inputs["Gecerlilik"].currentText()
            bitis = baslangic
            if secim == "6 Ay": bitis += relativedelta(months=6)
            elif secim == "1 Yıl": bitis += relativedelta(years=1)
            elif secim == "2 Yıl": bitis += relativedelta(years=2)
            elif secim == "3 Yıl": bitis += relativedelta(years=3)
            self.inputs["BitisTarihi"].setDate(QDate(bitis.year, bitis.month, bitis.day))
        except: pass

    def dosya_sec(self):
        yol, _ = QFileDialog.getOpenFileName(self, "Belge Seç", "", "PDF ve Resim (*.pdf *.jpg *.png)")
        if yol:
            self.secilen_dosya = yol
            self.lbl_dosya.setText(os.path.basename(yol))
            self.lbl_dosya.setStyleSheet("color: #4caf50;")

    def verileri_yukle(self):
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.loader = VeriYukleyici()
        self.loader.veri_hazir.connect(self.veriler_geldi)
        self.loader.hata_olustu.connect(lambda e: self.progress.setVisible(False))
        self.loader.start()

    def veriler_geldi(self, cihazlar_combo, cihaz_dict, firmalar, kalibrasyon_listesi):
        self.progress.setVisible(False)
        self.cihaz_sozlugu = cihaz_dict
        self.tum_kalibrasyonlar = kalibrasyon_listesi
        
        # Mevcut seçimi korumaya çalış
        mevcut_cihaz = self.inputs["Cihaz"].currentText()
        self.inputs["Cihaz"].blockSignals(True)
        self.inputs["Cihaz"].clear()
        self.inputs["Cihaz"].addItems(cihazlar_combo)
        self.inputs["Cihaz"].setCurrentText(mevcut_cihaz)
        self.inputs["Cihaz"].blockSignals(False)
        
        self.inputs["Firma"].clear()
        self.inputs["Firma"].addItems(firmalar)
        self.tabloyu_guncelle()

    def tabloyu_guncelle(self):
        self.tablo.setRowCount(0)
        # Veri Sırası: ID[0], CihazID[1], Firma[2], Sertifika[3], YapilanT[4], Gecerlilik[5], BitisT[6], Durum[7], Dosya[8], Aciklama[9]
        for row in reversed(self.tum_kalibrasyonlar):
            if len(row) < 8: continue 
            r = self.tablo.rowCount()
            self.tablo.insertRow(r)
            
            k_id = str(row[0])
            c_id = str(row[1])
            firma = str(row[2])
            bitis = str(row[6])
            durum = str(row[7])
            dosya = str(row[8]) if len(row) > 8 else "-"
            
            c_ad = self.cihaz_sozlugu.get(c_id, c_id)
            
            self.tablo.setItem(r, 0, QTableWidgetItem(k_id))
            self.tablo.setItem(r, 1, QTableWidgetItem(c_ad))
            self.tablo.setItem(r, 2, QTableWidgetItem(firma))
            
            item_tarih = QTableWidgetItem(bitis)
            try:
                bitis_dt = datetime.datetime.strptime(bitis, "%Y-%m-%d").date()
                kalan = (bitis_dt - datetime.date.today()).days
                if kalan < 0: item_tarih.setForeground(QColor("#ef5350"))
                elif kalan < 30: item_tarih.setForeground(QColor("#ffca28"))
                else: item_tarih.setForeground(QColor("#66bb6a"))
            except: pass
            self.tablo.setItem(r, 3, item_tarih)
            self.tablo.setItem(r, 4, QTableWidgetItem(durum))
            
            link_text = "📄 Belge" if "http" in dosya else "-"
            item_link = QTableWidgetItem(link_text)
            if "http" in dosya:
                item_link.setForeground(QColor("#42a5f5"))
                item_link.setToolTip(dosya)
            self.tablo.setItem(r, 5, item_link)
            
            self.tablo.item(r, 0).setData(Qt.UserRole, row)

    def satir_secildi(self, row, col):
        item = self.tablo.item(row, 0)
        if not item: return
        
        veri = item.data(Qt.UserRole)
        if not veri: return

        self.duzenleme_modu = True
        self.duzenlenen_id = str(veri[0])
        self.mevcut_link = str(veri[8]) if len(veri) > 8 else "-"
        
        self.btn_kaydet.setText("GÜNCELLE")
        self.btn_kaydet.setStyleSheet("background-color: #FFA000; color: white; border-radius: 8px; font-weight: bold;")

        c_id = str(veri[1])
        index = self.inputs["Cihaz"].findText(c_id, Qt.MatchContains)
        if index >= 0: self.inputs["Cihaz"].setCurrentIndex(index)
        
        self.inputs["Firma"].setCurrentText(str(veri[2]))
        self.inputs["Sertifika"].setText(str(veri[3]))
        
        try:
            self.inputs["YapilanTarih"].setDate(QDate.fromString(str(veri[4]), "yyyy-MM-dd"))
            self.inputs["BitisTarihi"].setDate(QDate.fromString(str(veri[6]), "yyyy-MM-dd"))
        except: pass
        
        self.inputs["Gecerlilik"].setCurrentText(str(veri[5]))
        self.inputs["Durum"].setCurrentText(str(veri[7]))
        
        if len(veri) > 9:
            self.inputs["Aciklama"].setText(str(veri[9]))
            
        if "http" in self.mevcut_link:
            self.lbl_dosya.setText("Mevcut Dosya Kayıtlı")
            self.lbl_dosya.setStyleSheet("color: #42a5f5;")
        else:
            self.lbl_dosya.setText("Dosya Yok")

    def formu_temizle(self):
        self.duzenleme_modu = False
        self.duzenlenen_id = None
        self.mevcut_link = "-"
        
        self.btn_kaydet.setText("💾 KAYDET")
        self.btn_kaydet.setStyleSheet("background-color: #2e7d32; color: white; border-radius: 8px; font-weight: bold;")
        
        self.inputs["Sertifika"].clear()
        self.inputs["Aciklama"].clear()
        self.inputs["Cihaz"].setCurrentIndex(-1)
        self.inputs["Durum"].setCurrentText("Tamamlandı")
        self.secilen_dosya = None
        self.lbl_dosya.setText("Dosya Seçilmedi")
        self.lbl_dosya.setStyleSheet("color: #666;")

    def kaydet_baslat(self):
        cihaz_text = self.inputs["Cihaz"].currentText()
        if not cihaz_text:
            show_info("Hata", "Lütfen bir cihaz seçiniz.", self)
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
            link = self.mevcut_link if self.duzenleme_modu else "-"
            self.kaydet_devam(link, cihaz_id)

    def kaydet_devam(self, link, cihaz_id):
        try:
            unique_id = self.duzenlenen_id if self.duzenleme_modu else f"K-{int(datetime.datetime.now().timestamp())}"
            
            firma = self.inputs["Firma"].currentText()
            sertifika = self.inputs["Sertifika"].text()
            yapilan = self.inputs["YapilanTarih"].date().toString("yyyy-MM-dd")
            gecerlilik = self.inputs["Gecerlilik"].currentText()
            bitis = self.inputs["BitisTarihi"].date().toString("yyyy-MM-dd")
            durum = self.inputs["Durum"].currentText()
            aciklama = self.inputs["Aciklama"].toPlainText()
            
            yeni_satir = [
                unique_id, cihaz_id, firma, sertifika, yapilan,
                gecerlilik, bitis, durum, link, aciklama
            ]
            
            mod = "guncelle" if self.duzenleme_modu else "yeni"
            
            self.saver = IslemKaydedici(yeni_satir, mod=mod, kayit_id=unique_id)
            self.saver.islem_tamam.connect(self.islem_bitti)
            self.saver.hata_olustu.connect(self.hata_goster)
            self.saver.start()
            
        except Exception as e:
            self.hata_goster(str(e))

    def islem_bitti(self):
        self.progress.setVisible(False)
        self.btn_kaydet.setEnabled(True)
        msg = "Kalibrasyon güncellendi." if self.duzenleme_modu else "Kalibrasyon kaydedildi."
        show_info("Başarılı", msg, self)
        self.formu_temizle()
        self.verileri_yukle()

    def hata_goster(self, msg):
        self.progress.setVisible(False)
        self.btn_kaydet.setEnabled(True)
        self.btn_kaydet.setText("GÜNCELLE" if self.duzenleme_modu else "💾 KAYDET")
        show_error("Hata", msg, self)

    def tabloyu_filtrele(self, text):
        text = text.lower()
        for i in range(self.tablo.rowCount()):
            match = False
            for j in range(self.tablo.columnCount()):
                item = self.tablo.item(i, j)
                if item and text in item.text().lower():
                    match = True
                    break
            self.tablo.setRowHidden(i, not match)

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
    from temalar.tema import TemaYonetimi
    TemaYonetimi.uygula_fusion_dark(app)
    win = KalibrasyonEklePenceresi()
    win.show()
    sys.exit(app.exec())