# -*- coding: utf-8 -*-
"""
Tüm formlar tarafından kullanılan ortak fonksiyonlar ve araçlar.
Kod tekrarını azaltmak ve bakım kolaylığı sağlamak için merkezi bir modül.
Hem eski (fonksiyonel) hem de yeni (sınıf tabanlı) yapıyı destekler.
"""

import logging
import sys
import os
from typing import Dict, List, Any

# PySide6 Kütüphaneleri
from PySide6.QtWidgets import (
    QWidget, QGroupBox, QFormLayout, QLineEdit, QComboBox, 
    QDateEdit, QMessageBox, QMdiSubWindow, QVBoxLayout, 
    QTableWidget, QHeaderView, QPushButton,
    QLabel, QHBoxLayout, QAbstractItemView, QMdiArea
)
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QIntValidator

# Loglama Ayarı
logger = logging.getLogger("OrtakAraclar")

# ============================================================================
# 1. PENCERE YÖNETİMİ
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
    
    # Formun başlığını ayarla
    hedef_form.setWindowTitle(baslik)

    if mdi_area:
        # Form zaten açıksa onu öne getir (Opsiyonel)
        # for sub in mdi_area.subWindowList():
        #     if sub.widget().__class__.__name__ == hedef_form.__class__.__name__:
        #          mdi_area.setActiveSubWindow(sub)
        #          return

        sub = mdi_area.addSubWindow(hedef_form)
        sub.showMaximized()
    else:
        hedef_form.show()

# ============================================================================
# 2. VERITABANI İŞLEMLERİ (HELPERS)
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
            
            for k in sabitler:
                sabitler[k].sort()
                
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
        else:
             logger.error("Veritabanı bağlantısı (ws) kurulamadı.")
             return False
    except Exception as e:
        logger.error(f"Satır ekleme hatası ({sayfa_adi}): {e}")
    return False

# ============================================================================
# 3. ESKİ UI BİLEŞEN OLUŞTURUCU (Fonksiyonel Yapı - Geriye Dönük Uyumluluk)
# ============================================================================

def create_group_box(title: str, renk: str = None) -> QGroupBox:
    grp = QGroupBox(title)
    if renk:
        grp.setStyleSheet(f"QGroupBox::title {{ color: {renk}; }}")
    return grp

def create_form_layout() -> QFormLayout:
    layout = QFormLayout()
    layout.setSpacing(15)
    layout.setContentsMargins(15, 20, 15, 15)
    return layout

def add_line_edit(layout, label_text: str, placeholder: str = "", default_text: str = "", 
                  max_length: int = None, only_int: bool = False, is_password: bool = False) -> QLineEdit:
    line_edit = QLineEdit()
    line_edit.setPlaceholderText(placeholder)
    line_edit.setText(str(default_text))
    if max_length: line_edit.setMaxLength(max_length)
    if only_int: line_edit.setValidator(QIntValidator())
    if is_password: line_edit.setEchoMode(QLineEdit.Password)
    layout.addRow(label_text, line_edit)
    return line_edit

def add_combo_box(layout: QFormLayout, label_text: str, items: List[str] = None) -> QComboBox:
    combo = QComboBox()
    combo.setMinimumHeight(35)
    if items: combo.addItems(items)
    layout.addRow(QLabel(label_text), combo)
    return combo

def add_date_edit(layout: QFormLayout, label_text: str, default_date: QDate = None) -> QDateEdit:
    date_edit = QDateEdit()
    date_edit.setCalendarPopup(True)
    if default_date: date_edit.setDate(default_date)
    else: date_edit.setDate(QDate.currentDate())
    date_edit.setDisplayFormat("dd.MM.yyyy")
    date_edit.setMinimumHeight(35)
    layout.addRow(QLabel(label_text), date_edit)
    return date_edit

# ============================================================================
# 4. YENİ SINIF YAPISI (OrtakAraclar Class) - PersonelEkle vb. için
# ============================================================================

class OrtakAraclar:
    """Yeni modüler formlar için merkezi araç seti."""

    @staticmethod
    def create_group_box(parent, title):
        gb = QGroupBox(title, parent)
        gb.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #555; margin-top: 10px; border-radius: 5px; } "
                         "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #4dabf7; }")
        return gb

    @staticmethod
    def create_combo_box(parent, items=None):
        combo = QComboBox(parent)
        if items: combo.addItems(items)
        combo.setStyleSheet("QComboBox { padding: 5px; border: 1px solid #555; background-color: #2b2b2b; color: white; border-radius: 3px; } "
                            "QComboBox::drop-down { border: 0px; }")
        return combo

    @staticmethod
    def create_line_edit(parent, placeholder=""):
        inp = QLineEdit(parent)
        inp.setPlaceholderText(placeholder)
        inp.setStyleSheet("QLineEdit { padding: 5px; border: 1px solid #555; background-color: #2b2b2b; color: white; border-radius: 3px; }")
        return inp

    @staticmethod
    def create_button(parent, text, slot=None):
        btn = QPushButton(text, parent)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton { background-color: #1976d2; color: white; padding: 6px 15px; border-radius: 4px; font-weight: bold; border: none; }
            QPushButton:hover { background-color: #1565c0; }
            QPushButton:pressed { background-color: #0d47a1; }
        """)
        if slot: btn.clicked.connect(slot)
        return btn

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
        table.setStyleSheet("""
            QTableWidget { border: 1px solid #444; background-color: #1e1e1e; gridline-color: #333; }
            QHeaderView::section { background-color: #333; color: white; padding: 5px; border: none; font-weight: bold; }
            QTableWidget::item { padding: 5px; color: #ddd; }
            QTableWidget::item:selected { background-color: #1976d2; color: white; }
        """)
        return table
    
    @staticmethod
    def mdi_pencere_ac(current_widget, target_form, title):
        mdi_pencere_ac(current_widget, target_form, title)

# ============================================================================
# 5. MESAJ KUTULARI VE DOĞRULAMA
# ============================================================================

def show_info(title: str, message: str, parent=None):
    QMessageBox.information(parent, title, message)

def show_warning(title: str, message: str, parent=None):
    QMessageBox.warning(parent, title, message)

def show_error(title: str, message: str, parent=None):
    QMessageBox.critical(parent, title, message)

# EKLENEN FONKSİYON: show_question
def show_question(title: str, message: str, parent=None) -> bool:
    """Evet/Hayır sorusu sorar. Evet ise True döner."""
    reply = QMessageBox.question(parent, title, message, 
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    return reply == QMessageBox.Yes

def validate_required_fields(fields_dict_or_list: Any) -> bool:
    """Hem sözlük (eski) hem liste (yeni) formatını destekler."""
    if isinstance(fields_dict_or_list, list):
        for widget in fields_dict_or_list:
            if isinstance(widget, QLineEdit):
                if not widget.text().strip():
                    show_warning("Eksik Bilgi", f"Lütfen zorunlu alanları doldurunuz.\n(Boş alan: {widget.placeholderText() or 'Belirtilmemiş'})")
                    widget.setFocus()
                    return False
            elif isinstance(widget, QComboBox):
                if widget.currentIndex() == -1 or not widget.currentText() or widget.currentText() == "Seçiniz...":
                    show_warning("Eksik Bilgi", "Lütfen bir seçim yapınız.")
                    widget.setFocus()
                    return False
        return True

    elif isinstance(fields_dict_or_list, dict):
        for field_name, value in fields_dict_or_list.items():
            if not value or str(value).strip() == "":
                show_warning("Eksik Bilgi", f"Lütfen '{field_name}' alanını doldurunuz.")
                return False
        return True
    
    return True