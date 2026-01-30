# -*- coding: utf-8 -*-
import sys
import os
import threading
import logging # STANDART EKLEME
from datetime import datetime
from google_baglanti import veritabani_getir

# Standart Python Logger Tanımı
logger = logging.getLogger(__name__)

class LogYoneticisi:
    """
    Tüm modüller için merkezi loglama sistemi.
    İşlemleri arka planda (Thread) yaparak arayüzü dondurmaz.
    """
    
    @staticmethod
    def log_ekle(modul, islem, detay, kullanici="Sistem"):
        """
        Log kaydı oluşturur.
        
        Parametreler:
        - modul: İşlemin yapıldığı yer (Örn: "Personel", "FHSZ", "RKE", "Cihaz")
        - islem: Yapılan ana işlem (Örn: "Ekleme", "Güncelleme", "Silme", "Hesaplama")
        - detay: İşlemin sözel açıklaması (Örn: "Ahmet, Ayşe'nin soyadını değiştirdi.")
        - kullanici: İşlemi yapan kişi
        """
        # İşlemi ayrı bir thread'de başlat (UI donmasın)
        try:
            t = threading.Thread(target=LogYoneticisi._log_gonder_thread, args=(modul, islem, detay, kullanici))
            t.daemon = True # Ana program kapanınca bu da kapansın
            t.start()
        except Exception as e:
            # Thread başlatma hatası çok nadirdir ama yakalanmalıdır
            logger.critical(f"Log thread'i baslatilamadi: {e}")

    @staticmethod
    def _log_gonder_thread(modul, islem, detay, kullanici):
        try:
            # 1. Log sayfasına bağlan
            ws = veritabani_getir('sabit', 'Loglar') # Sabitler spreadsheet'inde 'Loglar' sayfası
            
            # Eğer sayfa yoksa oluşturma mantığı google_baglanti içindedir, 
            # ancak biz burada başlık kontrolü yapalım.
            if len(ws.get_all_values()) == 0:
                ws.append_row(["Tarih", "Saat", "Kullanıcı", "Modül", "İşlem", "Detay"])
            
            # 2. Veriyi Hazırla
            simdi = datetime.now()
            tarih = simdi.strftime("%d.%m.%Y")
            saat = simdi.strftime("%H:%M:%S")
            
            # 3. Kaydet
            row = [tarih, saat, kullanici, modul, islem, detay]
            ws.append_row(row)
            
            # Print yerine standart logger kullanıldı
            logger.info(f"BULUT LOG KAYDEDİLDİ: {modul} - {islem}")
            
        except Exception as e:
            # Loglama hatası programı durdurmamalı
            logger.error(f"GOOGLE SHEETS LOG YAZMA HATASI: {e}")