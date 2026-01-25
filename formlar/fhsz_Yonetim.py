# -*- coding: utf-8 -*-
import sys
import os
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QTabWidget, QLabel, QPushButton
from PySide6.QtGui import QIcon, QFont

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from araclar.yetki_yonetimi import YetkiYoneticisi

# --- MODÜL İMPORTLARI ---
try:
    from formlar.fhsz_hesapla import FHSZHesaplamaPenceresi
    from formlar.fhsz_puantaj import PuantajRaporPenceresi
    from temalar.tema import TemaYonetimi
except ImportError as e:
    print(f"Import Hatası: {e}")
    # Fallback (Hata durumunda programın çökmemesi için)
    class FHSZHesaplamaPenceresi(QWidget): 
        def __init__(self, y=None, k=None): super().__init__()
    class PuantajRaporPenceresi(QWidget): 
        def __init__(self, y=None, k=None): super().__init__()

# =============================================================================
# FHSZ YÖNETİM PANELİ
# =============================================================================
class FHSZYonetimPaneli(QWidget):
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.setWindowTitle("FHSZ (Şua) Yönetim Paneli")
        self.resize(1300, 850)
        
        self.setup_ui()
        
        # Yetki Kontrolü
        YetkiYoneticisi.uygula(self, "fhsz_yonetim")

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Başlık
        lbl_baslik = QLabel("FHSZ (Şua) Hakediş ve Raporlama Sistemi")
        lbl_baslik.setFont(QFont("Segoe UI", 16, QFont.Bold))
        # Manuel renk kaldırıldı, tema.py yönetecek
        main_layout.addWidget(lbl_baslik)
        
        # Tab Widget
        self.tabs = QTabWidget()
        
        # --- 1. SEKME: HESAPLAMA ---
        self.tab_hesapla = FHSZHesaplamaPenceresi(self.yetki, self.kullanici_adi)
        self._gizle_kapat_butonlari(self.tab_hesapla)
        self.tabs.addTab(self.tab_hesapla, "📝 Hesaplama ve Veri Girişi")
        
        # --- 2. SEKME: RAPORLAMA ---
        self.tab_rapor = PuantajRaporPenceresi(self.yetki, self.kullanici_adi)
        self._gizle_kapat_butonlari(self.tab_rapor)
        self.tabs.addTab(self.tab_rapor, "📊 Raporlar ve Analiz")
        
        main_layout.addWidget(self.tabs)

    def _gizle_kapat_butonlari(self, widget):
        """
        Alt formlar bir container içinde çalıştığı için, onların kendi 
        'Kapat' veya 'İptal' butonlarına gerek yoktur. Bu metod onları gizler.
        """
        # Bilinen ID'ler
        if hasattr(widget, 'btn_iptal'): widget.btn_iptal.setVisible(False)
        if hasattr(widget, 'btn_kapat'): widget.btn_kapat.setVisible(False)
            
        # Genel Arama (Metin bazlı)
        btns = widget.findChildren(QPushButton)
        for b in btns:
            text = b.text().lower()
            if "çıkış" in text or "iptal" in text or "kapat" in text:
                b.setVisible(False)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Tema uygulaması
    try:
        TemaYonetimi.uygula_fusion_dark(app)
    except Exception as e:
        print(f"Tema uygulanamadı: {e}")
        app.setStyle("Fusion")
    
    win = FHSZYonetimPaneli()
    win.show()
    sys.exit(app.exec())