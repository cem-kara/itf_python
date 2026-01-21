# -*- coding: utf-8 -*-
import sys
import os
from datetime import datetime
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QFrame, QMessageBox)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QPixmap, QIcon

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

try:
    from google_baglanti import veritabani_getir
    from temalar.tema import TemaYonetimi
    from main import AnaPencere 
except ImportError:
    pass

class GirisWorker(QThread):
    # Sinyal: Başarılı mı?, Mesaj, Kullanıcı Adı, Rol
    sonuc = Signal(bool, str, str, str)

    def __init__(self, kadi, sifre):
        super().__init__()
        self.kadi = kadi
        self.sifre = sifre

    def run(self):
        try:
            # 1. BAĞLANTI: itf_user_vt dosyası, user_login sayfası
            # NOT: google_baglanti.py dosyanızın bu dosya ismini desteklediğinden emin olun.
            # Eğer hata alırsanız 'itf_user_vt' yerine spreadsheet ID'si veya tanımlı anahtarı kullanın.
            ws = veritabani_getir('user', 'user_login') 
            
            if not ws:
                self.sonuc.emit(False, "Veritabanına (itf_user_vt) erişilemedi.", "", "")
                return

            records = ws.get_all_records()
            
            # enumerate ile döngü kuruyoruz ki satır numarasını bilelim (Excel satırı = index + 2)
            for i, user in enumerate(records):
                # Sütun İsimleri: user_id, username, password, roller, login_date_time
                vt_kadi = str(user.get('username', '')).strip()
                vt_sifre = str(user.get('password', '')).strip()
                
                if vt_kadi == self.kadi and vt_sifre == self.sifre:
                    # GİRİŞ BAŞARILI
                    rol = str(user.get('roller', 'user'))
                    
                    # --- Login Tarihini Güncelleme ---
                    try:
                        # Satır numarası: Liste 0'dan başlar, başlık 1. satırdır -> Veri 2'den başlar.
                        row_num = i + 2 
                        simdi = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                        
                        # login_date_time 5. sütun olduğu için col=5
                        ws.update_cell(row_num, 5, simdi)
                    except Exception as log_err:
                        print(f"Log yazma hatası: {log_err}")

                    self.sonuc.emit(True, "Giriş Başarılı", vt_kadi, rol)
                    return
            
            self.sonuc.emit(False, "Kullanıcı adı veya şifre hatalı.", "", "")

        except Exception as e:
            self.sonuc.emit(False, f"Sistem Hatası: {str(e)}", "", "")

class LoginPenceresi(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sistem Girişi")
        self.resize(400, 500)
        self.setWindowFlags(Qt.FramelessWindowHint) 
        self.setAttribute(Qt.WA_TranslucentBackground) 
        
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Ana Kart
        self.frame = QFrame()
        self.frame.setStyleSheet("""
            QFrame {
                background-color: #2d2d30;
                border-radius: 15px;
                border: 1px solid #3e3e42;
            }
        """)
        card_layout = QVBoxLayout(self.frame)
        card_layout.setContentsMargins(40, 40, 40, 40)
        card_layout.setSpacing(20)

        # Başlık
        lbl_baslik = QLabel("İTF Radyoloji\nGiriş Paneli")
        lbl_baslik.setAlignment(Qt.AlignCenter)
        lbl_baslik.setStyleSheet("font-size: 26px; font-weight: bold; color: #4dabf7; border: none;")
        card_layout.addWidget(lbl_baslik)

        # Kullanıcı Adı
        self.txt_kadi = QLineEdit()
        self.txt_kadi.setPlaceholderText("Kullanıcı Adı")
        self.txt_kadi.setFixedHeight(45)
        self.txt_kadi.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e1e;
                border: 1px solid #444;
                border-radius: 5px;
                color: white;
                padding-left: 10px;
                font-size: 14px;
            }
            QLineEdit:focus { border: 1px solid #4dabf7; }
        """)
        card_layout.addWidget(self.txt_kadi)

        # Şifre
        self.txt_sifre = QLineEdit()
        self.txt_sifre.setPlaceholderText("Şifre")
        self.txt_sifre.setEchoMode(QLineEdit.Password)
        self.txt_sifre.setFixedHeight(45)
        self.txt_sifre.setStyleSheet(self.txt_kadi.styleSheet())
        self.txt_sifre.returnPressed.connect(self.giris_yap)
        card_layout.addWidget(self.txt_sifre)

        # Giriş Butonu
        self.btn_giris = QPushButton("GİRİŞ YAP")
        self.btn_giris.setFixedHeight(50)
        self.btn_giris.setCursor(Qt.PointingHandCursor)
        self.btn_giris.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                font-weight: bold;
                border-radius: 5px;
                font-size: 15px;
            }
            QPushButton:hover { background-color: #106ebe; }
            QPushButton:pressed { background-color: #005a9e; }
        """)
        self.btn_giris.clicked.connect(self.giris_yap)
        card_layout.addWidget(self.btn_giris)

        # Çıkış Butonu
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
            # Main Pencereyi Aç
            try:
                # İsterseniz yetkiyi AnaPencere'ye gönderebilirsiniz: AnaPencere(yetki=rol)
                self.main_win = AnaPencere() 
                self.main_win.show()
                self.close()
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Ana pencere açılamadı:\n{e}")
        else:
            QMessageBox.critical(self, "Giriş Başarısız", mesaj)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    try:
        TemaYonetimi.uygula_fusion_dark(app)
    except:
        pass
    win = LoginPenceresi()
    win.show()
    sys.exit(app.exec())