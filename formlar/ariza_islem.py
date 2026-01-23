# -*- coding: utf-8 -*-
import sys
import os
import uuid
import logging
from datetime import datetime

from PySide6.QtCore import Qt, QDate, QThread, Signal
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QLineEdit, QComboBox, QDateEdit, QPushButton, QMessageBox,
                               QScrollArea, QFrame, QGridLayout, QProgressBar, QTextEdit, 
                               QGraphicsDropShadowEffect, QMdiSubWindow)

# --- LOGLAMA ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ArizaIslem")

# --- ANA KLASÖR BAĞLANTISI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from araclar.yetki_yonetimi import YetkiYoneticisi

# --- İMPORTLAR ---
try:
    from google_baglanti import veritabani_getir
    from araclar.ortak_araclar import pencereyi_kapat, show_info, show_error
except ImportError:
    def veritabani_getir(vt, sayfa): return None
    def pencereyi_kapat(w): w.close()
    def show_info(t, m, p): print(m)
    def show_error(t, m, p): print(m)

# --- SABİTLER ---
ISLEM_TURLERI = [
    "Arıza Tespiti / İnceleme",
    "Onarım / Tamirat",
    "Parça Değişimi",
    "Yazılım Güncelleme",
    "Kalibrasyon",
    "Dış Servis Gönderimi",
    "Kapatma / Sonlandırma"
]

DURUM_SECENEKLERI = [
    "İşlemde",
    "Parça Bekliyor",
    "Dış Serviste",
    "Kapalı (Çözüldü)",
    "Kapalı (İptal)"
]

# =============================================================================
# 1. THREAD SINIFLARI
# =============================================================================
class VeriYukleyici(QThread):
    # (Arıza Bilgileri Dict, Geçmiş İşlemler Listesi)
    veri_hazir = Signal(dict, list)
    hata_olustu = Signal(str)

    def __init__(self, ariza_id):
        super().__init__()
        self.ariza_id = str(ariza_id).strip()

    def run(self):
        ariza_bilgisi = {}
        gecmis_islemler = []
        try:
            # 1. Arıza Kaydını Bul (cihaz_ariza)
            ws_ariza = veritabani_getir('cihaz', 'cihaz_ariza')
            if ws_ariza:
                # Tüm veriyi çekip ID eşleşmesi yap
                tum_arizalar = ws_ariza.get_all_records()
                for kayit in tum_arizalar:
                    # CSV başlıkları küçük/büyük harf duyarlı olabilir
                    mevcut_id = str(kayit.get('ArizaID') or kayit.get('ariza_id') or '').strip()
                    if mevcut_id == self.ariza_id:
                        ariza_bilgisi = kayit
                        break
            
            # 2. Geçmiş İşlemleri Bul (ariza_islem)
            if ariza_bilgisi:
                ws_islem = veritabani_getir('cihaz', 'ariza_islem')
                if ws_islem:
                    tum_islemler = ws_islem.get_all_records()
                    for islem in tum_islemler:
                        bagli_id = str(islem.get('ArizaID') or islem.get('ariza_id') or '').strip()
                        if bagli_id == self.ariza_id:
                            gecmis_islemler.append(islem)

            self.veri_hazir.emit(ariza_bilgisi, gecmis_islemler)

        except Exception as e:
            self.hata_olustu.emit(str(e))

class IslemKaydedici(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)

    def __init__(self, ariza_id, islem_verisi, yeni_durum):
        super().__init__()
        self.ariza_id = str(ariza_id).strip()
        self.islem_verisi = islem_verisi # Liste: [ID, ArizaID, Tarih...]
        self.yeni_durum = yeni_durum

    def run(self):
        try:
            # 1. İşlemi Kaydet (ariza_islem tablosuna ekle)
            ws_islem = veritabani_getir('cihaz', 'ariza_islem')
            if ws_islem:
                ws_islem.append_row(self.islem_verisi)
            
            # 2. Arızanın Durumunu Güncelle (cihaz_ariza tablosunda bul ve güncelle)
            ws_ariza = veritabani_getir('cihaz', 'cihaz_ariza')
            if ws_ariza:
                cell = ws_ariza.find(self.ariza_id)
                if cell:
                    headers = ws_ariza.row_values(1)
                    col_idx = -1
                    for i, h in enumerate(headers):
                        if h.lower() in ["durum", "status"]:
                            col_idx = i + 1
                            break
                    
                    if col_idx != -1:
                        ws_ariza.update_cell(cell.row, col_idx, self.yeni_durum)
            
            self.islem_tamam.emit()

        except Exception as e:
            self.hata_olustu.emit(str(e))

