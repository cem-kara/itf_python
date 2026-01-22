# -*- coding: utf-8 -*-
import sys
import os
import importlib
import logging
from functools import partial

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMdiArea, QMdiSubWindow, 
    QWidget, QVBoxLayout, QHBoxLayout, QStatusBar, 
    QFrame, QPushButton, QMessageBox, QToolBox, QStackedWidget
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QIcon, QFont

# --- LOGLAMA AYARLARI ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Main")

# --- YOL AYARLARI (PATH) ---
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# --- İMPORTLAR ---
# Login penceresini buradan import ediyoruz çünkü Yönetici sınıfı kullanacak
try:
    from formlar.login import LoginPenceresi
except ImportError:
    pass # Hata yönetimi aşağıda yapılacak

from araclar.yetki_yonetimi import YetkiYoneticisi

# --- MODÜLER IMPORTLAR ---
try:
    from temalar.tema import TemaYonetimi
    from araclar.ortak_araclar import pencereyi_kapat
except ImportError as e:
    logger.critical(f"Temel modüller eksik: {e}")
    sys.exit(1)

# =============================================================================
# FORM HARİTASI (AYNEN KORUNDU)
# =============================================================================
FORM_MAP = {
    # -- GENEL --
    "Dashboard":        ("formlar.dashboard", "DashboardPenceresi"),
    # "User Login":       ("formlar.login", "LoginPenceresi"), # Login artık menüden açılmayacak
    "Ayarlar":          ("formlar.ayarlar", "AyarlarPenceresi"),
    
    # -- PERSONEL --
    "Personel Listesi": ("formlar.personel_listesi", "PersonelListesiPenceresi"),
    "Personel Ekle":    ("formlar.personel_ekle", "PersonelEklePenceresi"),
    "İzin Takip":       ("formlar.izin_takip", "IzinGirisPenceresi"),
    "FHSZ Yönetim":     ("formlar.fhsz_Yonetim", "FHSZYonetimPaneli"),
    "Personel Verileri": ("formlar.user_dashboard", "DashboardWidget"),

    # -- CİHAZ --
    "Cihaz Listesi":    ("formlar.cihaz_listesi", "CihazListesiPenceresi"),
    "Cihaz Ekle":       ("formlar.cihaz_ekle", "CihazEklePenceresi"),
    "Ariza Kaydi":      ("formlar.ariza_kayit", "ArizaKayitPenceresi"),
    "Ariza Listesi":    ("formlar.ariza_listesi", "ArizaListesiPenceresi"),
    "Periyodik Bakim":  ("formlar.periyodik_bakim", "PeriyodikBakimPenceresi"),
    "Kalibrasyon Takip": ("formlar.kalibrasyon_ekle", "KalibrasyonEklePenceresi"),
    
    # -- RKE --
    "RKE Listesi":      ("formlar.rke_yonetim", "RKEYonetimPenceresi"),
    "Muayene Girişi":   ("formlar.rke_muayene", "RKEMuayenePenceresi"),
    "RKE Raporlama":    ("formlar.rke_rapor", "RKERaporPenceresi"),
}

# Akordeon Menü Yapısı (AYNEN KORUNDU)
MENU_STRUCTURE = {
    "GENEL": ["Dashboard", "Ayarlar"], # User Login kaldırıldı
    "PERSONEL": ["Personel Listesi", "Personel Ekle", "İzin Takip", "FHSZ Yönetim", "Personel Verileri"],
    "CİHAZ": ["Cihaz Listesi", "Cihaz Ekle", "Ariza Kaydi", "Ariza Listesi", "Periyodik Bakim", "Kalibrasyon Takip"],
    "RKE": ["RKE Listesi", "Muayene Girişi", "RKE Raporlama"]
}

