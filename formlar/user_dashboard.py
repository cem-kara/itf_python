# -*- coding: utf-8 -*-
import sys
import os
import math
from datetime import datetime

# PySide6 Kütüphaneleri
from PySide6.QtCore import Qt, QThread, Signal, QRectF, QPoint, QSize
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, 
    QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea,
    QGridLayout, QPushButton, QApplication, QTabWidget
)

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# --- PROJE MODÜLLERİ ---
try:
    from araclar.yetki_yonetimi import YetkiYoneticisi
    from temalar.tema import TemaYonetimi
    from google_baglanti import veritabani_getir
    from araclar.ortak_araclar import OrtakAraclar, show_error
except ImportError as e:
    print(f"Modül Hatası: {e}")

# =============================================================================
# ÖZEL BİLEŞEN: PASTA GRAFİK (PIE CHART)
# =============================================================================
class PastaGrafikWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = {} # {"Birim Adı": Sayı}
        self.colors = [
            QColor("#4dabf7"), QColor("#ff6b6b"), QColor("#51cf66"), 
            QColor("#fcc419"), QColor("#845ef7"), QColor("#ff922b"),
            QColor("#20c997"), QColor("#fa5252")
        ]
        self.setMinimumSize(300, 300)

    def veri_guncelle(self, veri_dict):
        self.data = veri_dict
        self.update() # Yeniden çiz

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = self.rect()
        genislik = min(rect.width(), rect.height()) - 40
        merkez = rect.center()
        
        if not self.data or sum(self.data.values()) == 0:
            painter.setPen(Qt.white)
            painter.drawText(rect, Qt.AlignCenter, "Veri Yok")
            return

        toplam = sum(self.data.values())
        baslangic_aci = 0 # Derece * 16 (Qt mantığı)
        
        i = 0
        for kategori, deger in self.data.items():
            if deger == 0: continue
            
            oran = deger / toplam
            aci_genisligi = int(oran * 360 * 16)
            
            color = self.colors[i % len(self.colors)]
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            
            # Dilimi Çiz
            r = QRectF(merkez.x() - genislik/2, merkez.y() - genislik/2, genislik, genislik)
            painter.drawPie(r, baslangic_aci, aci_genisligi)
            
            baslangic_aci += aci_genisligi
            i += 1

# =============================================================================
# WORKER: VERİ ANALİZİ
# =============================================================================
class DashboardWorker(QThread):
    veri_hazir = Signal(dict)
    
    def run(self):
        analiz = {
            "toplam_personel": 0,
            "aktif_personel": 0,
            "izinli_personel": 0,
            "dogum_gunleri": [], # [{"ad": "...", "tarih": "..."}, ...]
            "izindekiler": [],   # [{"ad": "...", "bitis": "..."}, ...]
            "birim_dagilimi": {} # {"Radyoloji": 5, "Lab": 3}
        }
        
        try:
            # 1. PERSONEL LİSTESİNİ ÇEK
            ws_p = veritabani_getir('personel', 'Personel')
            personeller = ws_p.get_all_records()
            
            bugun = datetime.now()
            bu_ay = bugun.month
            
            for p in personeller:
                # Anahtarları temizle (Boşlukları sil)
                p = {k.strip(): v for k, v in p.items()}
                
                ad = p.get('Ad_Soyad', '')
                durum = p.get('Durum', 'Aktif')
                birim = p.get('Hizmet_Sinifi', 'Diğer')
                dogum_tarihi_str = str(p.get('Dogum_Tarihi', ''))
                
                # İstatistikler
                analiz["toplam_personel"] += 1
                if durum == "Aktif":
                    analiz["aktif_personel"] += 1
                
                # Birim Dağılımı
                if birim:
                    analiz["birim_dagilimi"][birim] = analiz["birim_dagilimi"].get(birim, 0) + 1
                
                # Doğum Günü Kontrolü
                try:
                    dt = datetime.strptime(dogum_tarihi_str, "%d.%m.%Y")
                    if dt.month == bu_ay:
                        analiz["dogum_gunleri"].append({
                            "ad": ad,
                            "gun": dt.day,
                            "tam_tarih": dogum_tarihi_str
                        })
                except: pass

            # 2. İZİN DURUMUNU ÇEK (Aktif İzinler)
            ws_i = veritabani_getir('personel', 'izin_giris')
            izinler = ws_i.get_all_records()
            
            for i in izinler:
                i = {k.strip(): v for k, v in i.items()}
                try:
                    bas = datetime.strptime(i.get('Başlama_Tarihi', ''), "%d.%m.%Y")
                    bit = datetime.strptime(i.get('Bitiş_Tarihi', ''), "%d.%m.%Y")
                    
                    if bas <= bugun <= bit:
                        analiz["izinli_personel"] += 1
                        # Personel Adını ID'den veya direk listeden bulmak gerekebilir
                        # Şimdilik izin tablosunda Ad Soyad varsa onu alalım
                        ad_soyad = i.get('Ad_Soyad', i.get('personel_id', 'Bilinmiyor'))
                        analiz["izindekiler"].append({
                            "ad": ad_soyad,
                            "donus": bit.strftime("%d.%m.%Y"),
                            "tur": i.get('İzin_Türü', 'Yıllık')
                        })
                except: pass
                
            # Doğum günlerini sırala (Güne göre)
            analiz["dogum_gunleri"].sort(key=lambda x: x["gun"])
            
        except Exception as e:
            print(f"Dashboard Veri Hatası: {e}")
            
        self.veri_hazir.emit(analiz)

