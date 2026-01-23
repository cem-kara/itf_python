# -*- coding: utf-8 -*-
import sys
import os
import logging
import datetime
from datetime import datetime as dt

from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QFrame, QGraphicsDropShadowEffect, QProgressBar, 
                               QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
                               QGridLayout, QScrollArea, QSizePolicy)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QCursor

# --- LOGLAMA ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Dashboard")

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from araclar.yetki_yonetimi import YetkiYoneticisi

# --- İMPORTLAR ---
try:
    from google_baglanti import veritabani_getir
    from araclar.ortak_araclar import show_error
except ImportError:
    def veritabani_getir(v, s): return None
    def show_error(t, m, p): print(m)

# =============================================================================
# 1. WORKER THREAD (TÜM VERİLERİ ÇEKEN MOTOR)
# =============================================================================
class DashboardWorker(QThread):
    # Sinyal: (PersonelSayi, CihazSayi, AcikAriza, YaklasanBakim, SonArizalarListesi, YaklasanKalibrasyonListesi)
    veri_hazir = Signal(dict)
    hata_olustu = Signal(str)

    def run(self):
        ozet = {
            "toplam_personel": 0,
            "toplam_cihaz": 0,
            "aktif_ariza": 0,
            "yaklasan_bakim": 0,
            "son_arizalar": [],
            "yaklasan_kalibrasyon": []
        }
        
        try:
            # 1. PERSONEL SAYISI
            ws_p = veritabani_getir('personel', 'Personel')
            if ws_p:
                p_data = ws_p.get_all_values()
                # Başlık hariç satır sayısı (Basit sayım)
                # İstenirse 'Durum' == 'Aktif' filtresi eklenebilir
                ozet["toplam_personel"] = len(p_data) - 1 if len(p_data) > 1 else 0

            # 2. CİHAZ SAYISI
            ws_c = veritabani_getir('cihaz', 'Cihazlar')
            if ws_c:
                c_data = ws_c.get_all_values()
                ozet["toplam_cihaz"] = len(c_data) - 1 if len(c_data) > 1 else 0

            # 3. AÇIK ARIZALAR & SON KAYITLAR
            ws_a = veritabani_getir('cihaz', 'cihaz_ariza')
            if ws_a:
                a_data = ws_a.get_all_records()
                acik_sayisi = 0
                son_kayitlar = []
                
                # Tersten döngü (En son eklenenler)
                for row in reversed(a_data):
                    durum = str(row.get('Durum', '')).strip()
                    if durum not in ["Kapalı", "İptal", "Çözüldü"]:
                        acik_sayisi += 1
                    
                    # Son 5 arızayı listeye ekle
                    if len(son_kayitlar) < 5:
                        son_kayitlar.append({
                            'id': row.get('ArizaID', '-'),
                            'cihaz': row.get('CihazID', '-'),
                            'konu': row.get('Konu', '-'),
                            'durum': durum,
                            'tarih': row.get('Tarih', '-')
                        })
                
                ozet["aktif_ariza"] = acik_sayisi
                ozet["son_arizalar"] = son_kayitlar

            # 4. YAKLAŞAN KALİBRASYONLAR (Önümüzdeki 30 gün)
            ws_k = veritabani_getir('cihaz', 'Kalibrasyon')
            if ws_k:
                k_data = ws_k.get_all_records()
                bugun = datetime.date.today()
                yaklasanlar = []
                
                for row in k_data:
                    bitis_str = str(row.get('BitisTarihi', '')).strip()
                    if bitis_str:
                        try:
                            # Tarih formatı kontrolü
                            for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
                                try:
                                    bitis_dt = datetime.datetime.strptime(bitis_str, fmt).date()
                                    break
                                except: continue
                            else:
                                continue # Format uymazsa atla

                            kalan_gun = (bitis_dt - bugun).days
                            if 0 <= kalan_gun <= 45: # 45 gün kala uyarı
                                yaklasanlar.append({
                                    'cihaz': row.get('CihazID', '-'),
                                    'bitis': bitis_str,
                                    'kalan': kalan_gun
                                })
                        except: pass
                
                # Kalan güne göre sırala
                yaklasanlar.sort(key=lambda x: x['kalan'])
                ozet["yaklasan_kalibrasyon"] = yaklasanlar[:10] # İlk 10

            self.veri_hazir.emit(ozet)

        except Exception as e:
            self.hata_olustu.emit(str(e))

