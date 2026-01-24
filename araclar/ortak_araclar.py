# -*- coding: utf-8 -*-
"""
Tüm formlar tarafından kullanılan ortak fonksiyonlar ve araçlar.
KIDEMLİ PYTHON ASİSTANI TARAFINDAN REFACTOR EDİLMİŞTİR.
"""

import logging
import re
from typing import Dict, List, Any

# PySide6 Kütüphaneleri
from PySide6.QtWidgets import (
    QWidget, QGroupBox, QFormLayout, QLineEdit, QComboBox, 
    QDateEdit, QMessageBox, QMdiSubWindow, QVBoxLayout, 
    QTableWidget, QHeaderView, QPushButton, QLabel, 
    QMdiArea, QFrame, QGraphicsDropShadowEffect, QAbstractItemView
)
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QIntValidator, QColor

# Loglama Ayarı
logger = logging.getLogger("OrtakAraclar")

# ============================================================================
# 1. PENCERE VE MDI YÖNETİMİ
# ============================================================================

def pencereyi_kapat(widget_self):
    """MDI uyumlu pencere kapatma."""
    try:
        parent = widget_self.parent()
        while parent:
            if isinstance(parent, QMdiSubWindow):
                parent.close()
                return
            parent = parent.parent()
        widget_self.close()
    except Exception as e:
        logger.error(f"Pencere kapatma hatası: {e}")
        widget_self.close()

def mdi_pencere_ac(mevcut_widget, hedef_form, baslik):
    """
    Bir formu MDI (Ana Pencere) içinde açmaya çalışır.
    Eğer MDI alanı bulunamazsa normal pencere olarak açar.
    """
    mdi_area = None
    parent = mevcut_widget.parent()
    
    # Üst katmanlarda QMdiArea veya QMdiSubWindow arıyoruz
    while parent:
        if isinstance(parent, QMdiArea):
            mdi_area = parent
            break
        if isinstance(parent, QMdiSubWindow):
            mdi_area = parent.mdiArea()
            break
        parent = parent.parent()
    
    hedef_form.setWindowTitle(baslik)

    if mdi_area:
        # Form zaten açıksa onu öne getir
        for sub in mdi_area.subWindowList():
            if sub.widget() and sub.widget().__class__.__name__ == hedef_form.__class__.__name__:
                 mdi_area.setActiveSubWindow(sub)
                 return
        # MDI içine ekle
        sub = mdi_area.addSubWindow(hedef_form)
        sub.showMaximized()
    else:
        # MDI bulunamazsa normal aç
        hedef_form.show()

# ============================================================================
# 2. UI BİLEŞENLERİ (MODERN & KLASİK)
# ============================================================================

class OrtakAraclar:
    """Merkezi UI Factory Sınıfı"""

    @staticmethod
    def create_modern_input(parent, label_text, widget, stretch=0):
        """
        Modern etiketli giriş grubu oluşturur (Cihaz Ekle formundaki yapı).
        """
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(4)
        
        lbl = QLabel(label_text)
        # Stil tema.py'dan gelmeli ama default override için burada tutuyoruz (minimal)
        lbl.setStyleSheet("color: #b0b0b0; font-size: 11px; font-weight: bold; text-transform: uppercase;")
        
        widget.setMinimumHeight(35)
        # Not: Widget stili tema.py tarafından yönetilmelidir.
        
        layout.addWidget(lbl)
        layout.addWidget(widget)
        
        if hasattr(parent, "addWidget"): # Layout ise
            parent.addWidget(container, stretch)
        elif hasattr(parent, "add_widget"): # InfoCard ise
            parent.add_widget(container)
            
        return container

    @staticmethod
    def create_info_card(title: str, parent=None):
        """Bilgi Kartı (InfoCard) oluşturur."""
        card = QFrame(parent)
        card.setObjectName("InfoCard") # CSS seçicisi için ID
        
        # Gölge Efekti
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 80))
        card.setGraphicsEffect(shadow)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        if title:
            lbl_title = QLabel(title)
            lbl_title.setObjectName("CardTitle")
            lbl_title.setStyleSheet("color: #4dabf7; font-size: 14px; font-weight: bold; border-bottom: 1px solid #333; padding-bottom: 10px; margin-bottom: 5px;")
            layout.addWidget(lbl_title)
            
        # Dinamik ekleme metodları ekle
        card.add_widget = layout.addWidget
        card.add_layout = layout.addLayout
        
        return card

    @staticmethod
    def create_line_edit(parent=None, placeholder="", is_password=False, only_int=False):
        inp = QLineEdit(parent)
        inp.setPlaceholderText(placeholder)
        if is_password: inp.setEchoMode(QLineEdit.Password)
        if only_int: inp.setValidator(QIntValidator())
        return inp

    @staticmethod
    def create_combo_box(parent=None, items=None, db_kodu=None):
        combo = QComboBox(parent)
        if items: combo.addItems(items)
        if db_kodu: combo.setProperty("db_kodu", db_kodu)
        return combo
        
    @staticmethod
    def create_date_edit(parent=None):
        dt = QDateEdit(parent)
        dt.setCalendarPopup(True)
        dt.setDisplayFormat("dd.MM.yyyy")
        dt.setDate(QDate.currentDate())
        return dt

    @staticmethod
    def create_table(parent, headers):
        table = QTableWidget(parent)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False) 
        return table

