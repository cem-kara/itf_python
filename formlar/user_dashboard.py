# -*- coding: utf-8 -*-
import sys
import os
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, 
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QPushButton, QScrollArea, QSizePolicy, QGridLayout
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# --- MODÜLLER ---
try:
    from google_baglanti import veritabani_getir
    from araclar.ortak_araclar import show_error
except ImportError:
    pass

# =============================================================================
# WORKER: İSTATİSTİKLERİ HESAPLA
# =============================================================================
class DashboardWorker(QThread):
    # Sinyal Güncellendi: (Aktif, Pasif, İzinli, İzinli_Listesi, Hizmet_Sinifi_Dagilimi)
    veri_hazir = Signal(int, int, int, list, dict)
    
    def run(self):
        try:
            # 1. PERSONEL VERİLERİ
            ws_personel = veritabani_getir('personel', 'Personel')
            personel_listesi = ws_personel.get_all_records() if ws_personel else []
            
            toplam_aktif = 0
            toplam_pasif = 0
            
            # Hizmet Sınıfı Sözlüğü (Örn: {'GİH': 5, 'SHS': 10})
            sinif_dagilimi = {} 
            
            for p in personel_listesi:
                durum = str(p.get('Durum', 'Aktif')).strip()
                
                # Sadece AKTİF personelleri sınıflara dahil et
                if durum == 'Pasif':
                    toplam_pasif += 1
                else:
                    toplam_aktif += 1
                    # Hizmet Sınıfını Say
                    h_sinifi = str(p.get('Hizmet_Sinifi', 'Belirsiz')).strip()
                    if not h_sinifi: h_sinifi = "Belirsiz"
                    
                    if h_sinifi in sinif_dagilimi:
                        sinif_dagilimi[h_sinifi] += 1
                    else:
                        sinif_dagilimi[h_sinifi] = 1

            # 2. İZİN VERİLERİ (BUGÜN İZİNLİ OLANLAR)
            ws_izin = veritabani_getir('personel', 'izin_giris')
            izin_listesi = ws_izin.get_all_records() if ws_izin else []
            
            bugun = datetime.now()
            izinli_personeller = [] 
            
            for izin in izin_listesi:
                try:
                    bas_str = str(izin.get('Başlama_Tarihi', ''))
                    bit_str = str(izin.get('Bitiş_Tarihi', ''))
                    
                    if not bas_str or not bit_str: continue
                    
                    bas_tar = datetime.strptime(bas_str, "%d.%m.%Y")
                    bit_tar = datetime.strptime(bit_str, "%d.%m.%Y")
                    
                    if bas_tar.date() <= bugun.date() <= bit_tar.date():
                        ad = str(izin.get('Ad_Soyad', ''))
                        tip = str(izin.get('izin_tipi', ''))
                        izinli_personeller.append([ad, tip, bit_str])
                        
                except ValueError:
                    continue

            izinli_sayisi = len(izinli_personeller)
            
            # Verileri Gönder
            self.veri_hazir.emit(toplam_aktif, toplam_pasif, izinli_sayisi, izinli_personeller, sinif_dagilimi)
            
        except Exception as e:
            print(f"Dashboard Hatası: {e}")
            self.veri_hazir.emit(0, 0, 0, [], {})

