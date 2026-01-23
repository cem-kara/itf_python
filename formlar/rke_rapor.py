# -*- coding: utf-8 -*-
import sys
import os
import logging
import datetime
from datetime import datetime as dt

# Gerekli widget'lar
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                               QTableWidget, QTableWidgetItem, QHeaderView, 
                               QLineEdit, QPushButton, QLabel, QMessageBox, 
                               QComboBox, QRadioButton, QButtonGroup, 
                               QFrame, QGraphicsDropShadowEffect, 
                               QAbstractItemView, QFileDialog, QSizePolicy, QSpacerItem) 

# Temel kütüphaneler
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QSize, QMarginsF
from PySide6.QtGui import QColor, QDesktopServices, QTextDocument, QPdfWriter, QPageSize, QPageLayout, QFont, QIcon, QCursor

# --- LOGLAMA ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RKERapor")

# --- BAĞLANTILAR ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from araclar.yetki_yonetimi import YetkiYoneticisi

# --- İMPORTLAR ---
try:
    from google_baglanti import veritabani_getir, GoogleDriveService
    from araclar.ortak_araclar import show_info, show_error, pencereyi_kapat
except ImportError:
    def veritabani_getir(vt_tipi, sayfa_adi): return None
    def show_info(t, m, p): print(m)
    def show_error(t, m, p): print(m)
    def pencereyi_kapat(w): w.close()
    class GoogleDriveService:
        def upload_file(self, a, b): return None

# RKE Dosyaları için Sabit Klasör ID
DRIVE_KLASOR_ID = "1KIYRhomNGppMZCXbqyngT2kH0X8c-GEK"

# =============================================================================
# 1. RAPOR ŞABLONLARI
# =============================================================================

def get_base_css():
    return """
        body { font-family: 'Times New Roman', serif; font-size: 11pt; color: #000; }
        h1 { text-align: center; font-size: 14pt; font-weight: bold; margin-bottom: 5px; }
        h2 { font-size: 12pt; font-weight: bold; margin-top: 15px; margin-bottom: 5px; text-decoration: underline; }
        .center { text-align: center; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 10pt; }
        th, td { border: 1px solid #000; padding: 4px; text-align: center; vertical-align: middle; }
        th { background-color: #f0f0f0; font-weight: bold; }
        .left-align { text-align: left; }
        .signature-table { width: 100%; border: none; margin-top: 40px; }
        .signature-table td { border: none; text-align: center; vertical-align: top; padding: 20px; }
        .line { border-top: 1px solid #000; width: 80%; margin: 30px auto 0; }
        .legal-text { text-align: justify; margin-top: 5px; margin-bottom: 5px; line-height: 1.4; }
    """

def html_genel_rapor(veriler, filtre_ozeti):
    tarih = datetime.datetime.now().strftime("%d.%m.%Y")
    html = f"""
    <html>
    <head><style>{get_base_css()}</style></head>
    <body>
        <h1>RADYASYON KORUYUCU EKİPMAN (RKE) KONTROL RAPORU</h1>
        <div class="center">Filtre: {filtre_ozeti} | Rapor Tarihi: {tarih}</div>
        <table>
            <thead>
                <tr>
                    <th width="15%">Koruyucu Cinsi</th>
                    <th width="15%">Koruyucu No</th>
                    <th width="10%">Pb (mm)</th>
                    <th width="20%">Fiziksel Kontrol<br>(Tarih - Sonuç)</th>
                    <th width="20%">Skopi Kontrol<br>(Tarih - Sonuç)</th>
                    <th width="20%">Açıklama</th>
                </tr>
            </thead>
            <tbody>
    """
    for row in veriler:
        fiz_text = f"{row['Tarih']}<br>{row['Fiziksel']}"
        sko_text = f"{row['Tarih']}<br>{row['Skopi']}"
        html += f"""
            <tr>
                <td>{row['Cins']}</td>
                <td>{row['EkipmanNo']}</td>
                <td>{row['Pb']}</td>
                <td>{fiz_text}</td>
                <td>{sko_text}</td>
                <td class="left-align">{row['Aciklama']}</td>
            </tr>
        """
    html += """
            </tbody>
        </table>
        <div style="margin-top: 10px; font-size: 9pt; font-style: italic;">
            * Bu form, tek bir oturumda yapılan toplu sayımlar ve kontroller için üretilmiştir.
        </div>
        <table class="signature-table">
            <tr>
                <td><b>Kontrol Eden</b><div class="line">İmza</div></td>
                <td><b>Birim Sorumlusu</b><div class="line">İmza</div></td>
                <td><b>Radyasyon Koruma Sorumlusu</b><div class="line">İmza</div></td>
            </tr>
        </table>
    </body>
    </html>
    """
    return html

