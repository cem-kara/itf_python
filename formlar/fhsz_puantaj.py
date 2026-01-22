# -*- coding: utf-8 -*-
import sys
import os
import pandas as pd
from datetime import datetime

from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                               QTableWidget, QTableWidgetItem, QHeaderView, 
                               QPushButton, QLabel, QComboBox, QFrame, QAbstractItemView,
                               QFileDialog, QProgressBar) # QProgressBar eklendi
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor, QTextDocument, QPageSize
from PySide6.QtPrintSupport import QPrinter

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from araclar.yetki_yonetimi import YetkiYoneticisi

# --- İMPORTLAR ---
try:
    from google_baglanti import veritabani_getir
    from araclar.ortak_araclar import pencereyi_kapat, show_info, show_error
    from araclar.hesaplamalar import sua_hak_edis_hesapla
except ImportError as e:
    print(f"Modül Hatası: {e}")
    def veritabani_getir(t, s): return None
    def show_info(t, m, p): print(m)
    def show_error(t, m, p): print(m)
    def sua_hak_edis_hesapla(v): return 0

# =============================================================================
# WORKER: VERİ GETİR (ARAYÜZ DONMASINI ENGELLER)
# =============================================================================
class VeriGetirWorker(QThread):
    veri_hazir = Signal(pd.DataFrame)
    hata_olustu = Signal(str)

    def run(self):
        try:
            ws = veritabani_getir('personel', 'FHSZ_Puantaj') 
            if not ws:
                self.hata_olustu.emit("'FHSZ_Puantaj' sayfasına ulaşılamadı.")
                return

            data = ws.get_all_records()
            df = pd.DataFrame(data)
            # Sütun isimlerindeki boşlukları temizle
            df.columns = [c.strip() for c in df.columns]
            self.veri_hazir.emit(df)
            
        except Exception as e:
            self.hata_olustu.emit(str(e))