# ============================================================================
# 3. VERITABANI VE VERİ İŞLEME YARDIMCILARI
# ============================================================================

def sabitler_yukle(veritabani_getir_func) -> Dict[str, List[str]]:
    """'Sabitler' sayfasındaki verileri çeker."""
    sabitler = {}
    try:
        ws = veritabani_getir_func('sabit', 'Sabitler')
        if ws:
            kayitlar = ws.get_all_records()
            for satir in kayitlar:
                kod = str(satir.get('Kod', '')).strip()
                eleman = str(satir.get('MenuEleman', '')).strip()
                if kod and eleman:
                    if kod not in sabitler:
                        sabitler[kod] = []
                    sabitler[kod].append(eleman)
            for k in sabitler: sabitler[k].sort()
    except Exception as e:
        logger.error(f"Sabitler yüklenirken hata: {e}")
    return sabitler

def kayitlari_getir(veritabani_getir_func, vt_tipi: str, sayfa_adi: str) -> List[Dict]:
    """Genel amaçlı veri çekme fonksiyonu."""
    try:
        ws = veritabani_getir_func(vt_tipi, sayfa_adi)
        if ws:
            return ws.get_all_records()
    except Exception as e:
        logger.error(f"Kayıt getirme hatası ({sayfa_adi}): {e}")
    return []

def satir_ekle(veritabani_getir_func, vt_tipi: str, sayfa_adi: str, veri_listesi: List) -> bool:
    """Verilen listeyi Google Sheets'e yeni satır olarak ekler."""
    try:
        ws = veritabani_getir_func(vt_tipi, sayfa_adi)
        if ws:
            ws.append_row(veri_listesi)
            return True
        logger.error("Veritabanı bağlantısı (ws) kurulamadı.")
    except Exception as e:
        logger.error(f"Satır ekleme hatası ({sayfa_adi}): {e}")
    return False

# ============================================================================
# 4. DOĞRULAMA VE MESAJLAR
# ============================================================================

def show_info(title: str, message: str, parent=None):
    QMessageBox.information(parent, title, message)

def show_warning(title: str, message: str, parent=None):
    QMessageBox.warning(parent, title, message)

def show_error(title: str, message: str, parent=None):
    QMessageBox.critical(parent, title, message)

def show_question(title: str, message: str, parent=None) -> bool:
    reply = QMessageBox.question(parent, title, message, 
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    return reply == QMessageBox.Yes

def validate_required_fields(fields_list: List[QWidget]) -> bool:
    """Liste formatındaki widget'ların doluluğunu kontrol eder."""
    for widget in fields_list:
        if isinstance(widget, QLineEdit):
            if not widget.text().strip():
                show_warning("Eksik Bilgi", "Lütfen zorunlu alanları doldurunuz.")
                widget.setFocus()
                return False
        elif isinstance(widget, QComboBox):
            if widget.currentIndex() == -1 or not widget.currentText():
                show_warning("Eksik Bilgi", "Lütfen bir seçim yapınız.")
                widget.setFocus()
                return False
    return True

# Eski fonksiyonlar (uyumluluk için tutulabilir veya silinebilir)
create_group_box = OrtakAraclar.create_modern_input # Geçici mapping
create_form_layout = lambda: QFormLayout() 
add_line_edit = OrtakAraclar.create_line_edit