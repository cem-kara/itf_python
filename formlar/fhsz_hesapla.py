# -*- coding: utf-8 -*-
import sys
import os
import pandas as pd
import time
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# PySide6 Kütüphaneleri
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
    QTableWidgetItem, QHeaderView, QPushButton, QLabel, 
    QComboBox, QFrame, QAbstractItemView, QProgressBar, 
    QStyledItemDelegate, QStyle, QMessageBox
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
    from araclar.ortak_araclar import OrtakAraclar, pencereyi_kapat, show_info, show_error, show_question
    from araclar.hesaplamalar import sua_hak_edis_hesapla, tr_upper, is_gunu_hesapla
    from gspread.cell import Cell 
except ImportError as e:
    print(f"KRİTİK HATA: Modüller yüklenemedi! {e}")
    sys.exit(1)

# =============================================================================
# DELEGATE SINIFLARI
# =============================================================================
class ComboDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = ["Çalışma Koşulu A", "Çalışma Koşulu B"]

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        editor.addItems(self.items)
        editor.setStyleSheet("""
            QComboBox { background-color: #1e1e1e; color: #f0f0f0; border: 2px solid #0078d4; border-radius: 4px; padding: 4px; font-weight: bold; }
            QComboBox QAbstractItemView { background-color: #2b2b2b; color: white; selection-background-color: #0078d4; border: 1px solid #3e3e3e; outline: none; padding: 5px; }
        """)
        return editor

    def setEditorData(self, editor, index):
        text = index.model().data(index, Qt.EditRole)
        if text in self.items: editor.setCurrentText(text)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.EditRole)
        
    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

class SonucDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        if option.state & QStyle.State_Selected: painter.fillRect(option.rect, QColor("#2d2d2d")) 
        else: painter.fillRect(option.rect, QColor("#1e1e1e")) 

        try: deger = float(index.data(Qt.DisplayRole))
        except: deger = 0

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(option.rect); rect.adjust(10, 8, -10, -8) 
        
        if deger > 0: bg, border, text = "#1b5e20", "#66bb6a", "#ffffff"
        else: bg, border, text = "#333333", "#555555", "#aaaaaa"

        path = QPainterPath(); path.addRoundedRect(rect, 6, 6) 
        painter.setBrush(QBrush(QColor(bg))); painter.setPen(QPen(QColor(border), 1))
        painter.drawRoundedRect(rect, 6, 6)
        painter.setPen(QColor(text)); painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(rect, Qt.AlignCenter, f"{deger:.0f}")
        painter.restore()

# =============================================================================
# WORKER: PUANTAJ KONTROL
# =============================================================================
class PuantajKontrolWorker(QThread):
    durum_sinyali = Signal(bool, int)
    hata_olustu = Signal(str)

    def __init__(self, yil, ay): super().__init__(); self.yil = str(yil); self.ay = str(ay)

    def run(self):
        try:
            ws = veritabani_getir('personel', 'FHSZ_Puantaj')
            if not ws: self.hata_olustu.emit("Veritabanı hatası"); return
            all_data = ws.get_all_records(); count = 0
            for row in all_data:
                rc = {k.strip(): v for k, v in row.items()}
                if str(rc.get('Ait_Yil','')).strip() == self.yil and str(rc.get('Donem','')).strip() == self.ay: count += 1
            self.durum_sinyali.emit(count > 0, count)
        except Exception as e: self.hata_olustu.emit(str(e))