# =============================================================================
# ANA FORM: PUANTAJ RAPOR
# =============================================================================
class PuantajRaporPenceresi(QWidget):
    # DÜZELTME 1: Main.py uyumu için 'kullanici_adi' eklendi
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.setWindowTitle("Puantaj Raporlama ve Şua Takip Sistemi")
        self.resize(1280, 800)
        
        self.df_puantaj = pd.DataFrame()
        self.filtrelenmis_df = pd.DataFrame()
        
        self.setup_ui()
        
        # 🟢 YETKİ KONTROLÜ
        YetkiYoneticisi.uygula(self, "fhsz_puantaj")
        
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # --- ÜST PANEL (Filtreler ve Aksiyon) ---
        filter_frame = QFrame()
        filter_frame.setStyleSheet("""
            QFrame { background-color: #2d2d30; border-radius: 8px; border: 1px solid #3e3e42; }
            QLabel { border: none; background-color: transparent; }
        """)
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(20, 20, 20, 20)
        filter_layout.setSpacing(20)

        # Başlık
        lbl_title = QLabel("RAPOR FİLTRELERİ")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #4dabf7;")
        filter_layout.addWidget(lbl_title)

        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("border: none; background-color: #555; max-width: 1px;")
        filter_layout.addWidget(line)

        # Yıl Seçimi
        vbox_yil = QVBoxLayout(); vbox_yil.setSpacing(5)
        lbl_yil = QLabel("Rapor Yılı")
        lbl_yil.setStyleSheet("color: #aaa; font-size: 12px;")
        
        self.cmb_yil = QComboBox()
        bu_yil = datetime.now().year
        yillar = [str(y) for y in range(bu_yil - 5, bu_yil + 6)]
        self.cmb_yil.addItems(yillar)
        self.cmb_yil.setCurrentText(str(bu_yil)) 
        vbox_yil.addWidget(lbl_yil); vbox_yil.addWidget(self.cmb_yil)
        filter_layout.addLayout(vbox_yil)

        # Dönem Seçimi
        vbox_donem = QVBoxLayout(); vbox_donem.setSpacing(5)
        lbl_donem = QLabel("Dönem / Ay")
        lbl_donem.setStyleSheet("color: #aaa; font-size: 12px;")

        self.cmb_donem = QComboBox()
        self.cmb_donem.addItems(["TÜM YIL", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", 
                                 "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"])
        self.cmb_donem.setCurrentIndex(datetime.now().month) 
        vbox_donem.addWidget(lbl_donem); vbox_donem.addWidget(self.cmb_donem)
        filter_layout.addLayout(vbox_donem)

        filter_layout.addStretch()

        # Rapor Getir Butonu
        self.btn_getir = QPushButton(" Raporu Oluştur")
        self.btn_getir.setObjectName("btn_getir") # 🟢 Yetki için isim
        self.btn_getir.setCursor(Qt.PointingHandCursor)
        self.btn_getir.setMinimumHeight(40)
        self.btn_getir.setStyleSheet("""
            QPushButton { background-color: #0078d4; color: white; font-weight: bold; padding: 0 20px; border-radius: 6px; }
            QPushButton:hover { background-color: #106ebe; }
        """)
        self.btn_getir.clicked.connect(self.verileri_baslat)
        filter_layout.addWidget(self.btn_getir)

        main_layout.addWidget(filter_frame)

        # --- ORTA PANEL ---
        self.lbl_bilgi = QLabel("Veri bekleniyor...")
        self.lbl_bilgi.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_bilgi.setStyleSheet("color: #888; font-style: italic; font-size: 12px;")
        main_layout.addWidget(self.lbl_bilgi)

        self.tablo = QTableWidget()
        self.sutunlar = ["ID", "Ad Soyad", "Yıl", "Dönem", "Top. Gün", "Top. İzin", "Yıllık Fiili Saat", "Kümülatif Saat", "Hak Edilen Şua"]
        self.tablo.setColumnCount(len(self.sutunlar))
        self.tablo.setHorizontalHeaderLabels(self.sutunlar)
        self.tablo.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tablo.verticalHeader().setVisible(False)
        self.tablo.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tablo.setAlternatingRowColors(True)
        self.tablo.verticalHeader().setDefaultSectionSize(35)
        main_layout.addWidget(self.tablo)

        # --- ALT PANEL ---
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 10, 0, 0)

        # Progress Bar (Gizli)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 0) # Sonsuz döngü
        bottom_layout.addWidget(self.progress)

        btn_kapat = QPushButton(" Çıkış")
        btn_kapat.setFixedSize(100, 45)
        btn_kapat.setStyleSheet("background-color: #3e3e42; color: #ccc; border: 1px solid #555; border-radius:6px;")
        btn_kapat.clicked.connect(lambda: pencereyi_kapat(self))
        bottom_layout.addWidget(btn_kapat)

        bottom_layout.addStretch()

        # Excel Butonu
        self.btn_excel = QPushButton(" Excel İndir")
        self.btn_excel.setObjectName("btn_excel") # 🟢 Yetki için isim
        self.btn_excel.setFixedSize(140, 45)
        self.btn_excel.setStyleSheet("QPushButton { background-color: #107c10; color: white; font-weight: bold; border-radius: 6px; } QPushButton:hover { background-color: #0b5a0b; }")
        self.btn_excel.clicked.connect(self.excel_indir)
        bottom_layout.addWidget(self.btn_excel)

        # PDF Butonu
        self.btn_pdf = QPushButton(" PDF İndir")
        self.btn_pdf.setObjectName("btn_pdf") # 🟢 Yetki için isim
        self.btn_pdf.setFixedSize(140, 45)
        self.btn_pdf.setStyleSheet("QPushButton { background-color: #d13438; color: white; font-weight: bold; border-radius: 6px; } QPushButton:hover { background-color: #a4262c; }")
        self.btn_pdf.clicked.connect(self.pdf_indir)
        bottom_layout.addWidget(self.btn_pdf)

        main_layout.addLayout(bottom_layout)

    # --- İŞLEMLER ---

    def verileri_baslat(self):
        """Worker'ı başlatır."""
        self.btn_getir.setEnabled(False)
        self.btn_getir.setText("Yükleniyor...")
        self.progress.setVisible(True)
        self.tablo.setRowCount(0)
        
        self.worker = VeriGetirWorker()
        self.worker.veri_hazir.connect(self._veri_isleme)
        self.worker.hata_olustu.connect(self._hata_yakala)
        self.worker.start()

    def _veri_isleme(self, df):
        """Gelen veriyi filtreler ve tabloya basar."""
        self.progress.setVisible(False)
        self.btn_getir.setEnabled(True)
        self.btn_getir.setText(" Raporu Oluştur")
        
        self.df_puantaj = df
        
        try:
            secilen_yil = self.cmb_yil.currentText()
            secilen_donem = self.cmb_donem.currentText()

            # Sütun İsimleri (Google Sheets'teki olası varyasyonlar)
            col_yil = next((c for c in df.columns if c.lower() == 'ait_yil'), 'Ait_yil')
            col_donem_db = next((c for c in df.columns if 'donem' in c.lower() or '1. dönem' in c.lower()), '1. Dönem')
            col_saat = next((c for c in df.columns if 'fiili' in c.lower() and 'saat' in c.lower()), 'Fiili Çalışma (saat)')
            col_ad = next((c for c in df.columns if 'ad' in c.lower() and 'soyad' in c.lower()), 'Ad Soyad')
            col_aylik_gun = next((c for c in df.columns if 'aylik' in c.lower() and 'gun' in c.lower()), 'Aylık Gün')
            col_izin = next((c for c in df.columns if 'kullanilan' in c.lower() and 'izin' in c.lower()), 'Kullanılan İzin')

            # Yıl Filtresi
            df_temp = df[df[col_yil].astype(str) == secilen_yil].copy()
            
            if df_temp.empty:
                self.filtrelenmis_df = pd.DataFrame()
                self.lbl_bilgi.setText("⚠️ Seçilen yıla ait veri bulunamadı.")
                show_info("Bilgi", "Seçilen yıl için veri bulunamadı.", self)
                return

            # Sayısal Dönüşümler
            df_temp[col_saat] = pd.to_numeric(df_temp[col_saat].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
            df_temp[col_aylik_gun] = pd.to_numeric(df_temp[col_aylik_gun].astype(str), errors='coerce').fillna(0)
            df_temp[col_izin] = pd.to_numeric(df_temp[col_izin].astype(str), errors='coerce').fillna(0)

            # --- SENARYO 1: TÜM YIL ---
            if secilen_donem == "TÜM YIL":
                grouped_df = df_temp.groupby(['personel_id', col_ad], as_index=False).agg({
                    col_saat: 'sum',      
                    col_aylik_gun: 'sum', 
                    col_izin: 'sum'       
                })
                
                grouped_df[col_yil] = secilen_yil
                grouped_df[col_donem_db] = "YILLIK TOPLAM"
                grouped_df['Kumulatif_Saat'] = grouped_df[col_saat] 
                grouped_df['Toplam_Hak_Edilen_Sua'] = grouped_df['Kumulatif_Saat'].apply(sua_hak_edis_hesapla)
                
                self.filtrelenmis_df = grouped_df
                self.lbl_bilgi.setText(f"✓ {secilen_yil} Yılı Toplamları ({len(self.filtrelenmis_df)} personel)")

            # --- SENARYO 2: BELİRLİ AY ---
            else:
                # Kümülatif hesaplamak için önce sırala
                aylar_sirasi = {
                    "Ocak": 1, "Şubat": 2, "Mart": 3, "Nisan": 4, "Mayıs": 5, "Haziran": 6,
                    "Temmuz": 7, "Ağustos": 8, "Eylül": 9, "Ekim": 10, "Kasım": 11, "Aralık": 12
                }
                # Ay ismini bulmaya çalış
                df_temp['Ay_No'] = df_temp[col_donem_db].astype(str).apply(
                    lambda x: aylar_sirasi.get(x.strip().split('.')[0].title(), 0) if isinstance(x, str) else 0
                )
                
                df_temp = df_temp.sort_values(by=['personel_id', 'Ay_No'])
                df_temp['Kumulatif_Saat'] = df_temp.groupby('personel_id')[col_saat].cumsum()
                df_temp['Toplam_Hak_Edilen_Sua'] = df_temp['Kumulatif_Saat'].apply(sua_hak_edis_hesapla)
                
                # Sadece seçilen dönemi filtrele
                mask = df_temp[col_donem_db].astype(str).str.contains(secilen_donem, case=False, na=False)
                self.filtrelenmis_df = df_temp[mask].copy()
                
                self.lbl_bilgi.setText(f"✓ {secilen_donem} {secilen_yil} Dönemi ({len(self.filtrelenmis_df)} kayıt)")

            self.tabloyu_doldur(col_ad, col_donem_db, col_aylik_gun, col_izin, col_saat)

        except Exception as e:
            self._hata_yakala(f"Veri işleme hatası: {e}")

    def _hata_yakala(self, mesaj):
        self.progress.setVisible(False)
        self.btn_getir.setEnabled(True)
        self.btn_getir.setText(" Raporu Oluştur")
        self.lbl_bilgi.setText("❌ Hata oluştu.")
        show_error("Hata", mesaj, self)

    def tabloyu_doldur(self, col_ad, col_donem, col_gun, col_izin, col_saat):
        self.tablo.setRowCount(0)
        
        cols = ['personel_id', col_ad, 'Ait_yil', col_donem, col_gun, col_izin, col_saat, 'Kumulatif_Saat', 'Toplam_Hak_Edilen_Sua']
        
        for _, row in self.filtrelenmis_df.iterrows():
            idx = self.tablo.rowCount()
            self.tablo.insertRow(idx)
            
            for col_idx, db_col in enumerate(cols):
                # Sütun veri çerçevesinde yoksa boş geç
                val = row.get(db_col, '')
                
                # Sayısal formatlama
                if db_col in [col_saat, 'Kumulatif_Saat']:
                    try:
                        num_val = float(val)
                        val = f"{int(num_val)}" if num_val.is_integer() else f"{num_val:.1f}"
                    except: val = str(val)
                else:
                    val = str(val)
                    if val == "nan": val = ""
                
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter)
                
                if col_idx == 7: # Kümülatif
                    item.setForeground(QColor("#4dabf7")); item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                elif col_idx == 8: # Şua
                    item.setForeground(QColor("#57e389")); item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                
                self.tablo.setItem(idx, col_idx, item)

    def excel_indir(self):
        if self.filtrelenmis_df.empty:
            show_info("Uyarı", "İndirilecek veri yok.", self)
            return

        secilen_yil = self.cmb_yil.currentText()
        dosya_yolu, _ = QFileDialog.getSaveFileName(self, "Excel Kaydet", f"Puantaj_Rapor_{secilen_yil}.xlsx", "Excel (*.xlsx)")
        
        if dosya_yolu:
            try:
                self.filtrelenmis_df.to_excel(dosya_yolu, index=False)
                show_info("Başarılı", "Excel dosyası başarıyla oluşturuldu.", self)
            except Exception as e:
                show_error("Hata", f"Dosya kaydedilemedi:\n{e}", self)

    def pdf_indir(self):
        if self.filtrelenmis_df.empty:
            show_info("Uyarı", "İndirilecek veri yok.", self)
            return

        secilen_yil = self.cmb_yil.currentText()
        dosya_yolu, _ = QFileDialog.getSaveFileName(self, "PDF Kaydet", f"Puantaj_Rapor_{secilen_yil}.pdf", "PDF (*.pdf)")
        
        if dosya_yolu:
            try:
                headers = [self.tablo.horizontalHeaderItem(i).text() for i in range(self.tablo.columnCount())]
                
                html = f"""
                <html><head><style>
                    body {{ font-family: Arial; font-size: 10px; }}
                    h2 {{ text-align: center; }}
                    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
                    th, td {{ border: 1px solid #ccc; padding: 5px; text-align: center; }}
                    th {{ background-color: #f0f0f0; }}
                </style></head><body>
                    <h2>Puantaj Raporu ({secilen_yil} - {self.cmb_donem.currentText()})</h2>
                    <table><thead><tr>{''.join(f'<th>{h}</th>' for h in headers)}</tr></thead><tbody>
                """
                
                for row in range(self.tablo.rowCount()):
                    html += "<tr>"
                    for col in range(self.tablo.columnCount()):
                        item = self.tablo.item(row, col)
                        html += f"<td>{item.text() if item else ''}</td>"
                    html += "</tr>"
                html += "</tbody></table></body></html>"

                doc = QTextDocument()
                doc.setHtml(html)
                printer = QPrinter(QPrinter.HighResolution)
                printer.setOutputFormat(QPrinter.PdfFormat)
                printer.setOutputFileName(dosya_yolu)
                printer.setPageSize(QPageSize(QPageSize.A4))
                doc.print_(printer)
                
                show_info("Başarılı", "PDF dosyası oluşturuldu.", self)
            except Exception as e:
                show_error("Hata", f"PDF hatası:\n{e}", self)

    # 🟢 DÜZELTME 3: Çökme Önleyici
    def closeEvent(self, event):
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(500)
        event.accept()

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    # TemaYonetimi.uygula_fusion_dark(app)
    win = PuantajRaporPenceresi()
    win.show()
    sys.exit(app.exec())