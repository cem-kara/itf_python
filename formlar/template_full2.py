# -*- coding: utf-8 -*-
import sys
import os
from datetime import date

# Gerekli PySide6 Modülleri
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                               QTableWidget, QTableWidgetItem, QHeaderView, 
                               QLineEdit, QPushButton, QLabel, QComboBox, 
                               QDateEdit, QTextEdit, QProgressBar, QFrame, 
                               QGraphicsDropShadowEffect, QSplitter, QScrollArea, 
                               QGroupBox, QSizePolicy, QAbstractItemView)
from PySide6.QtCore import Qt, QDate, QSize
from PySide6.QtGui import QColor, QIcon, QFont

# --- YOL VE TEMA AYARLARI ---
# (Kendi proje yapınıza göre ayarlayın)
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

try:
    from temalar.tema import TemaYonetimi
    # from araclar.yetki_yonetimi import YetkiYoneticisi
except ImportError:
    class TemaYonetimi:
        @staticmethod
        def uygula_fusion_dark(app): app.setStyle("Fusion")

# =============================================================================
# 1. STANDART UI BİLEŞENLERİ (Bunu her forma kopyalayabilirsiniz veya
#    'bilesenler.py' gibi ortak bir dosyadan import edebilirsiniz)
# =============================================================================

class ModernInputGroup(QWidget):
    """
    Etiket ve Giriş Nesnesini dikey hizalar.
    Standart boşluk ayarları burada yapılır.
    """
    def __init__(self, label_text, widget, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        # (Sol, Üst, Sağ, Alt) - Alttan 10px boşluk bırakarak bir sonraki grupla mesafeyi korur
        layout.setContentsMargins(0, 0, 0, 5) 
        layout.setSpacing(5) # Etiket ile Input arasındaki mesafe
        
        self.lbl = QLabel(label_text)
        # Etiket Stili
        self.lbl.setStyleSheet("color: #b0b0b0; font-size: 11px; font-weight: bold; text-transform: uppercase;")
        
        self.widget = widget
        # Yükseklik ayarı TEMA dosyasından (CSS) gelir.
        # Sadece çok satırlı metin kutusu için özel yükseklik veririz.
        if isinstance(widget, QTextEdit):
            self.widget.setMinimumHeight(80)
        
        layout.addWidget(self.lbl)
        layout.addWidget(self.widget)

class InfoCard(QGroupBox):
    """
    Başlıklı ve gölgeli gruplama kutusu.
    QGroupBox kullanarak tema dosyasındaki stilleri otomatik alır.
    """
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        
        # Gölge Efekti
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)
        
        self.layout = QVBoxLayout(self)
        # Kartın içindeki kenar boşlukları
        self.layout.setContentsMargins(20, 25, 20, 20) 
        # Kart içindeki elemanlar arası mesafe
        self.layout.setSpacing(5) 

    def add_widget(self, widget):
        self.layout.addWidget(widget)

    def add_layout(self, layout):
        self.layout.addLayout(layout)

# =============================================================================
# 2. ANA ŞABLON PENCERESİ
# =============================================================================

