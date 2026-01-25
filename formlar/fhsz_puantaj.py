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
# Dosyanın 'formlar' klasöründe olduğu varsayılarak proje kök dizini eklenir
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# --- PROJE MODÜLLERİ ---
try:
    from araclar.yetki_yonetimi import YetkiYoneticisi
    from temalar.tema import TemaYonetimi
    
    # Hata sınıfları ve veritabanı fonksiyonu
    from google_baglanti import veritabani_getir, InternetBaglantiHatasi, KimlikDogrulamaHatasi
    # Ortak Araçlar
    from araclar.ortak_araclar import OrtakAraclar, pencereyi_kapat, show_info, show_error
    # Hesaplama Modülü
    from araclar.hesaplamalar import sua_hak_edis_hesapla
except ImportError as e:
    print(f"KRİTİK HATA: Modüller yüklenemedi! {e}")
    sys.exit(1)

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
                self.hata_olustu.emit("'FHSZ_Puantaj' sayfasına ulaşılamadı (Veritabanı Hatası).")
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
        
        # 🟢 YETKİ KONTROLÜ
        YetkiYoneticisi.uygula(self, "fhsz_puantaj")
        
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # --- ÜST PANEL (Filtreler - GroupBox) ---
        grp_filtre = QGroupBox("Rapor Filtreleri")
        # Dikeyde sadece gerektiği kadar yer kaplamasını sağlar
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

        # Rapor Getir Butonu
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
        bottom_layout.setContentsMargins(0, 5, 0, 0)

        # Progress Bar
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setFixedWidth(200)
        bottom_layout.addWidget(self.progress)

        # Kapat Butonu
        btn_kapat = QPushButton(" Çıkış")
        btn_kapat.setFixedSize(100, 45)
        btn_kapat.setObjectName("btn_iptal")
        btn_kapat.clicked.connect(lambda: pencereyi_kapat(self))
        bottom_layout.addWidget(btn_kapat)

        bottom_layout.addStretch()

        # Excel Butonu
        self.btn_excel = OrtakAraclar.create_button(self, " Excel İndir", self.excel_indir)
        self.btn_excel.setObjectName("btn_excel")
        self.btn_excel.setFixedSize(140, 45)
        bottom_layout.addWidget(self.btn_excel)

        # PDF Butonu
        self.btn_pdf = OrtakAraclar.create_button(self, " PDF İndir", self.pdf_indir)
        self.btn_pdf.setObjectName("btn_pdf")
        self.btn_pdf.setFixedSize(140, 45)
        bottom_layout.addWidget(self.btn_pdf)

        main_layout.addLayout(bottom_layout)

    # --- İŞLEMLER ---

    def verileri_baslat(self):
        """Worker'ı başlatır."""
        self.btn_getir.setEnabled(False)
        self.btn_getir.setText("Yükleniyor...")
        self.progress.setVisible(True)
        self.progress.setRange(0, 0) # Sonsuz döngü animasyonu
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
                
                # Veri Görselleştirme (Yeşil/Mavi Yazı)
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

    # 🟢 Çökme Önleyici
    def closeEvent(self, event):
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(500)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Tema uygulaması
    try:
        from temalar.tema import TemaYonetimi
        TemaYonetimi.uygula_fusion_dark(app)
    except: pass
    
    win = PuantajRaporPenceresi()
    win.show()
    sys.exit(app.exec())