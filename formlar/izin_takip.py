# -*- coding: utf-8 -*-
import sys
import os
import logging
import time
from datetime import datetime

# PySide6 Kütüphaneleri
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QTableWidgetItem, QPushButton, QDateEdit, 
                               QComboBox, QLineEdit, QProgressBar, QGroupBox, 
                               QHeaderView, QMessageBox, QApplication, QMenu)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt, QDate, QThread, Signal

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# --- MODÜLLER ---
try:
    from araclar.yetki_yonetimi import YetkiYoneticisi
    from araclar.ortak_araclar import OrtakAraclar, show_info, show_error, show_question, pencereyi_kapat, kayitlari_getir, satir_ekle
    from temalar.tema import TemaYonetimi
    from google_baglanti import veritabani_getir
except ImportError as e:
    print(f"Modül Hatası: {e}")

logging.basicConfig(level=logging.INFO)

# ================= WORKERLAR =================

class IzinGecmisiWorker(QThread):
    veri_indi = Signal(list)
    
    def __init__(self, tc_no):
        super().__init__()
        self.tc_no = tc_no 

    def run(self):
        try:
            tum_izinler = kayitlari_getir(veritabani_getir, 'personel', 'izin_giris')
            personel_izinleri = []
            if tum_izinler:
                for x in tum_izinler:
                    p_id = str(x.get('personel_id', '')).strip()
                    if p_id == str(self.tc_no).strip():
                        personel_izinleri.append(x)
            self.veri_indi.emit(personel_izinleri)
        except Exception as e: 
            self.veri_indi.emit([])

class IzinKayitWorker(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)
    
    def __init__(self, veri):
        super().__init__()
        self.veri = veri # [Id, Hizmet_Sinifi, personel_id, Ad_Soyad, izin_tipi, Başlama_Tarihi, Gun, Bitiş_Tarihi, Durum]

    def run(self):
        try:
            # 1. MÜKERRERLİK KONTROLÜ
            personel_id = str(self.veri[2]).strip()
            yeni_baslama = str(self.veri[5]).strip()
            
            tum_izinler = kayitlari_getir(veritabani_getir, 'personel', 'izin_giris')
            
            if tum_izinler:
                for kayit in tum_izinler:
                    durum = str(kayit.get('Durum', '')).strip()
                    
                    # 🟢 ÖNEMLİ GÜNCELLEME: Eğer izin zaten iptal edilmişse çakışma sayma!
                    if durum == "İptal Edildi":
                        continue

                    mevcut_id = str(kayit.get('personel_id', '')).strip()
                    mevcut_baslama = str(kayit.get('Başlama_Tarihi', '')).strip()
                    
                    if mevcut_id == personel_id and mevcut_baslama == yeni_baslama:
                        raise Exception(f"Bu personelin {yeni_baslama} tarihinde aktif bir izin kaydı zaten mevcut!")

            # 2. Kayıt İşlemi
            basari = satir_ekle(veritabani_getir, 'personel', 'izin_giris', self.veri)
            if basari: 
                self.islem_tamam.emit()
            else: 
                raise Exception("Kayıt işlemi başarısız oldu (API hatası).")
        except Exception as e: 
            self.hata_olustu.emit(str(e))

# 🟢 YENİ WORKER: İPTAL İŞLEMİ İÇİN
class IzinIptalWorker(QThread):
    islem_tamam = Signal()
    hata_olustu = Signal(str)
    
    def __init__(self, kayit_id):
        super().__init__()
        self.kayit_id = kayit_id

    def run(self):
        try:
            ws = veritabani_getir('personel', 'izin_giris')
            cell = ws.find(str(self.kayit_id)) # ID'ye göre satırı bul
            
            if cell:
                # Durum sütununu bul (Başlıklardan 'Durum'u arıyoruz)
                basliklar = ws.row_values(1)
                try:
                    # Google Sheets index 1'den başlar, python list 0'dan. +1 ekliyoruz.
                    col_idx = basliklar.index("Durum") + 1
                except ValueError:
                    # Eğer Durum başlığı yoksa son sütun varsayalım (Riskli ama yedek plan)
                    col_idx = 9 
                
                ws.update_cell(cell.row, col_idx, "İptal Edildi")
                self.islem_tamam.emit()
            else:
                raise Exception("İlgili kayıt veritabanında bulunamadı.")
        except Exception as e:
            self.hata_olustu.emit(str(e))

# ================= ANA FORM =================

