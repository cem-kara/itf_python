# -*- coding: utf-8 -*-
import sys
import os
import calendar
from datetime import datetime, timedelta

# PySide6 Kütüphaneleri
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QBrush, QFont, QPen, QPainter
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, 
    QPushButton, QApplication, QTableWidget, QTableWidgetItem, 
    QHeaderView, QAbstractItemView, QGridLayout, QStyledItemDelegate
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
# ÖZEL DELEGATE: RENKLERİ BOZMADAN ÇİZGİ ÇEKEN RESSAM
# =============================================================================
class SatirCizgiliDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        # 1. Önce standart çizimi yap (Arka plan renkleri, metinler vs. korunsun)
        super().paint(painter, option, index)
        
        # 2. Şimdi altına ince bir çizgi çek
        painter.save()
        # Çizgi Rengi: #333333 (Arka plandan biraz açık, silik gri)
        painter.setPen(QPen(QColor("#333333"), 1)) 
        
        # Koordinatlar: Sol Alt -> Sağ Alt
        p1 = option.rect.bottomLeft()
        p2 = option.rect.bottomRight()
        
        painter.drawLine(p1, p2)
        painter.restore()

# =============================================================================
# WORKER 1: İZİN VERİLERİNİ ÇEK
# =============================================================================
class TakvimWorker(QThread):
    veri_hazir = Signal(list)
    
    def run(self):
        izinler_listesi = []
        try:
            ws = veritabani_getir('personel', 'izin_giris')
            raw_data = ws.get_all_records()
            
            for row in raw_data:
                r = {k.strip(): v for k, v in row.items()}
                try:
                    s_bas = r.get('Başlama_Tarihi', '').strip()
                    s_bit = r.get('Bitiş_Tarihi', '').strip()
                    if not s_bas or not s_bit: continue
                    
                    bas = datetime.strptime(s_bas, "%d.%m.%Y").date()
                    bit = datetime.strptime(s_bit, "%d.%m.%Y").date()
                    
                    tur = str(r.get('izin_tipi', 'Diğer')).strip()
                    
                    izinler_listesi.append({
                        "ad": r.get('Ad_Soyad', r.get('personel_id', 'Bilinmiyor')),
                        "tur": tur,
                        "bas": bas,
                        "bit": bit
                    })
                except: continue
        except Exception as e:
            print(f"Takvim Veri Hatası: {e}")
            
        self.veri_hazir.emit(izinler_listesi)

# =============================================================================
# WORKER 2: RENKLERİ SABİTLER TABLOSUNDAN ÇEK
# =============================================================================
class RenkWorker(QThread):
    renkler_hazir = Signal(dict)
    
    def run(self):
        renk_map = {}
        try:
            ws = veritabani_getir('sabit', 'Sabitler')
            records = ws.get_all_records()
            for r in records:
                if str(r.get('Kod', '')).strip() == 'Izin_Tipi':
                    izin_adi = str(r.get('MenuEleman', '')).strip()
                    renk_kodu = str(r.get('Aciklama', '')).strip()
                    if izin_adi and renk_kodu.startswith('#'):
                        renk_map[izin_adi] = renk_kodu
        except Exception as e:
            print(f"Renk Yükleme Hatası: {e}")
        self.renkler_hazir.emit(renk_map)