# -----------------------------------------------------------------------------
# ANA PENCERE SINIFI
# -----------------------------------------------------------------------------
class AnaPencere(QMainWindow):
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi # Giriş yapanın TC'si
        
        self.setWindowTitle(f"ITF Python Yönetim Sistemi (v1.0) - {self.yetki.upper()}")
        self.resize(1280, 800)

        # UI Kurulumu
        self._setup_ui()
        
        # Durum Çubuğu
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(f"Hoşgeldiniz: {self.kullanici_adi} ({self.yetki})")

        # --- YETKİ KURALINI UYGULA ---
        YetkiYoneticisi.uygula(self, "main_window")

    def _setup_ui(self):
        """Ana pencere düzeni: Sol Akordeon Menü + Sağ MDI Alanı"""
        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. SOL MENÜ (AKORDEON STİLİ)
        self.sidebar_container = QFrame()
        self.sidebar_container.setObjectName("sidebar")
        self.sidebar_container.setFixedWidth(260)
        self.sidebar_container.setStyleSheet("""
            QFrame#sidebar { background-color: #2b2b2b; border-right: 1px solid #3e3e3e; }
            QToolBox { background-color: #2b2b2b; border: none; }
            QToolBox::tab { 
                background: #3e3e3e; 
                color: #ddd; 
                font-weight: bold; 
                border-radius: 4px;
                padding-left: 10px;
            }
            QToolBox::tab:selected { background: #0067c0; color: white; }
            QWidget { background-color: #2b2b2b; } 
        """)
        
        sidebar_layout = QVBoxLayout(self.sidebar_container)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # QToolBox (Akordeon Bileşeni)
        self.toolbox = QToolBox()
        
        # Menüleri Döngü ile Oluştur
        for baslik, elemanlar in MENU_STRUCTURE.items():
            page_widget = QWidget()
            page_layout = QVBoxLayout(page_widget)
            page_layout.setContentsMargins(5, 10, 5, 10)
            page_layout.setSpacing(5)
            page_layout.setAlignment(Qt.AlignTop)

            # ... (Döngü başlangıcı aynı) ...
            for item_name in elemanlar:
                if item_name in FORM_MAP:
                    btn = QPushButton(f"  {item_name}")
                    btn.setCursor(Qt.PointingHandCursor)
                    
                    # btn object name ataması
                    safe_name = "btn_" + item_name.lower().replace(" ", "_").replace("ç","c").replace("ğ","g").replace("ı","i").replace("ö","o").replace("ş","s").replace("ü","u")
                    btn.setObjectName(safe_name)

                    # ========================================================
                    # 🔴 EKLEMEN GEREKEN KRİTİK SATIR BURASI:
                    # Bu satır, butonu "self.btn_personel_listesi" gibi kaydeder.
                    setattr(self, safe_name, btn) 
                    # ========================================================
                    
                    btn.setStyleSheet("""
                        QPushButton {
                            text-align: center-left;
                            padding: 8px;
                            border: none;
                            background-color: transparent;
                            color: #cccccc;
                            border-radius: 4px;
                        }
                        QPushButton:hover { background-color: #3e3e3e; color: white; }
                    """)
                    
                    # Sinyal Bağlama
                    btn.clicked.connect(partial(self.form_ac, item_name))
                    page_layout.addWidget(btn)

            self.toolbox.addItem(page_widget, baslik)

        sidebar_layout.addWidget(self.toolbox)
        
        # Çıkış Butonu
        self.btn_cikis = QPushButton(" Çıkış Yap") # self ekledik, yetki için
        self.btn_cikis.setObjectName("btn_cikis")
        self.btn_cikis.setStyleSheet("background-color: #d32f2f; color: white; padding: 10px; border: none; font-weight: bold;")
        self.btn_cikis.clicked.connect(self.close)
        sidebar_layout.addWidget(self.btn_cikis)

        # 2. SAĞ TARAF (MDI Area)
        self.mdi_area = QMdiArea()
        self.mdi_area.setViewMode(QMdiArea.TabbedView) 
        self.mdi_area.setTabsClosable(True)
        self.mdi_area.setTabsMovable(True)
        self.mdi_area.setBackground(Qt.darkGray)

        # Layout Yerleşimi
        main_layout.addWidget(self.sidebar_container)
        main_layout.addWidget(self.mdi_area)
        
        self.setCentralWidget(central_widget)

    def form_ac(self, form_key):
        """
        Form açma fonksiyonu.
        Hata yönetimi: Form dosyası henüz yoksa kullanıcıya şık bir mesaj gösterir.
        """
        if form_key not in FORM_MAP:
            return

        module_path, class_name = FORM_MAP[form_key]

        # 1. Form zaten açık mı kontrol et
        for sub in self.mdi_area.subWindowList():
            if sub.windowTitle() == form_key:
                self.mdi_area.setActiveSubWindow(sub)
                return

        self.status_bar.showMessage(f"Yükleniyor: {form_key}...")

        try:
            # 2. Modülü Dinamik İçe Aktar
            modul = importlib.import_module(module_path)
            
            # 3. Sınıfı Bul ve Örnekle
            FormSinifi = getattr(modul, class_name)
            
            # -- YETKİ VE KULLANICI ADI AKTARIMI (ÖNEMLİ) --
            # Eğer form sınıfı bu parametreleri kabul ediyorsa gönder
            try:
                # Bazı formlar parametre almayabilir, hata almamak için try-except
                form_instance = FormSinifi(yetki=self.yetki, kullanici_adi=self.kullanici_adi)
            except TypeError:
                try:
                    # Sadece yetki alıyor olabilir
                     form_instance = FormSinifi(yetki=self.yetki)
                except TypeError:
                     # Hiç parametre almıyordur
                     form_instance = FormSinifi()
            
            # 4. MDI Penceresi Olarak Ekle
            sub = self.mdi_area.addSubWindow(form_instance)
            sub.setWindowTitle(form_key)
            sub.showMaximized()
            
            self.status_bar.showMessage(f"Açıldı: {form_key}")

        except (ImportError, ModuleNotFoundError):
            logger.warning(f"Modül henüz hazır değil: {module_path}")
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Yapım Aşamasında 🚧")
            msg_box.setText(f"<h3>{form_key}</h3>")
            msg_box.setInformativeText("Bu modül şu anda geliştirme aşamasındadır.")
            msg_box.setIcon(QMessageBox.Information)
            msg_box.exec()
            self.status_bar.showMessage("Modül henüz aktif değil.")

        except AttributeError:
            logger.warning(f"Sınıf bulunamadı: {class_name} -> {module_path}")
            QMessageBox.information(self, "Hata", f"Sınıf tanımı eksik: {class_name}")

        except Exception as e:
            logger.error(f"Beklenmeyen hata: {e}")
            QMessageBox.critical(self, "Sistem Hatası", f"Beklenmedik bir hata oluştu:\n{str(e)}")

