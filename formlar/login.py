# -*- coding: utf-8 -*-
import sys
import os
import logging
from datetime import datetime
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QFrame, QMessageBox)
# 1. DEĞİŞİKLİK: Signal eklendi
from PySide6.QtCore import Qt, QThread, Signal 
from PySide6.QtGui import QFont, QPixmap, QIcon
from araclar.ortak_araclar import show_toast
from araclar.log_yonetimi import LogYoneticisi

logger = logging.getLogger("Login")
# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# --- IMPORTLAR ---
# DİKKAT: 'from main import AnaPencere' SATIRINI SİLİN!
from araclar.guvenlik import GuvenlikAraclari
try:
    from formlar.sifre_degistir import SifreDegistirPenceresi
except ImportError:
    pass

try:
    from google_baglanti import veritabani_getir
    from temalar.tema import TemaYonetimi
except ImportError:
    pass

# ... (GirisWorker sınıfı aynen kalacak) ...
class GirisWorker(QThread):
    sonuc = Signal(bool, str, str, str)

    def __init__(self, kadi, sifre):
        super().__init__()
        self.kadi = kadi
        self.sifre = sifre

    def run(self):
        try:
            ws = veritabani_getir('user', 'user_login')
            # ...
            
            records = ws.get_all_records()
            
            for i, user in enumerate(records):
                vt_kadi = str(user.get('username', '')).strip()
                vt_sifre_hash = str(user.get('password', '')).strip() # Artık veritabanından HASH geliyor
                
                # Kontrol: Kullanıcı adı eşleşiyor mu?
                if vt_kadi == self.kadi:
                    
                    # Şifre Kontrolü (Hashleyerek kıyasla)
                    if GuvenlikAraclari.dogrula(self.sifre, vt_sifre_hash):
                        
                        # --- GİRİŞ BAŞARILI ---
                        rol = str(user.get('roller', 'user'))
                        degisim_gerekli = str(user.get('degisim_gerekli', 'HAYIR')).upper()
                        
                        if degisim_gerekli == 'EVET':
                            self.sonuc.emit(True, "CHANGE_REQUIRED", vt_kadi, rol)
                            return
                        
                        # ... (Tarih güncelleme ve OK sinyali aynı) ...
                        self.sonuc.emit(True, "OK", vt_kadi, rol)
                        return
                    else:
                        # Kullanıcı adı doğru ama şifre yanlış
                        self.sonuc.emit(False, "Şifre hatalı.", "", "")
                        return
            
            self.sonuc.emit(False, "Kullanıcı bulunamadı.", "", "")
            logger.info(f"Giriş denemesi yapılıyor: {self.kadi}")
            # ... 
        except Exception as e:
            logger.error(f"Giriş işlemi hatası: {e}")
            self.sonuc.emit(False, f"Bağlantı Hatası: {str(e)}", "", "")
        
