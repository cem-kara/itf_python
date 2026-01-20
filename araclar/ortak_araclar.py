# -*- coding: utf-8 -*-
"""
Tüm formlar tarafından kullanılan ortak fonksiyonlar ve araçlar.
Kod tekrarını azaltmak ve bakım kolaylığı sağlamak için merkezi bir modül.
Tema Yönetimi: Stil tanımları artık tema.py üzerinden yönetilmektedir.
Hem eski (fonksiyonel) hem de yeni (sınıf tabanlı) yapıyı destekler.
"""

import logging
import re
import sys
import os
from typing import Dict, List, Any, Optional

# PySide6 Kütüphaneleri
from PySide6.QtWidgets import (
    QWidget, QGroupBox, QFormLayout, QLineEdit, QComboBox, 
    QDateEdit, QMessageBox, QMdiSubWindow, QVBoxLayout, 
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QLabel, QHBoxLayout, QAbstractItemView, QMdiArea, QSizePolicy
)
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QFont, QColor, QIcon, QIntValidator # QIntValidator buraya eklendi
from PySide6.QtWidgets import QMdiArea, QMdiSubWindow # Bu importun yukarıda olduğundan emin olun


# Loglama Ayarı
logger = logging.getLogger("OrtakAraclar")

# ============================================================================
# 1. PENCERE YÖNETİMİ (ESKİ SİSTEM İÇİN)
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
    except Exception as e:
        logger.error(f"Satır ekleme hatası ({sayfa_adi}): {e}")
    return False

# ============================================================================
# 3. UI BİLEŞEN OLUŞTURUCU (ESKİ SİSTEM - FONKSİYONEL)
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
    """
    Forma etiketli bir giriş kutusu ekler.
    
    Argümanlar:
        layout: Widget'ın ekleneceği QFormLayout
        label_text: Etiket metni
        placeholder: Silik ipucu metni
        default_text: Varsayılan değer
        max_length: Maksimum karakter sayısı (Örn: TC için 11)
        only_int: Sadece sayı girişine izin verilsin mi? (True/False)
        is_password: Şifre maskelemesi yapılsın mı? (True/False)
    """
    line_edit = QLineEdit()
    line_edit.setPlaceholderText(placeholder)
    line_edit.setText(str(default_text))
    
    # 1. Maksimum Karakter Sınırı
    if max_length:
        line_edit.setMaxLength(max_length)
    
    # 2. Sadece Sayı Girişi (Validator)
    if only_int:
        # Sadece rakam girilmesini sağlayan validatör
        line_edit.setValidator(QIntValidator())

    # 3. Şifre Modu
    if is_password:
        line_edit.setEchoMode(QLineEdit.Password)

    # Layout'a Ekleme
    layout.addRow(label_text, line_edit)
    
    return line_edit

def add_combo_box(layout: QFormLayout, label_text: str, items: List[str] = None) -> QComboBox:
    combo = QComboBox()
    combo.setMinimumHeight(35)
    if items:
        combo.addItems(items)
    layout.addRow(QLabel(label_text), combo)
    return combo

def add_date_edit(layout: QFormLayout, label_text: str, default_date: QDate = None) -> QDateEdit:
    date_edit = QDateEdit()
    date_edit.setCalendarPopup(True)
    if default_date:
        date_edit.setDate(default_date)
    else:
        date_edit.setDate(QDate.currentDate())
        
    date_edit.setDisplayFormat("dd.MM.yyyy")
    date_edit.setMinimumHeight(35)
    layout.addRow(QLabel(label_text), date_edit)
    return date_edit

# ============================================================================
# 4. MESAJ KUTULARI VE DOĞRULAMA (ESKİ SİSTEM)
# ============================================================================

def show_info(title: str, message: str, parent=None):
    # parent None ise aktif pencereyi bulmaya çalışabilir veya None bırakırız
    QMessageBox.information(parent, title, message)

def show_warning(title: str, message: str, parent=None):
    QMessageBox.warning(parent, title, message)

def show_error(title: str, message: str, parent=None):
    QMessageBox.critical(parent, title, message)

