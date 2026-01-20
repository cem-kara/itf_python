# -*- coding: utf-8 -*-
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt

class TemaYonetimi:
    """
    Bu sınıf, uygulamanın 'Windows 11 Fusion Dark' temasını yönetir.
    Hem QPalette (temel renkler) hem de CSS (ince stil ayarları) kullanır.
    """
    
    @staticmethod
    def uygula_fusion_dark(app: QApplication):
        """
        Uygulamaya modern, koyu Fusion temasını uygular.
        
        Parametre:
        app (QApplication): Uygulama örneği.
        """
        # 1. Temel Stil Motoru: Fusion
        app.setStyle("Fusion")

        # 2. Renk Tanımları (Win11 Dark Palette)
        koyu_arka_plan = QColor(32, 32, 32)      # Ana zemin (#202020)
        panel_arka_plan = QColor(45, 45, 45)     # Kartlar/Paneller
        metin_rengi = QColor(240, 240, 240)      # Neredeyse beyaz
        pasif_metin = QColor(160, 160, 160)      # Gri metin
        vurgu_rengi = QColor(96, 205, 255)       # Win11 Accent Blue (Light)
        link_rengi = QColor(96, 205, 255)
        
        # 3. QPalette Oluşturma
        palet = QPalette()
        
        # Genel Zemin ve Metin
        palet.setColor(QPalette.Window, koyu_arka_plan)
        palet.setColor(QPalette.WindowText, metin_rengi)
        palet.setColor(QPalette.Base, QColor(25, 25, 25)) # Input zeminleri
        palet.setColor(QPalette.AlternateBase, panel_arka_plan)
        palet.setColor(QPalette.ToolTipBase, koyu_arka_plan)
        palet.setColor(QPalette.ToolTipText, metin_rengi)
        palet.setColor(QPalette.Text, metin_rengi)
        
        # Butonlar
        palet.setColor(QPalette.Button, panel_arka_plan)
        palet.setColor(QPalette.ButtonText, metin_rengi)
        
        # Link ve Vurgu
        palet.setColor(QPalette.Link, link_rengi)
        palet.setColor(QPalette.Highlight, QColor(0, 90, 158)) # Seçim arka planı (Daha koyu mavi)
        palet.setColor(QPalette.HighlightedText, Qt.white)
        
        # Pasif Durumlar
        palet.setColor(QPalette.Disabled, QPalette.Text, pasif_metin)
        palet.setColor(QPalette.Disabled, QPalette.ButtonText, pasif_metin)
        palet.setColor(QPalette.Disabled, QPalette.WindowText, pasif_metin)

        app.setPalette(palet)

        # 4. Kapsamlı CSS (Stylesheet)
        # Windows 11 stili yuvarlak köşeler, ince kenarlıklar ve hover efektleri
        css = """
        /* --- GENEL AYARLAR --- */
        QWidget {
            font-family: 'Segoe UI', sans-serif;
            font-size: 10pt;
            selection-background-color: #0078d4;
            selection-color: #ffffff;
        }
        QMainWindow, QMdiArea {
            background-color: #202020;
        }
        
        /* --- GRUPLAMA KUTULARI --- */
        QGroupBox {
            border: 1px solid #3e3e3e;
            border-radius: 6px;
            margin-top: 24px;
            background-color: #2b2b2b;
            font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 4px 8px;
            color: #d0d0d0;
        }

        /* --- INPUT ALANLARI (LineEdit, SpinBox, vb.) --- */
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QComboBox {
            background-color: #1e1e1e;
            border: 1px solid #3e3e3e;
            border-radius: 4px; /* Win11 stili hafif yuvarlak */
            padding: 4px;
            color: #ffffff;
            min-height: 22px;
        }
        QLineEdit:hover, QComboBox:hover, QSpinBox:hover {
            border: 1px solid #555555;
            background-color: #252525;
        }
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
            border: 1px solid #60cdff; /* Odaklanınca mavi border */
            background-color: #1a1a1a;
        }
        /* Read Only Durumu */
        QLineEdit[readOnly="true"] {
            background-color: #2d2d2d;
            color: #aaaaaa;
            border: 1px solid #333333;
        }

        /* --- BUTONLAR --- */
        QPushButton {
            background-color: #333333;
            border: 1px solid #3e3e3e;
            border-radius: 4px;
            padding: 6px 12px;
            color: #ffffff;
        }
        QPushButton:hover {
            background-color: #3e3e3e;
            border: 1px solid #555555;
        }
        QPushButton:pressed {
            background-color: #292929;
            border: 1px solid #3e3e3e;
            padding-top: 7px; /* Basılma hissi */
            padding-left: 13px;
        }
        QPushButton:disabled {
            background-color: #252525;
            color: #666666;
            border: 1px solid #2f2f2f;
        }
        
        /* Özel Aksiyon Butonları (İsimlendirilmiş ID'ler için) */
        QPushButton#btn_kaydet {
            background-color: #0067c0;
            border: 1px solid #005a9e;
        }
        QPushButton#btn_kaydet:hover {
            background-color: #187bcd;
        }
        QPushButton#btn_iptal {
            background-color: transparent;
            border: 1px solid #d13438;
            color: #d13438;
        }
        QPushButton#btn_iptal:hover {
            background-color: #d13438;
            color: #ffffff;
        }

        /* --- COMBOBOX ÖZEL --- */
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 20px;
            border-left-width: 0px;
            border-top-right-radius: 4px;
            border-bottom-right-radius: 4px;
        }
        QComboBox::down-arrow {
            image: none;
            border-left: 2px solid transparent;
            border-right: 2px solid transparent;
            border-top: 4px solid #aaaaaa; /* Basit ok çizimi */
            margin-right: 6px;
        }

        /* --- TABLOLAR (QTableWidget) --- */
        QTableWidget {
            background-color: #1e1e1e;
            border: 1px solid #333333;
            gridline-color: #333333;
            selection-background-color: #004578; /* Daha soft bir mavi */
            selection-color: white;
            alternate-background-color: #252525;
        }
        QHeaderView::section {
            background-color: #2d2d2d;
            color: #cccccc;
            padding: 4px;
            border: 1px solid #333333;
            font-weight: bold;
        }
        QTableCornerButton::section {
            background-color: #2d2d2d;
            border: 1px solid #333333;
        }

        /* --- MENÜLER --- */
        QMenuBar {
            background-color: #202020;
            color: #ffffff;
            border-bottom: 1px solid #333333;
        }
        QMenuBar::item {
            spacing: 3px; 
            padding: 6px 10px;
            background: transparent;
            border-radius: 4px;
        }
        QMenuBar::item:selected { 
            background-color: #333333;
        }
        QMenu {
            background-color: #2b2b2b;
            color: #ffffff;
            border: 1px solid #3e3e3e;
            border-radius: 6px;
            padding: 5px;
        }
        QMenu::item {
            padding: 6px 24px;
            border-radius: 4px;
        }
        QMenu::item:selected {
            background-color: #3e3e3e;
        }

        /* --- TABLAR (Sekmeler) --- */
        QTabWidget::pane { 
            border: 1px solid #3e3e3e;
            background-color: #2b2b2b;
            border-radius: 4px;
        }
        QTabBar::tab {
            background: #202020;
            border: 1px solid #3e3e3e;
            color: #aaaaaa;
            padding: 8px 16px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            margin-right: 2px;
        }
        QTabBar::tab:selected, QTabBar::tab:hover {
            background: #2b2b2b;
            color: #ffffff;
            border-bottom-color: #2b2b2b; /* Panelle bütünleşmesi için */
        }

        /* --- SCROLLBAR --- */
        QScrollBar:vertical {
            border: none;
            background: #202020;
            width: 10px;
            margin: 0px 0px 0px 0px;
            border-radius: 5px;
        }
        QScrollBar::handle:vertical {
            background: #4d4d4d;
            min-height: 20px;
            border-radius: 5px;
        }
        QScrollBar::handle:vertical:hover {
            background: #666666;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar:horizontal {
            border: none;
            background: #202020;
            height: 10px;
            margin: 0px 0px 0px 0px;
            border-radius: 5px;
        }
        QScrollBar::handle:horizontal {
            background: #4d4d4d;
            min-width: 20px;
            border-radius: 5px;
        }
        QScrollBar::handle:horizontal:hover {
            background: #666666;
        }

        /* --- MDI PENCERELERİ --- */
        QMdiSubWindow {
            background-color: #2b2b2b;
            border: 1px solid #3e3e3e;
            border-radius: 6px;
        }
        
        /* --- DİĞER --- */
        QProgressBar {
            border: 1px solid #3e3e3e;
            border-radius: 4px;
            text-align: center;
            background-color: #1e1e1e;
        }
        QProgressBar::chunk {
            background-color: #0067c0;
            border-radius: 3px;
        }
        QCheckBox, QRadioButton {
            spacing: 5px;
            color: #f0f0f0;
        }
        QCheckBox::indicator, QRadioButton::indicator {
            width: 16px;
            height: 16px;
        }
        QToolTip {
            background-color: #2b2b2b;
            color: #ffffff;
            border: 1px solid #555555;
            padding: 4px;
            border-radius: 4px;
        }
        """
        app.setStyleSheet(css)