# =============================================================================
# ANA PENCERE
# =============================================================================
class IzinTakvimPenceresi(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Personel İzin Çizelgesi")
        self.resize(1300, 750)
        
        # 🟢 GÜNCELLENMİŞ CSS (ITEM BORDER SİLİNDİ - DELEGATE HALLEDECEK)
        self.setStyleSheet("""
            QWidget {
                background-color: #121212;
                color: #e0e0e0;
                font-family: 'Segoe UI', sans-serif;
            }
            QFrame#TopBar {
                background-color: #1e1e1e;
                border: 1px solid #333;
                border-radius: 8px;
            }
            QPushButton {
                background-color: #2b2b2b;
                border: 1px solid #444;
                color: white;
                padding: 5px 15px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #444;
                border-color: #666;
            }
            QLabel#Title {
                font-size: 20px;
                font-weight: bold;
                color: #4dabf7;
            }
            QTableWidget {
                background-color: #1e1e1e;
                border: none;
                gridline-color: transparent; 
            }
            QHeaderView::section {
                background-color: #252525;
                color: #b0b0b0;
                padding: 4px;
                border: none;
                border-bottom: 2px solid #444;
                font-weight: bold;
                font-size: 12px;
            }
            /* NOT: QTableWidget::item burada YOK, çünkü Delegate kullanıyoruz. */
            
            QScrollBar:horizontal { border: none; background: #121212; height: 10px; }
            QScrollBar::handle:horizontal { background: #444; min-width: 20px; border-radius: 5px; }
            QScrollBar:vertical { border: none; background: #121212; width: 10px; }
            QScrollBar::handle:vertical { background: #444; min-height: 20px; border-radius: 5px; }
        """)
        
        self.current_date = datetime.now().date()
        self.izin_verileri = []
        self.ozel_renkler = {}
        
        self.setup_ui()
        YetkiYoneticisi.uygula(self, "izin_takvim")
        self.renkleri_yukle()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        # ÜST BAR
        top_bar = QFrame(); top_bar.setObjectName("TopBar")
        h_top = QHBoxLayout(top_bar)
        
        self.btn_prev = QPushButton("◀ Önceki Ay"); self.btn_prev.setFixedSize(100, 30); self.btn_prev.clicked.connect(self._onceki_ay)
        self.lbl_tarih = QLabel("..."); self.lbl_tarih.setObjectName("Title"); self.lbl_tarih.setAlignment(Qt.AlignCenter)
        self.btn_next = QPushButton("Sonraki Ay ▶"); self.btn_next.setFixedSize(100, 30); self.btn_next.clicked.connect(self._sonraki_ay)
        self.btn_yenile = QPushButton("⟳ Verileri Yenile"); self.btn_yenile.clicked.connect(self.verileri_yukle)
        
        h_top.addWidget(self.btn_prev); h_top.addStretch(); h_top.addWidget(self.lbl_tarih); h_top.addStretch(); h_top.addWidget(self.btn_next); h_top.addSpacing(20); h_top.addWidget(self.btn_yenile)
        main_layout.addWidget(top_bar)
        
        # TABLO
        self.table = QTableWidget()
        
        # 🟢 ÖZEL DELEGATE ATAMASI (Çizgiyi bu çizecek)
        self.table.setItemDelegate(SatirCizgiliDelegate(self.table))
        
        self.table.setShowGrid(False)  
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        
        self.table.verticalHeader().setVisible(True); self.table.verticalHeader().setFixedWidth(180)
        self.table.horizontalHeader().setDefaultSectionSize(30); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        
        main_layout.addWidget(self.table)
        
        # LEJAND
        self.legend_frame = QFrame()
        self.legend_layout = QGridLayout(self.legend_frame)
        self.legend_layout.setContentsMargins(0, 5, 0, 0)
        self.legend_layout.setSpacing(10)
        main_layout.addWidget(self.legend_frame)

    def renkleri_yukle(self):
        self.btn_yenile.setText("Renkler Yükleniyor...")
        self.btn_yenile.setEnabled(False)
        self.r_worker = RenkWorker()
        self.r_worker.renkler_hazir.connect(self._renkler_geldi)
        self.r_worker.start()

    def _renkler_geldi(self, renk_map):
        self.ozel_renkler = renk_map
        self._lejand_guncelle()
        self.verileri_yukle()

    def verileri_yukle(self):
        self.btn_yenile.setText("Veriler Yükleniyor...")
        self.btn_yenile.setEnabled(False)
        self.worker = TakvimWorker()
        self.worker.veri_hazir.connect(self._veri_geldi)
        self.worker.start()

    def _veri_geldi(self, data):
        self.izin_verileri = data
        self.btn_yenile.setText("⟳ Verileri Yenile")
        self.btn_yenile.setEnabled(True)
        self.cizelgeyi_ciz()

    def _lejand_guncelle(self):
        while self.legend_layout.count():
            item = self.legend_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        row, col, max_cols = 0, 0, 6
        for ad, kod in sorted(self.ozel_renkler.items()):
            container = QWidget()
            h_lay = QHBoxLayout(container); h_lay.setContentsMargins(0, 0, 0, 0); h_lay.setSpacing(5)
            
            lbl_c = QLabel(); lbl_c.setFixedSize(16, 16)
            lbl_c.setStyleSheet(f"background-color: {kod}; border-radius: 4px;")
            lbl_t = QLabel(ad); lbl_t.setStyleSheet("color: #aaa; font-weight: bold; font-size: 11px;")
            
            h_lay.addWidget(lbl_c); h_lay.addWidget(lbl_t); h_lay.addStretch()
            self.legend_layout.addWidget(container, row, col)
            col += 1
            if col >= max_cols: col = 0; row += 1

    def _renk_bul(self, izin_turu):
        if izin_turu in self.ozel_renkler: return self.ozel_renkler[izin_turu]
        for db_tur, db_renk in self.ozel_renkler.items():
            if db_tur.lower() == izin_turu.lower(): return db_renk
        return "#868e96"

    def _onceki_ay(self):
        self.current_date = (self.current_date.replace(day=1) - timedelta(days=1)).replace(day=1); self.cizelgeyi_ciz()

    def _sonraki_ay(self):
        y, m = self.current_date.year, self.current_date.month
        self.current_date = datetime(y+1, 1, 1).date() if m == 12 else datetime(y, m+1, 1).date()
        self.cizelgeyi_ciz()

    def cizelgeyi_ciz(self):
        yil, ay = self.current_date.year, self.current_date.month
        gun_sayisi = calendar.monthrange(yil, ay)[1]
        aylar_tr = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        self.lbl_tarih.setText(f"{aylar_tr[ay]} {yil}")

        self.table.clear(); self.table.setColumnCount(gun_sayisi)
        self.table.setHorizontalHeaderLabels([str(i) for i in range(1, gun_sayisi + 1)])
        
        ay_basi = datetime(yil, ay, 1).date(); ay_sonu = datetime(yil, ay, gun_sayisi).date()
        
        ilgili_personeller = set(); personel_izinleri = {}
        for izin in self.izin_verileri:
            if izin['bas'] <= ay_sonu and izin['bit'] >= ay_basi:
                ad = izin['ad']; ilgili_personeller.add(ad)
                personel_izinleri.setdefault(ad, []).append(izin)
        
        sorted_personel = sorted(list(ilgili_personeller))
        self.table.setRowCount(len(sorted_personel)); self.table.setVerticalHeaderLabels(sorted_personel)
        
        brush_weekend = QBrush(QColor("#252525"))
        brush_default = QBrush(QColor("#1e1e1e"))
        
        for r in range(self.table.rowCount()):
            for c in range(self.table.columnCount()):
                gun_tarih = datetime(yil, ay, c + 1).date()
                bg = brush_weekend if gun_tarih.weekday() >= 5 else brush_default
                item = QTableWidgetItem(""); item.setBackground(bg)
                self.table.setItem(r, c, item)

        for row_idx, ad in enumerate(sorted_personel):
            izinler = personel_izinleri.get(ad, [])
            for izin in izinler:
                eff_bas = max(izin['bas'], ay_basi); eff_bit = min(izin['bit'], ay_sonu)
                start_day = eff_bas.day; end_day = eff_bit.day
                
                hex_color = self._renk_bul(izin['tur'])
                qcolor = QColor(hex_color)
                
                for d in range(start_day, end_day + 1):
                    col_idx = d - 1
                    item = self.table.item(row_idx, col_idx)
                    
                    if item:
                        item.setText("X")
                        item.setTextAlignment(Qt.AlignCenter)
                        item.setBackground(qcolor)
                        item.setForeground(qcolor) 
                        item.setToolTip(f"{ad}\n{izin['tur']}\n{izin['bas'].strftime('%d.%m.%Y')} - {izin['bit'].strftime('%d.%m.%Y')}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = IzinTakvimPenceresi()
    win.show()
    sys.exit(app.exec())