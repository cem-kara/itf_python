# -*- coding: utf-8 -*-
import sys
import os
import logging
import uuid
from datetime import datetime

from PySide6.QtCore import Qt, QDate, QThread, Signal, QSize
from PySide6.QtGui import QPixmap, QCursor, QFont, QColor
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QLineEdit, QComboBox, QDateEdit, QPushButton, QMessageBox,
                               QScrollArea, QFrame, QFileDialog, QGridLayout, 
                               QProgressBar, QGraphicsDropShadowEffect, QTextEdit, QMdiSubWindow, 
                               QCompleter, QGroupBox, QSizePolicy)

# --- LOGLAMA ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ArizaKayit")

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

# --- AYARLAR ---
DRIVE_KLASORLERI = {
    "ARIZA_DOSYALARI": "1eOq_NfrjN_XwKirUuX_0uyOonk137HjF"
}

# --- SABİT LİSTELER ---
ARIZA_TIPLERI = [
    "Donanımsal Arıza", "Yazılımsal Arıza", "Kullanıcı Hatası",
    "Ağ / Bağlantı Sorunu", "Parça Değişimi", "Periyodik Bakım Talebi", "Diğer"
]

ONCELIK_DURUMLARI = [
    "Düşük", "Normal", "Yüksek", "Acil (Kritik)"
]

# =============================================================================
# 1. THREAD SINIFLARI
# =============================================================================
class BaslangicYukleyici(QThread):
    veri_hazir = Signal(str, list)
    
    def run(self):
        yeni_id = "ARZ-001"
        cihaz_listesi = []

        try:
            # 1. Cihaz Listesini Çek
            ws_cihaz = veritabani_getir('cihaz', 'Cihazlar')
            if ws_cihaz:
                data = ws_cihaz.get_all_values()
                if len(data) > 1:
                    headers = [str(h).strip() for h in data[0]]
                    idx_id = -1; idx_marka = -1; idx_model = -1
                    
                    for i, h in enumerate(headers):
                        if h in ["cihaz_id", "CihazID", "kayit_no"]: idx_id = i
                        elif h in ["Marka"]: idx_marka = i
                        elif h in ["Model"]: idx_model = i
                    
                    if idx_id != -1:
                        for row in data[1:]:
                            if len(row) > idx_id:
                                c_id = str(row[idx_id]).strip()
                                c_marka = str(row[idx_marka]).strip() if idx_marka != -1 and len(row) > idx_marka else ""
                                c_model = str(row[idx_model]).strip() if idx_model != -1 and len(row) > idx_model else ""
                                if c_id:
                                    cihaz_str = f"{c_id} | {c_marka} {c_model}"
                                    cihaz_listesi.append(cihaz_str)

            # 2. Son Arıza ID
            ws_ariza = veritabani_getir('cihaz', 'cihaz_ariza')
            if ws_ariza:
                col_values = ws_ariza.col_values(1)
                if len(col_values) > 1:
                    last_id = col_values[-1]
                    if "ARZ-" in last_id:
                        try:
                            num = int(last_id.split("-")[1])
                            yeni_id = f"ARZ-{str(num + 1).zfill(3)}"
                        except: pass
        except Exception as e:
            logger.error(f"Başlangıç yükleme hatası: {e}")
        
        self.veri_hazir.emit(yeni_id, sorted(cihaz_listesi))

class KayitIslemi(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)

    def __init__(self, veri_listesi, dosya_yollari):
        super().__init__()
        self.veri = veri_listesi
        self.dosyalar = dosya_yollari

    def run(self):
        try:
            drive = GoogleDriveService()
            yuklenen_linkler = []
            for yol in self.dosyalar:
                if yol and os.path.exists(yol):
                    link = drive.upload_file(yol, DRIVE_KLASORLERI["ARIZA_DOSYALARI"])
                    if link: yuklenen_linkler.append(link)
            
            link_str = " | ".join(yuklenen_linkler)
            self.veri.append(link_str)

            ws = veritabani_getir('cihaz', 'cihaz_ariza')
            if not ws: raise Exception("Veritabanı bağlantısı yok.")
            
            ws.append_row(self.veri)
            self.islem_tamam.emit()

        except Exception as e:
            self.hata_olustu.emit(str(e))

