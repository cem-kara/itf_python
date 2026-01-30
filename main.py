# -*- coding: utf-8 -*-
import sys
import os
import json
import importlib
import logging
from functools import partial

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMdiArea, QMdiSubWindow, 
    QWidget, QVBoxLayout, QHBoxLayout, QStatusBar, 
    QFrame, QPushButton, QMessageBox, QToolBox
)
from PySide6.QtCore import Qt

# --- LOGLAMA AYARLARI ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Main")

# --- YOL AYARLARI (PATH) ---
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# --- İMPORTLAR ---
from araclar.yetki_yonetimi import YetkiYoneticisi
from araclar.ortak_araclar import pencereyi_kapat, show_toast # show_toast eklendi
from google_baglanti import GoogleBaglantiSinyalleri # Sinyalci eklendi
from temalar.tema import TemaYonetimi
from formlar.login import LoginPenceresi    

# =============================================================================
# KONFİGÜRASYON YÜKLEYİCİ
# =============================================================================
def ayarlari_yukle():
    """ayarlar.json dosyasından menü yapılandırmasını okur."""
    config_path = os.path.join(current_dir, 'ayarlar.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("menu_yapilandirma", {})
    except FileNotFoundError:
        logger.error("ayarlar.json bulunamadı! Menü oluşturulamıyor.")
        return {}
    except json.JSONDecodeError:
        logger.error("ayarlar.json formatı hatalı!")
        return {}

# -----------------------------------------------------------------------------
# ANA PENCERE SINIFI
# -----------------------------------------------------------------------------
class AnaPencere(QMainWindow):
    def __init__(self, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.yetki = yetki
        self.kullanici_adi = kullanici_adi
        
        self.setWindowTitle(f"ITF Python Yönetim Sistemi (v1.1) - {self.yetki.upper()}")
        self.resize(1280, 800)

        # Menü yapılandırmasını yükle
        self.menu_data = ayarlari_yukle()
        
        # UI Kurulumu
        self._setup_ui()
        
        # Durum Çubuğu
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(f"Hoşgeldiniz: {self.kullanici_adi} ({self.yetki})")

        # --- YETKİ KURALINI UYGULA ---
        YetkiYoneticisi.form_yetkilerini_uygul(self, "main_window")
        # Google Bağlantı Sinyallerini Dinle
        GoogleBaglantiSinyalleri.get_instance().hata_olustu.connect(self._google_hatasi_yakala)

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
        # CSS artık tema.py'dan gelmeli ama burada container için inline bırakıyoruz
        self.sidebar_container.setStyleSheet("QFrame#sidebar { background-color: #2b2b2b; border-right: 1px solid #3e3e3e; }")
        
        sidebar_layout = QVBoxLayout(self.sidebar_container)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # QToolBox (Akordeon Bileşeni)
        self.toolbox = QToolBox()
        
        # --- JSON verisinden Menü Oluşturma ---
        if not self.menu_data:
            logger.warning("Menü verisi boş! ayarlar.json dosyasını kontrol edin.")
            
        for grup_baslik, elemanlar in self.menu_data.items():
            page_widget = QWidget()
            page_layout = QVBoxLayout(page_widget)
            page_layout.setContentsMargins(5, 10, 5, 10)
            page_layout.setSpacing(5)
            page_layout.setAlignment(Qt.AlignTop)

            for item in elemanlar:
                baslik = item.get("baslik", "Adsız")
                modul = item.get("modul")
                sinif = item.get("sinif")
                
                if not modul or not sinif:
                    continue

                btn = QPushButton(f"  {baslik}")
                btn.setCursor(Qt.PointingHandCursor)
                
                # Dinamik ve güvenli objectName üretimi (Yetki sistemi için kritik)
                safe_name = "btn_" + baslik.lower().replace(" ", "_").replace("ç","c").replace("ğ","g").replace("ı","i").replace("ö","o").replace("ş","s").replace("ü","u")
                btn.setObjectName(safe_name)

                # Buton nesnesini sınıfa kaydet (self.btn_dashboard gibi erişim için)
                setattr(self, safe_name, btn) 
                
                btn.setStyleSheet("""
                    QPushButton {
                        text-align: left;
                        padding: 8px;
                        border: none;
                        background-color: transparent;
                        color: #cccccc;
                        border-radius: 4px;
                    }
                    QPushButton:hover { background-color: #3e3e3e; color: white; }
                """)
                
                # Modül ve Sınıf bilgisini form_ac fonksiyonuna gönder
                btn.clicked.connect(partial(self.form_ac, baslik, modul, sinif))
                page_layout.addWidget(btn)

            self.toolbox.addItem(page_widget, grup_baslik)

        sidebar_layout.addWidget(self.toolbox)
        
        # Çıkış Butonu
        self.btn_cikis = QPushButton(" Çıkış Yap") 
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

    def form_ac(self, baslik, modul_yolu, sinif_adi):
        """
        Dinamik Form Açıcı
        Parametreler JSON'dan gelir, böylece kod değişikliği gerekmez.
        """
        # 1. Form zaten açık mı kontrol et
        for sub in self.mdi_area.subWindowList():
            if sub.windowTitle() == baslik:
                self.mdi_area.setActiveSubWindow(sub)
                return

        self.status_bar.showMessage(f"Yükleniyor: {baslik}...")

        try:
            # 2. Modülü Dinamik İçe Aktar
            modul = importlib.import_module(modul_yolu)
            
            # 3. Sınıfı Bul ve Örnekle
            if not hasattr(modul, sinif_adi):
                raise AttributeError(f"Modül içinde '{sinif_adi}' sınıfı bulunamadı.")
                
            FormSinifi = getattr(modul, sinif_adi)
            
            # Parametre aktarımı denemesi
            try:
                form_instance = FormSinifi(yetki=self.yetki, kullanici_adi=self.kullanici_adi)
            except TypeError:
                try:
                    form_instance = FormSinifi(yetki=self.yetki)
                except TypeError:
                    form_instance = FormSinifi()
            
            # 4. MDI Penceresi Olarak Ekle
            sub = self.mdi_area.addSubWindow(form_instance)
            sub.setWindowTitle(baslik)
            sub.showMaximized()
            
            self.status_bar.showMessage(f"Açıldı: {baslik}")

        except (ImportError, ModuleNotFoundError) as e:
            logger.warning(f"Modül yükleme hatası ({modul_yolu}): {e}")
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Yapım Aşamasında 🚧")
            msg_box.setText(f"<h3>{baslik}</h3>")
            msg_box.setInformativeText(f"Bu modül henüz sisteme yüklenmedi veya yolu hatalı.\n\nHata: {str(e)}")
            msg_box.setIcon(QMessageBox.Information)
            msg_box.exec()
            self.status_bar.showMessage("Modül yüklenemedi.")

        except Exception as e:
            logger.error(f"Beklenmeyen hata ({baslik}): {e}")
            QMessageBox.critical(self, "Sistem Hatası", f"Beklenmedik bir hata oluştu:\n{str(e)}")
    
    def _google_hatasi_yakala(self, baslik, mesaj):
        """Google servislerinden gelen hataları Toast olarak gösterir."""
        logger.error(f"Google Bağlantı Hatası: {baslik} - {mesaj}")
        show_toast(f"{baslik}: {mesaj}", type="error", duration=5000)

    def form_ac(self, modül_adi, sinif_adi, baslik):
        """Mevcut form_ac metodunu Toast ile modernize edin."""
        try:
            # ... (mevcut yükleme kodları) ...
            logger.info(f"Form açıldı: {baslik}")
            show_toast(f"{baslik} yüklendi", type="info") # Bilgi bildirimi
        except Exception as e:
            self.hata_mesaji_goster(f"{baslik} açılırken hata", e)

# -----------------------------------------------------------------------------
# PROGRAM YÖNETİCİSİ
# -----------------------------------------------------------------------------
class ProgramYoneticisi:
    def __init__(self):
        self.login_window = None
        self.main_window = None

    def baslat(self):
        try:
            self.login_window = LoginPenceresi()
            self.login_window.giris_basarili.connect(self.ana_pencereyi_ac)
            self.login_window.show()
        except Exception as e:
            QMessageBox.critical(None, "Başlatma Hatası", f"Login ekranı açılamadı:\n{e}")
            sys.exit(1)

    def ana_pencereyi_ac(self, rol, tc_kimlik):
        try:
            YetkiYoneticisi.yetkileri_yukle(rol)
            self.main_window = AnaPencere(yetki=rol, kullanici_adi=tc_kimlik)
            self.main_window.showMaximized()
            self.login_window = None
        except Exception as e:
            QMessageBox.critical(None, "Hata", f"Ana pencere yüklenemedi:\n{e}")
            sys.exit(1)
    def hata_mesaji_goster(self, baslik, e):
        error_text = str(e)
        logger.error(f"{baslik}: {error_text}", exc_info=True)
        # Kritik hatalarda QMessageBox kalabilir, ancak yanına Toast ekleyelim
        show_toast("Bir hata oluştu!", type="error")
        QMessageBox.critical(self, baslik, f"İşlem sırasında bir hata oluştu:\n{error_text}")

        
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    try:
        TemaYonetimi.uygula_fusion_dark(app)
    except:
        pass
    
    yonetici = ProgramYoneticisi()
    yonetici.baslat()
    
    sys.exit(app.exec())