class LoginPenceresi(QWidget):
    # 2. DEĞİŞİKLİK: Bu satırı eklemezseniz hata alırsınız!
    giris_basarili = Signal(str, str) # Sinyal: (Rol, TC_Kimlik)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sistem Girişi")
        self.resize(400, 500)
        self.setWindowFlags(Qt.FramelessWindowHint) 
        self.setAttribute(Qt.WA_TranslucentBackground) 
        
        self.setup_ui()

    def setup_ui(self):
        # ... (Tasarım kodları aynen kalacak) ...
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.frame = QFrame()
        self.frame.setStyleSheet("QFrame { background-color: #2d2d30; border-radius: 15px; border: 1px solid #3e3e42; }")
        card_layout = QVBoxLayout(self.frame)
        card_layout.setContentsMargins(40, 40, 40, 40)
        card_layout.setSpacing(20)

        lbl_baslik = QLabel("İTF Radyoloji\nGiriş Paneli")
        lbl_baslik.setAlignment(Qt.AlignCenter)
        lbl_baslik.setStyleSheet("font-size: 26px; font-weight: bold; color: #4dabf7; border: none;")
        card_layout.addWidget(lbl_baslik)

        self.txt_kadi = QLineEdit()
        self.txt_kadi.setPlaceholderText("Kullanıcı Adı")
        self.txt_kadi.setFixedHeight(45)
        self.txt_kadi.setStyleSheet("QLineEdit { background-color: #1e1e1e; border: 1px solid #444; border-radius: 5px; color: white; padding-left: 10px; font-size: 14px; }")
        card_layout.addWidget(self.txt_kadi)

        self.txt_sifre = QLineEdit()
        self.txt_sifre.setPlaceholderText("Şifre")
        self.txt_sifre.setEchoMode(QLineEdit.Password)
        self.txt_sifre.setFixedHeight(45)
        self.txt_sifre.setStyleSheet(self.txt_kadi.styleSheet())
        self.txt_sifre.returnPressed.connect(self.giris_yap)
        card_layout.addWidget(self.txt_sifre)

        self.btn_giris = QPushButton("GİRİŞ YAP")
        self.btn_giris.setFixedHeight(50)
        self.btn_giris.setCursor(Qt.PointingHandCursor)
        self.btn_giris.setStyleSheet("QPushButton { background-color: #0078d4; color: white; font-weight: bold; border-radius: 5px; font-size: 15px; } QPushButton:hover { background-color: #106ebe; }")
        self.btn_giris.clicked.connect(self.giris_yap)
        card_layout.addWidget(self.btn_giris)

        btn_cikis = QPushButton("Kapat")
        btn_cikis.setCursor(Qt.PointingHandCursor)
        btn_cikis.setStyleSheet("background: transparent; color: #888; border: none;")
        btn_cikis.clicked.connect(self.close)
        card_layout.addWidget(btn_cikis)

        layout.addWidget(self.frame)

    def giris_yap(self):
        kadi = self.txt_kadi.text().strip()
        sifre = self.txt_sifre.text().strip()

        if not kadi or not sifre:
            QMessageBox.warning(self, "Uyarı", "Kullanıcı adı ve şifre gereklidir.")
            return

        self.btn_giris.setText("Kontrol Ediliyor...")
        self.btn_giris.setEnabled(False)

        self.worker = GirisWorker(kadi, sifre)
        self.worker.sonuc.connect(self.islem_sonucu)
        self.worker.start()

    def islem_sonucu(self, basarili, mesaj, kadi, rol):
        self.btn_giris.setEnabled(True)
        self.btn_giris.setText("GİRİŞ YAP")

        if basarili:
            logger.info(f"Giriş başarılı: {kadi} (Rol: {rol})")
            show_toast(f"Hoş geldiniz, {kadi}", type="success")
            if mesaj == "CHANGE_REQUIRED":
                self.hide()
                try:
                    dialog = SifreDegistirPenceresi(kadi)
                    if dialog.exec():
                        # Şifre değişti, şimdi ana pencereyi açmak için sinyal gönder
                        self.giris_basarili.emit(rol, kadi)
                        self.close()
                    else:
                        self.show()
                except Exception as e:
                    self.show()
                    QMessageBox.critical(self, "Hata", f"Şifre ekranı hatası: {e}")

            else:
                # 3. DEĞİŞİKLİK: Doğrudan açmak yerine SİNYAL GÖNDERİYORUZ
                # self.main_win = AnaPencere(...)  <-- BU YOK
                self.giris_basarili.emit(rol, kadi)
                self.close()
        else:
            logger.warning(f"Hatalı giriş denemesi: {kadi} - Neden: {mesaj}")
            show_toast(mesaj, type="error")
            # Kritik hatalarda QMessageBox yedek olarak kalabilir
            if "Bağlantı" in mesaj:
                QMessageBox.critical(self, "Hata", mesaj)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = LoginPenceresi()
    win.show()
    sys.exit(app.exec())