# =============================================================================
# 2. UI BİLEŞENLERİ (ModernInputGroup & InfoCard)
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
        
        base_style = """
            background-color: #2b2b2b; border: 1px solid #3a3a3a; border-radius: 6px; 
            padding: 8px; color: #e0e0e0; font-size: 14px;
        """
        focus_style = "border: 1px solid #4dabf7;"
        
        if isinstance(widget, QTextEdit):
            self.widget.setMinimumHeight(80)
            self.widget.setStyleSheet(f"QTextEdit {{ {base_style} }} QTextEdit:focus {{ {focus_style} }}")
        else:
            self.widget.setStyleSheet(f"""
                QLineEdit, QComboBox, QDateEdit {{ {base_style} }}
                QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{ {focus_style} }}
                QLineEdit:read-only {{ background-color: #202020; color: #777; border: none; }}
            """)
        
        layout.addWidget(self.lbl)
        layout.addWidget(self.widget)

class InfoCard(QFrame):
    def __init__(self, title, parent=None, color_accent="#4dabf7"):
        super().__init__(parent)
        self.setStyleSheet("InfoCard { background-color: #1e1e1e; border-radius: 12px; border: 1px solid #333; }")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20); shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)
        
        if title:
            lbl_title = QLabel(title)
            lbl_title.setStyleSheet(f"color: {color_accent}; font-size: 14px; font-weight: bold; border-bottom: 1px solid #333; padding-bottom: 10px;")
            self.layout.addWidget(lbl_title)

    def add_widget(self, widget): self.layout.addWidget(widget)
    def add_layout(self, layout): self.layout.addLayout(layout)