# -----------------------------------------------------------------------------
# PROGRAM YÖNETİCİSİ (CONTROLLER)
# -----------------------------------------------------------------------------
class ProgramYoneticisi:
    def __init__(self):
        self.login_window = None
        self.main_window = None

    def baslat(self):
        """Uygulamayı Login ekranı ile başlatır."""
        try:
            # Login penceresini oluştur
            self.login_window = LoginPenceresi()
            # Sinyal bağlantısı: Login başarılı olunca ana_pencereyi_ac çalışacak
            self.login_window.giris_basarili.connect(self.ana_pencereyi_ac)
            self.login_window.show()
        except Exception as e:
            QMessageBox.critical(None, "Başlatma Hatası", f"Login ekranı açılamadı:\n{e}")
            sys.exit(1)

    def ana_pencereyi_ac(self, rol, tc_kimlik):
        """Login başarılı olduğunda tetiklenir."""
        try:
            # 1. Yetkileri Yükle
            YetkiYoneticisi.yetkileri_yukle(rol)
            
            # 2. Ana Pencereyi Başlat
            self.main_window = AnaPencere(yetki=rol, kullanici_adi=tc_kimlik)
            self.main_window.showMaximized()
            
            # 3. Login penceresi referansını temizle (zaten kapandı)
            self.login_window = None
            
        except Exception as e:
            QMessageBox.critical(None, "Hata", f"Ana pencere yüklenemedi:\n{e}")
            sys.exit(1)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # --- TEMANIN UYGULANMASI ---
    try:
        TemaYonetimi.uygula_fusion_dark(app)
    except:
        pass
    
    # Yönetici Sınıfı ile Başlat
    yonetici = ProgramYoneticisi()
    yonetici.baslat()
    
    sys.exit(app.exec())