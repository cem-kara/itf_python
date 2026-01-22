# -*- coding: utf-8 -*-
import sys
import os
# DİKKAT: QPushButton'u import listesine ekledik
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QTabWidget, QLabel, QPushButton
from PySide6.QtGui import QIcon, QFont

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# --- MODÜL İMPORTLARI ---
try:
    from formlar.fhsz_hesapla import FHSZHesaplamaPenceresi
    from formlar.fhsz_puantaj import PuantajRaporPenceresi
    from temalar.tema import TemaYonetimi
except ImportError as e:
    print(f"Import Hatası: {e}")
    try:
        from fhsz_hesapla import FHSZHesaplamaPenceresi
        from FHSZ_Puantaj import PuantajRaporPenceresi
    except:
        pass
from araclar.yetki_yonetimi import YetkiYoneticisi
# =============================================================================
# 1. FHSZ YÖNETİM PANELİ
# =============================================================================

class FHSZYonetimPaneli(QWidget):
    def __init__(self, yetki='viewer'):
        super().__init__()
        self.yetki = yetki
        self.setWindowTitle("FHSZ Yönetim Sistemi")
        self.resize(1350, 900)
        
        # Ana Düzen
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # --- BAŞLIK ---
        lbl_baslik = QLabel("Radyoloji / FHSZ (Şua) Takip Sistemi")
        # Eğer tema dosyanız yoksa veya hata verirse font kısmını basitleştirebilirsiniz
        lbl_baslik.setStyleSheet("font-size: 20px; font-weight: bold; color: #4dabf7; margin-bottom: 5px;")
        layout.addWidget(lbl_baslik)

        # --- SEKME (TAB) YAPISI ---
        self.tabs = QTabWidget()
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
        self.tab_hesapla = FHSZHesaplamaPenceresi(self.yetki)
        
        # Buton gizleme (Güvenli Yöntem)
        if hasattr(self.tab_hesapla, 'btn_kapat'):
            self.tab_hesapla.btn_kapat.setVisible(False)
        else:
            # Sadece QPushButton olanları buluyoruz
            btns = self.tab_hesapla.findChildren(QPushButton)
            for b in btns:
                if "Çıkış" in b.text() or "İptal" in b.text():
                    b.setVisible(False)
            
        self.tabs.addTab(self.tab_hesapla, "📝 Hesaplama ve Veri Girişi")

        # --- 2. SEKME: RAPORLAMA ---
        self.tab_rapor = PuantajRaporPenceresi(self.yetki)
        
        # Buton gizleme (Güvenli Yöntem)
        if hasattr(self.tab_rapor, 'btn_kapat'): 
             self.tab_rapor.btn_kapat.setVisible(False)
        else:
            # DÜZELTME BURADA: QWidget yerine QPushButton kullanıldı.
            # Artık sadece butonları tarıyor, QFrame hatası vermez.
            btns = self.tab_rapor.findChildren(QPushButton) 
            for b in btns:
                if "Çıkış" in b.text() or "İptal" in b.text():
                    b.setVisible(False)

        self.tabs.addTab(self.tab_rapor, "📊 Raporlar ve Analiz")
        YetkiYoneticisi.uygula(self, "fhsz_yonetim")
        layout.addWidget(self.tabs)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    try:
        TemaYonetimi.uygula_fusion_dark(app)
    except:
        app.setStyle("Fusion")

    window = FHSZYonetimPaneli()
    window.show()
    sys.exit(app.exec())