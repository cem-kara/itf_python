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
# 1. FHSZ YÖNETİM PANELİ
# =============================================================================

class FHSZYonetimPaneli(QWidget):
    # 🟢 DÜZELTME 1: Main.py uyumu için 'kullanici_adi' parametresi eklendi
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.setWindowTitle("FHSZ Yönetim Sistemi")
        self.resize(1350, 900)
        
        # Ana Düzen
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # --- BAŞLIK ---
        lbl_baslik = QLabel("Radyoloji / FHSZ (Şua) Takip Sistemi")
        lbl_baslik.setStyleSheet("font-size: 20px; font-weight: bold; color: #4dabf7; margin-bottom: 5px;")
        layout.addWidget(lbl_baslik)

        # --- SEKME (TAB) YAPISI ---
        self.tabs = QTabWidget()
        self.tabs.setObjectName("tabs_fhsz") # Yetki için isim
        self.tabs.setStyleSheet("""
            QTabWidget::pane { 
                border: 1px solid #3e3e42; 
                background: #1e1e1e; 
                border-radius: 4px;
            }
            QTabBar::tab {
                background: #2d2d30;
                color: #aaa;
                padding: 12px 25px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #3e3e42;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background: #0078d4; 
                color: white;
                border-color: #0078d4;
            }
            QTabBar::tab:hover {
                background: #3e3e42;
                color: white;
            }
        """)

        # --- 1. SEKME: HESAPLAMA ---
        # Yetki ve kullanıcı adını alt forma iletiyoruz
        self.tab_hesapla = FHSZHesaplamaPenceresi(self.yetki, self.kullanici_adi)
        self.tab_hesapla.setObjectName("tab_hesapla") # Yetki için
        
        # Alt formdaki "Kapat/Çıkış" butonlarını gizle (Çünkü zaten ana pencere içinde)
        # 1. Yöntem: Doğrudan erişim (Varsa)
        if hasattr(self.tab_hesapla, 'btn_kapat'):
            self.tab_hesapla.btn_kapat.setVisible(False)
        # 2. Yöntem: Genel arama (Yedek)
        else:
            btns = self.tab_hesapla.findChildren(QPushButton)
            for b in btns:
                text = b.text().lower()
                if "çıkış" in text or "iptal" in text or "kapat" in text:
                    b.setVisible(False)
            
        self.tabs.addTab(self.tab_hesapla, "📝 Hesaplama ve Veri Girişi")

        # --- 2. SEKME: RAPORLAMA ---
        # Yetki ve kullanıcı adını alt forma iletiyoruz
        self.tab_rapor = PuantajRaporPenceresi(self.yetki, self.kullanici_adi)
        self.tab_rapor.setObjectName("tab_rapor") # Yetki için
        
        # Buton gizleme
        if hasattr(self.tab_rapor, 'btn_kapat'): # btn_kapat varsa gizle
             self.tab_rapor.btn_kapat.setVisible(False)
        else:
            btns = self.tab_rapor.findChildren(QPushButton)
            for b in btns:
                text = b.text().lower()
                if "çıkış" in text or "iptal" in text or "kapat" in text:
                    b.setVisible(False)

        self.tabs.addTab(self.tab_rapor, "📊 Raporlar ve Analiz")
        
        # 🟢 YETKİ KURALINI UYGULA
        YetkiYoneticisi.uygula(self, "fhsz_yonetim")
        
        layout.addWidget(self.tabs)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    try:
        from temalar.tema import TemaYonetimi
        TemaYonetimi.uygula_fusion_dark(app)
    except:
        app.setStyle("Fusion")

    window = FHSZYonetimPaneli()
    window.show()
    sys.exit(app.exec())