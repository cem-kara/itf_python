# -*- coding: utf-8 -*-
import sys
import os
import time
from datetime import datetime

# PySide6 Kütüphaneleri
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QTextEdit, 
                               QProgressBar, QLabel, QMessageBox, QCheckBox, 
                               QGroupBox, QApplication)
from PySide6.QtCore import Qt, QThread, Signal

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

try:
    from google_baglanti import veritabani_getir, InternetBaglantiHatasi
except ImportError:
    print("Google bağlantı modülü bulunamadı!")

# =============================================================================
# WORKER: BATCH UPDATE (TEK SEFERDE YAZMA) İLE GÜNCELLENMİŞ
# =============================================================================
class DevirWorker(QThread):
    log_sinyali = Signal(str)
    progress_sinyali = Signal(int)
    islem_bitti = Signal()
    
    def run(self):
        try:
            self.log_sinyali.emit("⏳ Veritabanına bağlanılıyor...")
            ws_personel = veritabani_getir('personel', 'Personel')
            ws_izin = veritabani_getir('personel', 'izin_bilgi')
            
            # 1. Verileri Çek (Tüm tabloyu hafızaya al)
            self.log_sinyali.emit("📥 Veriler çekiliyor...")
            
            # get_all_values() tüm tabloyu liste listesi olarak verir [[başlık], [satır1], [satır2]...]
            tum_personel_raw = ws_personel.get_all_values()
            tum_izin_raw = ws_izin.get_all_values()
            
            if len(tum_izin_raw) < 2:
                self.log_sinyali.emit("⚠️ İşlenecek veri bulunamadı.")
                self.islem_bitti.emit()
                return

            # Başlıkları ve Veriyi Ayır
            izin_basliklar = tum_izin_raw[0]
            izin_veriler = tum_izin_raw[1:] # Sadece veri satırları
            
            personel_basliklar = tum_personel_raw[0]
            personel_veriler = tum_personel_raw[1:]

            # Sütun İndekslerini Bul
            def get_idx(headers, name):
                try: return headers.index(name)
                except: return -1

            # İzin Tablosu İndeksleri
            idx_tc = get_idx(izin_basliklar, "TC_Kimlik")
            idx_devir = get_idx(izin_basliklar, "Yillik_Devir")
            idx_hakedis = get_idx(izin_basliklar, "Yillik_Hakedis")
            idx_toplam = get_idx(izin_basliklar, "Yillik_Toplam_Hak")
            idx_kul = get_idx(izin_basliklar, "Yillik_Kullanilan")
            idx_kalan = get_idx(izin_basliklar, "Yillik_Kalan")

            # Personel Tablosu İndeksleri
            p_idx_tc = get_idx(personel_basliklar, "Kimlik_No")
            p_idx_baslama = get_idx(personel_basliklar, "Baslama_Tarihi") # Veya sizin tablodaki adı neyse

            if -1 in [idx_tc, idx_devir, idx_hakedis, idx_toplam, idx_kul, idx_kalan, p_idx_tc]:
                self.log_sinyali.emit("❌ Sütun başlıkları bulunamadı! Lütfen veritabanı yapısını kontrol edin.")
                self.islem_bitti.emit()
                return

            # Personel Başlama Tarihlerini Haritala (Hız için)
            baslama_map = {}
            for p in personel_veriler:
                try: baslama_map[str(p[p_idx_tc]).strip()] = str(p[p_idx_baslama])
                except: pass

            self.log_sinyali.emit("⚙️ Hesaplamalar yapılıyor...")
            
            # --- HAFIZADA İŞLEME (API YOK, SADECE MATEMATİK) ---
            guncellenmis_veriler = []
            
            for i, row in enumerate(izin_veriler):
                # Orijinal satırın kopyasını al (Veri kaybını önlemek için)
                yeni_row = list(row)
                
                tc = str(row[idx_tc]).strip()
                
                # Personel verisi yoksa satırı olduğu gibi bırak
                if tc not in baslama_map:
                    guncellenmis_veriler.append(yeni_row)
                    continue

                try:
                    # Mevcut Değerleri Al
                    eski_hakedis = int(row[idx_hakedis]) if str(row[idx_hakedis]).isdigit() else 0
                    # Kalan, formülle hesaplanmış olabilir veya manuel olabilir. Güvenli int dönüşümü:
                    try: mevcut_kalan = int(float(str(row[idx_kalan]).replace(',', '.')))
                    except: mevcut_kalan = 0

                    # 1. Yeni Devir Hesabı
                    yeni_devir = min(mevcut_kalan, eski_hakedis)
                    
                    # 2. Yeni Hakediş Hesabı
                    hizmet_yili = self._hizmet_yili_hesapla(baslama_map.get(tc))
                    yeni_hakedis = 30 if hizmet_yili >= 10 else (20 if hizmet_yili > 0 else 0)
                    
                    # 3. Yeni Toplamlar
                    yeni_toplam_hak = yeni_devir + yeni_hakedis
                    yeni_kullanilan = 0 # Sıfırla
                    yeni_kalan = yeni_toplam_hak

                    # 4. Listeyi Güncelle
                    yeni_row[idx_devir] = yeni_devir
                    yeni_row[idx_hakedis] = yeni_hakedis
                    yeni_row[idx_toplam] = yeni_toplam_hak
                    yeni_row[idx_kul] = yeni_kullanilan
                    yeni_row[idx_kalan] = yeni_kalan
                    
                    guncellenmis_veriler.append(yeni_row)
                    
                    # Log (Her 10 kişide bir yaz ki log şişmesin)
                    if i % 10 == 0:
                        self.log_sinyali.emit(f"işleniyor... {tc}")

                except Exception as e:
                    self.log_sinyali.emit(f"Hata ({tc}): {e}")
                    guncellenmis_veriler.append(row) # Hata olursa eskiyi koru

                # Progress Bar
                self.progress_sinyali.emit(int((i+1)/len(izin_veriler)*100))

            # --- TEK SEFERDE YAZMA (BATCH UPDATE) ---
            self.log_sinyali.emit("📤 Güncellemeler buluta gönderiliyor (Bu işlem birkaç saniye sürebilir)...")
            
            # A2 hücresinden başlayarak tüm veriyi yapıştır
            # range_name "A2" dediğimizde gspread otomatik olarak verinin boyutuna göre alanı genişletir
            ws_izin.update("A2", guncellenmis_veriler)
            
            self.log_sinyali.emit("✅ Tüm veriler başarıyla güncellendi!")
            self.islem_bitti.emit()

        except Exception as e:
            self.log_sinyali.emit(f"❌ KRİTİK HATA: {str(e)}")
            self.islem_bitti.emit()

    def _hizmet_yili_hesapla(self, tarih_str):
        try:
            for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    baslama = datetime.strptime(str(tarih_str), fmt)
                    bugun = datetime.now()
                    return bugun.year - baslama.year - ((bugun.month, bugun.day) < (baslama.month, baslama.day))
                except: continue
            return 0
        except: return 0

