# -*- coding: utf-8 -*-
import sys
import os
import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# PySide6 Kütüphaneleri
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
    QTableWidgetItem, QHeaderView, QPushButton, QLabel, 
    QComboBox, QFrame, QAbstractItemView, QProgressBar, QStyledItemDelegate, QStyle
)
from PySide6.QtCore import Qt, QCoreApplication, QThread, Signal, QRectF
from PySide6.QtGui import QFont, QColor, QPainter, QBrush, QPen, QPainterPath

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
    from araclar.hesaplamalar import sua_hak_edis_hesapla, tr_upper, is_gunu_hesapla
    
    from gspread.cell import Cell 
except ImportError as e:
    print(f"KRİTİK HATA: Modüller yüklenemedi! {e}")
    sys.exit(1)

# =============================================================================
# DELEGATE SINIFLARI (GÜNCELLENDİ)
# =============================================================================

class ComboDelegate(QStyledItemDelegate):
    """
    Çalışma Koşulu sütunu için özel düzenleyici.
    Açılır menü (Dropdown) stil iyileştirmesi yapıldı.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = ["Çalışma Koşulu A", "Çalışma Koşulu B"]

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        editor.addItems(self.items)
        
        # GÜNCELLENMİŞ STİL: Seçeneklerin net görünmesi için
        editor.setStyleSheet("""
            QComboBox {
                background-color: #1e1e1e;
                color: #f0f0f0;
                border: 2px solid #0078d4; /* Aktifken mavi çerçeve */
                border-radius: 4px;
                padding: 4px;
                font-weight: bold;
            }
            /* Açılır Liste Stili */
            QComboBox QAbstractItemView {
                background-color: #2b2b2b;
                color: white;
                selection-background-color: #0078d4;
                selection-color: white;
                border: 1px solid #3e3e3e;
                outline: none;
                padding: 5px;
            }
            /* Ok İşareti Alanı */
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 25px;
                border-left-width: 1px;
                border-left-color: #3e3e3e;
                border-left-style: solid;
                background-color: #252525;
            }
        """)
        return editor

    def setEditorData(self, editor, index):
        text = index.model().data(index, Qt.EditRole)
        if text in self.items:
            editor.setCurrentText(text)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.EditRole)
        
    def updateEditorGeometry(self, editor, option, index):
        # Editörün hücreyi tam kaplamasını sağla
        editor.setGeometry(option.rect)

class SonucDelegate(QStyledItemDelegate):
    """
    Son sütun (Fiili Çalışma) için 'Badge' görünümlü çizim yapar.
    """
    def paint(self, painter, option, index):
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor("#2d2d2d")) 
        else:
            painter.fillRect(option.rect, QColor("#1e1e1e")) 

        try:
            deger = float(index.data(Qt.DisplayRole))
        except (ValueError, TypeError):
            deger = 0

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = QRectF(option.rect)
        rect.adjust(10, 8, -10, -8) 
        
        if deger > 0:
            bg_color = QColor("#1b5e20") # Koyu Yeşil
            border_color = QColor("#66bb6a") 
            text_color = QColor("#ffffff")
        else:
            bg_color = QColor("#333333") # Gri
            border_color = QColor("#555555")
            text_color = QColor("#aaaaaa")

        path = QPainterPath()
        path.addRoundedRect(rect, 6, 6) 
        
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1))
        painter.drawRoundedRect(rect, 6, 6)

        painter.setPen(text_color)
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(rect, Qt.AlignCenter, f"{deger:.0f}")

        painter.restore()

# =============================================================================
# WORKER: PUANTAJ KAYDETME
# =============================================================================
class PuantajKaydetWorker(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)
    
    def __init__(self, puantaj_verisi):
        super().__init__()
        self.veri = puantaj_verisi

    def run(self):
        try:
            ws_izin = veritabani_getir('personel', 'Izin_Takip')
            if not ws_izin:
                self.hata_olustu.emit("İzin veritabanına bağlanılamadı.")
                return

            batch_updates = []
            tum_veriler = ws_izin.get_all_values()
            
            if not tum_veriler:
                 self.hata_olustu.emit("Veritabanı boş.")
                 return

            basliklar = tum_veriler[0]
            try:
                idx_kimlik = basliklar.index("TC Kimlik No")
                idx_sua = -1
                for i, b in enumerate(basliklar):
                    if "Şua" in b and "Hak" in b:
                        idx_sua = i
                        break
                if idx_sua == -1: idx_sua = len(basliklar) 
            except ValueError:
                self.hata_olustu.emit("Veritabanı sütun yapısı hatalı (TC Kimlik No bulunamadı).")
                return

            row_map = {} 
            for i, row in enumerate(tum_veriler):
                if i == 0: continue 
                if len(row) > idx_kimlik:
                    tc = str(row[idx_kimlik]).strip()
                    row_map[tc] = i + 1 

            updates = []
            for tc, gun in self.veri.items():
                if tc in row_map:
                    row_idx = row_map[tc]
                    updates.append(Cell(row=row_idx, col=idx_sua + 1, value=gun))
            
            if updates:
                ws_izin.update_cells(updates)
                self.islem_tamam.emit()
            else:
                self.hata_olustu.emit("Güncellenecek kayıt bulunamadı.")
        
        except InternetBaglantiHatasi:
             self.hata_olustu.emit("İnternet bağlantısı kesildi. Kayıt yapılamadı.")
        except KimlikDogrulamaHatasi:
             self.hata_olustu.emit("Google oturum süresi doldu.")
        except Exception as e:
            self.hata_olustu.emit(f"Kayıt işlemi hatası: {str(e)}")

# =============================================================================
# ANA FORM: FHSZ HESAPLAMA
# =============================================================================
class FHSZHesaplamaPenceresi(QWidget):
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.setWindowTitle("FHSZ (Şua) Hesaplama Modülü")
        self.resize(1150, 780)
        
        # --- VERİLER ---
        self.df_personel = pd.DataFrame()
        self.df_izin = pd.DataFrame()
        self.tatil_listesi_np = []
        self.birim_kosul_map = {} 
        self.standart_is_gunu = 22 # Varsayılan
        
        self.setup_ui()
        
        # Yetki Kontrolü
        YetkiYoneticisi.uygula(self, "fhsz_hesapla")
        
        # Verileri Yükle
        self.verileri_yukle()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # --- 1. ÜST PANEL (FİLTRELER) ---
        filter_frame = QFrame()
        filter_frame.setObjectName("filter_frame") 
        filter_frame.setStyleSheet("""
            QFrame#filter_frame {
                background-color: #2b2b2b; 
                border-radius: 8px; 
                border: 1px solid #3e3e3e;
            }
        """)
        
        h_layout = QHBoxLayout(filter_frame)
        h_layout.setContentsMargins(20, 15, 20, 15)
        h_layout.setSpacing(15)
        
        # Yıl
        h_layout.addWidget(QLabel("Dönem Yılı:"))
        bu_yil = datetime.now().year
        self.cmb_yil = OrtakAraclar.create_combo_box(filter_frame, [str(y) for y in range(bu_yil - 3, bu_yil + 3)])
        self.cmb_yil.setCurrentText(str(bu_yil))
        self.cmb_yil.setFixedWidth(100)
        h_layout.addWidget(self.cmb_yil)
        
        # Ay
        h_layout.addWidget(QLabel("Dönem Ayı:"))
        aylar = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
                 "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        self.cmb_ay = OrtakAraclar.create_combo_box(filter_frame, aylar)
        self.cmb_ay.setCurrentIndex(datetime.now().month - 1)
        self.cmb_ay.setFixedWidth(140)
        h_layout.addWidget(self.cmb_ay)

        # Bilgi Etiketi
        self.lbl_donem_bilgi = QLabel("...")
        self.lbl_donem_bilgi.setStyleSheet("color: #60cdff; font-weight: bold; margin-left: 15px; font-size: 13px;")
        h_layout.addWidget(self.lbl_donem_bilgi)
        
        h_layout.addStretch()

        # Hesapla Butonu
        self.btn_hesapla = OrtakAraclar.create_button(filter_frame, "⚡ LİSTELE VE HESAPLA", self.tabloyu_olustur_ve_hesapla)
        self.btn_hesapla.setObjectName("btn_hesapla")
        self.btn_hesapla.setFixedHeight(35)
        self.btn_hesapla.setCursor(Qt.PointingHandCursor)
        h_layout.addWidget(self.btn_hesapla)
        
        main_layout.addWidget(filter_frame)

        # --- 2. ORTA PANEL (TABLO) ---
        self.sutunlar = ["Kimlik No", "Adı Soyadı", "Birim", "Çalışma Koşulu", 
                         "Aylık Gün", "Kullanılan İzin", "Fiili Çalışma (Saat)"]
        
        self.tablo = QTableWidget()
        self.tablo.setColumnCount(len(self.sutunlar))
        self.tablo.setHorizontalHeaderLabels(self.sutunlar)
        self.tablo.verticalHeader().setVisible(False)
        self.tablo.setShowGrid(False) 
        self.tablo.setAlternatingRowColors(True)
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectRows)
        
        # Başlık ve Satır Stili (Modern)
        self.tablo.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e1e;
                border: 1px solid #3e3e3e;
                border-radius: 4px;
                gridline-color: #2d2d2d;
            }
            QHeaderView::section {
                background-color: #2d2d2d;
                color: #f0f0f0;
                padding: 8px;
                border: none;
                font-weight: bold;
            }
            QTableWidget::item {
                padding: 5px;
                border-bottom: 1px solid #2d2d2d;
            }
            QTableWidget::item:selected {
                background-color: #3a3a3a;
                color: white;
            }
        """)
        
        header = self.tablo.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents) # Kimlik
        header.setSectionResizeMode(3, QHeaderView.Fixed) # Koşul
        self.tablo.setColumnWidth(3, 180)
        header.setSectionResizeMode(6, QHeaderView.Fixed) # Sonuç
        self.tablo.setColumnWidth(6, 120)

        # Delegate Atamaları
        self.tablo.setItemDelegateForColumn(3, ComboDelegate(self.tablo))
        self.tablo.setItemDelegateForColumn(6, SonucDelegate(self.tablo))
        
        self.tablo.itemChanged.connect(self._hucre_degisti)

        main_layout.addWidget(self.tablo)
        
        # --- 3. ALT PANEL (KAYDET) ---
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 5, 0, 0)
        
        lbl_info = QLabel("ℹ️ Bilgi: 'Çalışma Koşulu' üzerine tıklayarak A/B değişimini yapabilirsiniz. Hesaplama otomatik güncellenir.")
        lbl_info.setStyleSheet("color: #888; font-style: italic;")
        footer_layout.addWidget(lbl_info)
        
        footer_layout.addStretch()
        
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setFixedWidth(200)
        self.progress.setTextVisible(False)
        footer_layout.addWidget(self.progress)

        # İptal Butonu
        btn_iptal = QPushButton("Kapat")
        btn_iptal.setFixedSize(100, 40)
        btn_iptal.setObjectName("btn_iptal")
        btn_iptal.setCursor(Qt.PointingHandCursor)
        btn_iptal.clicked.connect(lambda: pencereyi_kapat(self))
        footer_layout.addWidget(btn_iptal)

        # Kaydet Butonu
        self.btn_kaydet = OrtakAraclar.create_button(self, "💾 VERİTABANINA KAYDET", self.kaydet)
        self.btn_kaydet.setObjectName("btn_kaydet")
        self.btn_kaydet.setFixedSize(220, 40)
        footer_layout.addWidget(self.btn_kaydet)
        
        main_layout.addLayout(footer_layout)

        self.cmb_yil.currentIndexChanged.connect(self.donem_guncelle_label)
        self.cmb_ay.currentIndexChanged.connect(self.donem_guncelle_label)
        self.donem_guncelle_label()

    def donem_guncelle_label(self):
        try:
            yil = int(self.cmb_yil.currentText())
            ay_index = self.cmb_ay.currentIndex() + 1
            baslangic = datetime(yil, ay_index, 15)
            bitis = baslangic + relativedelta(months=1) - timedelta(days=1)
            self.lbl_donem_bilgi.setText(f"Dönem: {baslangic.strftime('%d.%m.%Y')} - {bitis.strftime('%d.%m.%Y')}")
        except:
            pass

    def verileri_yukle(self):
        try:
            # 1. Personel
            ws_p = veritabani_getir('personel', 'Personel')
            if ws_p:
                self.df_personel = pd.DataFrame(ws_p.get_all_records())
                if 'Kimlik_No' in self.df_personel.columns:
                    self.df_personel['Kimlik_No'] = self.df_personel['Kimlik_No'].astype(str).apply(lambda x: x.split('.')[0] if x else "0")
                if 'Gorev_Yeri' in self.df_personel.columns:
                    self.df_personel['Gorev_Yeri'] = self.df_personel['Gorev_Yeri'].fillna("").astype(str)

            # 2. İzinler
            ws_i = veritabani_getir('personel', 'izin_giris')
            if ws_i:
                self.df_izin = pd.DataFrame(ws_i.get_all_records())
                if not self.df_izin.empty:
                    if 'personel_id' in self.df_izin.columns:
                        self.df_izin['personel_id'] = self.df_izin['personel_id'].astype(str).apply(lambda x: x.split('.')[0] if x else "0")
                    for col in ['Başlama_Tarihi', 'Bitiş_Tarihi']:
                        if col in self.df_izin.columns:
                            self.df_izin[col] = pd.to_datetime(self.df_izin[col], dayfirst=True, errors='coerce')

            # 3. Tatiller
            ws_tatil = veritabani_getir('sabit', 'Tatiller') 
            self.tatil_listesi_np = []
            if ws_tatil:
                df_t = pd.DataFrame(ws_tatil.get_all_records())
                if not df_t.empty and 'Tarih' in df_t.columns:
                    tatiller = pd.to_datetime(df_t['Tarih'], dayfirst=True, errors='coerce')
                    self.tatil_listesi_np = tatiller.dropna().dt.strftime('%Y-%m-%d').tolist()
            
            # 4. Kriterler
            self.birim_kosul_map = {}
            ws_kriter = veritabani_getir('sabit', 'FHSZ_Kriter') 
            if ws_kriter:
                df_k = pd.DataFrame(ws_kriter.get_all_records())
                if not df_k.empty:
                    df_k.columns = df_k.columns.str.strip()
                    col_menu = 'menuEleman' if 'menuEleman' in df_k.columns else 'MenuEleman'
                    col_acik = 'Aciklama' if 'Aciklama' in df_k.columns else 'aciklama'
                    
                    if col_menu in df_k.columns and col_acik in df_k.columns:
                        for _, row in df_k.iterrows():
                            anahtar = tr_upper(str(row[col_menu]).strip())
                            deger = tr_upper(str(row[col_acik]).strip())
                            kosul = "A" if ("KOŞULU A" in deger or "KOSULU A" in deger or "A" == deger) else "B"
                            if anahtar: self.birim_kosul_map[anahtar] = kosul

        except InternetBaglantiHatasi:
            show_error("Bağlantı Hatası", "İnternet bağlantısı koptu.", self)
        except Exception as e:
            show_error("Veri Hatası", f"Veriler yüklenirken hata oluştu: {e}", self)

    def kesisim_izin_gunu_hesapla(self, kimlik_no, donem_bas, donem_bit):
        if self.df_izin.empty: return 0
        if 'personel_id' not in self.df_izin.columns: return 0
        
        p_izinler = self.df_izin[self.df_izin['personel_id'].astype(str) == str(kimlik_no)]
        toplam = 0
        
        for _, row in p_izinler.iterrows():
            try:
                ib = row['Başlama_Tarihi']
                ie = row['Bitiş_Tarihi']
                if pd.isnull(ib) or pd.isnull(ie): continue

                kb = max(donem_bas, ib)
                ke = min(donem_bit, ie)
                
                if kb <= ke:
                    toplam += is_gunu_hesapla(kb, ke, self.tatil_listesi_np)
            except: 
                pass
        return toplam

    def tabloyu_olustur_ve_hesapla(self):
        self.tablo.blockSignals(True) 
        self.tablo.setRowCount(0)
        self.btn_hesapla.setEnabled(False)
        self.btn_hesapla.setText("Hesaplanıyor...")
        QApplication.processEvents()
        
        try:
            yil = int(self.cmb_yil.currentText())
            ay_index = self.cmb_ay.currentIndex() + 1
            donem_bas = datetime(yil, ay_index, 15)
            donem_bit = donem_bas + relativedelta(months=1) - timedelta(days=1)
            
            self.standart_is_gunu = is_gunu_hesapla(donem_bas, donem_bit, self.tatil_listesi_np)
            
            if self.df_personel.empty:
                show_info("Uyarı", "Personel listesi bulunamadı.", self)
                self.btn_hesapla.setEnabled(True)
                self.btn_hesapla.setText("⚡ LİSTELE VE HESAPLA")
                self.tablo.blockSignals(False)
                return

            sorted_df = self.df_personel.sort_values(by="Ad_Soyad")

            for _, row in sorted_df.iterrows():
                row_idx = self.tablo.rowCount()
                self.tablo.insertRow(row_idx)
                
                kimlik = str(row.get('Kimlik_No', '')).strip()
                ad = row.get('Ad_Soyad', '')
                personel_gorev_yeri = str(row.get('Gorev_Yeri', '')).strip()
                
                self._set_item(row_idx, 0, kimlik)
                self._set_item(row_idx, 1, ad)
                self._set_item(row_idx, 2, personel_gorev_yeri)
                
                varsayilan_kosul = "Çalışma Koşulu B"
                personel_gorev_key = tr_upper(personel_gorev_yeri)
                if personel_gorev_key in self.birim_kosul_map:
                    if self.birim_kosul_map[personel_gorev_key] == "A":
                        varsayilan_kosul = "Çalışma Koşulu A"
                
                item_kosul = QTableWidgetItem(varsayilan_kosul)
                item_kosul.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable)
                self.tablo.setItem(row_idx, 3, item_kosul)
                
                self._set_item(row_idx, 4, str(self.standart_is_gunu))
                
                izin_gunu = self.kesisim_izin_gunu_hesapla(kimlik, donem_bas, donem_bit)
                self._set_item(row_idx, 5, str(izin_gunu))
                
                self._satir_hesapla(row_idx)
                
        except InternetBaglantiHatasi:
             show_error("Bağlantı Hatası", "İnternet bağlantısı koptu.", self)
        except Exception as e:
            show_error("Hesaplama Hatası", str(e), self)
        
        self.btn_hesapla.setEnabled(True)
        self.btn_hesapla.setText("⚡ LİSTELE VE HESAPLA")
        self.tablo.blockSignals(False)

    def _set_item(self, row, col, text):
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled) 
        self.tablo.setItem(row, col, item)

    def _hucre_degisti(self, item):
        if item.column() == 3: 
            self._satir_hesapla(item.row())

    def _satir_hesapla(self, row_idx):
        try:
            kosul_text = self.tablo.item(row_idx, 3).text()
            izin_gunu = int(self.tablo.item(row_idx, 5).text())
            
            puan = 0
            if "KOŞULU A" in tr_upper(kosul_text): 
                net_gun = max(0, self.standart_is_gunu - izin_gunu)
                puan = net_gun * 7
            
            self.tablo.setItem(row_idx, 6, QTableWidgetItem(str(puan)))
            
        except Exception:
            pass

    def kaydet(self):
        try:
            ws = veritabani_getir('personel', 'FHSZ_Puantaj')
            if not ws:
                show_error("Hata", "FHSZ_Puantaj sayfasına erişilemedi.", self)
                return
            
            ait_yil = self.cmb_yil.currentText()
            donem_adi = self.cmb_ay.currentText() 
            
            self.btn_kaydet.setText("Kaydediliyor...")
            self.btn_kaydet.setEnabled(False)
            self.progress.setVisible(True)
            self.progress.setRange(0, 0)
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
        
        except InternetBaglantiHatasi:
             show_error("Bağlantı Hatası", "İnternet bağlantısı kesildi. Kaydedilemedi.", self)
        except Exception as e:
            show_error("Hata", f"Kaydetme hatası: {e}", self)
        finally:
            self.btn_kaydet.setText("💾 VERİTABANINA KAYDET")
            self.btn_kaydet.setEnabled(True)
            self.progress.setVisible(False)
            QApplication.restoreOverrideCursor()

    def izin_bilgi_guncelle(self, ait_yil):
        print(f"\n--- TOPLU GÜNCELLEME İŞLEMİ BAŞLADI ({ait_yil}) ---")
        try:
            ws_puantaj = veritabani_getir('personel', 'FHSZ_Puantaj')
            ws_izin = veritabani_getir('personel', 'izin_bilgi')
            
            if not ws_puantaj or not ws_izin: return

            df_puantaj = pd.DataFrame(ws_puantaj.get_all_records())
            if df_puantaj.empty: return

            df_puantaj.columns = df_puantaj.columns.str.strip()
            
            col_yil = next((c for c in df_puantaj.columns if c.lower() == 'ait_yil'), None)
            col_saat = next((c for c in df_puantaj.columns if 'fiili' in c.lower() and 'saat' in c.lower()), None)
            col_id = next((c for c in df_puantaj.columns if 'personel_id' in c.lower()), None)

            if not col_yil or not col_saat or not col_id: return

            df_yil = df_puantaj[df_puantaj[col_yil].astype(str).str.split('.').str[0] == str(ait_yil)].copy()
            df_yil['clean_id'] = df_yil[col_id].astype(str).str.split('.').str[0].str.strip()
            df_yil[col_saat] = pd.to_numeric(df_yil[col_saat].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)

            kisi_toplamlari = df_yil.groupby('clean_id')[col_saat].sum().to_dict()

            all_values = ws_izin.get_all_values()
            basliklar = [str(x).strip() for x in all_values[0]]
            
            target_col = "Hak_Edilen_sua"
            kimlik_col = "Kimlik_No"

            if target_col not in basliklar or kimlik_col not in basliklar: return

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
                ws_izin.update_cells(batch_updates)
                
        except Exception as e:
            print(f"GÜNCELLEME HATASI: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    try:
        TemaYonetimi.uygula_fusion_dark(app)
    except Exception as e:
        print(f"Tema uygulanamadı: {e}")
        app.setStyle("Fusion")
    
    w = FHSZHesaplamaPenceresi()
    w.show()
    sys.exit(app.exec())