# =============================================================================
# 2. UI: MODERN KONTROLLER
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
        
        if isinstance(widget, QTextEdit):
            self.widget.setMinimumHeight(100)
        
        # Manuel stiller kaldırıldı, TemaYonetimi yönetecek
        
        layout.addWidget(self.lbl)
        layout.addWidget(self.widget)

class InfoCard(QGroupBox):
    """
    Görsel gruplama sağlayan kart bileşeni (QGroupBox).
    """
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        
        self.setStyleSheet("""
            QGroupBox {
                background-color: #2d2d2d;
                border: 1px solid #444;
                border-radius: 8px;
                margin-top: 20px; 
                font-weight: bold;
                color: #ff5252; /* Arıza olduğu için kırmızımsı başlık */
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 10px;
                left: 10px;
            }
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

    def add_widget(self, widget):
        self.layout.addWidget(widget)

    def add_layout(self, layout):
        self.layout.addLayout(layout)

# =============================================================================
# 3. ANA PENCERE: ARIZA KAYIT
# =============================================================================
class ArizaKayitPenceresi(QWidget):
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.setWindowTitle("Yeni Arıza Kaydı")
        self.resize(1000, 750)
        # Manuel arka plan kaldırıldı

        self.inputs = {}
        self.control_buttons = {}
        self.secilen_dosyalar = [] 
        
        self.setup_ui()
        
        # Yetki
        YetkiYoneticisi.uygula(self, "ariza_kayit")
        
        self.baslangic_yukle()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0,0,0,0)
        main_layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setFixedHeight(60)
        header.setObjectName("panel_frame") 
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(25, 0, 25, 0)
        
        lbl_baslik = QLabel("Arıza Bildirim Formu")
        lbl_baslik.setFont(QFont("Segoe UI", 16, QFont.Bold))
        # Renk temaya bırakıldı veya özel renk korunabilir
        lbl_baslik.setStyleSheet("color: #ff5252;")
        
        self.progress = QProgressBar()
        self.progress.setFixedSize(150, 6)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("QProgressBar {background: #333; border-radius: 3px;} QProgressBar::chunk {background: #ff5252; border-radius: 3px;}")
        
        h_lay.addWidget(lbl_baslik)
        h_lay.addStretch()
        h_lay.addWidget(self.progress)
        main_layout.addWidget(header)

        # Scroll
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        content = QWidget()
        # content.setStyleSheet("background: transparent;")
        grid = QGridLayout(content)
        grid.setContentsMargins(25, 25, 25, 25)
        grid.setSpacing(25)
        
        # --- SOL KOLON (Cihaz & Kimlik) ---
        card_cihaz = InfoCard("Cihaz ve Bildirim Bilgileri")
        
        self.add_modern_input(card_cihaz, "Arıza Kayıt No (Otomatik)", "ArizaID")
        self.inputs["ArizaID"].setReadOnly(True)
        # Sadece ID alanı için özel stil
        self.inputs["ArizaID"].setStyleSheet("background-color: #202020; color: #ff5252; font-weight: bold;")
        
        self.add_modern_input(card_cihaz, "İlgili Cihazı Seçiniz", "CihazID", "combo", stretch=1)
        self.inputs["CihazID"].setEditable(True)
        self.inputs["CihazID"].setPlaceholderText("ID veya Marka yazarak arayın...")
        self.inputs["CihazID"].completer().setCompletionMode(QCompleter.PopupCompletion)
        
        row1 = QHBoxLayout(); row1.setSpacing(15)
        self.add_modern_input(row1, "Bildirim Tarihi", "Tarih", "date", stretch=1)
        self.add_modern_input(row1, "Bildirim Saati", "Saat", "text", stretch=1)
        self.inputs["Saat"].setPlaceholderText("HH:MM")
        card_cihaz.add_layout(row1)
        
        self.add_modern_input(card_cihaz, "Bildiren Personel", "Bildiren")
        grid.addWidget(card_cihaz, 0, 0)

        # --- SAĞ KOLON (Arıza Detay) ---
        card_detay = InfoCard("Arıza Detayları")
        row2 = QHBoxLayout(); row2.setSpacing(15)
        self.add_modern_input(row2, "Arıza Tipi", "ArizaTipi", "combo", stretch=1)
        self.inputs["ArizaTipi"].addItems(ARIZA_TIPLERI)
        self.add_modern_input(row2, "Öncelik Durumu", "Oncelik", "combo", stretch=1)
        self.inputs["Oncelik"].addItems(ONCELIK_DURUMLARI)
        card_detay.add_layout(row2)
        
        self.add_modern_input(card_detay, "Konu / Başlık", "Konu")
        
        txt_aciklama = QTextEdit()
        txt_aciklama.setPlaceholderText("Arızayı detaylı bir şekilde açıklayınız...")
        grp_aciklama = ModernInputGroup("Arıza Açıklaması", txt_aciklama)
        card_detay.add_widget(grp_aciklama)
        self.inputs["Aciklama"] = txt_aciklama
        grid.addWidget(card_detay, 0, 1)

        # --- ALT SATIR (Dosyalar) ---
        card_dosya = InfoCard("Ekler ve Medya")
        self.create_file_manager(card_dosya, "Arıza Görseli / Tutanağı Ekle", "Dosya")
        grid.addWidget(card_dosya, 1, 0, 1, 2)

        scroll.setWidget(content)
        main_layout.addWidget(scroll)

        # Footer
        footer = QFrame()
        footer.setFixedHeight(80)
        footer.setObjectName("panel_frame")
        foot_lay = QHBoxLayout(footer)
        foot_lay.setContentsMargins(30, 15, 30, 15)
        
        self.btn_iptal = QPushButton("İptal")
        self.btn_iptal.setObjectName("btn_iptal")
        self.btn_iptal.setFixedSize(140, 45)
        self.btn_iptal.setCursor(Qt.PointingHandCursor)
        self.btn_iptal.clicked.connect(self.pencereyi_kapat)
        
        self.btn_kaydet = QPushButton("⚠️ Arıza Kaydı Oluştur")
        self.btn_kaydet.setObjectName("btn_kaydet") # Tema ID (Genellikle yeşil olur ama burası arıza kaydı)
        self.btn_kaydet.setFixedSize(220, 45)
        self.btn_kaydet.setCursor(Qt.PointingHandCursor)
        # Arıza kaydı olduğu için kırmızı stil özel olarak korunabilir veya temadan 'btn_danger' vb. kullanılabilir.
        # Şimdilik manuel stil yerine, temaya uygun kırmızı tanımını bırakıyorum (tema yoksa çalışır).
        self.btn_kaydet.setStyleSheet("""
            QPushButton { background-color: #d32f2f; color: white; border: none; border-radius: 8px; font-weight: bold; font-size: 14px; }
            QPushButton:hover { background-color: #b71c1c; }
            QPushButton:disabled { background-color: #444; color: #888; }
        """)
        self.btn_kaydet.clicked.connect(self.kaydet_baslat)
        
        foot_lay.addWidget(self.btn_iptal)
        foot_lay.addStretch()
        foot_lay.addWidget(self.btn_kaydet)
        main_layout.addWidget(footer)

    def pencereyi_kapat(self):
        pencereyi_kapat(self)

    # --- UI YARDIMCILARI ---
    def add_modern_input(self, parent, label, key, tip="text", db_kodu=None, stretch=0):
        widget = None
        if tip == "text": widget = QLineEdit()
        elif tip == "combo": widget = QComboBox(); widget.setProperty("db_kodu", db_kodu)
        elif tip == "date": 
            widget = QDateEdit(); widget.setCalendarPopup(True); widget.setDisplayFormat("dd.MM.yyyy")
            widget.setDate(QDate.currentDate())
            
        grp = ModernInputGroup(label, widget)
        if isinstance(parent, InfoCard): parent.add_widget(grp)
        elif hasattr(parent, "addWidget"): parent.addWidget(grp, stretch)
        
        self.inputs[key] = widget
        return widget

    def create_file_manager(self, card, label, key):
        container = QWidget()
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0,0,0,0)
        
        edt = QLineEdit()
        edt.setReadOnly(True)
        edt.setPlaceholderText("Dosya seçilmedi")
        # Stil temaya bırakıldı
        
        btn = QPushButton("📎 Ekle")
        btn.setFixedSize(60, 35)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setObjectName("btn_standart") # Tema ID
        btn.clicked.connect(lambda: self.dosya_sec(key, edt))
        
        lay.addWidget(edt)
        lay.addWidget(btn)
        
        self.inputs[key] = edt 
        grp = ModernInputGroup(label, container)
        container.setStyleSheet("background: transparent;")
        card.add_widget(grp)

    # --- MANTIK ---
    def baslangic_yukle(self):
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.loader = BaslangicYukleyici()
        self.loader.veri_hazir.connect(self.veriler_yuklendi)
        self.loader.start()

    def veriler_yuklendi(self, yeni_id, cihaz_listesi):
        self.progress.setRange(0, 100); self.progress.setValue(100)
        self.inputs["ArizaID"].setText(yeni_id)
        
        simdi = datetime.now().strftime("%H:%M")
        self.inputs["Saat"].setText(simdi)
        
        # 🟢 OTOMATİK DOLDURMA: Bildiren Personel
        if self.kullanici_adi:
            self.inputs["Bildiren"].setText(str(self.kullanici_adi))
        
        self.inputs["CihazID"].clear()
        self.inputs["CihazID"].addItem("")
        self.inputs["CihazID"].addItems(cihaz_listesi)

    def dosya_sec(self, key, line_edit):
        yol, _ = QFileDialog.getOpenFileName(self, "Dosya Seç", "", "Resim/PDF (*.jpg *.png *.pdf)")
        if yol:
            line_edit.setText(yol)
            self.secilen_dosyalar = [yol]

    def kaydet_baslat(self):
        cihaz_secim = self.inputs["CihazID"].currentText()
        cihaz_id = cihaz_secim.split("|")[0].strip() if "|" in cihaz_secim else cihaz_secim.strip()
        konu = self.inputs["Konu"].text().strip()
        
        if not cihaz_id or not konu:
            show_error("Eksik", "Lütfen Cihaz ve Konu alanlarını doldurun.", self)
            return

        self.btn_kaydet.setText("⏳ Kaydediliyor...")
        self.btn_kaydet.setEnabled(False)
        self.progress.setRange(0, 0)
        QApplication.setOverrideCursor(Qt.WaitCursor)

        def v(k):
            w = self.inputs.get(k)
            if not w: return ""
            if isinstance(w, QLineEdit): return w.text().strip()
            if isinstance(w, QComboBox): return w.currentText()
            if isinstance(w, QDateEdit): return w.date().toString("yyyy-MM-dd")
            if isinstance(w, QTextEdit): return w.toPlainText().strip()
            return ""

        veri_listesi = [
            v("ArizaID"), cihaz_id, v("Tarih"), v("Saat"), v("Bildiren"),
            v("ArizaTipi"), v("Oncelik"), v("Konu"), v("Aciklama"), "Açık"
        ]

        dosyalar = []
        dosya_yolu = self.inputs["Dosya"].text()
        if dosya_yolu: dosyalar.append(dosya_yolu)

        self.saver = KayitIslemi(veri_listesi, dosyalar)
        self.saver.islem_tamam.connect(self.kayit_basarili)
        self.saver.hata_olustu.connect(self.kayit_hatali)
        self.saver.start()

    def kayit_basarili(self):
        QApplication.restoreOverrideCursor()
        self.progress.setRange(0, 100); self.progress.setValue(100)
        show_info("Başarılı", "Arıza kaydı oluşturuldu.", self)
        self.pencereyi_kapat() 

    def kayit_hatali(self, hata):
        QApplication.restoreOverrideCursor()
        self.progress.setRange(0, 100); self.progress.setValue(0)
        self.btn_kaydet.setText("⚠️ Arıza Kaydı Oluştur")
        self.btn_kaydet.setEnabled(True)
        show_error("Hata", f"Kayıt Hatası: {hata}", self)

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
    
    try:
        TemaYonetimi.uygula_fusion_dark(app)
    except Exception as e:
        print(f"Tema uygulanamadı: {e}")
        app.setStyle("Fusion")
        
    win = ArizaKayitPenceresi()
    win.show()
    sys.exit(app.exec())