# -*- coding: utf-8 -*-
import sys
import os
import pandas as pd
from datetime import datetime

from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                               QTableWidget, QTableWidgetItem, QHeaderView, 
                               QPushButton, QLabel, QComboBox, QFrame, QAbstractItemView)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QTextDocument
from PySide6.QtPrintSupport import QPrinter

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# --- İMPORTLAR ---
try:
    from google_baglanti import veritabani_getir
    from araclar.ortak_araclar import pencereyi_kapat, show_info, show_error
    # YENİ: Hesaplama buradan geliyor
    from araclar.hesaplamalar import sua_hak_edis_hesapla
except ImportError as e:
    print(f"Modül Hatası: {e}")
    # Dummy tanımlar... (önceki gibi)

class PuantajRaporPenceresi(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Puantaj Raporlama ve Şua Takip Sistemi")
        self.resize(1280, 800)
        self.df_puantaj = pd.DataFrame()
        self.filtrelenmis_df = pd.DataFrame()
        self.setup_ui()
        
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # --- ÜST PANEL (Filtreler ve Aksiyon) ---
        filter_frame = QFrame()
        # Card Görünümü için özel stil
        filter_frame.setStyleSheet("""
            QFrame {
                background-color: #2d2d30;
                border-radius: 8px;
                border: 1px solid #3e3e42;
            }
            QLabel {
                border: none;
                background-color: transparent;
            }
        """)
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(20, 20, 20, 20)
        filter_layout.setSpacing(20)

        # Başlık
        lbl_title = QLabel("RAPOR FİLTRELERİ")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #4dabf7;")
        filter_layout.addWidget(lbl_title)

        # Ayırıcı
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("border: none; background-color: #555; max-width: 1px;")
        filter_layout.addWidget(line)

        # Yıl Seçimi
        vbox_yil = QVBoxLayout()
        vbox_yil.setSpacing(5)
        lbl_yil = QLabel("Rapor Yılı")
        lbl_yil.setStyleSheet("color: #aaa; font-size: 12px;")
        
        self.cmb_yil = QComboBox()
        bu_yil = datetime.now().year
        yillar = [str(y) for y in range(bu_yil - 5, bu_yil + 6)]
        self.cmb_yil.addItems(yillar)
        self.cmb_yil.setCurrentText(str(bu_yil)) 
        
        vbox_yil.addWidget(lbl_yil)
        vbox_yil.addWidget(self.cmb_yil)
        filter_layout.addLayout(vbox_yil)

        # Dönem Seçimi
        vbox_donem = QVBoxLayout()
        vbox_donem.setSpacing(5)
        lbl_donem = QLabel("Dönem / Ay")
        lbl_donem.setStyleSheet("color: #aaa; font-size: 12px;")

        self.cmb_donem = QComboBox()
        self.cmb_donem.addItems(["TÜM YIL", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", 
                                 "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"])
        self.cmb_donem.setCurrentIndex(datetime.now().month) 
        
        vbox_donem.addWidget(lbl_donem)
        vbox_donem.addWidget(self.cmb_donem)
        filter_layout.addLayout(vbox_donem)

        filter_layout.addStretch()

        # Rapor Getir Butonu
        self.btn_getir = QPushButton(" Raporu Oluştur")
        self.btn_getir.setCursor(Qt.PointingHandCursor)
        self.btn_getir.setMinimumHeight(40)
        # Özel Buton Stili (Tema dışında özelleştirme)
        self.btn_getir.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                font-weight: bold;
                padding: 0 20px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #106ebe; }
        """)
        self.btn_getir.clicked.connect(self.verileri_getir_ve_filtrele)
        filter_layout.addWidget(self.btn_getir)

        main_layout.addWidget(filter_frame)

        # --- ORTA PANEL (Tablo ve Bilgi) ---
        
        self.lbl_bilgi = QLabel("Veri bekleniyor...")
        self.lbl_bilgi.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_bilgi.setStyleSheet("color: #888; font-style: italic; font-size: 12px;")
        main_layout.addWidget(self.lbl_bilgi)

        # Tablo
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

        # --- ALT PANEL (Export Butonları) ---
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 10, 0, 0)

        # Kapat Butonu (Ortak Araçlardan)
        btn_kapat = QPushButton(" Çıkış")
        btn_kapat.setFixedSize(100, 45)
        btn_kapat.setStyleSheet("background-color: #3e3e42; color: #ccc; border: 1px solid #555; border-radius:6px;")
        btn_kapat.clicked.connect(lambda: pencereyi_kapat(self))
        bottom_layout.addWidget(btn_kapat)

        bottom_layout.addStretch()

        # Excel Butonu
        btn_excel = QPushButton(" Excel İndir")
        btn_excel.setFixedSize(140, 45)
        btn_excel.setStyleSheet("""
            QPushButton {
                background-color: #107c10;
                color: white;
                font-weight: bold;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #0b5a0b; }
        """)
        btn_excel.clicked.connect(self.excel_indir)
        bottom_layout.addWidget(btn_excel)

        # PDF Butonu
        btn_pdf = QPushButton(" PDF İndir")
        btn_pdf.setFixedSize(140, 45)
        btn_pdf.setStyleSheet("""
            QPushButton {
                background-color: #d13438;
                color: white;
                font-weight: bold;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #a4262c; }
        """)
        btn_pdf.clicked.connect(self.pdf_indir)
        bottom_layout.addWidget(btn_pdf)

        main_layout.addLayout(bottom_layout)

    # --- FONKSİYONLAR ---

    def verileri_getir_ve_filtrele(self):
        self.setCursor(Qt.WaitCursor)
        self.btn_getir.setEnabled(False)
        self.btn_getir.setText("Yükleniyor...")
        self.tablo.setRowCount(0)
        QApplication.processEvents()

        try:
            ws = veritabani_getir('personel', 'FHSZ_Puantaj') 
            if not ws:
                raise Exception("'FHSZ_Puantaj' sayfasına ulaşılamadı.")

            data = ws.get_all_records()
            self.df_puantaj = pd.DataFrame(data)
            self.df_puantaj.columns = [c.strip() for c in self.df_puantaj.columns]

            secilen_yil = self.cmb_yil.currentText()
            secilen_donem = self.cmb_donem.currentText()

            # Veritabanı sütun eşleştirmeleri
            col_yil = 'Ait_yil' if 'Ait_yil' in self.df_puantaj.columns else 'Ait_Yil'
            col_donem_db = '1. Dönem' if '1. Dönem' in self.df_puantaj.columns else 'Donem'
            if 'Donem' in self.df_puantaj.columns: col_donem_db = 'Donem'
            col_saat = 'Fiili Çalışma (saat)' if 'Fiili Çalışma (saat)' in self.df_puantaj.columns else 'Fiili_calisma_(saat)'
            col_ad = 'Ad_Soyad' if 'Ad_Soyad' in self.df_puantaj.columns else 'Ad Soyad'
            col_aylik_gun = 'Aylik_Gun' if 'Aylik_Gun' in self.df_puantaj.columns else 'Aylık Gün'
            col_izin = 'Kullanilan_izin' if 'Kullanilan_izin' in self.df_puantaj.columns else 'Kullanılan İzin'

            df_temp = self.df_puantaj[self.df_puantaj[col_yil].astype(str) == secilen_yil].copy()
            
            if df_temp.empty:
                self.filtrelenmis_df = pd.DataFrame()
                self.lbl_bilgi.setText("⚠️ Seçilen yıla ait veri bulunamadı.")
                show_info("Bilgi", "Seçilen yıl için veri bulunamadı.", self)
                return

            # Sayısal Dönüşümler
            df_temp[col_saat] = pd.to_numeric(df_temp[col_saat].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
            if col_aylik_gun in df_temp.columns:
                 df_temp[col_aylik_gun] = pd.to_numeric(df_temp[col_aylik_gun].astype(str), errors='coerce').fillna(0)
            if col_izin in df_temp.columns:
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
                aylar_sirasi = {
                    "Ocak": 1, "Şubat": 2, "Mart": 3, "Nisan": 4, "Mayıs": 5, "Haziran": 6,
                    "Temmuz": 7, "Ağustos": 8, "Eylül": 9, "Ekim": 10, "Kasım": 11, "Aralık": 12
                }
                df_temp['Ay_No'] = df_temp[col_donem_db].astype(str).map(lambda x: aylar_sirasi.get(x.title(), 0))
                df_temp = df_temp.sort_values(by=['personel_id', 'Ay_No'])
                
                df_temp['Kumulatif_Saat'] = df_temp.groupby('personel_id')[col_saat].cumsum()
                df_temp['Toplam_Hak_Edilen_Sua'] = df_temp['Kumulatif_Saat'].apply(sua_hak_edis_hesapla)
                
                mask = (df_temp[col_donem_db].astype(str) == secilen_donem)
                self.filtrelenmis_df = df_temp[mask].copy()
                
                self.lbl_bilgi.setText(f"✓ {secilen_donem} {secilen_yil} Dönemi ({len(self.filtrelenmis_df)} kayıt)")

            self.tabloyu_doldur()

        except Exception as e:
            show_error("Hata", f"Veri işleme hatası:\n{e}", self)
            self.lbl_bilgi.setText("❌ Hata oluştu.")
        finally:
            self.setCursor(Qt.ArrowCursor)
            self.btn_getir.setEnabled(True)
            self.btn_getir.setText(" Raporu Oluştur")

    def tabloyu_doldur(self):
        self.tablo.setRowCount(0)
        
        col_ad = 'Ad_Soyad' if 'Ad_Soyad' in self.filtrelenmis_df.columns else 'Ad Soyad'
        col_donem_db = '1. Dönem' if '1. Dönem' in self.filtrelenmis_df.columns else 'Donem'
        if 'Donem' in self.filtrelenmis_df.columns: col_donem_db = 'Donem'
        col_saat = 'Fiili Çalışma (saat)' if 'Fiili Çalışma (saat)' in self.filtrelenmis_df.columns else 'Fiili_calisma_(saat)'
        col_aylik_gun = 'Aylik_Gun' if 'Aylik_Gun' in self.filtrelenmis_df.columns else 'Aylık Gün'
        col_izin = 'Kullanilan_izin' if 'Kullanilan_izin' in self.filtrelenmis_df.columns else 'Kullanılan İzin'
        
        gosterilecek_sutunlar = [
            'personel_id', col_ad, 'Ait_yil', col_donem_db, 
            col_aylik_gun, col_izin, col_saat, 
            'Kumulatif_Saat', 'Toplam_Hak_Edilen_Sua'
        ]
        
        for _, row in self.filtrelenmis_df.iterrows():
            idx = self.tablo.rowCount()
            self.tablo.insertRow(idx)
            
            for col, db_col in enumerate(gosterilecek_sutunlar):
                val = row.get(db_col, '')
                
                if db_col in [col_saat, 'Kumulatif_Saat']:
                    try:
                        num_val = float(val)
                        val = f"{int(num_val)}" if num_val.is_integer() else f"{num_val:.1f}"
                    except:
                        val = str(val)
                else:
                    val = str(val)
                    if val == "nan": val = ""
                
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter)
                
                if col == 7: # Kümülatif Saat
                    item.setForeground(QColor("#4dabf7")) 
                    item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                elif col == 8: # Hak Edilen Şua
                    item.setForeground(QColor("#57e389")) 
                    item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                
                self.tablo.setItem(idx, col, item)

    def excel_indir(self):
        if self.filtrelenmis_df.empty:
            show_info("Uyarı", "İndirilecek veri yok.", self)
            return

        secilen_yil = self.cmb_yil.currentText()
        dosya_yolu, _ = QFileDialog.getSaveFileName(self, "Excel Kaydet", f"Puantaj_Rapor_{secilen_yil}.xlsx", "Excel (*.xlsx)")
        
        if dosya_yolu:
            try:
                export_df = self.filtrelenmis_df.copy()
                
                col_map = {
                    'personel_id': 'Personel ID',
                    'Ad_Soyad': 'Ad Soyad',
                    'Ait_yil': 'Yıl',
                    'Donem': 'Dönem', 
                    '1. Dönem': 'Dönem',
                    'Fiili_calisma_(saat)': 'Fiili Çalışma Saati',
                    'Fiili Çalışma (saat)': 'Fiili Çalışma Saati',
                    'Kumulatif_Saat': 'Kümülatif/Toplam Saat',
                    'Toplam_Hak_Edilen_Sua': 'Hak Edilen Gün',
                    'Aylik_Gun': 'Toplam Gün',
                    'Kullanilan_izin': 'Toplam İzin'
                }
                
                export_df.rename(columns=col_map, inplace=True)
                cols_to_export = [c for c in col_map.values() if c in export_df.columns]
                export_df = export_df[cols_to_export]

                export_df.to_excel(dosya_yolu, index=False)
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
                headers = []
                for i in range(self.tablo.columnCount()):
                    headers.append(self.tablo.horizontalHeaderItem(i).text())

                html_icerik = f"""
                <html>
                <head>
                    <style>
                        body {{ font-family: 'Segoe UI', Arial, sans-serif; font-size: 10px; }}
                        h2 {{ text-align: center; color: #333; }}
                        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
                        th, td {{ border: 1px solid #ccc; padding: 6px; text-align: center; }}
                        th {{ background-color: #f2f2f2; font-weight: bold; }}
                        tr:nth-child(even) {{ background-color: #f9f9f9; }}
                    </style>
                </head>
                <body>
                    <h2>Puantaj ve Şua Raporu<br><small>{secilen_yil} - {self.cmb_donem.currentText()}</small></h2>
                    <table>
                        <thead>
                            <tr>
                                {''.join(f'<th>{h}</th>' for h in headers)}
                            </tr>
                        </thead>
                        <tbody>
                """
                
                for row in range(self.tablo.rowCount()):
                    html_icerik += "<tr>"
                    for col in range(self.tablo.columnCount()):
                        item = self.tablo.item(row, col)
                        val = item.text() if item else ""
                        html_icerik += f"<td>{val}</td>"
                    html_icerik += "</tr>"
                
                html_icerik += """
                        </tbody>
                    </table>
                </body>
                </html>
                """

                document = QTextDocument()
                document.setHtml(html_icerik)
                
                printer = QPrinter(QPrinter.HighResolution)
                printer.setOutputFormat(QPrinter.PdfFormat)
                printer.setOutputFileName(dosya_yolu)
                printer.setPageSize(QPageSize(QPageSize.A4))
                
                document.print_(printer)
                show_info("Başarılı", "PDF dosyası başarıyla oluşturuldu.", self)
            
            except Exception as e:
                show_error("Hata", f"PDF hatası:\n{e}", self)

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    # TemaYonetimi entegrasyonu (Test için)
    # Gerçek uygulamada main.py üzerinden çağrılır.
    try:
        from temalar.tema import TemaYonetimi
    except:
        pass
        
    app = QApplication(sys.argv)
    # Eğer test ediyorsanız aşağıdaki satırı açabilirsiniz:
    # if 'TemaYonetimi' in locals(): TemaYonetimi.uygula_fusion_dark(app)
    
    window = PuantajRaporPenceresi()
    window.show()
    sys.exit(app.exec())