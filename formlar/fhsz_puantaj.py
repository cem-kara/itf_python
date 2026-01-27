# -*- coding: utf-8 -*-
import sys
import os
import pandas as pd
from datetime import datetime

# PySide6 Kütüphaneleri
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
    QTableWidget, QTableWidgetItem, QHeaderView, 
    QPushButton, QLabel, QComboBox, QFrame, QAbstractItemView,
    QFileDialog, QProgressBar, QGroupBox, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor, QTextDocument, QPageSize
from PySide6.QtPrintSupport import QPrinter

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# --- PROJE MODÜLLERİ ---
try:
    from araclar.yetki_yonetimi import YetkiYoneticisi
    from temalar.tema import TemaYonetimi
    from google_baglanti import veritabani_getir, InternetBaglantiHatasi, KimlikDogrulamaHatasi
    from araclar.ortak_araclar import OrtakAraclar, pencereyi_kapat, show_info, show_error
    from araclar.hesaplamalar import sua_hak_edis_hesapla
except ImportError as e:
    print(f"KRİTİK HATA: Modüller yüklenemedi! {e}")
    sys.exit(1)

# =============================================================================
# WORKER: SADECE VERİ OKUMA
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
            if not data:
                self.hata_olustu.emit("Veritabanı boş veya veri çekilemedi.")
                return

            df = pd.DataFrame(data)
            # Sütun isimlerindeki boşlukları temizle
            df.columns = [c.strip() for c in df.columns]
            self.veri_hazir.emit(df)
            
        except InternetBaglantiHatasi:
            self.hata_olustu.emit("İnternet bağlantısı yok.")
        except KimlikDogrulamaHatasi:
            self.hata_olustu.emit("Google oturum süresi doldu.")
        except Exception as e:
            self.hata_olustu.emit(f"Veri çekme hatası: {str(e)}")

