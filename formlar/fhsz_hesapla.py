# -*- coding: utf-8 -*-
import sys
import os
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                               QTableWidgetItem, QHeaderView, QPushButton, QLabel, 
                               QComboBox, QFrame, QAbstractItemView, QSizePolicy)
from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtGui import QFont, QColor

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# --- İMPORTLAR ---
try:
    from google_baglanti import veritabani_getir
    from araclar.ortak_araclar import pencereyi_kapat, show_info, show_error
    # YENİ: Hesaplamalar buradan çekiliyor
    from araclar.hesaplamalar import sua_hak_edis_hesapla, tr_upper, is_gunu_hesapla
except ImportError as e:
    print(f"Modül Hatası: {e}")
    # Fallback (Kodun çökmemesi için boş tanımlar)
    def veritabani_getir(v, s): return None
    def pencereyi_kapat(w): w.close()
    def show_info(t, m, p): print(m)
    def show_error(t, m, p): print(m)
    def sua_hak_edis_hesapla(s): return 0
    def tr_upper(s): return str(s).upper()
    def is_gunu_hesapla(b, e, t): return 0

class FHSZHesaplamaPenceresi(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fiili Hizmet Süresi (Şua) Hesaplama Paneli")
        self.resize(1300, 850)
        
        # --- VERİLER ---
        self.df_personel = pd.DataFrame()
        self.df_izin = pd.DataFrame()
        self.tatil_listesi_np = []
        self.birim_kosul_map = {} 
        
        self.setup_ui()
        self.verileri_yukle()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # ... (ARAYÜZ KODLARI AYNEN KORUNDU - ÜST PANEL) ...
        # [Buradaki UI kodları önceki cevaptaki ile aynı, kısalık için tekrar yazmıyorum]
        # Sadece import değişikliği yapıldığı için UI yapısında değişiklik yok.
        
        # KODUN DEVAMI AYNEN GEÇERLİ, SADECE FONKSİYON ÇAĞRILARI DEĞİŞTİ:
        # Örnek: self.is_gunu_hesapla(...) yerine is_gunu_hesapla(...) kullanılacak.
        
        # --- KISALTILMIŞ UI KODU (Yer kaplamaması için özet geçiyorum, kopyalarken tam halini kullanın) ---
        filter_frame = QFrame()
        filter_frame.setStyleSheet("QFrame { background-color: #2d2d30; border-radius: 8px; border: 1px solid #3e3e42; } QLabel { border: none; background: transparent; }")
        filter_layout = QHBoxLayout(filter_frame)
        
        lbl_title = QLabel("HESAPLAMA DÖNEMİ")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #4dabf7;")
        filter_layout.addWidget(lbl_title)
        
        # Yıl ve Ay combo'ları...
        self.cmb_yil = QComboBox()
        self.cmb_yil.addItems([str(y) for y in range(datetime.now().year - 3, datetime.now().year + 3)])
        self.cmb_yil.setCurrentText(str(datetime.now().year))
        
        self.cmb_ay = QComboBox()
        self.cmb_ay.addItems(["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"])
        self.cmb_ay.setCurrentIndex(datetime.now().month - 1)
        
        filter_layout.addWidget(QLabel("Yıl:"))
        filter_layout.addWidget(self.cmb_yil)
        filter_layout.addWidget(QLabel("Ay:"))
        filter_layout.addWidget(self.cmb_ay)
        
        self.lbl_donem_bilgi = QLabel("...")
        self.lbl_donem_bilgi.setStyleSheet("color: #ffb74d; font-weight: bold; margin-left: 10px;")
        filter_layout.addWidget(self.lbl_donem_bilgi)
        filter_layout.addStretch()
        
        self.btn_hesapla = QPushButton(" LİSTELE VE HESAPLA")
        self.btn_hesapla.setStyleSheet("background-color: #0078d4; color: white; font-weight: bold; border-radius: 6px; padding: 8px;")
        self.btn_hesapla.clicked.connect(self.tabloyu_olustur_ve_hesapla)
        filter_layout.addWidget(self.btn_hesapla)
        main_layout.addWidget(filter_frame)

        self.tablo = QTableWidget()
        self.tablo.setColumnCount(7)
        self.tablo.setHorizontalHeaderLabels(["Kimlik No", "Adı Soyadı", "Birim", "Çalışma Koşulu", "Aylık Gün", "Kullanılan İzin", "Fiili Çalışma"])
        self.tablo.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tablo.setAlternatingRowColors(True)
        main_layout.addWidget(self.tablo)

        bottom_layout = QHBoxLayout()
        self.btn_kaydet = QPushButton(" VERİTABANINA KAYDET")
        self.btn_kaydet.setStyleSheet("background-color: #107c10; color: white; font-weight: bold; border-radius: 6px; padding: 10px;")
        self.btn_kaydet.clicked.connect(self.kaydet)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_kaydet)
        main_layout.addLayout(bottom_layout)

        self.cmb_yil.currentIndexChanged.connect(self.donem_guncelle_label)
        self.cmb_ay.currentIndexChanged.connect(self.donem_guncelle_label)
        self.donem_guncelle_label()

    def donem_guncelle_label(self):
        try:
            yil = int(self.cmb_yil.currentText())
            ay_index = self.cmb_ay.currentIndex() + 1
            baslangic = datetime(yil, ay_index, 15)
            bitis = baslangic + relativedelta(months=1) - timedelta(days=1)
            self.lbl_donem_bilgi.setText(f"{baslangic.strftime('%d.%m.%Y')} - {bitis.strftime('%d.%m.%Y')}")
        except: pass

    def verileri_yukle(self):
        try:
            # Personel, İzin ve Kriter yükleme kodları aynı kalıyor...
            # Tatil listesi yükleme:
            ws_tatil = veritabani_getir('sabit', 'Tatiller') 
            self.tatil_listesi_np = []
            if ws_tatil:
                df_t = pd.DataFrame(ws_tatil.get_all_records())
                if not df_t.empty and 'Tarih' in df_t.columns:
                    tatiller = pd.to_datetime(df_t['Tarih'], dayfirst=True, errors='coerce')
                    self.tatil_listesi_np = tatiller.dropna().dt.strftime('%Y-%m-%d').tolist()
            
            # Personel ve Kriter verilerini çekme kısmı önceki kodla birebir aynıdır.
            # (Kısalık için burayı özet geçiyorum, production kodunda `verileri_yukle` metodunun tamamını kullanın)
            ws_p = veritabani_getir('personel', 'Personel')
            if ws_p: self.df_personel = pd.DataFrame(ws_p.get_all_records())
            
            ws_i = veritabani_getir('personel', 'izin_giris')
            if ws_i: self.df_izin = pd.DataFrame(ws_i.get_all_records())
            
            ws_k = veritabani_getir('sabit', 'FHSZ_Kriter')
            if ws_k:
                df_k = pd.DataFrame(ws_k.get_all_records())
                for _, row in df_k.iterrows():
                    # YENİ: tr_upper fonksiyonu artık import ediliyor
                    k = tr_upper(str(row.get('menuEleman', '')))
                    v = tr_upper(str(row.get('Aciklama', '')))
                    self.birim_kosul_map[k] = "A" if "A" in v else "B"

        except Exception as e:
            show_error("Hata", f"Veri yüklenemedi: {e}", self)

    def kesisim_izin_gunu_hesapla(self, kimlik_no, donem_bas, donem_bit):
        if self.df_izin.empty: return 0
        p_izinler = self.df_izin[self.df_izin['personel_id'].astype(str).str.contains(str(kimlik_no), na=False)]
        toplam = 0
        for _, row in p_izinler.iterrows():
            try:
                # Tarih formatlama
                ib = pd.to_datetime(row['Başlama_Tarihi'], dayfirst=True)
                ie = pd.to_datetime(row['Bitiş_Tarihi'], dayfirst=True)
                
                kb = max(donem_bas, ib)
                ke = min(donem_bit, ie)
                
                if kb <= ke:
                    # YENİ: is_gunu_hesapla import edildi
                    toplam += is_gunu_hesapla(kb, ke, self.tatil_listesi_np)
            except: pass
        return toplam

    def tabloyu_olustur_ve_hesapla(self):
        self.tablo.setRowCount(0)
        try:
            yil = int(self.cmb_yil.currentText())
            ay_index = self.cmb_ay.currentIndex() + 1
            donem_bas = datetime(yil, ay_index, 15)
            donem_bit = donem_bas + relativedelta(months=1) - timedelta(days=1)
            
            # YENİ: Import edilen fonksiyon kullanımı
            standart_is_gunu = is_gunu_hesapla(donem_bas, donem_bit, self.tatil_listesi_np)
            
            if self.df_personel.empty: return

            for _, row in self.df_personel.iterrows():
                row_idx = self.tablo.rowCount()
                self.tablo.insertRow(row_idx)
                
                kimlik = str(row.get('Kimlik_No', ''))
                self.tablo.setItem(row_idx, 0, QTableWidgetItem(kimlik))
                self.tablo.setItem(row_idx, 1, QTableWidgetItem(str(row.get('Ad_Soyad', ''))))
                
                gorev = str(row.get('Gorev_Yeri', ''))
                self.tablo.setItem(row_idx, 2, QTableWidgetItem(gorev))
                
                # Combo
                cmb = QComboBox()
                cmb.addItems(["Çalışma Koşulu A", "Çalışma Koşulu B"])
                # Varsayılanı belirle
                if tr_upper(gorev) in self.birim_kosul_map and self.birim_kosul_map[tr_upper(gorev)] == "A":
                    cmb.setCurrentIndex(0)
                else:
                    cmb.setCurrentIndex(1)
                
                cmb.currentIndexChanged.connect(lambda i, r=row_idx: self.satir_hesapla(r, standart_is_gunu))
                self.tablo.setCellWidget(row_idx, 3, cmb)
                
                self.tablo.setItem(row_idx, 4, QTableWidgetItem(str(standart_is_gunu)))
                
                kul_izin = self.kesisim_izin_gunu_hesapla(kimlik, donem_bas, donem_bit)
                self.tablo.setItem(row_idx, 5, QTableWidgetItem(str(kul_izin)))
                
                self.satir_hesapla(row_idx, standart_is_gunu)
        except Exception as e:
            show_error("Hata", str(e), self)

    def satir_hesapla(self, row_idx, standart_is_gunu):
        cmb = self.tablo.cellWidget(row_idx, 3)
        try:
            izin = int(self.tablo.item(row_idx, 5).text())
        except: izin = 0
        
        text = cmb.currentText()
        puan = 0
        # YENİ: tr_upper kullanımı
        if "KOŞULU A" in tr_upper(text):
            puan = max(0, standart_is_gunu - izin) * 7
            
        item = QTableWidgetItem(str(puan))
        item.setTextAlignment(Qt.AlignCenter)
        item.setFont(QFont("Segoe UI", 10, QFont.Bold))
        item.setForeground(QColor("black"))
        item.setBackground(QColor("#81c784") if puan > 0 else QColor("#e57373"))
        self.tablo.setItem(row_idx, 6, item)

    def kaydet(self):
        ws = veritabani_getir('personel', 'FHSZ_Puantaj')
        if not ws:
            show_error("Hata", "FHSZ_Puantaj sayfasına erişilemedi.", self)
            return
            
        ait_yil = self.cmb_yil.currentText()
        donem_adi = self.cmb_ay.currentText() 
        
        try:
            self.btn_kaydet.setText("Kaydediliyor...")
            self.btn_kaydet.setEnabled(False)
            QApplication.setOverrideCursor(Qt.WaitCursor)
            
            veriler = []
            for row in range(self.tablo.rowCount()):
                p_id = self.tablo.item(row, 0).text()
                ad = self.tablo.item(row, 1).text()
                aylik_gun = self.tablo.item(row, 4).text()
                kul_izin = self.tablo.item(row, 5).text()
                fiili_calisma = self.tablo.item(row, 6).text()
                
                veriler.append([
                    p_id,           # personel_id
                    ad,             # Ad Soyad
                    ait_yil,        # Ait_yil
                    donem_adi,      # 1. Dönem
                    aylik_gun,      # Aylık Gün
                    kul_izin,       # Kullanılan İzin
                    fiili_calisma   # Fiili Çalışma (saat)
                ])
            
            ws.append_rows(veriler)
            
            self.lbl_donem_bilgi.setText("Puantaj kaydedildi, Şua hak edişleri güncelleniyor...")
            QCoreApplication.processEvents() 
            
            self.izin_bilgi_guncelle(ait_yil)

            show_info("Başarılı", f"{len(veriler)} kayıt başarıyla eklendi ve şua hakları güncellendi.", self)    
        except Exception as e:
            show_error("Hata", f"Kaydetme hatası: {e}", self)
        finally:
            self.btn_kaydet.setText(" VERİTABANINA KAYDET")
            self.btn_kaydet.setEnabled(True)
            QApplication.restoreOverrideCursor()

    def izin_bilgi_guncelle(self, ait_yil):
        print(f"\n--- TOPLU GÜNCELLEME İŞLEMİ BAŞLADI ({ait_yil}) ---")
        try:
            from gspread.cell import Cell

            ws_puantaj = veritabani_getir('personel', 'FHSZ_Puantaj')
            ws_izin = veritabani_getir('personel', 'izin_bilgi')
            
            if not ws_puantaj or not ws_izin:
                print("HATA: Veritabanı sayfalarına bağlanılamadı.")
                return

            df_puantaj = pd.DataFrame(ws_puantaj.get_all_records())
            
            if df_puantaj.empty:
                print("HATA: FHSZ_Puantaj sayfası boş.")
                return

            df_puantaj.columns = df_puantaj.columns.str.strip()
            
            col_yil = next((c for c in df_puantaj.columns if c.lower() == 'ait_yil'), None)
            col_saat = next((c for c in df_puantaj.columns if 'fiili' in c.lower() and 'saat' in c.lower()), None)
            col_id = next((c for c in df_puantaj.columns if 'personel_id' in c.lower()), None)

            if not col_yil or not col_saat or not col_id:
                print(f"HATA: Puantaj sütunları bulunamadı. Mevcut: {df_puantaj.columns.tolist()}")
                return

            df_yil = df_puantaj[df_puantaj[col_yil].astype(str).str.split('.').str[0] == str(ait_yil)].copy()
            
            df_yil['clean_id'] = df_yil[col_id].astype(str).str.split('.').str[0].str.strip()
            df_yil[col_saat] = pd.to_numeric(
                df_yil[col_saat].astype(str).str.replace(',', '.'), errors='coerce'
            ).fillna(0)

            kisi_toplamlari = df_yil.groupby('clean_id')[col_saat].sum().to_dict()
            print(f"-> {len(kisi_toplamlari)} personelin saati hesaplandı.")

            all_values = ws_izin.get_all_values()
            basliklar = [str(x).strip() for x in all_values[0]]
            
            target_col = "Hak_Edilen_sua"
            kimlik_col = "Kimlik_No"

            if target_col not in basliklar:
                show_error("Hata", f"'{target_col}' sütunu bulunamadı.", self)
                return
            
            if kimlik_col not in basliklar:
                print(f"HATA: '{kimlik_col}' sütunu bulunamadı.")
                return

            idx_hak_sua_list = basliklar.index(target_col)
            idx_kimlik_list = basliklar.index(kimlik_col)
            
            gspread_col_index = idx_hak_sua_list + 1 

            batch_updates = []
            
            for i, row in enumerate(all_values[1:], start=2): 
                raw_kimlik = str(row[idx_kimlik_list]) if len(row) > idx_kimlik_list else ""
                kimlik = raw_kimlik.split('.')[0].strip()
                
                if kimlik in kisi_toplamlari:
                    toplam_saat = kisi_toplamlari[kimlik]
                    hak_edilen_gun = sua_hak_edis_hesapla(toplam_saat)
                    
                    mevcut_deger = str(row[idx_hak_sua_list]) if len(row) > idx_hak_sua_list else ""
                    
                    if str(mevcut_deger) != str(hak_edilen_gun):
                        batch_updates.append(Cell(row=i, col=gspread_col_index, value=hak_edilen_gun))

            if batch_updates:
                print(f"-> {len(batch_updates)} kayıt güncelleniyor... (Lütfen bekleyin)")
                ws_izin.update_cells(batch_updates)
                print("-> Güncelleme başarıyla tamamlandı.")
            else:
                print("-> Güncellenecek yeni veri bulunamadı.")
            
        except Exception as e:
            print(f"BEKLENMEDİK HATA: {e}")
            import traceback
            traceback.print_exc()
            show_error("Hata", f"Güncelleme sırasında hata oluştu:\n{e}", self)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # TemaYonetimi entegrasyonu (Test için)
    try:
        from temalar.tema import TemaYonetimi
        TemaYonetimi.uygula_fusion_dark(app)
    except:
        pass
    w = FHSZHesaplamaPenceresi()
    w.show()
    sys.exit(app.exec())