def html_hurda_rapor(veriler, filtre_ozeti):
    tarih = datetime.datetime.now().strftime("%d.%m.%Y")
    html = f"""
    <html>
    <head><style>{get_base_css()}</style></head>
    <body>
        <h1>HURDA (HEK) EKİPMAN TEKNİK RAPORU</h1>
        <div class="center">Tarih: {tarih}</div>
        <h2>A. İMHA EDİLECEK EKİPMAN LİSTESİ</h2>
        <table>
            <thead>
                <tr>
                    <th width="5%">Sıra</th>
                    <th width="20%">Malzeme Adı (Cinsi)</th>
                    <th width="15%">Barkod / Demirbaş No</th>
                    <th width="15%">Bulunduğu Bölüm</th>
                    <th width="10%">Pb (mm)</th>
                    <th width="35%">Tespit Edilen Uygunsuzluk</th>
                </tr>
            </thead>
            <tbody>
    """
    for i, row in enumerate(veriler, 1):
        sorunlar = []
        if "Değil" in row['Fiziksel']: sorunlar.append(f"Fiziksel: {row['Fiziksel']}")
        if "Değil" in row['Skopi']: sorunlar.append(f"Skopi: {row['Skopi']}")
        if row['Aciklama']: sorunlar.append(row['Aciklama'])
        aciklama_full = " | ".join(sorunlar)
        html += f"""
            <tr>
                <td>{i}</td>
                <td>{row['Cins']}</td>
                <td>{row['EkipmanNo']}</td>
                <td>{row['Birim']}</td>
                <td>{row['Pb']}</td>
                <td class="left-align">{aciklama_full}</td>
            </tr>
        """
    html += """
            </tbody>
        </table>
        <h2>B. TEKNİK RAPOR VE TALEP</h2>
        <div class="legal-text">
            Yukarıdaki tabloda kimlik bilgileri belirtilen ekipmanların fiziksel veya radyolojik bütünlüklerini yitirdikleri tespit edilmiştir.
            Hizmet dışı bırakılarak (HEK) demirbaş kayıtlarından düşülmesi arz olunur.
        </div>
        <table class="signature-table">
            <tr>
                <td><b>Kontrol Eden</b><div class="line">İmza</div></td>
                <td><b>Birim Sorumlusu</b><div class="line">İmza</div></td>
                <td><b>RKS</b><div class="line">İmza</div></td>
            </tr>
        </table>
    </body>
    </html>
    """
    return html

def pdf_olustur(html_content, dosya_yolu):
    try:
        document = QTextDocument()
        document.setHtml(html_content)
        writer = QPdfWriter(dosya_yolu)
        writer.setPageSize(QPageSize(QPageSize.A4))
        writer.setResolution(300) 
        layout = QPageLayout()
        layout.setPageSize(QPageSize(QPageSize.A4))
        layout.setOrientation(QPageLayout.Portrait)
        layout.setMargins(QMarginsF(15, 15, 15, 15)) 
        writer.setPageLayout(layout)
        document.print_(writer)
        return True
    except Exception as e:
        print(f"PDF Hatası: {e}")
        return False

# =============================================================================
# 2. UI BİLEŞENLERİ (MODERN STİL)
# =============================================================================

class ModernInputGroup(QWidget):
    def __init__(self, label_text, widget, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 5)
        layout.setSpacing(5)
        
        self.lbl = QLabel(label_text)
        self.lbl.setStyleSheet("color: #cfcfcf; font-size: 11px; font-weight: 600; text-transform: uppercase;")
        
        self.widget = widget
        self.widget.setMinimumHeight(35)
        
        self.widget.setStyleSheet("""
            QLineEdit, QComboBox, QDateEdit { 
                border: 1px solid #454545; border-radius: 6px; padding: 0 10px; 
                background-color: #2d2d2d; color: white; font-size: 13px;
            }
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus { border: 1px solid #42a5f5; }
            QComboBox::drop-down { border: none; }
        """)
        
        layout.addWidget(self.lbl)
        layout.addWidget(self.widget)

