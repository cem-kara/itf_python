# -*- coding: utf-8 -*-
import logging
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt
logger = logging.getLogger("TemaYonetimi")


class TemaYonetimi:
    """
    Windows 11 Fusion Dark temasını yöneten sınıf.
    Modern, tutarlı ve erişilebilir bir arayüz sağlar.
    """
    
    # Tema Renk Paleti (Win11 Design System)
    RENKLER = {
        'arka_plan': '#1c1c1c',           # Ana zemin
        'panel': '#2d2d2d',               # Kartlar/Paneller
        'panel_hover': '#343434',         # Hover durumu
        'input_bg': '#1e1e1e',            # Input arka planları
        'input_border': '#3e3e3e',        # Varsayılan kenarlık
        'input_border_hover': '#5a5a5a',  # Hover kenarlık
        'input_border_focus': '#60cdff',  # Odaklanma (Win11 Accent)
        
        'metin': '#f0f0f0',               # Ana metin
        'metin_pasif': '#a0a0a0',         # Devre dışı metin
        'metin_ikincil': '#c0c0c0',       # İkincil metin
        
        'vurgu': '#60cdff',               # Win11 Accent (Light Blue)
        'vurgu_koyu': '#0078d4',          # Accent koyu ton
        'vurgu_hover': '#5cb8e6',         # Accent hover
        'secim_bg': '#0067c0',            # Seçim arka planı
        
        'basari': '#0f7b0f',              # Yeşil aksiyon
        'basari_hover': '#13a10e',
        'hata': '#c42b1c',                # Kırmızı aksiyon
        'hata_hover': '#e81123',
        
        'kenarlık': '#3e3e3e',            # Genel kenarlıklar
        'kenarlık_acik': '#4d4d4d',       # Açık kenarlık
        'ayirici': '#333333',             # Bölücü çizgiler

        # --- TOAST BİLDİRİM RENKLERİ (Yeni Standart) ---
        'toast_bilgi': '#323232',
        'toast_basari': '#2D8A2D',
        'toast_hata': '#D32F2F',
        'toast_metin': '#ffffff'
    }
    
    
    @staticmethod
    def uygula_fusion_dark(app: QApplication):
        """Uygulamaya Windows 11 Fusion Dark temasını güvenli şekilde uygular."""
        try:
            app.setStyle("Fusion")
            TemaYonetimi._palette_ayarla(app)
            app.setStyleSheet(TemaYonetimi._css_olustur())
            logger.info("Win11 Dark Teması başarıyla uygulandı.")
        except Exception as e:
            logger.error(f"Tema uygulanırken hata: {e}")
    
    @staticmethod
    def _palette_ayarla(app: QApplication):
        """QPalette renklerini ayarlar."""
        r = TemaYonetimi.RENKLER
        palet = QPalette()
        
        palet.setColor(QPalette.Window, QColor(r['arka_plan']))
        palet.setColor(QPalette.WindowText, QColor(r['metin']))
        palet.setColor(QPalette.Base, QColor(r['input_bg']))
        palet.setColor(QPalette.AlternateBase, QColor(r['panel']))
        palet.setColor(QPalette.ToolTipBase, QColor(r['panel']))
        palet.setColor(QPalette.ToolTipText, QColor(r['metin']))
        palet.setColor(QPalette.Text, QColor(r['metin']))
        palet.setColor(QPalette.Button, QColor(r['panel']))
        palet.setColor(QPalette.ButtonText, QColor(r['metin']))
        palet.setColor(QPalette.Link, QColor(r['vurgu']))
        palet.setColor(QPalette.LinkVisited, QColor(r['vurgu_koyu']))
        palet.setColor(QPalette.Highlight, QColor(r['secim_bg']))
        palet.setColor(QPalette.HighlightedText, QColor('#ffffff'))
        
        palet.setColor(QPalette.Disabled, QPalette.Text, QColor(r['metin_pasif']))
        palet.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(r['metin_pasif']))
        palet.setColor(QPalette.Disabled, QPalette.WindowText, QColor(r['metin_pasif']))
        
        app.setPalette(palet)
    
    @staticmethod
    def _css_olustur() -> str:
        """Kapsamlı CSS stilleri oluşturur."""
        r = TemaYonetimi.RENKLER
        
        return f"""
        /* ==================== GENEL AYARLAR ==================== */
        QWidget {{
            font-family: 'Segoe UI Variable', 'Segoe UI', sans-serif;
            font-size: 10pt;
            selection-background-color: {r['secim_bg']};
            selection-color: #ffffff;
        }}
        
        /* Toast Bildirim Widget Stili (ZORUNLU EKLEME) */
        ToastWidget {{
            background-color: {r['toast_bilgi']};
            border: 1px solid {r['input_border']};
            border-radius: 10px;
        }}

        QMainWindow, QDialog, QMdiArea {{
            background-color: {r['arka_plan']};
        }}
        
        /* ==================== GRUPLAMA KUTULARI ==================== */
        QGroupBox {{
            border: 1px solid {r['kenarlık']};
            border-radius: 8px;
            margin-top: 16px;
            padding-top: 12px;
            background-color: {r['panel']};
            font-weight: 600;
        }}
        
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 4px 12px;
            color: {r['metin_ikincil']};
            background-color: transparent;
        }}
        
        /* ==================== INPUT ALANLARI ==================== */
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, 
        QDateEdit, QTimeEdit, QDateTimeEdit {{
            background-color: {r['input_bg']};
            border: 1px solid {r['input_border']};
            border-radius: 4px;
            padding: 6px 8px;
            color: {r['metin']};
            min-height: 18px;
        }}
        
        QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover,
        QSpinBox:hover, QDoubleSpinBox:hover {{
            border: 1px solid {r['input_border_hover']};
            background-color: #242424;
        }}
        
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
        QSpinBox:focus, QDoubleSpinBox:focus {{
            border: 2px solid {r['input_border_focus']};
            background-color: {r['input_bg']};
            padding: 5px 7px;
        }}
        
        QLineEdit[readOnly="true"], QTextEdit[readOnly="true"] {{
            background-color: #282828;
            color: {r['metin_pasif']};
            border: 1px solid #353535;
        }}
        
        /* ==================== COMBOBOX ==================== */
        QComboBox {{
            background-color: {r['input_bg']};
            border: 1px solid {r['input_border']};
            border-radius: 4px;
            padding: 6px 8px;
            color: {r['metin']};
            min-height: 18px;
            padding-right: 28px;
        }}
        
        QComboBox:hover {{
            border: 1px solid {r['input_border_hover']};
            background-color: #242424;
        }}
        
        QComboBox:focus {{
            border: 2px solid {r['input_border_focus']};
            padding: 5px 7px;
        }}
        
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: center right;
            width: 24px;
            border: none;
            border-top-right-radius: 4px;
            border-bottom-right-radius: 4px;
        }}
        
        QComboBox::drop-down:hover {{
            background-color: {r['panel_hover']};
        }}
        
        QComboBox::down-arrow {{
            image: none;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 5px solid {r['metin_ikincil']};
            width: 0px;
            height: 0px;
            margin-right: 8px;
        }}
        
        QComboBox QAbstractItemView {{
            background-color: {r['panel']};
            border: 1px solid {r['kenarlık_acik']};
            border-radius: 8px;
            padding: 4px;
            selection-background-color: {r['secim_bg']};
            selection-color: #ffffff;
            outline: none;
        }}
        
        QComboBox QAbstractItemView::item {{
            min-height: 18px;
            padding: 4px 8px;
            border-radius: 4px;
        }}
        
        QComboBox QAbstractItemView::item:hover {{
            background-color: {r['panel_hover']};
        }}
        
        /* ==================== BUTONLAR ==================== */
        QPushButton {{
            background-color: {r['panel']};
            border: 1px solid {r['kenarlık']};
            border-radius: 4px;
            padding: 7px 16px;
            color: {r['metin']};
            font-weight: 500;
            min-height: 18px;
        }}
        
        QPushButton:hover {{
            background-color: {r['panel_hover']};
            border: 1px solid {r['kenarlık_acik']};
        }}
        
        QPushButton:pressed {{
            background-color: #252525;
            border: 1px solid {r['kenarlık']};
        }}
        
        QPushButton:disabled {{
            background-color: #222222;
            color: {r['metin_pasif']};
            border: 1px solid #2a2a2a;
        }}
        
        /* Özel Buton Stilleri */
        QPushButton#btn_kaydet, QPushButton[isim="kaydet"] {{
            background-color: {r['vurgu_koyu']};
            border: 1px solid {r['vurgu_koyu']};
            color: #ffffff;
        }}
        
        QPushButton#btn_kaydet:hover, QPushButton[isim="kaydet"]:hover {{
            background-color: {r['vurgu_hover']};
            border: 1px solid {r['vurgu_hover']};
        }}
        
        QPushButton#btn_kaydet:pressed, QPushButton[isim="kaydet"]:pressed {{
            background-color: #0067c0;
        }}
        
        QPushButton#btn_iptal, QPushButton[isim="iptal"] {{
            background-color: transparent;
            border: 1px solid {r['hata']};
            color: {r['hata']};
        }}
        
        QPushButton#btn_iptal:hover, QPushButton[isim="iptal"]:hover {{
            background-color: {r['hata']};
            border: 1px solid {r['hata']};
            color: #ffffff;
        }}
        
        QPushButton#btn_sil, QPushButton[isim="sil"] {{
            background-color: {r['hata']};
            border: 1px solid {r['hata']};
            color: #ffffff;
        }}
        
        QPushButton#btn_sil:hover, QPushButton[isim="sil"]:hover {{
            background-color: {r['hata_hover']};
        }}
        
        /* ==================== TABLOLAR ==================== */
        QTableWidget, QTableView {{
            background-color: {r['input_bg']};
            border: 1px solid {r['kenarlık']};
            border-radius: 8px;
            gridline-color: {r['ayirici']};
            selection-background-color: {r['secim_bg']};
            selection-color: #ffffff;
            alternate-background-color: #232323;
        }}
        
        QTableWidget::item, QTableView::item {{
            padding: 4px;
            border: none;
        }}
        
        QTableWidget::item:hover, QTableView::item:hover {{
            background-color: #252525;
        }}
        
        QHeaderView::section {{
            background-color: {r['panel']};
            color: {r['metin_ikincil']};
            padding: 8px 4px;
            border: none;
            border-right: 1px solid {r['ayirici']};
            border-bottom: 1px solid {r['ayirici']};
            font-weight: 600;
        }}
        
        QHeaderView::section:first {{
            border-top-left-radius: 8px;
        }}
        
        QHeaderView::section:last {{
            border-right: none;
            border-top-right-radius: 8px;
        }}
        
        QHeaderView::section:hover {{
            background-color: {r['panel_hover']};
        }}
        
        QTableCornerButton::section {{
            background-color: {r['panel']};
            border: none;
            border-right: 1px solid {r['ayirici']};
            border-bottom: 1px solid {r['ayirici']};
            border-top-left-radius: 8px;
        }}
        
        /* ==================== MENÜLER ==================== */
        QMenuBar {{
            background-color: {r['arka_plan']};
            color: {r['metin']};
            border-bottom: 1px solid {r['kenarlık']};
            spacing: 2px;
        }}
        
        QMenuBar::item {{
            padding: 6px 12px;
            background: transparent;
            border-radius: 4px;
        }}
        
        QMenuBar::item:selected {{
            background-color: {r['panel']};
        }}
        
        QMenuBar::item:pressed {{
            background-color: {r['panel_hover']};
        }}
        
        QMenu {{
            background-color: {r['panel']};
            color: {r['metin']};
            border: 1px solid {r['kenarlık_acik']};
            border-radius: 8px;
            padding: 6px;
        }}
        
        QMenu::item {{
            padding: 6px 24px 6px 12px;
            border-radius: 4px;
            min-width: 120px;
        }}
        
        QMenu::item:selected {{
            background-color: {r['panel_hover']};
        }}
        
        QMenu::separator {{
            height: 1px;
            background: {r['ayirici']};
            margin: 4px 8px;
        }}
        
        QMenu::indicator {{
            width: 16px;
            height: 16px;
        }}
        
        /* ==================== SEKMELER (TABS) ==================== */
        QTabWidget::pane {{
            border: 1px solid {r['kenarlık']};
            background-color: {r['panel']};
            border-radius: 8px;
            top: -1px;
        }}
        
        QTabBar::tab {{
            background: transparent;
            border: 1px solid transparent;
            color: {r['metin_ikincil']};
            padding: 8px 20px;
            margin-right: 4px;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
        }}
        
        QTabBar::tab:hover {{
            background: {r['panel']};
            color: {r['metin']};
        }}
        
        QTabBar::tab:selected {{
            background: {r['panel']};
            color: {r['metin']};
            border: 1px solid {r['kenarlık']};
            border-bottom-color: {r['panel']};
            font-weight: 600;
        }}
        
        /* ==================== SCROLLBAR ==================== */
        QScrollBar:vertical {{
            background: transparent;
            width: 12px;
            margin: 0;
        }}
        
        QScrollBar::handle:vertical {{
            background: #4a4a4a;
            min-height: 30px;
            border-radius: 6px;
            margin: 2px;
        }}
        
        QScrollBar::handle:vertical:hover {{
            background: #5a5a5a;
        }}
        
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: transparent;
        }}
        
        QScrollBar:horizontal {{
            background: transparent;
            height: 12px;
            margin: 0;
        }}
        
        QScrollBar::handle:horizontal {{
            background: #4a4a4a;
            min-width: 30px;
            border-radius: 6px;
            margin: 2px;
        }}
        
        QScrollBar::handle:horizontal:hover {{
            background: #5a5a5a;
        }}
        
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}
        
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: transparent;
        }}
        
        /* ==================== CHECKBOX & RADIO ==================== */
        QCheckBox, QRadioButton {{
            spacing: 8px;
            color: {r['metin']};
        }}
        
        QCheckBox::indicator, QRadioButton::indicator {{
            width: 18px;
            height: 18px;
            border: 2px solid {r['kenarlık_acik']};
            background-color: {r['input_bg']};
        }}
        
        QCheckBox::indicator {{
            border-radius: 4px;
        }}
        
        QRadioButton::indicator {{
            border-radius: 9px;
        }}
        
        QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
            border-color: {r['input_border_hover']};
            background-color: #242424;
        }}
        
        QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
            background-color: {r['vurgu_koyu']};
            border-color: {r['vurgu_koyu']};
        }}
        
        QCheckBox::indicator:checked:hover, QRadioButton::indicator:checked:hover {{
            background-color: {r['vurgu_hover']};
            border-color: {r['vurgu_hover']};
        }}
        
        QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
            background-color: #222222;
            border-color: #353535;
        }}
        
        /* ==================== PROGRESS BAR ==================== */
        QProgressBar {{
            border: 1px solid {r['kenarlık']};
            border-radius: 4px;
            text-align: center;
            background-color: {r['input_bg']};
            color: {r['metin']};
            font-weight: 500;
            height: 20px;
        }}
        
        QProgressBar::chunk {{
            background-color: {r['vurgu_koyu']};
            border-radius: 3px;
        }}
        
        /* ==================== SLIDER ==================== */
        QSlider::groove:horizontal {{
            border: none;
            height: 4px;
            background: {r['kenarlık']};
            border-radius: 2px;
        }}
        
        QSlider::handle:horizontal {{
            background: {r['vurgu_koyu']};
            border: none;
            width: 16px;
            height: 16px;
            margin: -6px 0;
            border-radius: 8px;
        }}
        
        QSlider::handle:horizontal:hover {{
            background: {r['vurgu_hover']};
        }}
        
        /* ==================== TOOLTIP ==================== */
        QToolTip {{
            background-color: {r['panel']};
            color: {r['metin']};
            border: 1px solid {r['kenarlık_acik']};
            padding: 6px 8px;
            border-radius: 6px;
            font-size: 9pt;
        }}
        
        /* ==================== MDI WINDOWS ==================== */
        QMdiSubWindow {{
            background-color: {r['panel']};
            border: 1px solid {r['kenarlık']};
            border-radius: 8px;
        }}
        
        /* ==================== STATUSBAR ==================== */
        QStatusBar {{
            background-color: {r['arka_plan']};
            color: {r['metin_ikincil']};
            border-top: 1px solid {r['kenarlık']};
        }}
        
        QStatusBar::item {{
            border: none;
        }}
        
        /* ==================== TOOLBAR ==================== */
        QToolBar {{
            background-color: {r['arka_plan']};
            border: none;
            spacing: 4px;
            padding: 4px;
        }}
        
        QToolBar::separator {{
            background-color: {r['kenarlık']};
            width: 1px;
            margin: 4px 8px;
        }}
        
        QToolButton {{
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: 4px;
            padding: 6px;
            color: {r['metin']};
        }}
        
        QToolButton:hover {{
            background-color: {r['panel']};
            border: 1px solid {r['kenarlık']};
        }}
        
        QToolButton:pressed {{
            background-color: {r['panel_hover']};
        }}
        
        /* ==================== LIST WIDGET ==================== */
        QListWidget {{
            background-color: {r['input_bg']};
            border: 1px solid {r['kenarlık']};
            border-radius: 8px;
            padding: 4px;
            outline: none;
        }}
        
        QListWidget::item {{
            padding: 8px 12px;
            border-radius: 4px;
            color: {r['metin']};
        }}
        
        QListWidget::item:hover {{
            background-color: #252525;
        }}
        
        QListWidget::item:selected {{
            background-color: {r['secim_bg']};
            color: #ffffff;
        }}
        
        /* ==================== TREE WIDGET ==================== */
        QTreeWidget, QTreeView {{
            background-color: {r['input_bg']};
            border: 1px solid {r['kenarlık']};
            border-radius: 8px;
            outline: none;
        }}
        
        QTreeWidget::item, QTreeView::item {{
            padding: 4px;
        }}
        
        QTreeWidget::item:hover, QTreeView::item:hover {{
            background-color: #252525;
        }}
        
        QTreeWidget::item:selected, QTreeView::item:selected {{
            background-color: {r['secim_bg']};
        }}
        
        QTreeWidget::branch:has-children:!has-siblings:closed,
        QTreeWidget::branch:closed:has-children:has-siblings,
        QTreeWidget::branch:open:has-children:!has-siblings,
        QTreeWidget::branch:open:has-children:has-siblings {{
            image: none;
            border: none;
        }}
        
        /* ==================== SPIN BOX OKLARI ==================== */
        
        QAbstractSpinBox {{
            padding-right: 15px; 
        }}
        
        /* Yukarı ve Aşağı Butonlarının Genel Yapısı */
        QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
            background-color: {r['panel']};
            border-left: 1px solid {r['kenarlık_acik']};
            border-radius: 0px;
            width: 20px;
        }}
        
        /* Üst Buton (Yukarı) */
        QAbstractSpinBox::up-button {{
            border-top-right-radius: 4px;
            margin-top: 1px;
            margin-right: 1px;
        }}
        
        /* Alt Buton (Aşağı) */
        QAbstractSpinBox::down-button {{
            border-bottom-right-radius: 4px;
            margin-bottom: 1px;
            margin-right: 1px;
        }}
        
        /* Hover Durumu */
        QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{
            background-color: {r['panel_hover']};
        }}
        
        /* Pressed Durumu */
        QAbstractSpinBox::up-button:pressed, QAbstractSpinBox::down-button:pressed {{
            background-color: {r['vurgu']};
        }}
        
        /* Oklar */
        QAbstractSpinBox::up-arrow, QAbstractSpinBox::down-arrow {{
            width: 8px;
            height: 8px;
        }}
        QPushButton {{
            background-color: {r['panel']};
            border: 1px solid {r['kenarlık']};
            border-radius: 4px;
            padding: 7px 16px;
            color: {r['metin']};
        }}
        """