# =============================================================================
# 2. UI BİLEŞENLERİ (KARTLAR)
# =============================================================================
class StatCard(QFrame):
    def __init__(self, title, value, icon_text="📊", color="#42a5f5", parent=None):
        super().__init__(parent)
        self.setFixedSize(240, 130)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #1e1e1e;
                border-radius: 12px;
                border-left: 5px solid {color};
            }}
        """)
        
        # Gölge
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)
        
        layout = QVBoxLayout(self)
        
        # Üst Kısım (Başlık ve İkon)
        top_layout = QHBoxLayout()
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color: #aaa; font-size: 14px; font-weight: bold;")
        
        lbl_icon = QLabel(icon_text)
        lbl_icon.setStyleSheet(f"color: {color}; font-size: 24px;")
        
        top_layout.addWidget(lbl_title)
        top_layout.addStretch()
        top_layout.addWidget(lbl_icon)
        
        # Orta Kısım (Değer)
        self.lbl_value = QLabel(str(value))
        self.lbl_value.setStyleSheet("color: white; font-size: 32px; font-weight: bold;")
        self.lbl_value.setAlignment(Qt.AlignLeft)
        
        layout.addLayout(top_layout)
        layout.addWidget(self.lbl_value)
        layout.addStretch()

    def set_value(self, val):
        self.lbl_value.setText(str(val))

class ModernTable(QTableWidget):
    def __init__(self, headers):
        super().__init__()
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.NoSelection)
        self.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e1e;
                border: 1px solid #333;
                border-radius: 8px;
                gridline-color: #333;
            }
            QHeaderView::section {
                background-color: #2b2b2b;
                color: #ccc;
                padding: 8px;
                border: none;
                font-weight: bold;
            }
            QTableWidget::item {
                padding: 5px;
                color: #ddd;
                border-bottom: 1px solid #2a2a2a;
            }
        """)