# =============================================================================
# GUI SINIFI
# =============================================================================
class YilSonuDevirYoneticisi(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Yıl Sonu Devir İşlemleri")
        self.resize(600, 500)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        grp_uyari = QGroupBox("⚠️ DİKKAT")
        grp_uyari.setStyleSheet("QGroupBox { border: 1px solid #e81123; border-radius: 5px; margin-top: 10px; font-weight: bold; color: #e81123; }")
        v_uyari = QVBoxLayout(grp_uyari)
        
        lbl_bilgi = QLabel(
            "Bu işlem YILDA BİR KEZ (Yılbaşında) yapılmalıdır.\n"
            "Tüm personelin izin bakiyeleri yeniden hesaplanıp Google Sheets'e TEK SEFERDE yazılacaktır.\n\n"
            "- Eski Devirler Silinir.\n"
            "- Kullanılmayan haklar yeni devir olur.\n"
            "- Yeni yıl hakedişleri eklenir.\n"
            "- 'Kullanılan' sütunu sıfırlanır."
        )
        lbl_bilgi.setWordWrap(True)
        lbl_bilgi.setStyleSheet("color: #cccccc; font-weight: normal;")
        v_uyari.addWidget(lbl_bilgi)
        
        self.chk_onay = QCheckBox("Riskleri anladım, işlemi onaylıyorum.")
        self.chk_onay.setStyleSheet("color: #e81123; font-weight: bold;")
        self.chk_onay.stateChanged.connect(self._onay_degisti)
        v_uyari.addWidget(self.chk_onay)
        
        layout.addWidget(grp_uyari)
        
        layout.addWidget(QLabel("İşlem Logları:"))
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Consolas;")
        layout.addWidget(self.txt_log)
        
        self.pbar = QProgressBar()
        self.pbar.setValue(0)
        self.pbar.setVisible(False)
        self.pbar.setStyleSheet("QProgressBar::chunk { background-color: #e81123; }")
        layout.addWidget(self.pbar)
        
        self.btn_baslat = QPushButton("🚀 DEVİR İŞLEMİNİ BAŞLAT")
        self.btn_baslat.setFixedHeight(50)
        self.btn_baslat.setEnabled(False)
        self.btn_baslat.setStyleSheet("background-color: #333; color: #aaa; font-weight: bold; font-size: 14px;")
        self.btn_baslat.clicked.connect(self._islemi_baslat)
        layout.addWidget(self.btn_baslat)

    def _onay_degisti(self):
        if self.chk_onay.isChecked():
            self.btn_baslat.setEnabled(True)
            self.btn_baslat.setStyleSheet("background-color: #e81123; color: white; font-weight: bold; font-size: 14px;")
        else:
            self.btn_baslat.setEnabled(False)
            self.btn_baslat.setStyleSheet("background-color: #333; color: #aaa; font-weight: bold; font-size: 14px;")

    def _islemi_baslat(self):
        self.btn_baslat.setEnabled(False)
        self.chk_onay.setEnabled(False)
        self.pbar.setVisible(True)
        self.txt_log.clear()
        
        self.worker = DevirWorker()
        self.worker.log_sinyali.connect(self.txt_log.append)
        self.worker.progress_sinyali.connect(self.pbar.setValue)
        self.worker.islem_bitti.connect(self._islem_bitti)
        self.worker.start()

    def _islem_bitti(self):
        self.chk_onay.setChecked(False)
        self.chk_onay.setEnabled(True)
        QMessageBox.information(self, "Bilgi", "İşlem tamamlandı.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = YilSonuDevirYoneticisi()
    win.show()
    sys.exit(app.exec())