# =============================================================================
# WORKER: TAM KAYIT
# =============================================================================
class TamKayitWorker(QThread):
    log_sinyali = Signal(str); islem_bitti = Signal(); hata_olustu = Signal(str)
    
    def __init__(self, puantaj, yil, ay, overwrite):
        super().__init__(); self.veriler = puantaj; self.yil = str(yil); self.ay = str(ay); self.overwrite = overwrite

    def run(self):
        try:
            self.log_sinyali.emit("⏳ Veritabanına bağlanılıyor...")
            ws_puantaj = veritabani_getir('personel', 'FHSZ_Puantaj')
            ws_izin = veritabani_getir('personel', 'izin_bilgi')
            
            if self.overwrite:
                self.log_sinyali.emit(f"⚠️ {self.yil} {self.ay} dönemi temizleniyor...")
                all_rows = ws_puantaj.get_all_values()
                if len(all_rows) > 1:
                    headers = [str(h).strip() for h in all_rows[0]]
                    idx_y, idx_a = -1, -1
                    for i, h in enumerate(headers):
                        if h in ['Ait_Yil', 'Ait_yil']: idx_y = i
                        if h in ['Donem', 'Dönem']: idx_a = i
                    if idx_y != -1 and idx_a != -1:
                        new_data = [all_rows[0]] + [r for r in all_rows[1:] if not (str(r[idx_y]) == self.yil and str(r[idx_a]) == self.ay)]
                        ws_puantaj.clear(); ws_puantaj.update('A1', new_data)

            self.log_sinyali.emit("💾 Kaydediliyor...")
            ws_puantaj.append_rows(self.veriler)
            
            self.log_sinyali.emit("🔄 Şua güncelleniyor...")
            all_p = ws_puantaj.get_all_records(); df = pd.DataFrame(all_p)
            if not df.empty:
                df.columns = [c.strip() for c in df.columns]
                c_yil = next((c for c in df.columns if c in ['Ait_Yil']), None)
                c_saat = next((c for c in df.columns if 'Fiili' in c), None)
                c_id = next((c for c in df.columns if 'Kimlik' in c or 'id' in c), None)
                
                if c_yil and c_saat and c_id:
                    df_yil = df[df[c_yil].astype(str) == self.yil].copy()
                    df_yil['saat'] = pd.to_numeric(df_yil[c_saat].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
                    df_yil['cid'] = df_yil[c_id].astype(str).str.split('.').str[0].str.strip()
                    totals = df_yil.groupby('cid')['saat'].sum().to_dict()
                    
                    b_rows = ws_izin.get_all_values()
                    headers = [str(x).strip() for x in b_rows[0]]
                    if "Sua_Cari_Yil_Kazanim" in headers and "TC_Kimlik" in headers:
                        it, ic = headers.index("Sua_Cari_Yil_Kazanim")+1, headers.index("TC_Kimlik")
                        updates = []
                        for i, r in enumerate(b_rows[1:], 2):
                            tc = str(r[ic]).strip().split('.')[0]
                            if tc in totals:
                                yeni = sua_hak_edis_hesapla(totals[tc])
                                try: mevc = float(str(r[it-1]).replace(',', '.'))
                                except: mevc = -1
                                if mevc != yeni: updates.append(Cell(i, it, yeni))
                        if updates: ws_izin.update_cells(updates)
            self.islem_bitti.emit()
        except Exception as e: self.hata_olustu.emit(str(e))

# =============================================================================
# ANA FORM
# =============================================================================
class FHSZHesaplamaPenceresi(QWidget):
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.setWindowTitle("FHSZ (Şua) Hesaplama Modülü")
        self.resize(1150, 780)
        
        self.df_personel = pd.DataFrame()
        self.df_izin = pd.DataFrame()
        self.tatil_listesi_np = []
        self.birim_kosul_map = {} 
        self.standart_is_gunu = 22 
        
        self.setup_ui()
        YetkiYoneticisi.uygula(self, "fhsz_hesapla")
        self.verileri_yukle()

    def setup_ui(self):
        main_layout = QVBoxLayout(self); main_layout.setContentsMargins(20,20,20,20); main_layout.setSpacing(15)
        
        ff = QFrame(); ff.setObjectName("filter_frame"); ff.setStyleSheet("QFrame#filter_frame{background-color:#2b2b2b; border-radius:8px; border:1px solid #3e3e3e;}")
        hl = QHBoxLayout(ff); hl.setContentsMargins(20,15,20,15); hl.setSpacing(15)
        
        hl.addWidget(QLabel("Dönem Yılı:"))
        by = datetime.now().year
        self.cmb_yil = OrtakAraclar.create_combo_box(ff, [str(y) for y in range(by-3, by+3)]); self.cmb_yil.setCurrentText(str(by)); self.cmb_yil.setFixedWidth(100); hl.addWidget(self.cmb_yil)
        
        hl.addWidget(QLabel("Dönem Ayı:"))
        aylar = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        self.cmb_ay = OrtakAraclar.create_combo_box(ff, aylar); self.cmb_ay.setCurrentIndex(datetime.now().month-1); self.cmb_ay.setFixedWidth(140); hl.addWidget(self.cmb_ay)
        
        self.lbl_donem = QLabel("..."); self.lbl_donem.setStyleSheet("color:#60cdff; font-weight:bold; margin-left:15px;"); hl.addWidget(self.lbl_donem); hl.addStretch()
        
        self.btn_hesapla = OrtakAraclar.create_button(ff, "⚡ LİSTELE VE HESAPLA", self.tabloyu_olustur_ve_hesapla); self.btn_hesapla.setFixedHeight(35); hl.addWidget(self.btn_hesapla)
        main_layout.addWidget(ff)

        self.cols = ["Kimlik No", "Adı Soyadı", "Birim", "Çalışma Koşulu", "Aylık Gün", "Kullanılan İzin", "Fiili Çalışma (Saat)"]
        self.tablo = QTableWidget(); self.tablo.setColumnCount(len(self.cols)); self.tablo.setHorizontalHeaderLabels(self.cols)
        self.tablo.verticalHeader().setVisible(False); self.tablo.setAlternatingRowColors(True); self.tablo.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tablo.setStyleSheet("QTableWidget{background-color:#1e1e1e; border:1px solid #3e3e3e; gridline-color:#2d2d2d;} QHeaderView::section{background-color:#2d2d2d; color:#f0f0f0; padding:8px; border:none; font-weight:bold;}")
        
        h = self.tablo.horizontalHeader(); h.setSectionResizeMode(QHeaderView.Stretch)
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents); h.setSectionResizeMode(3, QHeaderView.Fixed); self.tablo.setColumnWidth(3, 180)
        h.setSectionResizeMode(6, QHeaderView.Fixed); self.tablo.setColumnWidth(6, 120)
        self.tablo.setItemDelegateForColumn(3, ComboDelegate(self.tablo)); self.tablo.setItemDelegateForColumn(6, SonucDelegate(self.tablo))
        self.tablo.itemChanged.connect(self._hucre_degisti)
        main_layout.addWidget(self.tablo)
        
        fl = QHBoxLayout(); self.lbl_durum = QLabel("Hazır"); self.lbl_durum.setStyleSheet("color:#888;"); fl.addWidget(self.lbl_durum); fl.addStretch()
        self.progress = QProgressBar(); self.progress.setVisible(False); self.progress.setFixedWidth(200); fl.addWidget(self.progress)
        btn_kapat = QPushButton("Kapat"); btn_kapat.setFixedSize(100,40); btn_kapat.clicked.connect(lambda: pencereyi_kapat(self)); fl.addWidget(btn_kapat)
        self.btn_kaydet = OrtakAraclar.create_button(self, "💾 VERİTABANINA KAYDET", self.kaydet_baslat); self.btn_kaydet.setFixedSize(220,40); fl.addWidget(self.btn_kaydet)
        main_layout.addLayout(fl)

        self.cmb_yil.currentIndexChanged.connect(self.donem_guncelle); self.cmb_ay.currentIndexChanged.connect(self.donem_guncelle); self.donem_guncelle()

    def donem_guncelle(self):
        try:
            y = int(self.cmb_yil.currentText()); a = self.cmb_ay.currentIndex()+1
            d1 = datetime(y, a, 15); d2 = d1 + relativedelta(months=1) - timedelta(days=1)
            self.lbl_donem.setText(f"Dönem: {d1.strftime('%d.%m.%Y')} - {d2.strftime('%d.%m.%Y')}")
        except: pass

    def verileri_yukle(self):
        try:
            # Personel verisi
            wsp = veritabani_getir('personel', 'Personel')
            if wsp:
                self.df_personel = pd.DataFrame(wsp.get_all_records())
                # Kolon temizliği
                self.df_personel.columns = [c.strip() for c in self.df_personel.columns]
                
                if 'Kimlik_No' in self.df_personel.columns:
                    self.df_personel['Kimlik_No'] = self.df_personel['Kimlik_No'].astype(str).apply(lambda x: x.split('.')[0] if x else "0")
                if 'Gorev_Yeri' in self.df_personel.columns:
                    self.df_personel['Gorev_Yeri'] = self.df_personel['Gorev_Yeri'].fillna("").astype(str)

            # İzinler
            wsi = veritabani_getir('personel', 'izin_giris')
            if wsi:
                self.df_izin = pd.DataFrame(wsi.get_all_records())
                if not self.df_izin.empty:
                    if 'personel_id' in self.df_izin.columns:
                        self.df_izin['personel_id'] = self.df_izin['personel_id'].astype(str).apply(lambda x: x.split('.')[0] if x else "0")
                    for c in ['Başlama_Tarihi', 'Bitiş_Tarihi']:
                        if c in self.df_izin.columns: self.df_izin[c] = pd.to_datetime(self.df_izin[c], dayfirst=True, errors='coerce')

            # Tatiller
            wst = veritabani_getir('sabit', 'Tatiller')
            self.tatil_listesi_np = []
            if wst:
                dft = pd.DataFrame(wst.get_all_records())
                if not dft.empty and 'Tarih' in dft.columns:
                    self.tatil_listesi_np = pd.to_datetime(dft['Tarih'], dayfirst=True, errors='coerce').dropna().dt.strftime('%Y-%m-%d').tolist()
            
            # Sabitler
            wss = veritabani_getir('sabit', 'Sabitler')
            self.birim_kosul_map = {}
            if wss:
                dfs = pd.DataFrame(wss.get_all_records())
                if not dfs.empty:
                    dff = dfs[dfs['Kod'] == 'Gorev_Yeri']
                    for _, r in dff.iterrows():
                        b = tr_upper(str(r.get('MenuEleman','')).strip())
                        ka = tr_upper(str(r.get('Aciklama','')).strip())
                        k = "A" if ("KOŞULU A" in ka or "KOSULU A" in ka or "A" == ka) else "B"
                        if b: self.birim_kosul_map[b] = k
        except Exception as e: show_error("Hata", str(e), self)

    def kesisim_izin_gunu_hesapla(self, kimlik, db, de):
        if self.df_izin.empty: return 0
        if 'personel_id' not in self.df_izin.columns: return 0
        p_izin = self.df_izin[self.df_izin['personel_id'].astype(str) == str(kimlik)]
        toplam = 0
        for _, r in p_izin.iterrows():
            try:
                ib, ie = r['Başlama_Tarihi'], r['Bitiş_Tarihi']
                if pd.isnull(ib) or pd.isnull(ie): continue
                kb, ke = max(db, ib), min(de, ie)
                if kb <= ke: toplam += is_gunu_hesapla(kb, ke, self.tatil_listesi_np)
            except: pass
        return toplam

    # 🟢 GÜNCELLENEN KISIM: 26.04.2022 KONTROLÜ VE GEÇİŞ MANTIĞI
    def tabloyu_olustur_ve_hesapla(self):
        self.tablo.blockSignals(True); self.tablo.setRowCount(0)
        self.btn_hesapla.setEnabled(False); self.btn_hesapla.setText("Hesaplanıyor...")
        QApplication.processEvents()
        
        try:
            yil = int(self.cmb_yil.currentText())
            ay_idx = self.cmb_ay.currentIndex() + 1
            donem_bas = datetime(yil, ay_idx, 15)
            donem_bit = donem_bas + relativedelta(months=1) - timedelta(days=1)
            
            # 🟢 TARİH KONTROLÜ (YENİ KANUN YÜRÜRLÜĞÜ)
            esik_tarih = datetime(2022, 4, 26)
            
            # A. Tamamen eski dönem mi? (Bitiş bile esikten önceyse)
            if donem_bit < esik_tarih:
                show_info("Tarih Kısıtlaması", 
                          "Seçilen dönem, yeni kanunun yürürlük tarihi olan 26.04.2022'den öncedir.\n"
                          "Bu dönem için hesaplama yapılamaz.", self)
                self.btn_hesapla.setEnabled(True); self.btn_hesapla.setText("⚡ LİSTELE VE HESAPLA"); self.tablo.blockSignals(False)
                return

            # B. Geçiş Dönemi mi? (Başlangıç eski, Bitiş yeni)
            hesaplama_baslangic = donem_bas
            if donem_bas < esik_tarih:
                hesaplama_baslangic = esik_tarih # 26.04.2022
                # Kullanıcıyı uyar (Opsiyonel, çok sık çıkmasın diye yoruma alabilirsiniz)
                # show_info("Bilgi", "Bu dönem geçiş dönemidir (26.04.2022). Hesaplama bu tarihten itibaren yapılacaktır.", self)

            # Standart iş günü (Revize edilmiş başlangıca göre)
            self.standart_is_gunu = is_gunu_hesapla(hesaplama_baslangic, donem_bit, self.tatil_listesi_np)
            
            # İZİN VERİLEN SINIFLAR
            izin_verilen_siniflar = ["Akademik Personel", "Asistan Doktor", "Radyasyon Görevlisi", "Hemşire"]

            if self.df_personel.empty: return

            sorted_df = self.df_personel.sort_values(by="Ad_Soyad")

            for _, row in sorted_df.iterrows():
                kimlik = str(row.get('Kimlik_No', '')).strip()
                ad = row.get('Ad_Soyad', '')
                birim = str(row.get('Gorev_Yeri', '')).strip()
                durum = str(row.get('Durum', 'Aktif')).strip()
                hizmet_sinifi = str(row.get('Hizmet_Sinifi', '') or row.get('Hizmet Sınıfı', '')).strip()
                ayrilis_tarihi_str = str(row.get('Ayrilis_Tarihi', '')).strip()

                # SINIF FİLTRESİ
                if hizmet_sinifi not in izin_verilen_siniflar: continue

                # PASİF KONTROLÜ VE KISTALYEVM
                kisi_bitis = donem_bit
                
                if durum == "Pasif":
                    try: ayrilis_date = datetime.strptime(ayrilis_tarihi_str, "%d.%m.%Y")
                    except: ayrilis_date = None
                    
                    if ayrilis_date:
                        # Ayrılış, hesaplamanın başlayacağı tarihten bile önceyse -> Listeleme
                        if ayrilis_date < hesaplama_baslangic: continue 
                        # Ayrılış dönem içindeyse -> Bitiş tarihini çek
                        if ayrilis_date < donem_bit: kisi_bitis = ayrilis_date
                
                # SATIR EKLE
                row_idx = self.tablo.rowCount(); self.tablo.insertRow(row_idx)
                self._set_item(row_idx, 0, kimlik); self._set_item(row_idx, 1, ad); self._set_item(row_idx, 2, birim)
                
                varsayilan_kosul = "Çalışma Koşulu B"
                b_key = tr_upper(birim)
                if b_key in self.birim_kosul_map and self.birim_kosul_map[b_key] == "A":
                    varsayilan_kosul = "Çalışma Koşulu A"
                
                item_kosul = QTableWidgetItem(varsayilan_kosul)
                item_kosul.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable)
                self.tablo.setItem(row_idx, 3, item_kosul)
                
                # İŞ GÜNÜ HESAPLA (Kişiye ve Döneme Özel)
                kisi_ozel_is_gunu = is_gunu_hesapla(hesaplama_baslangic, kisi_bitis, self.tatil_listesi_np)
                self._set_item(row_idx, 4, str(kisi_ozel_is_gunu))
                
                # İZİN HESAPLA (Yine aynı tarih aralığında)
                izin_gunu = self.kesisim_izin_gunu_hesapla(kimlik, hesaplama_baslangic, kisi_bitis)
                self._set_item(row_idx, 5, str(izin_gunu))
                
                self._satir_hesapla(row_idx)
                
        except InternetBaglantiHatasi: show_error("Hata", "İnternet bağlantısı yok.", self)
        except Exception as e: show_error("Hesaplama Hatası", str(e), self)
        
        self.btn_hesapla.setEnabled(True); self.btn_hesapla.setText("⚡ LİSTELE VE HESAPLA")
        self.tablo.blockSignals(False)

    def _set_item(self, r, c, t):
        i = QTableWidgetItem(t); i.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled); self.tablo.setItem(r, c, i)

    def _hucre_degisti(self, item):
        if item.column() == 3: self._satir_hesapla(item.row())

    def _satir_hesapla(self, r):
        try:
            kosul = self.tablo.item(r, 3).text()
            is_gunu = int(self.tablo.item(r, 4).text()) 
            izin = int(self.tablo.item(r, 5).text())
            puan = 0
            if "KOŞULU A" in tr_upper(kosul):
                net = max(0, is_gunu - izin)
                puan = net * 7
            self.tablo.setItem(r, 6, QTableWidgetItem(str(puan)))
        except: pass

    def kaydet_baslat(self):
        if self.tablo.rowCount() == 0: return
        y = self.cmb_yil.currentText(); a = self.cmb_ay.currentText()
        self.btn_kaydet.setEnabled(False); self.lbl_durum.setText("Kontrol ediliyor...")
        self.progress.setVisible(True); self.progress.setRange(0,0)
        self.k_worker = PuantajKontrolWorker(y, a)
        self.k_worker.durum_sinyali.connect(self._on_kontrol)
        self.k_worker.hata_olustu.connect(self._on_hata)
        self.k_worker.start()

    def _on_kontrol(self, var, sayi):
        ow = False
        if var:
            if not show_question("Mükerrer", f"{sayi} kayıt var. Üzerine yazılsın mı?", self):
                self.btn_kaydet.setEnabled(True); self.progress.setVisible(False); return
            ow = True
        v = []
        for r in range(self.tablo.rowCount()):
            v.append([self.tablo.item(r,0).text(), self.tablo.item(r,1).text(), self.cmb_yil.currentText(), self.cmb_ay.currentText(), self.tablo.item(r,4).text(), self.tablo.item(r,5).text(), self.tablo.item(r,6).text()])
        self.t_worker = TamKayitWorker(v, self.cmb_yil.currentText(), self.cmb_ay.currentText(), ow)
        self.t_worker.log_sinyali.connect(self.lbl_durum.setText)
        self.t_worker.islem_bitti.connect(self._on_basari)
        self.t_worker.hata_olustu.connect(self._on_hata)
        self.t_worker.start()

    def _on_basari(self):
        self.btn_kaydet.setEnabled(True); self.progress.setVisible(False)
        show_info("Başarılı", "Kaydedildi.", self); self.lbl_durum.setText("Hazır")

    def _on_hata(self, m):
        self.btn_kaydet.setEnabled(True); self.progress.setVisible(False); show_error("Hata", m, self)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    try: TemaYonetimi.uygula_fusion_dark(app)
    except: pass
    w = FHSZHesaplamaPenceresi()
    w.show()
    sys.exit(app.exec())