def show_question(title: str, message: str, parent=None) -> bool:
    reply = QMessageBox.question(parent, title, message, 
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    return reply == QMessageBox.Yes

def validate_required_fields(fields_dict_or_list: Any) -> bool:
    """
    Hem sözlük (eski) hem liste (yeni) formatını destekler.
    Liste formatı: [QLineEdit, QLineEdit, ...]
    Sözlük formatı: {'Alan Adı': 'Değer'} (Eski kullanım, string kontrolü yapar)
    """
    # 1. Eğer liste olarak Widget objeleri geldiyse (Yeni Template Kullanımı)
    if isinstance(fields_dict_or_list, list):
        for widget in fields_dict_or_list:
            if isinstance(widget, QLineEdit):
                if not widget.text().strip():
                    show_warning("Eksik Bilgi", f"Lütfen zorunlu alanları doldurunuz.\nBoş alan: {widget.placeholderText() or 'Belirtilmemiş'}")
                    widget.setFocus()
                    return False
            elif isinstance(widget, QComboBox):
                if widget.currentIndex() == 0 or widget.currentText() == "Seçiniz...":
                    show_warning("Eksik Bilgi", "Lütfen bir seçim yapınız.")
                    widget.setFocus()
                    return False
        return True

    # 2. Eğer sözlük geldiyse (Eski kullanım: {'Ad': 'Ahmet'})
    elif isinstance(fields_dict_or_list, dict):
        for field_name, value in fields_dict_or_list.items():
            if not value or str(value).strip() == "":
                # Eski sistemde uyarıyı çağıran yer veriyordu, burada sadece False dönüyoruz
                # veya uyarı ekleyebiliriz:
                show_warning("Eksik Bilgi", f"Lütfen '{field_name}' alanını doldurunuz.")
                return False
        return True
    
    return True

def is_valid_email(email: str) -> bool:
    if not email: return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def is_valid_phone(phone: str) -> bool:
    if not phone: return False
    clean_phone = re.sub(r'\D', '', phone)
    return 10 <= len(clean_phone) <= 11

def dict_to_list(data_dict: Dict[str, Any], keys: List[str]) -> List[Any]:
    return [data_dict.get(key, "") for key in keys]

def combine_dicts(d1: Dict, d2: Dict) -> Dict:
    z = d1.copy()
    z.update(d2)
    return z

# ============================================================================
# 5. YENİ SINIF YAPISI (PersonelListesi vb. YENİ FORMLAR İÇİN)
# Bu sınıf, yukarıdaki fonksiyonları kapsar ve genişletir.
# ============================================================================

class OrtakAraclar:
    """
    Yeni modüler formlar için merkezi araç seti.
    Statik metodlar kullanarak 'OrtakAraclar.metod_adi' şeklinde erişilir.
    """

    @staticmethod
    def create_group_box(parent, title):
        """Yeni stil GroupBox oluşturur."""
        gb = QGroupBox(title, parent)
        gb.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #555; margin-top: 10px; border-radius: 5px; } "
                         "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #4dabf7; }")
        return gb

    @staticmethod
    def create_combo_box(parent, items=None):
        """Standart ComboBox"""
        combo = QComboBox(parent)
        if items:
            combo.addItems(items)
        combo.setStyleSheet("QComboBox { padding: 5px; border: 1px solid #555; background-color: #2b2b2b; color: white; border-radius: 3px; } "
                            "QComboBox::drop-down { border: 0px; }")
        return combo

    @staticmethod
    def create_line_edit(parent, placeholder=""):
        """Standart LineEdit"""
        inp = QLineEdit(parent)
        inp.setPlaceholderText(placeholder)
        inp.setStyleSheet("QLineEdit { padding: 5px; border: 1px solid #555; background-color: #2b2b2b; color: white; border-radius: 3px; }")
        return inp

    @staticmethod
    def create_button(parent, text, slot=None, icon_name=None):
        """Standart Buton"""
        btn = QPushButton(text, parent)
        btn.setCursor(Qt.PointingHandCursor)
        # Mavi modern buton stili
        btn.setStyleSheet("""
            QPushButton { background-color: #1976d2; color: white; padding: 6px 15px; border-radius: 4px; font-weight: bold; border: none; }
            QPushButton:hover { background-color: #1565c0; }
            QPushButton:pressed { background-color: #0d47a1; }
        """)
        if slot:
            btn.clicked.connect(slot)
        return btn

    @staticmethod
    def create_table(parent, headers):
        """Standart Tablo"""
        table = QTableWidget(parent)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        
        # Görünüm ayarları
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False) 
        
        # Stil
        table.setStyleSheet("""
            QTableWidget { border: 1px solid #444; background-color: #1e1e1e; gridline-color: #333; }
            QHeaderView::section { background-color: #333; color: white; padding: 5px; border: none; font-weight: bold; }
            QTableWidget::item { padding: 5px; color: #ddd; }
            QTableWidget::item:selected { background-color: #1976d2; color: white; }
        """)
        return table

    @staticmethod
    def show_error(parent, title, message):
        """Hata mesajı"""
        QMessageBox.critical(parent, title, message)

    @staticmethod
    def mdi_pencere_ac(current_widget, target_form, title):
        """
        Formu MDI içinde açmaya çalışır, yoksa normal pencere olarak açar.
        """
        mdi_area = None
        p = current_widget.parent()
        
        # MDI Area'yı bulmak için yukarı tırman
        while p:
            if isinstance(p, QMdiArea):
                mdi_area = p
                break
            if isinstance(p, QMdiSubWindow):
                mdi_area = p.mdiArea()
                break
            p = p.parent()
        
        if mdi_area:
            # Pencere zaten açık mı kontrol et
            for sub in mdi_area.subWindowList():
                if sub.windowTitle() == title:
                    mdi_area.setActiveSubWindow(sub)
                    return

            sub = mdi_area.addSubWindow(target_form)
            target_form.setWindowTitle(title)
            sub.showMaximized()
        else:
            # MDI bulunamazsa normal show
            target_form.setWindowTitle(title)
            target_form.show()
