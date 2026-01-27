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
# WORKER: BATCH UPDATE (TEK SEFERDE YAZMA)
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
            
            # 1. Verileri Çek
            self.log_sinyali.emit("📥 Veriler çekiliyor...")
            tum_personel_raw = ws_personel.get_all_values()
            tum_izin_raw = ws_izin.get_all_values()
            
            if len(tum_izin_raw) < 2:
                self.log_sinyali.emit("⚠️ İşlenecek veri bulunamadı.")
                self.islem_bitti.emit()
                return

            # Başlıkları ve Veriyi Ayır
            izin_basliklar = tum_izin_raw[0]
            izin_veriler = tum_izin_raw[1:]
            
            personel_basliklar = tum_personel_raw[0]
            personel_veriler = tum_personel_raw[1:]

            # --- SÜTUN İNDEKSLERİNİ BUL ---
            def get_idx(headers, name):
                try: return headers.index(name)
                except: return -1

            # Yıllık İzin
            idx_tc = get_idx(izin_basliklar, "TC_Kimlik")
            idx_devir = get_idx(izin_basliklar, "Yillik_Devir")
            idx_hakedis = get_idx(izin_basliklar, "Yillik_Hakedis")
            idx_toplam = get_idx(izin_basliklar, "Yillik_Toplam_Hak")
            idx_kul = get_idx(izin_basliklar, "Yillik_Kullanilan")
            idx_kalan = get_idx(izin_basliklar, "Yillik_Kalan")
            
            # Şua İzin (YENİ YAPILANDIRMA)
            idx_sua_hak = get_idx(izin_basliklar, "Sua_Kullanilabilir_Hak")
            idx_sua_kul = get_idx(izin_basliklar, "Sua_Kullanilan")
            idx_sua_kal = get_idx(izin_basliklar, "Sua_Kalan")
            idx_sua_cari = get_idx(izin_basliklar, "Sua_Cari_Yil_Kazanim")

            # Personel Bilgisi
            p_idx_tc = get_idx(personel_basliklar, "Kimlik_No")
            p_idx_baslama = get_idx(personel_basliklar, "Baslama_Tarihi")

            # Kontrol
            if -1 in [idx_tc, idx_devir, idx_hakedis, idx_sua_hak, idx_sua_cari, p_idx_tc]:
                self.log_sinyali.emit("❌ Kritik sütun başlıkları bulunamadı! Veritabanı yapısını kontrol edin.")
                self.islem_bitti.emit()
                return

            # Personel Haritası
            baslama_map = {}
            for p in personel_veriler:
                try: baslama_map[str(p[p_idx_tc]).strip()] = str(p[p_idx_baslama])
                except: pass

            self.log_sinyali.emit("⚙️ Hesaplamalar yapılıyor...")
            guncellenmis_veriler = []
            
            # --- DÖNGÜ VE HESAPLAMA ---
            for i, row in enumerate(izin_veriler):
                yeni_row = list(row) # Kopyala
                tc = str(row[idx_tc]).strip()
                
                if tc not in baslama_map:
                    guncellenmis_veriler.append(yeni_row)
                    continue

                try:
                    # --- A. YILLIK İZİN HESABI ---
                    eski_hakedis = int(row[idx_hakedis]) if str(row[idx_hakedis]).isdigit() else 0
                    try: mevcut_kalan = int(float(str(row[idx_kalan]).replace(',', '.')))
                    except: mevcut_kalan = 0

                    # 1. Yeni Devir (Kalan ile Hakediş'in küçüğü)
                    yeni_devir = min(mevcut_kalan, eski_hakedis)
                    
                    # 2. Yeni Hakediş
                    hizmet_yili = self._hizmet_yili_hesapla(baslama_map.get(tc))
                    yeni_hakedis = 30 if hizmet_yili >= 10 else (20 if hizmet_yili > 0 else 0)
                    
                    # 3. Yıllık İzin Güncelleme
                    yeni_row[idx_devir] = yeni_devir
                    yeni_row[idx_hakedis] = yeni_hakedis
                    yeni_row[idx_toplam] = yeni_devir + yeni_hakedis
                    yeni_row[idx_kul] = 0 # Sıfırla
                    yeni_row[idx_kalan] = yeni_devir + yeni_hakedis

                    # --- B. ŞUA İZNİ HESABI (YENİ MANTIK) ---
                    # Cari yıl kazanımı -> Yeni yıl hakkı olur
                    yeni_sua_hak = int(row[idx_sua_cari]) if str(row[idx_sua_cari]).isdigit() else 0
                    
                    # Şua İzin Güncelleme
                    yeni_row[idx_sua_hak] = yeni_sua_hak # Cari -> Hak oldu
                    yeni_row[idx_sua_kul] = 0            # Sıfırla
                    yeni_row[idx_sua_kal] = yeni_sua_hak # Henüz kullanılmadı
                    yeni_row[idx_sua_cari] = 0           # Yeni yıl için boşalt

                    guncellenmis_veriler.append(yeni_row)
                    
                    if i % 10 == 0: self.log_sinyali.emit(f"işleniyor... {tc}")

                except Exception as e:
                    self.log_sinyali.emit(f"Hata ({tc}): {e}")
                    guncellenmis_veriler.append(row) 

                self.progress_sinyali.emit(int((i+1)/len(izin_veriler)*100))

            # --- TEK SEFERDE YAZMA ---
            self.log_sinyali.emit("📤 Güncellemeler buluta gönderiliyor...")
            ws_izin.update("A2", guncellenmis_veriler)
            
            self.log_sinyali.emit("✅ Yıl sonu devir işlemi başarıyla tamamlandı!")
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
        
        grp_uyari = QGroupBox("⚠️ DİKKAT: YIL SONU İŞLEMİ")
        grp_uyari.setStyleSheet("QGroupBox { border: 1px solid #e81123; border-radius: 5px; margin-top: 10px; font-weight: bold; color: #e81123; }")
        v_uyari = QVBoxLayout(grp_uyari)
        
        lbl_bilgi = QLabel(
            "Bu işlem <b>YILDA BİR KEZ (Yılbaşında)</b> yapılmalıdır.<br><br>"
            "<b>Yapılacak İşlemler:</b><br>"
            "1. <b>Yıllık İzin:</b> Eski devirler silinir, sadece bu yılın artan hakkı devreder.<br>"
            "2. <b>Şua İzni:</b> 'Cari Yıl Kazanım' sütunundaki hak, 'Kullanılabilir Hak'ka taşınır.<br>"
            "3. <b>Genel:</b> Tüm 'Kullanılan' sayaçları sıfırlanır ve yeni yıl hakedişleri eklenir.<br><br>"
            "<i>Lütfen işlemden önce yedek alınız!</i>"
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