# =============================================================================
# ANA PENCERE
# =============================================================================
class DashboardPenceresi(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Yönetici Kontrol Paneli")
        self.resize(1200, 800)
        self.setStyleSheet("background-color: #121212; color: #e0e0e0;")
        
        self.setup_ui()
        self.verileri_yukle()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)
        
        # --- 1. BAŞLIK VE YENİLE ---
        header_layout = QHBoxLayout()
        lbl_baslik = QLabel(f"👋 Hoş Geldiniz, {datetime.now().strftime('%d %B %Y')}")
        lbl_baslik.setStyleSheet("font-size: 24px; font-weight: bold; color: #4dabf7;")
        
        btn_yenile = QPushButton("⟳ Verileri Yenile")
        btn_yenile.setStyleSheet("background-color: #333; color: white; padding: 8px 15px; border-radius: 5px;")
        btn_yenile.setCursor(Qt.PointingHandCursor)
        btn_yenile.clicked.connect(self.verileri_yukle)
        
        header_layout.addWidget(lbl_baslik)
        header_layout.addStretch()
        header_layout.addWidget(btn_yenile)
        main_layout.addLayout(header_layout)
        
        # --- 2. BİLGİ KARTLARI (KPI CARDS) ---
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(20)
        
        self.card_total = self._create_card("TOPLAM PERSONEL", "0", "#339af0") # Mavi
        self.card_active = self._create_card("AKTİF ÇALIŞAN", "0", "#51cf66") # Yeşil
        self.card_leave = self._create_card("İZİNDEKİLER", "0", "#fcc419")   # Sarı
        
        cards_layout.addWidget(self.card_total)
        cards_layout.addWidget(self.card_active)
        cards_layout.addWidget(self.card_leave)
        main_layout.addLayout(cards_layout)
        
        # --- 3. ORTA BÖLÜM (GRAFİK VE LİSTELER) ---
        middle_layout = QHBoxLayout()
        
        # SOL: Grafik Alanı
        chart_frame = QFrame()
        chart_frame.setStyleSheet("background-color: #1e1e1e; border-radius: 10px;")
        v_chart = QVBoxLayout(chart_frame)
        
        lbl_chart_title = QLabel("📊 Birimlere Göre Dağılım")
        lbl_chart_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #adb5bd; border: none;")
        v_chart.addWidget(lbl_chart_title, 0, Qt.AlignCenter)
        
        self.pie_chart = PastaGrafikWidget()
        v_chart.addWidget(self.pie_chart, 1, Qt.AlignCenter)
        
        # Legend (Açıklama) Alanı
        self.legend_layout = QGridLayout()
        v_chart.addLayout(self.legend_layout)
        
        middle_layout.addWidget(chart_frame, 2) # Sol taraf %40 genişlik (oran 2)
        
        # SAĞ: Listeler (Tab Yapısı)
        right_tabs = QTabWidget()
        right_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #333; background: #1e1e1e; border-radius: 5px; }
            QTabBar::tab { background: #2b2b2b; color: #aaa; padding: 10px 20px; }
            QTabBar::tab:selected { background: #1e1e1e; color: #4dabf7; font-weight: bold; border-top: 2px solid #4dabf7; }
        """)
        
        # Tab 1: Doğum Günleri
        self.tab_dogum = QWidget()
        v_dogum = QVBoxLayout(self.tab_dogum)
        self.table_dogum = self._create_table(["Gün", "Adı Soyadı", "Tarih"])
        v_dogum.addWidget(self.table_dogum)
        right_tabs.addTab(self.tab_dogum, "🎂 Bu Ay Doğanlar")
        
        # Tab 2: İzindekiler
        self.tab_izin = QWidget()
        v_izin = QVBoxLayout(self.tab_izin)
        self.table_izin = self._create_table(["Adı Soyadı", "Dönüş Tarihi", "İzin Türü"])
        v_izin.addWidget(self.table_izin)
        right_tabs.addTab(self.tab_izin, "🏖️ Şu An İzinde Olanlar")
        
        middle_layout.addWidget(right_tabs, 3) # Sağ taraf %60 genişlik (oran 3)
        
        main_layout.addLayout(middle_layout, 1) # Orta bölüm esnek

    def _create_card(self, title, value, color_hex):
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: #1e1e1e;
                border-left: 5px solid {color_hex};
                border-radius: 8px;
            }}
        """)
        lay = QVBoxLayout(frame)
        
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color: #adb5bd; font-size: 14px; font-weight: bold; border: none;")
        
        lbl_val = QLabel(value)
        lbl_val.setObjectName("value_label") # Güncellemek için ID
        lbl_val.setStyleSheet(f"color: {color_hex}; font-size: 36px; font-weight: bold; border: none;")
        
        lay.addWidget(lbl_title)
        lay.addWidget(lbl_val)
        return frame

    def _create_table(self, headers):
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setStyleSheet("""
            QTableWidget { background-color: #1e1e1e; border: none; gridline-color: #333; }
            QHeaderView::section { background-color: #2b2b2b; color: white; padding: 5px; border: none; }
            QTableWidget::item { padding: 5px; border-bottom: 1px solid #333; }
        """)
        return table

    def verileri_yukle(self):
        self.worker = DashboardWorker()
        self.worker.veri_hazir.connect(self._verileri_isles)
        self.worker.start()

    def _verileri_isles(self, data):
        # 1. Kartları Güncelle
        self.card_total.findChild(QLabel, "value_label").setText(str(data["toplam_personel"]))
        self.card_active.findChild(QLabel, "value_label").setText(str(data["aktif_personel"]))
        self.card_leave.findChild(QLabel, "value_label").setText(str(data["izinli_personel"]))
        
        # 2. Doğum Günleri Tablosu
        self.table_dogum.setRowCount(0)
        for d in data["dogum_gunleri"]:
            row = self.table_dogum.rowCount()
            self.table_dogum.insertRow(row)
            self.table_dogum.setItem(row, 0, QTableWidgetItem(str(d["gun"])))
            self.table_dogum.setItem(row, 1, QTableWidgetItem(d["ad"]))
            self.table_dogum.setItem(row, 2, QTableWidgetItem(d["tam_tarih"]))
            
        # 3. İzin Tablosu
        self.table_izin.setRowCount(0)
        for i in data["izindekiler"]:
            row = self.table_izin.rowCount()
            self.table_izin.insertRow(row)
            self.table_izin.setItem(row, 0, QTableWidgetItem(i["ad"]))
            self.table_izin.setItem(row, 1, QTableWidgetItem(i["donus"]))
            self.table_izin.setItem(row, 2, QTableWidgetItem(i["tur"]))
            
        # 4. Pasta Grafik ve Legend
        self.pie_chart.veri_guncelle(data["birim_dagilimi"])
        
        # Legend Temizle
        while self.legend_layout.count():
            child = self.legend_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
            
        # Legend Ekle
        colors = self.pie_chart.colors
        row, col = 0, 0
        i = 0
        for birim, sayi in data["birim_dagilimi"].items():
            if sayi == 0: continue
            color = colors[i % len(colors)]
            
            lbl_color = QLabel("  ")
            lbl_color.setStyleSheet(f"background-color: {color.name()}; border-radius: 3px;")
            lbl_color.setFixedSize(15, 15)
            
            lbl_text = QLabel(f"{birim} ({sayi})")
            lbl_text.setStyleSheet("color: #e0e0e0; font-size: 11px; border: none;")
            
            self.legend_layout.addWidget(lbl_color, row, col)
            self.legend_layout.addWidget(lbl_text, row, col+1)
            
            i += 1
            col += 2
            if col > 2: # 2 Sütunlu Legend
                col = 0
                row += 1

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = DashboardPenceresi()
    win.show()
    sys.exit(app.exec())