class InfoCard(QFrame):
    def __init__(self, title, parent=None, color="#42a5f5"):
        super().__init__(parent)
        self.setStyleSheet("InfoCard { background-color: #1e1e1e; border: 1px solid #333; border-radius: 12px; }")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20); shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)
        
        self.layout = QVBoxLayout(self)
        # 🟢 GÜNCELLEME: İç boşluklar azaltıldı, daha kompakt görünüm
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.layout.setSpacing(10)
        
        if title:
            h_lay = QHBoxLayout()
            indicator = QFrame()
            indicator.setFixedSize(4, 18)
            indicator.setStyleSheet(f"background-color: {color}; border-radius: 2px;")
            lbl = QLabel(title)
            lbl.setStyleSheet(f"color: {color}; font-size: 15px; font-weight: bold;")
            h_lay.addWidget(indicator); h_lay.addWidget(lbl); h_lay.addStretch()
            self.layout.addLayout(h_lay)
            line = QFrame(); line.setFrameShape(QFrame.HLine)
            line.setStyleSheet("background-color: #333; margin-bottom: 5px;")
            self.layout.addWidget(line)

    def add_widget(self, w): self.layout.addWidget(w)
    
    def add_layout(self, l): self.layout.addLayout(l)

# =============================================================================
# 3. WORKER THREADS (VERİ VE İŞLEM)
# =============================================================================

class RaporVeriYukleyici(QThread):
    # Sinyal: List, Headers, ABD_List, Birim_List, Tarih_List
    veri_hazir = Signal(list, list, list, list, list) 
    hata_olustu = Signal(str)

    def run(self):
        try:
            envanter_map = {}
            abd_set = set()
            birim_set = set()
            tarih_set = set()
            
            # Envanter (RKE List)
            ws_list = veritabani_getir('rke', 'rke_list')
            if ws_list:
                all_data = ws_list.get_all_records()
                for row in all_data:
                    ekipman_no = str(row.get('EkipmanNo', '')).strip()
                    abd = str(row.get('AnaBilimDali', '')).strip()
                    birim = str(row.get('Birim', '')).strip()
                    cins = str(row.get('KoruyucuCinsi', '')).strip()
                    pb = str(row.get('KursunEsdegeri', '')).strip()
                    
                    if ekipman_no:
                        envanter_map[ekipman_no] = {'ABD': abd, 'Birim': birim, 'Cins': cins, 'Pb': pb}
                        if abd: abd_set.add(abd)
                        if birim: birim_set.add(birim)

            # Muayene
            birlesik_veri = []
            ws_muayene = veritabani_getir('rke', 'rke_muayene')
            if ws_muayene:
                raw_muayene = ws_muayene.get_all_records()
                for row in raw_muayene:
                    ekipman_no = str(row.get('EkipmanNo', '')).strip()
                    tarih = str(row.get('F_MuayeneTarihi', '')).strip()
                    fiz = str(row.get('FizikselDurum', '')).strip()
                    sko = str(row.get('SkopiDurum', '')).strip()
                    
                    if tarih: tarih_set.add(tarih)

                    item = {
                        'EkipmanNo': ekipman_no,
                        'Tarih': tarih,
                        'Fiziksel': fiz,
                        'Skopi': sko,
                        'KontrolEden': str(row.get('KontrolEden', '')).strip(),
                        'Aciklama': str(row.get('Aciklamalar', '')).strip(),
                        'Sonuc': "Kullanıma Uygun"
                    }
                    
                    if "Değil" in item['Fiziksel'] or "Değil" in item['Skopi']:
                        item['Sonuc'] = "Kullanıma Uygun Değil"
                        
                    info = envanter_map.get(ekipman_no, {'ABD': '-', 'Birim': '-', 'Cins': '-', 'Pb': '-'})
                    item.update(info)
                    birlesik_veri.append(item)

            headers = ["Ekipman No", "Cins", "Pb", "Birim", "Tarih", "Fiziksel", "Skopi", "Sonuç"]
            # Tarihleri sırala
            sirali_tarih = sorted(list(tarih_set), reverse=True)
            
            self.veri_hazir.emit(birlesik_veri, headers, sorted(list(abd_set)), sorted(list(birim_set)), sirali_tarih)

        except Exception as e:
            self.hata_olustu.emit(str(e))