class SablonPenceresi(QWidget):
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.setWindowTitle("Form Başlığı Buraya")
        self.resize(1300, 800)
        
        self.inputs = {} # Tüm inputları burada tutarız
        
        self.setup_ui()
        
        # YetkiYoneticisi.uygula(self, "form_kodu")
        # self.verileri_yukle() # Veritabanı işlemleri

    def setup_ui(self):
        # --- ANA DÜZEN ---
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15) # Pencere kenar boşlukları
        main_layout.setSpacing(10) # Sol ve Sağ panel arası boşluk
        
        # Ayırıcı (Splitter) - Panellerin boyutunu kullanıcı ayarlayabilir
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle { background-color: #3e3e3e; }")

        # ==========================================================
        # SOL PANEL: VERİ GİRİŞ FORMU
        # ==========================================================
        sol_widget = QWidget()
        sol_layout = QVBoxLayout(sol_widget)
        sol_layout.setContentsMargins(0, 0, 10, 0) # Sağdan biraz boşluk bırak
        
        # Scroll Area (Ekran küçükse form kaydırılabilsin)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        form_inner = QWidget()
        form_inner.setStyleSheet("background: transparent;")
        form_layout = QVBoxLayout(form_inner)
        form_layout.setSpacing(5) # Kartlar arası boşluk
        form_layout.setContentsMargins(5, 5, 5, 20)

        # --- KART 1: TEMEL BİLGİLER ---
        card_1 = InfoCard("Temel Bilgiler")
        
        # Input Ekleme (Helper fonksiyonu ile)
        self.add_input(card_1, "Adı Soyadı / Başlık", "Baslik", "text")
        
        # Yan Yana Inputlar
        row_1 = QHBoxLayout()
        row_1.setSpacing(10) # Yan yana elemanlar arası boşluk
        self.add_input_to_layout(row_1, "Kategori", "Kategori", "combo")
        self.inputs["Kategori"].addItems(["Seçenek 1", "Seçenek 2"])
        
        self.add_input_to_layout(row_1, "Tarih", "Tarih", "date")
        card_1.add_layout(row_1)
        
        form_layout.addWidget(card_1)

        # --- KART 2: DETAYLAR ---
        card_2 = InfoCard("Detaylı Bilgiler")
        
        # TextEdit (Açıklama)
        txt_aciklama = QTextEdit()
        txt_aciklama.setPlaceholderText("Detaylı açıklama giriniz...")
        self.add_custom_input(card_2, "Açıklama", txt_aciklama, "Aciklama")
        
        form_layout.addWidget(card_2)

        # Formu Scroll'a ekle
        scroll.setWidget(form_inner)
        sol_layout.addWidget(scroll)

        # --- SOL PANEL BUTONLARI ---
        # Progress Bar
        self.pbar = QProgressBar()
        self.pbar.setVisible(False)
        self.pbar.setFixedHeight(4)
        sol_layout.addWidget(self.pbar)
        
        btn_layout = QHBoxLayout()
        self.btn_temizle = QPushButton("Temizle / Yeni")
        self.btn_temizle.setObjectName("btn_standart") # Temada tanımlı değilse varsayılan olur
        self.btn_temizle.setCursor(Qt.PointingHandCursor)
        self.btn_temizle.setFixedHeight(45) # Standart buton yüksekliği
        
        self.btn_kaydet = QPushButton("KAYDET")
        self.btn_kaydet.setObjectName("btn_kaydet") # Temada yeşil/mavi tanımlı ID
        self.btn_kaydet.setCursor(Qt.PointingHandCursor)
        self.btn_kaydet.setFixedHeight(45)
        
        btn_layout.addWidget(self.btn_temizle)
        btn_layout.addWidget(self.btn_kaydet)
        sol_layout.addLayout(btn_layout)

        # ==========================================================
        # SAĞ PANEL: LİSTE VE FİLTRE
        # ==========================================================
        sag_widget = QWidget()
        sag_layout = QVBoxLayout(sag_widget)
        sag_layout.setContentsMargins(10, 0, 0, 0)
        sag_layout.setSpacing(10)
        
        # --- FİLTRE ALANI (GroupBox) ---
        grp_filtre = QGroupBox("Listeleme ve Filtre")
        grp_filtre.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        
        filter_layout = QHBoxLayout(grp_filtre)
        filter_layout.setContentsMargins(10, 20, 10, 10)
        filter_layout.setSpacing(10)
        
        self.cmb_filtre = QComboBox()
        self.cmb_filtre.addItems(["Tümü", "Aktif", "Pasif"])
        
        self.txt_ara = QLineEdit()
        self.txt_ara.setPlaceholderText("Ara...")
        
        btn_yenile = QPushButton("⟳")
        btn_yenile.setFixedSize(45, 45) # Kareye yakın buton
        
        filter_layout.addWidget(self.cmb_filtre)
        filter_layout.addWidget(self.txt_ara)
        filter_layout.addWidget(btn_yenile)
        
        sag_layout.addWidget(grp_filtre)
        
        # --- TABLO ---
        self.tablo = QTableWidget()
        self.tablo.setColumnCount(4)
        self.tablo.setHorizontalHeaderLabels(["ID", "Başlık", "Tarih", "Durum"])
        self.tablo.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tablo.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tablo.setAlternatingRowColors(True)
        # Tablo stili tema.py'dan gelir, buraya manuel yazmaya gerek yok
        
        sag_layout.addWidget(self.tablo)
        
        # Alt Bilgi Label
        self.lbl_bilgi = QLabel("Toplam: 0 Kayıt")
        self.lbl_bilgi.setAlignment(Qt.AlignRight)
        self.lbl_bilgi.setStyleSheet("color: #777; font-size: 11px;")
        sag_layout.addWidget(self.lbl_bilgi)

        # ==========================================================
        # SPLITTER BİRLEŞTİRME
        # ==========================================================
        splitter.addWidget(sol_widget)
        splitter.addWidget(sag_widget)
        # Varsayılan Genişlik Oranı: %35 Form - %65 Liste
        splitter.setStretchFactor(0, 35)
        splitter.setStretchFactor(1, 65)
        
        main_layout.addWidget(splitter)

    # =========================================================================
    # YARDIMCI METODLAR (Kod Tekrarını Önler)
    # =========================================================================
    
    def add_input(self, parent_card, label_text, key, tip="text"):
        """
        Karta standart bir input ekler ve self.inputs sözlüğüne kaydeder.
        """
        widget = None
        if tip == "text":
            widget = QLineEdit()
        elif tip == "combo":
            widget = QComboBox()
        elif tip == "date":
            widget = QDateEdit()
            widget.setCalendarPopup(True)
            widget.setDate(QDate.currentDate())
            widget.setDisplayFormat("dd.MM.yyyy")
            
        grp = ModernInputGroup(label_text, widget)
        parent_card.add_widget(grp)
        
        self.inputs[key] = widget
        return widget

    def add_input_to_layout(self, layout, label_text, key, tip="text"):
        """
        Mevcut bir QHBoxLayout içine input ekler (Yan yana dizilim için).
        """
        widget = None
        if tip == "text": widget = QLineEdit()
        elif tip == "combo": widget = QComboBox()
        elif tip == "date": 
            widget = QDateEdit(); widget.setCalendarPopup(True); widget.setDate(QDate.currentDate()); widget.setDisplayFormat("dd.MM.yyyy")
            
        grp = ModernInputGroup(label_text, widget)
        layout.addWidget(grp)
        self.inputs[key] = widget
        return widget

    def add_custom_input(self, parent_card, label_text, widget, key):
        """
        Özel oluşturulmuş bir widget'ı (örn: QTextEdit) ekler.
        """
        grp = ModernInputGroup(label_text, widget)
        parent_card.add_widget(grp)
        self.inputs[key] = widget

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Temayı Uygula
    try:
        TemaYonetimi.uygula_fusion_dark(app)
    except Exception as e:
        print(f"Tema uygulanamadı: {e}")
        app.setStyle("Fusion")
        
    win = SablonPenceresi()
    win.show()
    sys.exit(app.exec())