class IzinTakipPenceresi(QWidget):
    def __init__(self, personel_data, yetki='viewer', kullanici_adi=None):
        super().__init__()
        self.p_data = personel_data 
        self.tc_no = str(personel_data[0]) 
        self.ad_soyad = str(personel_data[1])
        
        try: self.hizmet_sinifi = str(personel_data[4])
        except IndexError: self.hizmet_sinifi = "Belirtilmemiş"
        
        self.setWindowTitle(f"İzin Girişi - {self.ad_soyad}")
        self.resize(1000, 600)
        self._setup_ui()
        self._verileri_yukle()
        
        YetkiYoneticisi.uygula(self, "izin_takip")

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        
        # --- SOL PANEL ---
        sol_panel = QGroupBox(f"Yeni İzin ({self.hizmet_sinifi})")
        sol_layout = QVBoxLayout(sol_panel)
        sol_layout.setSpacing(15)
        
        self.cmb_tur = OrtakAraclar.create_combo_box(sol_panel)
        self.cmb_tur.addItems(["Yıllık İzin", "Rapor", "Mazeret İzni", "Ücretsiz İzin", "İdari İzin", "Ölüm İzni", "Evlilik İzni"])
        
        self.dt_baslama = QDateEdit(QDate.currentDate())
        self.dt_baslama.setCalendarPopup(True); self.dt_baslama.setDisplayFormat("dd.MM.yyyy")
        self.dt_baslama.setMinimumHeight(40)
        
        self.dt_bitis = QDateEdit(QDate.currentDate().addDays(1))
        self.dt_bitis.setCalendarPopup(True); self.dt_bitis.setDisplayFormat("dd.MM.yyyy")
        self.dt_bitis.setMinimumHeight(40)
        
        self.lbl_gun = QLabel("Süre: 1 Gün")
        self.lbl_gun.setStyleSheet("color: #60cdff; font-weight: bold; font-size: 16px; margin-top: 5px;")
        
        self.dt_baslama.dateChanged.connect(self._gun_hesapla)
        self.dt_bitis.dateChanged.connect(self._gun_hesapla)
        
        self.btn_kaydet = OrtakAraclar.create_button(sol_panel, "💾 İzni Kaydet", self._kaydet)
        self.btn_kaydet.setObjectName("btn_kaydet")

        sol_layout.addWidget(QLabel("İzin Tipi:"))
        sol_layout.addWidget(self.cmb_tur)
        sol_layout.addWidget(QLabel("Başlama Tarihi:"))
        sol_layout.addWidget(self.dt_baslama)
        sol_layout.addWidget(QLabel("Bitiş Tarihi (İşe Başlama):"))
        sol_layout.addWidget(self.dt_bitis)
        sol_layout.addWidget(self.lbl_gun)
        sol_layout.addStretch()
        sol_layout.addWidget(self.btn_kaydet)
        
        # --- SAĞ PANEL ---
        sag_panel = QGroupBox("İzin Geçmişi")
        sag_layout = QVBoxLayout(sag_panel)
        
        headers = ["Id", "İzin Tipi", "Başlama", "Bitiş", "Gün", "Durum"]
        self.table = OrtakAraclar.create_table(self, headers)
        
        # ID sütununu gizle (Kullanıcı görmesin ama biz kullanalım)
        self.table.setColumnHidden(0, True)
        
        # 🟢 SAĞ TIK MENÜSÜ AKTİF
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._sag_tik_menu)
        
        sag_layout.addWidget(self.table)
        
        main_layout.addWidget(sol_panel, 35)
        main_layout.addWidget(sag_panel, 65)
        
        self.progress = QProgressBar(self)
        self.progress.setVisible(False)
        self.progress.setStyleSheet("QProgressBar {border: 0px; background-color: transparent;} QProgressBar::chunk {background-color: #60cdff;}")
        self.progress.setGeometry(0, 0, self.width(), 4)

    def _gun_hesapla(self):
        d1 = self.dt_baslama.date()
        d2 = self.dt_bitis.date()
        gun = d1.daysTo(d2)
        if gun <= 0: 
            self.lbl_gun.setText("⚠️ Hatalı Tarih!")
            self.lbl_gun.setStyleSheet("color: #e81123; font-weight: bold; font-size: 16px;")
            self.btn_kaydet.setEnabled(False)
        else:
            self.lbl_gun.setText(f"Süre: {gun} Gün")
            self.lbl_gun.setStyleSheet("color: #60cdff; font-weight: bold; font-size: 16px;")
            self.btn_kaydet.setEnabled(True)

    def _verileri_yukle(self):
        self.progress.setVisible(True)
        self.table.setRowCount(0)
        self.worker = IzinGecmisiWorker(self.tc_no)
        self.worker.veri_indi.connect(self._tablo_doldur)
        self.worker.start()

    def _tablo_doldur(self, veri):
        self.progress.setVisible(False)
        if not veri: return
        
        self.table.setRowCount(len(veri))
        for i, row in enumerate(reversed(veri)):
            # Id, İzin Tipi, Başlama, Bitiş, Gün, Durum
            self.table.setItem(i, 0, QTableWidgetItem(str(row.get('Id', '')))) # Gizli Sütun
            self.table.setItem(i, 1, QTableWidgetItem(str(row.get('izin_tipi', ''))))
            self.table.setItem(i, 2, QTableWidgetItem(str(row.get('Başlama_Tarihi', ''))))
            self.table.setItem(i, 3, QTableWidgetItem(str(row.get('Bitiş_Tarihi', ''))))
            self.table.setItem(i, 4, QTableWidgetItem(str(row.get('Gun', ''))))
            
            durum = str(row.get('Durum', ''))
            item_durum = QTableWidgetItem(durum)
            
            # Renklendirme
            if durum == "İşlendi": 
                item_durum.setForeground(Qt.green)
            elif durum == "İptal Edildi": 
                item_durum.setForeground(Qt.red)
                # İptal edilen satırı komple gri yapalım (Görsel ayrım için)
                for col in range(6):
                    item = self.table.item(i, col)
                    if item: item.setForeground(Qt.gray)
            else: 
                item_durum.setForeground(Qt.yellow)
            
            self.table.setItem(i, 5, item_durum)

    # 🟢 SAĞ TIK MENÜSÜ
    def _sag_tik_menu(self, pos):
        row = self.table.currentRow()
        if row < 0: return
        
        # Durumu kontrol et
        item_durum = self.table.item(row, 5)
        durum = item_durum.text() if item_durum else ""
        
        menu = QMenu()
        
        if durum != "İptal Edildi":
            act_iptal = QAction("🚫 İzni İptal Et", self)
            act_iptal.triggered.connect(lambda: self._iptal_et(row))
            menu.addAction(act_iptal)
        else:
            act_bilgi = QAction("ℹ️ Bu izin iptal edilmiş.", self)
            act_bilgi.setEnabled(False)
            menu.addAction(act_bilgi)
            
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # 🟢 İPTAL İŞLEMİ
    def _iptal_et(self, row):
        if show_question("Onay", "Seçili izin kaydı 'İptal Edildi' olarak işaretlenecek.\nEmin misiniz?", self):
            kayit_id = self.table.item(row, 0).text() # Gizli ID sütunundan alıyoruz
            
            self.progress.setVisible(True)
            self.i_worker = IzinIptalWorker(kayit_id)
            self.i_worker.islem_tamam.connect(lambda: (show_info("Başarılı", "İzin iptal edildi.", self), self._verileri_yukle()))
            self.i_worker.hata_olustu.connect(lambda e: (show_error("Hata", e, self), self.progress.setVisible(False)))
            self.i_worker.start()

    def _kaydet(self):
        if not self.btn_kaydet.isEnabled(): return
        self.btn_kaydet.setEnabled(False)
        self.progress.setVisible(True)
        
        unique_id = int(time.time())
        gun_sayisi = self.dt_baslama.date().daysTo(self.dt_bitis.date())
        
        veri_listesi = [
            unique_id,
            self.hizmet_sinifi,
            self.tc_no,
            self.ad_soyad,
            self.cmb_tur.currentText(),
            self.dt_baslama.date().toString("dd.MM.yyyy"),
            gun_sayisi,
            self.dt_bitis.date().toString("dd.MM.yyyy"),
            "İşlendi"
        ]
        
        self.k_worker = IzinKayitWorker(veri_listesi)
        self.k_worker.islem_tamam.connect(self._kayit_basarili)
        self.k_worker.hata_olustu.connect(self._kayit_hata)
        self.k_worker.start()

    def _kayit_basarili(self):
        show_info("Başarılı", "İzin kaydı başarıyla oluşturuldu.", self)
        self._verileri_yukle()
        self.btn_kaydet.setEnabled(True)

    def _kayit_hata(self, mesaj):
        show_error("Hata", f"Kayıt sırasında hata oluştu:\n{mesaj}", self)
        self.progress.setVisible(False)
        self.btn_kaydet.setEnabled(True)

if __name__ == "__main__":
    app = QApplication([])
    try: TemaYonetimi.uygula_fusion_dark(app)
    except: pass
    win = IzinTakipPenceresi(["11111111111", "Ahmet Yılmaz", "", "", "Teknik Hizmetler"])
    win.show()
    app.exec()