# =============================================================================
# WIDGET: DASHBOARD
# =============================================================================
class DashboardWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.verileri_guncelle()

    def setup_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(20)

        # --- 1. BAŞLIK ALANI ---
        header_layout = QHBoxLayout()
        lbl_baslik = QLabel("Sistem Özeti ve Durum")
        lbl_baslik.setStyleSheet("font-size: 24px; font-weight: bold; color: #4dabf7;")
        
        btn_yenile = QPushButton("🔄 Verileri Yenile")
        btn_yenile.setCursor(Qt.PointingHandCursor)
        btn_yenile.setStyleSheet("""
            QPushButton { background-color: #2d2d30; color: #ccc; border: 1px solid #444; padding: 8px 15px; border-radius: 5px; }
            QPushButton:hover { background-color: #3e3e42; color: white; }
        """)
        btn_yenile.clicked.connect(self.verileri_guncelle)
        
        header_layout.addWidget(lbl_baslik)
        header_layout.addStretch()
        header_layout.addWidget(btn_yenile)
        self.layout.addLayout(header_layout)

        # --- 2. KARTLAR (İSTATİSTİKLER) ---
        self.cards_layout = QHBoxLayout()
        self.cards_layout.setSpacing(15)
        
        self.card_aktif = self.create_card("👥 Aktif Personel", "-", "#0078d4") 
        self.card_izinli = self.create_card("🏖️ Bugün İzinli", "-", "#28a745") 
        self.card_pasif = self.create_card("🚫 Ayrılan/Pasif", "-", "#d13438") 
        
        self.cards_layout.addWidget(self.card_aktif)
        self.cards_layout.addWidget(self.card_izinli)
        self.cards_layout.addWidget(self.card_pasif)
        self.layout.addLayout(self.cards_layout)

        # --- 3. TABLO: BUGÜN İZİNLİ OLANLAR ---
        lbl_tablo = QLabel("Bugün İzinli Olan Personel Listesi")
        lbl_tablo.setStyleSheet("font-size: 16px; font-weight: bold; color: #ccc; margin-top: 10px;")
        self.layout.addWidget(lbl_tablo)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Personel Adı", "İzin Tipi", "Dönüş Tarihi"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setFixedHeight(200) # Tablo yüksekliğini sabitleyelim ki aşağıya yer kalsın
        self.table.setStyleSheet("QTableWidget { background-color: #1e1e1e; border: 1px solid #333; border-radius: 5px; } QHeaderView::section { background-color: #2d2d30; color: #ccc; padding: 5px; border: none; }")
        self.layout.addWidget(self.table)

        # --- 4. HİZMET SINIFI DAĞILIMI (YENİ EKLENEN KISIM) ---
        lbl_sinif = QLabel("Hizmet Sınıfına Göre Personel Dağılımı")
        lbl_sinif.setStyleSheet("font-size: 16px; font-weight: bold; color: #ccc; margin-top: 15px;")
        self.layout.addWidget(lbl_sinif)

        # Scroll Area içine koyuyoruz çünkü çok fazla sınıf olabilir
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFixedHeight(130) # Yükseklik sınırı
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; } QScrollBar:horizontal { height: 8px; }")
        
        self.sinif_container = QWidget()
        self.sinif_container.setStyleSheet("background: transparent;")
        self.sinif_layout = QHBoxLayout(self.sinif_container)
        self.sinif_layout.setContentsMargins(0, 0, 0, 0)
        self.sinif_layout.setSpacing(10)
        self.sinif_layout.setAlignment(Qt.AlignLeft) # Kartları sola yasla
        
        scroll_area.setWidget(self.sinif_container)
        self.layout.addWidget(scroll_area)

    def create_card(self, title, value, color):
        """Üst kısımdaki büyük kartlar."""
        frame = QFrame()
        frame.setStyleSheet(f"QFrame {{ background-color: {color}; border-radius: 12px; min-height: 90px; }}")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(15, 15, 15, 15)
        
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color: white; font-size: 14px; font-weight: 500; background: transparent;")
        
        lbl_val = QLabel(value)
        lbl_val.setObjectName("value_label")
        lbl_val.setStyleSheet("color: white; font-size: 32px; font-weight: bold; background: transparent;")
        lbl_val.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        
        fl.addWidget(lbl_title)
        fl.addStretch()
        fl.addWidget(lbl_val)
        return frame

    def create_mini_card(self, title, value):
        """Alt kısımdaki küçük hizmet sınıfı kartları."""
        frame = QFrame()
        frame.setFixedSize(140, 80)
        # Mor/Gri tonlarında tasarım
        frame.setStyleSheet("""
            QFrame { 
                background-color: #3b3b40; 
                border-radius: 8px; 
                border: 1px solid #555;
            }
            QFrame:hover {
                background-color: #45454a;
                border: 1px solid #777;
            }
        """)
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(10, 10, 10, 10)
        
        lbl_title = QLabel(title)
        # Uzun metinleri sığdırmak için word wrap
        lbl_title.setWordWrap(True) 
        lbl_title.setStyleSheet("color: #bbb; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        lbl_title.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        lbl_val = QLabel(str(value))
        lbl_val.setStyleSheet("color: #4dabf7; font-size: 24px; font-weight: bold; background: transparent; border: none;")
        lbl_val.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        
        fl.addWidget(lbl_title)
        fl.addWidget(lbl_val)
        return frame

    def verileri_guncelle(self):
        # Yükleniyor durumu
        self._update_card_value(self.card_aktif, "...")
        self._update_card_value(self.card_izinli, "...")
        self.worker = DashboardWorker()
        self.worker.veri_hazir.connect(self._verileri_islet)
        self.worker.start()

    def _verileri_islet(self, aktif, pasif, izinli_sayisi, izinli_liste, sinif_dagilimi):
        # 1. Kartları Güncelle
        self._update_card_value(self.card_aktif, str(aktif))
        self._update_card_value(self.card_pasif, str(pasif))
        self._update_card_value(self.card_izinli, str(izinli_sayisi))
        
        # 2. Tabloyu Güncelle
        self.table.setRowCount(len(izinli_liste))
        for i, row in enumerate(izinli_liste):
            self.table.setItem(i, 0, QTableWidgetItem(row[0]))
            self.table.setItem(i, 1, QTableWidgetItem(row[1]))
            self.table.setItem(i, 2, QTableWidgetItem(row[2]))

        # 3. Hizmet Sınıflarını Güncelle (Önce temizle, sonra ekle)
        self._clear_layout(self.sinif_layout)
        
        # Sözlüğü alfabetik sırala
        for sinif, sayi in sorted(sinif_dagilimi.items()):
            widget = self.create_mini_card(sinif, sayi)
            self.sinif_layout.addWidget(widget)
        
        # Sola yaslamak için stretch ekle (Eğer az kart varsa sola biriksin)
        self.sinif_layout.addStretch()

    def _update_card_value(self, card_widget, new_value):
        lbl = card_widget.findChild(QLabel, "value_label")
        if lbl: lbl.setText(new_value)

    def _clear_layout(self, layout):
        """Layout içindeki tüm widgetları temizler."""
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    try:
        from temalar.tema import TemaYonetimi
        TemaYonetimi.uygula_fusion_dark(app)
    except:
        app.setStyle("Fusion")
    
    win = DashboardWidget()
    win.show()
    sys.exit(app.exec())