# =============================================================================
# ANA FORM: PUANTAJ RAPOR
# =============================================================================
class PuantajRaporPenceresi(QWidget):
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.setWindowTitle("Puantaj Raporlama ve Şua Takip Sistemi")
        self.resize(1280, 800)
        
        self.df_puantaj = pd.DataFrame()
        self.filtrelenmis_df = pd.DataFrame()
        
        self.setup_ui()
        YetkiYoneticisi.uygula(self, "fhsz_puantaj")
        
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # --- ÜST PANEL (Filtreler) ---
        grp_filtre = QGroupBox("Rapor Filtreleri")
        grp_filtre.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        filter_layout = QHBoxLayout(grp_filtre)
        filter_layout.setContentsMargins(10, 15, 10, 10) 
        filter_layout.setSpacing(20)

        # Yıl Seçimi
        vbox_yil = QVBoxLayout(); vbox_yil.setSpacing(5)
        vbox_yil.addWidget(QLabel("Rapor Yılı"))
        bu_yil = datetime.now().year
        yillar = [str(y) for y in range(bu_yil - 5, bu_yil + 6)]
        self.cmb_yil = OrtakAraclar.create_combo_box(grp_filtre, yillar)
        self.cmb_yil.setCurrentText(str(bu_yil)) 
        vbox_yil.addWidget(self.cmb_yil)
        filter_layout.addLayout(vbox_yil)

        # Dönem Seçimi
        vbox_donem = QVBoxLayout(); vbox_donem.setSpacing(5)
        vbox_donem.addWidget(QLabel("Dönem / Ay"))
        donemler = ["TÜM YIL", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", 
                    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        self.cmb_donem = OrtakAraclar.create_combo_box(grp_filtre, donemler)
        self.cmb_donem.setCurrentIndex(datetime.now().month) 
        vbox_donem.addWidget(self.cmb_donem)
        filter_layout.addLayout(vbox_donem)

        filter_layout.addStretch()

        # Buton
        self.btn_getir = OrtakAraclar.create_button(grp_filtre, " Raporu Oluştur", self.verileri_baslat)
        self.btn_getir.setObjectName("btn_getir") 
        self.btn_getir.setMinimumHeight(40)
        filter_layout.addWidget(self.btn_getir)

        main_layout.addWidget(grp_filtre)

        # --- ORTA PANEL (Tablo) ---
        self.lbl_bilgi = QLabel("Veri bekleniyor...")
        self.lbl_bilgi.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_bilgi.setStyleSheet("color: #888; font-style: italic; font-size: 12px;")
        main_layout.addWidget(self.lbl_bilgi)

        self.sutunlar = ["ID", "Ad Soyad", "Yıl", "Dönem", "Top. Gün", "Top. İzin", "Yıllık Fiili Saat", "Kümülatif Saat", "Hak Edilen Şua"]
        self.tablo = OrtakAraclar.create_table(self, self.sutunlar)
        self.tablo.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tablo.verticalHeader().setVisible(False)
        self.tablo.verticalHeader().setDefaultSectionSize(35)
        main_layout.addWidget(self.tablo)

        # --- ALT PANEL (Butonlar) ---
        bottom_layout = QHBoxLayout()
        self.progress = QProgressBar(); self.progress.setVisible(False); self.progress.setFixedWidth(200)
        bottom_layout.addWidget(self.progress)

        btn_kapat = QPushButton(" Çıkış"); btn_kapat.setFixedSize(100, 45)
        btn_kapat.setObjectName("btn_iptal")
        btn_kapat.clicked.connect(lambda: pencereyi_kapat(self))
        bottom_layout.addWidget(btn_kapat)
        bottom_layout.addStretch()

        self.btn_excel = OrtakAraclar.create_button(self, " Excel İndir", self.excel_indir)
        self.btn_excel.setFixedSize(140, 45)
        bottom_layout.addWidget(self.btn_excel)

        self.btn_pdf = OrtakAraclar.create_button(self, " PDF İndir", self.pdf_indir)
        self.btn_pdf.setFixedSize(140, 45)
        bottom_layout.addWidget(self.btn_pdf)

        main_layout.addLayout(bottom_layout)

    # --- İŞLEMLER ---
    def verileri_baslat(self):
        self.btn_getir.setEnabled(False)
        self.btn_getir.setText("Yükleniyor...")
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.tablo.setRowCount(0)
        
        self.worker = VeriGetirWorker()
        self.worker.veri_hazir.connect(self._veri_isleme)
        self.worker.hata_olustu.connect(self._hata_yakala)
        self.worker.start()

    def _veri_isleme(self, df):
        self.progress.setVisible(False)
        self.btn_getir.setEnabled(True)
        self.btn_getir.setText(" Raporu Oluştur")
        
        self.df_puantaj = df
        
        try:
            secilen_yil = self.cmb_yil.currentText()
            secilen_donem = self.cmb_donem.currentText()

            # --- SÜTUN EŞLEŞTİRME ---
            def find_col(keywords):
                for col in df.columns:
                    for k in keywords:
                        if k.lower() in col.lower(): return col
                return None

            col_yil = find_col(['ait_yil', 'yil'])
            col_donem_db = find_col(['donem', 'ay'])
            col_saat = find_col(['fiili', 'saat'])
            col_ad = find_col(['ad_soyad', 'ad'])
            col_id = find_col(['personel_id', 'kimlik', 'tc'])
            col_gun = find_col(['aylik_gun', 'gun'])
            col_izin = find_col(['kullanilan_izin', 'izin'])

            if not col_yil:
                show_error("Hata", "Veritabanında 'Yıl' sütunu bulunamadı.", self); return

            # Yıl Filtresi
            df_temp = df[df[col_yil].astype(str) == secilen_yil].copy()
            if df_temp.empty:
                self.filtrelenmis_df = pd.DataFrame()
                self.lbl_bilgi.setText("⚠️ Veri yok.")
                return

            # Sayısal Dönüşüm
            df_temp[col_saat] = pd.to_numeric(df_temp[col_saat].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
            df_temp[col_gun] = pd.to_numeric(df_temp[col_gun].astype(str), errors='coerce').fillna(0)
            df_temp[col_izin] = pd.to_numeric(df_temp[col_izin].astype(str), errors='coerce').fillna(0)

            # --- RAPORLAMA MANTIĞI ---
            if secilen_donem == "TÜM YIL":
                grouped_df = df_temp.groupby([col_id, col_ad], as_index=False).agg({
                    col_saat: 'sum', col_gun: 'sum', col_izin: 'sum'
                })
                grouped_df[col_yil] = secilen_yil
                grouped_df[col_donem_db] = "YILLIK TOPLAM"
                grouped_df['Kumulatif_Saat'] = grouped_df[col_saat]
                
                self.filtrelenmis_df = grouped_df
                self.lbl_bilgi.setText(f"✓ {secilen_yil} Yılı Özeti")

            else:
                aylar = {"Ocak":1, "Şubat":2, "Mart":3, "Nisan":4, "Mayıs":5, "Haziran":6,
                         "Temmuz":7, "Ağustos":8, "Eylül":9, "Ekim":10, "Kasım":11, "Aralık":12}
                
                df_temp['Ay_No'] = df_temp[col_donem_db].apply(lambda x: aylar.get(str(x).strip().title(), 0))
                df_temp = df_temp.sort_values(by=[col_ad, 'Ay_No'])
                
                df_temp['Kumulatif_Saat'] = df_temp.groupby(col_id)[col_saat].cumsum()
                
                mask = df_temp[col_donem_db].astype(str).str.contains(secilen_donem, case=False, na=False)
                self.filtrelenmis_df = df_temp[mask].copy()
                self.lbl_bilgi.setText(f"✓ {secilen_donem} {secilen_yil} Detayı")

            self.filtrelenmis_df['Hak_Edilen_Sua'] = self.filtrelenmis_df['Kumulatif_Saat'].apply(sua_hak_edis_hesapla)

            self.tabloyu_doldur(col_id, col_ad, col_donem_db, col_gun, col_izin, col_saat)

        except Exception as e:
            self._hata_yakala(f"İşleme hatası: {e}")

    def _hata_yakala(self, mesaj):
        self.progress.setVisible(False)
        self.btn_getir.setEnabled(True)
        self.btn_getir.setText(" Raporu Oluştur")
        show_error("Hata", mesaj, self)

    def tabloyu_doldur(self, c_id, c_ad, c_donem, c_gun, c_izin, c_saat):
        self.tablo.setRowCount(0)
        cols = [c_id, c_ad, 'Ait_yil', c_donem, c_gun, c_izin, c_saat, 'Kumulatif_Saat', 'Hak_Edilen_Sua']
        if 'Ait_yil' not in self.filtrelenmis_df.columns:
             for c in self.filtrelenmis_df.columns:
                 if 'yil' in c.lower(): cols[2] = c; break

        for _, row in self.filtrelenmis_df.iterrows():
            idx = self.tablo.rowCount(); self.tablo.insertRow(idx)
            for i, col_name in enumerate(cols):
                val = row.get(col_name, '')
                if isinstance(val, (int, float)):
                    val = f"{val:.1f}" if i in [6, 7] else f"{int(val)}"
                
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignCenter)
                
                if i == 7: item.setForeground(QColor("#4dabf7")); item.setFont(QFont("Segoe UI", 9, QFont.Bold))
                elif i == 8: item.setForeground(QColor("#57e389")); item.setFont(QFont("Segoe UI", 9, QFont.Bold))
                
                self.tablo.setItem(idx, i, item)

    def excel_indir(self):
        if self.filtrelenmis_df.empty: return
        path, _ = QFileDialog.getSaveFileName(self, "Kaydet", f"Rapor_{self.cmb_yil.currentText()}.xlsx", "Excel (*.xlsx)")
        if path:
            try:
                self.filtrelenmis_df.to_excel(path, index=False)
                show_info("Tamam", "Excel kaydedildi.", self)
            except Exception as e: show_error("Hata", str(e), self)

    def pdf_indir(self):
        if self.filtrelenmis_df.empty: return
        path, _ = QFileDialog.getSaveFileName(self, "Kaydet", "Rapor.pdf", "PDF (*.pdf)")
        if path:
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat); printer.setOutputFileName(path)
            printer.setPageSize(QPageSize(QPageSize.A4))
            
            doc = QTextDocument()
            html = "<html><head><style>table{width:100%;border-collapse:collapse;} td,th{border:1px solid #ddd;padding:4px;text-align:center;}</style></head><body>"
            html += f"<h2 style='text-align:center'>Puantaj Raporu - {self.cmb_yil.currentText()}</h2><table><thead><tr>"
            for i in range(self.tablo.columnCount()): html += f"<th>{self.tablo.horizontalHeaderItem(i).text()}</th>"
            html += "</tr></thead><tbody>"
            for r in range(self.tablo.rowCount()):
                html += "<tr>"
                for c in range(self.tablo.columnCount()): html += f"<td>{self.tablo.item(r,c).text()}</td>"
                html += "</tr>"
            html += "</tbody></table></body></html>"
            doc.setHtml(html); doc.print_(printer)
            show_info("Tamam", "PDF kaydedildi.", self)

    def closeEvent(self, event):
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.quit(); self.worker.wait(500)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    try: TemaYonetimi.uygula_fusion_dark(app)
    except: pass
    win = PuantajRaporPenceresi()
    win.show()
    sys.exit(app.exec())