def mdi_pencere_ac(mevcut_widget, hedef_form, baslik):
    """
    Bir formu MDI (Ana Pencere) içinde açmaya çalışır.
    Eğer MDI alanı bulunamazsa normal pencere olarak açar.
    
    Argümanlar:
        mevcut_widget: Şu an açık olan form (self)
        hedef_form: Açılacak olan yeni form nesnesi (PersonelEklePenceresi vb.)
        baslik: Pencere başlığı
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
        # Form zaten açıksa onu öne getir (Opsiyonel kontrol)
        for sub in mdi_area.subWindowList():
            if sub.widget() and sub.widget().__class__.__name__ == hedef_form.__class__.__name__:
                 # Burada aynı sınıftan birden fazla açmaya izin veriyoruz (Detay için gerekli)
                 # Eğer tekil açılmasını isterseniz buraya kontrol eklenir.
                 pass

        # MDI içine ekle
        sub = mdi_area.addSubWindow(hedef_form)
        sub.showMaximized() # Veya sub.show()
    else:
        # MDI bulunamazsa normal aç
        hedef_form.show()

# ============================================================================
# VERİTABANI YARDIMCI FONKSİYONLARI (EKLENECEK KISIM)
# ============================================================================

def kayitlari_getir(veritabani_getir_func, vt_tipi: str, sayfa_adi: str):
    """
    Belirtilen veritabanı ve sayfadan tüm kayıtları sözlük listesi olarak çeker.
    """
    try:
        ws = veritabani_getir_func(vt_tipi, sayfa_adi)
        if ws:
            return ws.get_all_records()
    except Exception as e:
        logger.error(f"Kayıt getirme hatası ({sayfa_adi}): {e}")
    return []

def satir_ekle(veritabani_getir_func, vt_tipi: str, sayfa_adi: str, veri_listesi: list) -> bool:
    """
    Verilen listeyi Google Sheets'e yeni satır olarak ekler.
    
    Args:
        veritabani_getir_func: google_baglanti.veritabani_getir fonksiyonu
        vt_tipi: 'personel', 'cihaz', 'sabit' vb.
        sayfa_adi: Sheet adı (Örn: 'Personel')
        veri_listesi: Eklenecek satır verisi (Liste formatında)
    """
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