class RaporOlusturucuWorker(QThread):
    log_mesaji = Signal(str)
    islem_bitti = Signal()
    
    def __init__(self, mod, veriler, filtreler):
        super().__init__()
        self.mod = mod # 1: Genel, 2: Hurda, 3: Kişi
        self.veriler = veriler
        self.filtreler = filtreler

    def run(self):
        drive = GoogleDriveService()
        temp_files = []
        try:
            ozet = self.filtreler.get('ozet', '')
            
            if self.mod == 1: # Genel
                dosya_adi = f"RKE_Genel_{datetime.datetime.now().strftime('%Y%m%d')}.pdf"
                if not self.veriler:
                    self.log_mesaji.emit("⚠️ Veri yok.")
                    return
                html = html_genel_rapor(self.veriler, ozet)
                if pdf_olustur(html, dosya_adi):
                    temp_files.append(dosya_adi)
                    self.log_mesaji.emit(f"Yükleniyor: {dosya_adi}")
                    link = drive.upload_file(dosya_adi, DRIVE_KLASOR_ID)
                    self.log_mesaji.emit(f"✅ Drive'a Yüklendi. Link panoya kopyalanabilir.")
                else:
                    self.log_mesaji.emit("❌ PDF oluşturulamadı.")

            elif self.mod == 2: # Hurda
                dosya_adi = f"RKE_Hurda_{datetime.datetime.now().strftime('%Y%m%d')}.pdf"
                hurda_veri = [v for v in self.veriler if "Değil" in v['Sonuc']]
                if not hurda_veri:
                    self.log_mesaji.emit("⚠️ Hurda kaydı bulunamadı.")
                    return
                html = html_hurda_rapor(hurda_veri, ozet)
                if pdf_olustur(html, dosya_adi):
                    temp_files.append(dosya_adi)
                    drive.upload_file(dosya_adi, DRIVE_KLASOR_ID)
                    self.log_mesaji.emit(f"✅ Hurda Raporu Yüklendi.")

            elif self.mod == 3: # Kişi Bazlı
                gruplar = {}
                for item in self.veriler:
                    key = (item['KontrolEden'], item['Tarih'])
                    if key not in gruplar: gruplar[key] = []
                    gruplar[key].append(item)
                
                self.log_mesaji.emit(f"{len(gruplar)} farklı rapor hazırlanıyor...")
                
                for (kisi, tarih), liste in gruplar.items():
                    dosya_adi = f"Rapor_{kisi}_{tarih}.pdf".replace(" ", "_")
                    html = html_genel_rapor(liste, f"Kontrolör: {kisi} - {tarih}")
                    if pdf_olustur(html, dosya_adi):
                        temp_files.append(dosya_adi)
                        drive.upload_file(dosya_adi, DRIVE_KLASOR_ID)
                        self.log_mesaji.emit(f"✅ {dosya_adi} yüklendi.")

        except Exception as e:
            self.log_mesaji.emit(f"❌ HATA: {e}")
        finally:
            for f in temp_files: 
                if os.path.exists(f): os.remove(f)
            self.islem_bitti.emit()

# =============================================================================
# 4. ANA PENCERE (YENİ DÜZENLİ TASARIM)
# =============================================================================