# =============================================================================
# 3. ANA PENCERE
# =============================================================================
class ArizaIslemPenceresi(QWidget):
    # 🟢 DEĞİŞİKLİK 1: Parametreler
    def __init__(self, ariza_id, yetki='viewer', kullanici_adi=None, ana_pencere=None):
        super().__init__()
        self.ariza_id = str(ariza_id).strip()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        self.ana_pencere = ana_pencere
        
        self.setWindowTitle(f"Arıza Çözüm Süreci | {self.ariza_id}")
        self.resize(1100, 700)
        self.setStyleSheet("background-color: #121212;")
        
        self.inputs = {}
        self.ariza_data = {} 
        
        self.setup_ui()
        
        # 🟢 DEĞİŞİKLİK 2: Yetki
        YetkiYoneticisi.uygula(self, "ariza_islem")
        
        self.verileri_yukle()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0,0,0,0)
        
        # --- HEADER ---
        header = QFrame()
        header.setFixedHeight(60)
        header.setStyleSheet("background-color: #1e1e1e; border-bottom: 1px solid #333;")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(25, 0, 25, 0)
        
        lbl_baslik = QLabel(f"Arıza Takip Kartı: {self.ariza_id}")
        lbl_baslik.setFont(QFont("Segoe UI", 16, QFont.Bold))
        lbl_baslik.setStyleSheet("color: white;")
        
        self.progress = QProgressBar()
        self.progress.setFixedSize(150, 6)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("QProgressBar {background: #333; border-radius: 3px;} QProgressBar::chunk {background: #4dabf7;}")
        
        h_lay.addWidget(lbl_baslik)
        h_lay.addStretch()
        h_lay.addWidget(self.progress)
        main_layout.addWidget(header)

        # --- CONTENT (Scroll) ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        grid = QGridLayout(content)
        grid.setContentsMargins(25, 25, 25, 25)
        grid.setSpacing(25)
        grid.setColumnStretch(0, 1) 
        grid.setColumnStretch(1, 2) 

        # ================= SOL KOLON: ARIZA ÖZETİ (ReadOnly) =================
        card_ozet = InfoCard("Arıza Bilgileri", color_accent="#ff5252")
        
        self.add_input(card_ozet, "Cihaz", "cihaz_id", read_only=True)
        self.add_input(card_ozet, "Bildiren", "Bildiren", read_only=True)
        self.add_input(card_ozet, "Bildirim Tarihi", "baslangic_tarihi", read_only=True)
        self.add_input(card_ozet, "Konu", "baslik", read_only=True)
        
        txt_ozet = QTextEdit()
        txt_ozet.setReadOnly(True)
        grp_ozet = ModernInputGroup("Arıza Açıklaması", txt_ozet)
        card_ozet.add_widget(grp_ozet)
        self.inputs["ariza_acikla"] = txt_ozet
        
        self.add_input(card_ozet, "Mevcut Durum", "Durum", read_only=True)
        
        lbl_gecmis = QLabel("Geçmiş İşlemler")
        lbl_gecmis.setStyleSheet("color: #aaa; font-weight: bold; margin-top: 10px;")
        card_ozet.add_widget(lbl_gecmis)
        
        self.txt_gecmis = QTextEdit()
        self.txt_gecmis.setReadOnly(True)
        self.txt_gecmis.setStyleSheet("background: #262626; color: #888; font-size: 12px; border: 1px solid #333;")
        card_ozet.add_widget(self.txt_gecmis)
        
        grid.addWidget(card_ozet, 0, 0)

        # ================= SAĞ KOLON: MÜDAHALE GİRİŞİ =================
        card_islem = InfoCard("Müdahale & Çözüm Girişi", color_accent="#4CAF50")
        
        row1 = QHBoxLayout(); row1.setSpacing(15)
        self.add_input(row1, "İşlem Tarihi", "IslemTarih", "date")
        self.add_input(row1, "İşlem Saati", "IslemSaat")
        self.inputs["IslemSaat"].setText(datetime.now().strftime("%H:%M"))
        card_islem.add_layout(row1)
        
        row2 = QHBoxLayout(); row2.setSpacing(15)
        self.add_input(row2, "İşlemi Yapan", "IslemYapan")
        # 🟢 OTOMATİK DOLDURMA
        if self.kullanici_adi:
            self.inputs["IslemYapan"].setText(str(self.kullanici_adi))
        
        self.add_input(row2, "İşlem Türü", "IslemTuru", "combo")
        self.inputs["IslemTuru"].addItems(ISLEM_TURLERI)
        card_islem.add_layout(row2)
        
        txt_yapilan = QTextEdit()
        txt_yapilan.setPlaceholderText("Yapılan işlemleri detaylıca yazınız...")
        grp_yapilan = ModernInputGroup("Yapılan İşlem / Açıklama", txt_yapilan)
        card_islem.add_widget(grp_yapilan)
        self.inputs["YapilanIslem"] = txt_yapilan
        
        self.add_input(card_islem, "Kullanılan Malzeme / Parça", "Malzeme")
        
        self.add_input(card_islem, "Arızanın Yeni Durumu", "YeniDurum", "combo")
        self.inputs["YeniDurum"].addItems(DURUM_SECENEKLERI)
        self.inputs["YeniDurum"].setStyleSheet("QComboBox { border: 1px solid #4CAF50; color: #4CAF50; font-weight: bold; }")
        
        grid.addWidget(card_islem, 0, 1)

        scroll.setWidget(content)
        main_layout.addWidget(scroll)

        # --- FOOTER ---
        footer = QFrame()
        footer.setFixedHeight(80)
        footer.setStyleSheet("background-color: #1e1e1e; border-top: 1px solid #333;")
        foot_lay = QHBoxLayout(footer)
        foot_lay.setContentsMargins(30, 15, 30, 15)
        
        self.btn_kapat = QPushButton("Vazgeç")
        self.btn_kapat.setObjectName("btn_kapat") # 🟢 Yetki için
        self.btn_kapat.setFixedSize(120, 45)
        self.btn_kapat.setCursor(Qt.PointingHandCursor)
        self.btn_kapat.setStyleSheet("background: transparent; border: 1px solid #555; color: #aaa; border-radius: 8px;")
        self.btn_kapat.clicked.connect(lambda: pencereyi_kapat(self))
        
        self.btn_kaydet = QPushButton("✅ İşlemi Kaydet ve Durumu Güncelle")
        self.btn_kaydet.setObjectName("btn_kaydet") # 🟢 Yetki için
        self.btn_kaydet.setCursor(Qt.PointingHandCursor)
        self.btn_kaydet.setFixedHeight(45)
        self.btn_kaydet.setStyleSheet("""
            QPushButton { background-color: #2e7d32; color: white; border: none; border-radius: 8px; font-weight: bold; font-size: 14px; padding: 0 20px;}
            QPushButton:hover { background-color: #1b5e20; }
        """)
        self.btn_kaydet.clicked.connect(self.kaydet_baslat)
        
        foot_lay.addWidget(self.btn_kapat)
        foot_lay.addStretch()
        foot_lay.addWidget(self.btn_kaydet)
        main_layout.addWidget(footer)

    # --- UI YARDIMCILARI ---
    def add_input(self, parent, label, key, tip="text", read_only=False):
        widget = None
        if tip == "text": widget = QLineEdit()
        elif tip == "combo": widget = QComboBox()
        elif tip == "date": 
            widget = QDateEdit(); widget.setCalendarPopup(True); widget.setDisplayFormat("dd.MM.yyyy")
            widget.setDate(QDate.currentDate())
            
        if read_only:
            widget.setReadOnly(True)
            if tip == "combo": widget.setEnabled(False)
            
        grp = ModernInputGroup(label, widget)
        
        if isinstance(parent, InfoCard): parent.add_widget(grp)
        elif hasattr(parent, "addLayout"): parent.addWidget(grp)
        
        self.inputs[key] = widget
        return widget

    # --- MANTIK ---
    def verileri_yukle(self):
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.loader = VeriYukleyici(self.ariza_id)
        self.loader.veri_hazir.connect(self.verileri_doldur)
        self.loader.hata_olustu.connect(self.hata_goster)
        self.loader.start()

    def verileri_doldur(self, ariza_info, gecmis):
        self.progress.setRange(0, 100); self.progress.setValue(100)
        self.ariza_data = ariza_info
        
        if not ariza_info:
            show_error("Hata", "Arıza kaydı bulunamadı!", self)
            pencereyi_kapat(self)
            return

        def get_val(k):
            return str(ariza_info.get(k) or ariza_info.get(k.lower()) or ariza_info.get(k.capitalize()) or "-")

        self.inputs["cihaz_id"].setText(get_val("cihaz_id"))
        self.inputs["Bildiren"].setText(get_val("bildiren"))
        self.inputs["baslangic_tarihi"].setText(get_val("baslangic_tarihi"))
        self.inputs["baslik"].setText(get_val("baslik"))
        self.inputs["ariza_acikla"].setText(get_val("ariza_acikla"))
        self.inputs["Durum"].setText(get_val("durum"))
        
        mevcut_durum = get_val("durum")
        index = self.inputs["YeniDurum"].findText(mevcut_durum)
        if index >= 0: self.inputs["YeniDurum"].setCurrentIndex(index)

        log_text = ""
        for islem in gecmis:
            tarih = islem.get("Tarih", "")
            yapan = islem.get("IslemYapan", "")
            tur = islem.get("IslemTuru", "")
            detay = islem.get("YapilanIslem", "")
            log_text += f"[{tarih}] {yapan} ({tur}):\n{detay}\n{'-'*30}\n"
        
        if not log_text: log_text = "Henüz işlem yapılmamış."
        self.txt_gecmis.setText(log_text)

    def kaydet_baslat(self):
        yapan = self.inputs["IslemYapan"].text().strip()
        yapilan = self.inputs["YapilanIslem"].toPlainText().strip()
        
        if not yapan or not yapilan:
            show_info("Eksik", "Lütfen 'İşlemi Yapan' ve 'Yapılan İşlem' alanlarını doldurun.", self)
            return

        self.btn_kaydet.setText("Kaydediliyor...")
        self.btn_kaydet.setEnabled(False)
        self.progress.setRange(0, 0)
        
        islem_id = f"ISL-{uuid.uuid4().hex[:8].upper()}"
        tarih = self.inputs["IslemTarih"].date().toString("dd.MM.yyyy")
        saat = self.inputs["IslemSaat"].text()
        tur = self.inputs["IslemTuru"].currentText()
        malzeme = self.inputs["Malzeme"].text()
        yeni_durum = self.inputs["YeniDurum"].currentText()
        
        islem_verisi = [
            islem_id,
            self.ariza_id,
            tarih,
            saat,
            yapan,
            tur,
            yapilan,
            malzeme,
            yeni_durum
        ]
        
        self.saver = IslemKaydedici(self.ariza_id, islem_verisi, yeni_durum)
        self.saver.islem_tamam.connect(self.kayit_basarili)
        self.saver.hata_olustu.connect(self.hata_goster)
        self.saver.start()

    def kayit_basarili(self):
        self.progress.setRange(0, 100)
        show_info("Başarılı", "İşlem kaydedildi ve arıza durumu güncellendi.", self)
        
        if self.ana_pencere and hasattr(self.ana_pencere, 'verileri_yenile'):
            self.ana_pencere.verileri_yenile()
            
        pencereyi_kapat(self)

    def hata_goster(self, msg):
        self.progress.setRange(0, 100)
        show_error("Hata", msg, self)
        self.btn_kaydet.setEnabled(True)
        self.btn_kaydet.setText("✅ İşlemi Kaydet")

    # 🟢 DEĞİŞİKLİK 3: Thread Güvenliği
    def closeEvent(self, event):
        if hasattr(self, 'loader') and self.loader.isRunning():
            self.loader.quit()
            self.loader.wait(500)
        if hasattr(self, 'saver') and self.saver.isRunning():
            self.saver.quit()
            self.saver.wait(500)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = ArizaIslemPenceresi("ARZ-001")
    win.show()
    sys.exit(app.exec())