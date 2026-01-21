# -*- coding: utf-8 -*-
import sys
import os
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox)
from PySide6.QtCore import Qt, QThread, Signal

try:
    from google_baglanti import veritabani_getir
except ImportError:
    pass

class SifreGuncelleWorker(QThread):
    sonuc = Signal(bool, str)

    def __init__(self, kadi, yeni_sifre):
        super().__init__()
        self.kadi = kadi
        self.yeni_sifre = yeni_sifre

    def run(self):
        try:
            ws = veritabani_getir('user', 'user_login')
            if not ws:
                self.sonuc.emit(False, "Veritabanı hatası.")
                return

            cell = ws.find(self.kadi)
            if cell:
                # 3. Sütun: Password, 6. Sütun: degisim_gerekli
                # Not: find hücresi (row, col) döner.
                ws.update_cell(cell.row, 3, self.yeni_sifre)
                ws.update_cell(cell.row, 6, "HAYIR") # Artık değişim gerekmiyor
                self.sonuc.emit(True, "Şifre başarıyla güncellendi.")
            else:
                self.sonuc.emit(False, "Kullanıcı bulunamadı.")
        except Exception as e:
            self.sonuc.emit(False, f"Hata: {str(e)}")

class SifreDegistirPenceresi(QDialog):
    def __init__(self, kullanici_adi):
        super().__init__()
        self.setWindowTitle("Zorunlu Şifre Değişikliği")
        self.setFixedWidth(350)
        self.kullanici_adi = kullanici_adi
        self.basarili_mi = False # Login ekranına bilgi vermek için

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        lbl_bilgi = QLabel(f"Merhaba {self.kullanici_adi},\nİlk girişiniz olduğu için şifrenizi değiştirmelisiniz.")
        lbl_bilgi.setStyleSheet("color: #d13438; font-weight: bold;")
        lbl_bilgi.setWordWrap(True)
        layout.addWidget(lbl_bilgi)

        self.txt_yeni1 = QLineEdit()
        self.txt_yeni1.setPlaceholderText("Yeni Şifre")
        self.txt_yeni1.setEchoMode(QLineEdit.Password)
        
        self.txt_yeni2 = QLineEdit()
        self.txt_yeni2.setPlaceholderText("Yeni Şifre (Tekrar)")
        self.txt_yeni2.setEchoMode(QLineEdit.Password)

        layout.addWidget(self.txt_yeni1)
        layout.addWidget(self.txt_yeni2)

        self.btn_kaydet = QPushButton("ŞİFREYİ GÜNCELLE VE GİR")
        self.btn_kaydet.setStyleSheet("background-color: #0078d4; color: white; padding: 10px; font-weight: bold;")
        self.btn_kaydet.clicked.connect(self.kaydet)
        layout.addWidget(self.btn_kaydet)

    def kaydet(self):
        s1 = self.txt_yeni1.text().strip()
        s2 = self.txt_yeni2.text().strip()

        if not s1 or not s2:
            QMessageBox.warning(self, "Hata", "Şifre alanları boş olamaz.")
            return

        if s1 != s2:
            QMessageBox.warning(self, "Hata", "Şifreler uyuşmuyor.")
            return
            
        if s1 == "12345":
            QMessageBox.warning(self, "Hata", "Yeni şifreniz varsayılan şifreyle aynı olamaz.")
            return

        self.btn_kaydet.setEnabled(False)
        self.btn_kaydet.setText("Güncelleniyor...")
        
        self.worker = SifreGuncelleWorker(self.kullanici_adi, s1)
        self.worker.sonuc.connect(self.islem_sonucu)
        self.worker.start()

    def islem_sonucu(self, basari, mesaj):
        if basari:
            QMessageBox.information(self, "Başarılı", mesaj)
            self.basarili_mi = True
            self.accept() # Pencereyi kapat (OK koduyla)
        else:
            QMessageBox.critical(self, "Hata", mesaj)
            self.btn_kaydet.setEnabled(True)
            self.btn_kaydet.setText("ŞİFREYİ GÜNCELLE VE GİR")