class RKERaporPenceresi(QWidget):
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.setWindowTitle("RKE Raporlama ve Analiz")
        self.resize(1250, 800)
        self.setStyleSheet("background-color: #121212; color: #e0e0e0; font-family: 'Segoe UI';")
        
        self.ham_veriler = []
        self.filtrelenmis_veri = []
        
        self.setup_ui()
        YetkiYoneticisi.uygula(self, "rke_rapor")
        self.verileri_cek()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        
        # --- BAŞLIK ---
        lbl_baslik = QLabel("RKE Raporlama Merkezi")
        lbl_baslik.setStyleSheet("color: #42a5f5; font-size: 22px; font-weight: bold; margin-bottom: 5px;")
        main_layout.addWidget(lbl_baslik)

        # --- KONTROL PANELI (INFOCARD) ---
        control_panel = InfoCard("Rapor Ayarları ve Filtreler", color="#ab47bc")
        
        # 🟢 GÜNCELLEME: Boyut Politikası SABİT yapıldı. Panel sadece gerektiği kadar yüksek olacak.
        control_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        # Panel İçeriği (Yatay Düzen: Radyo | Combo | Butonlar)
        h_panel = QHBoxLayout()
        h_panel.setContentsMargins(0, 5, 0, 5)
        h_panel.setSpacing(25)

        # ================= SOL TARAFT: RAPOR TÜRÜ (RADYO BUTONLAR) =================
        v_left = QVBoxLayout()
        v_left.setSpacing(10)
        
        lbl_tur = QLabel("RAPOR TÜRÜ")
        lbl_tur.setStyleSheet("color: #777; font-size: 11px; font-weight: bold; letter-spacing: 1px;")
        v_left.addWidget(lbl_tur)

        radio_style = """
            QRadioButton { color: #ccc; font-size: 13px; padding: 4px; }
            QRadioButton::indicator { width: 16px; height: 16px; border-radius: 9px; border: 2px solid #555; background: #222; }
            QRadioButton::indicator:checked { background-color: #ab47bc; border-color: #ab47bc; border-image: none; }
            QRadioButton::indicator:hover { border-color: #888; }
            QRadioButton:hover { color: white; }
        """
        self.rb_genel = QRadioButton("A. Kontrol Raporu (Genel)"); self.rb_genel.setChecked(True); self.rb_genel.setStyleSheet(radio_style)
        self.rb_hurda = QRadioButton("B. Hurda (HEK) Raporu"); self.rb_hurda.setStyleSheet(radio_style)
        self.rb_kisi = QRadioButton("C. Personel Bazlı Raporlar"); self.rb_kisi.setStyleSheet(radio_style)
        
        self.bg = QButtonGroup(self)
        self.bg.addButton(self.rb_genel); self.bg.addButton(self.rb_hurda); self.bg.addButton(self.rb_kisi)
        self.bg.buttonClicked.connect(self.filtrele)
        
        v_left.addWidget(self.rb_genel)
        v_left.addWidget(self.rb_hurda)
        v_left.addWidget(self.rb_kisi)
        v_left.addStretch() 

        h_panel.addLayout(v_left)

        # ================= ORTA: DİKEY AYRAÇ =================
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setStyleSheet("background-color: #333; width: 1px;")
        h_panel.addWidget(line)

        # ================= SAĞ TARAF: FİLTRELER VE BUTONLAR =================
        # Sağ tarafı Dikey bir layout'a alıyoruz (Üstte Filtreler, Altta Butonlar)
        v_right_container = QVBoxLayout()
        v_right_container.setSpacing(15)

        # 1. Satır: Filtreler (Yan Yana)
        h_filters = QHBoxLayout()
        h_filters.setSpacing(15)
        
        self.cmb_abd = QComboBox(); self.cmb_abd.addItem("Tüm Bölümler"); self.cmb_abd.setMinimumWidth(180)
        self.cmb_birim = QComboBox(); self.cmb_birim.addItem("Tüm Birimler"); self.cmb_birim.setMinimumWidth(180)
        self.cmb_tarih = QComboBox(); self.cmb_tarih.addItem("Tüm Tarihler"); self.cmb_tarih.setMinimumWidth(180)
        
        # Bağlantılar
        self.cmb_abd.currentIndexChanged.connect(self.abd_birim_degisti)
        self.cmb_birim.currentIndexChanged.connect(self.abd_birim_degisti)
        self.cmb_tarih.currentIndexChanged.connect(self.filtrele)

        h_filters.addWidget(ModernInputGroup("Ana Bilim Dalı", self.cmb_abd))
        h_filters.addWidget(ModernInputGroup("Birim", self.cmb_birim))
        h_filters.addWidget(ModernInputGroup("İşlem Tarihi", self.cmb_tarih))
        
        v_right_container.addLayout(h_filters)

        # 2. Satır: Butonlar (Yan Yana ve Geniş)
        h_buttons = QHBoxLayout()
        h_buttons.setSpacing(20)
        
        self.btn_yenile = QPushButton("⟳ VERİLERİ YENİLE")
        self.btn_yenile.setCursor(Qt.PointingHandCursor)
        self.btn_yenile.setFixedHeight(45)
        self.btn_yenile.setStyleSheet("""
            QPushButton { 
                background-color: #333; color: #ccc; border: 1px solid #444; border-radius: 6px; 
                font-weight: bold; font-size: 14px; letter-spacing: 1px;
            }
            QPushButton:hover { background-color: #444; color: white; border-color: #666; }
        """)
        self.btn_yenile.clicked.connect(self.verileri_cek)
        
        self.btn_olustur = QPushButton("📄 PDF RAPOR OLUŞTUR")
        self.btn_olustur.setObjectName("btn_kaydet") # Yetki için
        self.btn_olustur.setCursor(Qt.PointingHandCursor)
        self.btn_olustur.setFixedHeight(45)
        self.btn_olustur.setStyleSheet("""
            QPushButton { 
                background-color: #d32f2f; color: white; font-weight: bold; font-size: 14px; 
                border-radius: 6px; border: none; letter-spacing: 1px;
            }
            QPushButton:hover { background-color: #b71c1c; }
            QPushButton:disabled { background-color: #333; color: #555; }
        """)
        self.btn_olustur.clicked.connect(self.rapor_baslat)
        
        h_buttons.addWidget(self.btn_yenile)
        h_buttons.addWidget(self.btn_olustur)
        
        v_right_container.addLayout(h_buttons)
        v_right_container.addStretch() 

        h_panel.addLayout(v_right_container)
        
        control_panel.add_layout(h_panel)
        main_layout.addWidget(control_panel)

        # --- TABLO ---
        self.tablo = QTableWidget()
        self.tablo.setColumnCount(7)
        self.tablo.setHorizontalHeaderLabels(["Ekipman No", "Cins", "Pb", "Birim", "Tarih", "Sonuç", "Açıklama"])
        self.tablo.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tablo.setAlternatingRowColors(True)
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tablo.setStyleSheet("""
            QTableWidget { background-color: #1e1e1e; gridline-color: #333; border: 1px solid #333; border-radius: 8px; }
            QHeaderView::section { background-color: #2d2d2d; color: #ccc; padding: 8px; border: none; font-weight: bold; }
            QTableWidget::item { padding: 5px; }
        """)
        main_layout.addWidget(self.tablo)

        # 🟢 GÜNCELLEME: Alt log/progress bar tamamen kaldırıldı.
        
    # --- MANTIK ---
    def log(self, msg):
        # Log bar olmadığı için kritik bilgileri konsola veya durum çubuğuna (yok) yazarız.
        # Hata varsa Pop-up ile gösteririz.
        if "HATA" in msg:
            show_error("Hata", msg, self)
        print(f"LOG: {msg}")

    def tarih_cevir(self, tarih_str):
        if not tarih_str: return None
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
            try: return datetime.datetime.strptime(tarih_str, fmt).date()
            except: continue
        return None

    def verileri_cek(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.btn_olustur.setEnabled(False)
        self.btn_yenile.setText("Yükleniyor...")
        
        self.loader = RaporVeriYukleyici()
        self.loader.veri_hazir.connect(self.veriler_geldi)
        self.loader.hata_olustu.connect(lambda e: self.log(f"HATA: {e}"))
        self.loader.start()

    def veriler_geldi(self, data, headers, abd_l, birim_l, tarih_l):
        QApplication.restoreOverrideCursor()
        self.btn_olustur.setEnabled(True)
        self.btn_yenile.setText("⟳ VERİLERİ YENİLE")
        self.ham_veriler = data
        
        # Combo Doldur (Sinyalleri kapatarak)
        for cmb, liste in [(self.cmb_abd, abd_l), (self.cmb_birim, birim_l), (self.cmb_tarih, tarih_l)]:
            cmb.blockSignals(True)
            curr = cmb.currentText()
            cmb.clear(); cmb.addItem(f"Tüm {cmb.objectName()}" if "Tarih" not in str(liste) else "Tümü")
            cmb.addItems(liste)
            # Eski seçimi korumaya çalış
            idx = cmb.findText(curr)
            if idx >= 0: cmb.setCurrentIndex(idx)
            else: cmb.setCurrentIndex(0)
            cmb.blockSignals(False)
            
        self.abd_birim_degisti()

    def abd_birim_degisti(self):
        f_abd = self.cmb_abd.currentText()
        f_birim = self.cmb_birim.currentText()
        
        mevcut_tarihler = set()
        for row in self.ham_veriler:
            if "Tüm" not in f_abd and row['ABD'] != f_abd: continue
            if "Tüm" not in f_birim and row['Birim'] != f_birim: continue
            if row['Tarih']: mevcut_tarihler.add(row['Tarih'])
        
        sirali = sorted(list(mevcut_tarihler), reverse=True, key=lambda x: self.tarih_cevir(x) or datetime.date.min)
        
        self.cmb_tarih.blockSignals(True)
        self.cmb_tarih.clear(); self.cmb_tarih.addItem("Tümü"); self.cmb_tarih.addItems(sirali)
        self.cmb_tarih.blockSignals(False)
        
        self.filtrele()

    def filtrele(self):
        f_abd = self.cmb_abd.currentText()
        f_birim = self.cmb_birim.currentText()
        f_tarih = self.cmb_tarih.currentText()
        
        filtrelenmis = []
        for row in self.ham_veriler:
            # 1. Combo Filtreleri
            if "Tüm" not in f_abd and row['ABD'] != f_abd: continue
            if "Tüm" not in f_birim and row['Birim'] != f_birim: continue
            if "Tüm" not in f_tarih and row['Tarih'] != f_tarih: continue
            
            # 2. Radyo Filtreleri
            if self.rb_hurda.isChecked():
                if "Değil" not in row['Sonuc']: continue # Sadece uygunsuzlar hurda adayıdır
            
            filtrelenmis.append(row)
            
        self.filtrelenmis_veri = filtrelenmis
        self.tabloyu_doldur(filtrelenmis)

    def tabloyu_doldur(self, data):
        self.tablo.setRowCount(0)
        for i, row in enumerate(data):
            self.tablo.insertRow(i)
            self.tablo.setItem(i, 0, QTableWidgetItem(row['EkipmanNo']))
            self.tablo.setItem(i, 1, QTableWidgetItem(row['Cins']))
            self.tablo.setItem(i, 2, QTableWidgetItem(row['Pb']))
            self.tablo.setItem(i, 3, QTableWidgetItem(row['Birim']))
            self.tablo.setItem(i, 4, QTableWidgetItem(row['Tarih']))
            
            item_sonuc = QTableWidgetItem(row['Sonuc'])
            if "Değil" in row['Sonuc']: item_sonuc.setForeground(QColor("#ef5350"))
            else: item_sonuc.setForeground(QColor("#66bb6a"))
            self.tablo.setItem(i, 5, item_sonuc)
            
            self.tablo.setItem(i, 6, QTableWidgetItem(row['Aciklama']))

    def rapor_baslat(self):
        if not self.filtrelenmis_veri:
            show_info("Uyarı", "Listede veri yok.", self)
            return
            
        mod = 1
        if self.rb_hurda.isChecked(): mod = 2
        elif self.rb_kisi.isChecked(): mod = 3
        
        ozet = f"{self.cmb_abd.currentText()} - {self.cmb_birim.currentText()}"
        filtreler = {"ozet": ozet}
        
        self.btn_olustur.setEnabled(False)
        self.btn_olustur.setText("İşleniyor...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        
        self.worker = RaporOlusturucuWorker(mod, self.filtrelenmis_veri, filtreler)
        self.worker.log_mesaji.connect(self.log)
        self.worker.islem_bitti.connect(self.islem_tamam)
        self.worker.start()

    def islem_tamam(self):
        QApplication.restoreOverrideCursor()
        self.btn_olustur.setEnabled(True)
        self.btn_olustur.setText("📄 PDF RAPOR OLUŞTUR")
        show_info("Tamamlandı", "Rapor işlemleri tamamlandı. PDF oluşturulduysa Drive'a yüklenmiştir.", self)

    def closeEvent(self, event):
        if hasattr(self, 'loader') and self.loader.isRunning():
            self.loader.quit()
            self.loader.wait(500)
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(500)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    from temalar.tema import TemaYonetimi
    TemaYonetimi.uygula_fusion_dark(app)
    win = RKERaporPenceresi()
    win.show()
    sys.exit(app.exec())