# =============================================================================
# 3. ANA PENCERE
# =============================================================================
class DashboardPenceresi(QWidget):
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.setWindowTitle("Yönetim Paneli (Dashboard)")
        self.resize(1200, 800)
        self.setStyleSheet("background-color: #121212;")
        
        self.setup_ui()
        YetkiYoneticisi.uygula(self, "dashboard")
        self.verileri_yenile()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)
        
        # --- 1. BAŞLIK VE YENİLEME ---
        header_layout = QHBoxLayout()
        
        lbl_welcome = QLabel(f"Hoşgeldiniz, {self.kullanici_adi if self.kullanici_adi else 'Misafir'}")
        lbl_welcome.setStyleSheet("color: white; font-size: 24px; font-weight: bold;")
        
        lbl_date = QLabel(datetime.datetime.now().strftime("%d.%m.%Y %H:%M"))
        lbl_date.setStyleSheet("color: #777; font-size: 14px;")
        
        self.btn_refresh = QPushButton("⟳ Yenile")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setFixedSize(100, 40)
        self.btn_refresh.setStyleSheet("""
            QPushButton { background-color: #333; color: white; border: 1px solid #555; border-radius: 6px; }
            QPushButton:hover { background-color: #444; }
        """)
        self.btn_refresh.clicked.connect(self.verileri_yenile)
        
        header_info = QVBoxLayout()
        header_info.addWidget(lbl_welcome)
        header_info.addWidget(lbl_date)
        
        header_layout.addLayout(header_info)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_refresh)
        
        main_layout.addLayout(header_layout)
        
        # --- 2. İSTATİSTİK KARTLARI ---
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(20)
        
        self.card_personel = StatCard("TOPLAM PERSONEL", "0", "👥", "#42a5f5")
        self.card_cihaz = StatCard("TOPLAM CİHAZ", "0", "📟", "#66bb6a")
        self.card_ariza = StatCard("AÇIK ARIZALAR", "0", "⚠️", "#ef5350")
        self.card_bakim = StatCard("YAKLAŞAN KALİB.", "0", "⏳", "#ffa726")
        
        cards_layout.addWidget(self.card_personel)
        cards_layout.addWidget(self.card_cihaz)
        cards_layout.addWidget(self.card_ariza)
        cards_layout.addWidget(self.card_bakim)
        cards_layout.addStretch()
        
        main_layout.addLayout(cards_layout)
        
        # --- 3. DETAY TABLOLARI ---
        tables_layout = QHBoxLayout()
        
        # Sol Tablo: Son Arızalar
        vbox_left = QVBoxLayout()
        lbl_left = QLabel("Son Bildirilen Arızalar")
        lbl_left.setStyleSheet("color: #ccc; font-size: 16px; font-weight: bold; margin-bottom: 5px;")
        self.tbl_ariza = ModernTable(["ID", "Cihaz", "Konu", "Durum", "Tarih"])
        vbox_left.addWidget(lbl_left)
        vbox_left.addWidget(self.tbl_ariza)
        
        # Sağ Tablo: Yaklaşan Kalibrasyonlar
        vbox_right = QVBoxLayout()
        lbl_right = QLabel("Yaklaşan Kalibrasyonlar (45 Gün)")
        lbl_right.setStyleSheet("color: #ccc; font-size: 16px; font-weight: bold; margin-bottom: 5px;")
        self.tbl_kalib = ModernTable(["Cihaz", "Bitiş Tarihi", "Kalan Gün"])
        vbox_right.addWidget(lbl_right)
        vbox_right.addWidget(self.tbl_kalib)
        
        tables_layout.addLayout(vbox_left, 60) # %60 genişlik
        tables_layout.addSpacing(20)
        tables_layout.addLayout(vbox_right, 40) # %40 genişlik
        
        main_layout.addLayout(tables_layout)
        
        # Progress Bar (Yükleme için)
        self.pbar = QProgressBar()
        self.pbar.setFixedHeight(4)
        self.pbar.setStyleSheet("background: transparent; border: none; QProgressBar::chunk { background: #4dabf7; }")
        self.pbar.setVisible(False)
        main_layout.addWidget(self.pbar)

    def verileri_yenile(self):
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("Yükleniyor...")
        self.pbar.setVisible(True)
        self.pbar.setRange(0, 0) # Sonsuz döngü
        
        self.worker = DashboardWorker()
        self.worker.veri_hazir.connect(self.verileri_guncelle)
        self.worker.hata_olustu.connect(self.hata_yakala)
        self.worker.start()

    def verileri_guncelle(self, data):
        self.pbar.setVisible(False)
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("⟳ Yenile")
        
        # Kartları Güncelle
        self.card_personel.set_value(data.get("toplam_personel", 0))
        self.card_cihaz.set_value(data.get("toplam_cihaz", 0))
        self.card_ariza.set_value(data.get("aktif_ariza", 0))
        self.card_bakim.set_value(len(data.get("yaklasan_kalibrasyon", [])))
        
        # Arıza Tablosunu Doldur
        arizalar = data.get("son_arizalar", [])
        self.tbl_ariza.setRowCount(0)
        for row in arizalar:
            r = self.tbl_ariza.rowCount()
            self.tbl_ariza.insertRow(r)
            self.tbl_ariza.setItem(r, 0, QTableWidgetItem(str(row['id'])))
            self.tbl_ariza.setItem(r, 1, QTableWidgetItem(str(row['cihaz'])))
            self.tbl_ariza.setItem(r, 2, QTableWidgetItem(str(row['konu'])))
            
            item_durum = QTableWidgetItem(str(row['durum']))
            if "Açık" in row['durum']: item_durum.setForeground(QColor("#ef5350"))
            elif "İşlemde" in row['durum']: item_durum.setForeground(QColor("#ffa726"))
            self.tbl_ariza.setItem(r, 3, item_durum)
            
            self.tbl_ariza.setItem(r, 4, QTableWidgetItem(str(row['tarih'])))

        # Kalibrasyon Tablosunu Doldur
        kalibler = data.get("yaklasan_kalibrasyon", [])
        self.tbl_kalib.setRowCount(0)
        for row in kalibler:
            r = self.tbl_kalib.rowCount()
            self.tbl_kalib.insertRow(r)
            self.tbl_kalib.setItem(r, 0, QTableWidgetItem(str(row['cihaz'])))
            self.tbl_kalib.setItem(r, 1, QTableWidgetItem(str(row['bitis'])))
            
            kalan = row['kalan']
            item_kalan = QTableWidgetItem(f"{kalan} Gün")
            if kalan < 15: item_kalan.setForeground(QColor("#ef5350")) # 15 günden azsa kırmızı
            else: item_kalan.setForeground(QColor("#ffa726")) # Sarı
            item_kalan.setFont(QFont("Segoe UI", 9, QFont.Bold))
            self.tbl_kalib.setItem(r, 2, item_kalan)

    def hata_yakala(self, err):
        self.pbar.setVisible(False)
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("⟳ Yenile")
        show_error("Veri Hatası", err, self)

    def closeEvent(self, event):
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(500)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    from temalar.tema import TemaYonetimi
    TemaYonetimi.uygula_fusion_dark(app)
    win = DashboardPenceresi(kullanici_adi="Test Admin")
    win.show()
    sys.exit(app.exec())