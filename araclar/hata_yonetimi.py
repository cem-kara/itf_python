# -*- coding: utf-8 -*-
"""
Merkezi hata yönetim sistemi
Tüm hata türleri ve yönetimi buradan yapılır
"""
import logging
from typing import Optional, Callable
from PySide6.QtWidgets import QMessageBox, QWidget

logger = logging.getLogger("HataYonetimi")

class HataYoneticisi:
    """Kullanıcı dostu hata mesajları ve loglama"""
    
    # Bilinen hataların kullanıcı dostu mesajları
    HATA_MESAJLARI = {
        'SpreadsheetNotFound': {
            'baslik': '📋 Veritabanı Bulunamadı',
            'mesaj': 'Veritabanı dosyasına erişilemiyor.\n\nLütfen Google Drive bağlantınızı kontrol edin.',
            'seviye': 'critical'
        },
        'RefreshError': {
            'baslik': '🔐 Oturum Süresi Doldu',
            'mesaj': 'Oturumunuzun süresi dolmuş.\n\nLütfen programı yeniden başlatın.',
            'seviye': 'warning'
        },
        'ConnectionError': {
            'baslik': '🌐 Bağlantı Hatası',
            'mesaj': 'İnternet bağlantısı kurulamıyor.\n\nLütfen ağ bağlantınızı kontrol edin.',
            'seviye': 'critical'
        },
        'ValueError': {
            'baslik': '⚠️ Geçersiz Veri',
            'mesaj': 'Girdiğiniz veri formatı hatalı.\n\nLütfen bilgileri kontrol edip tekrar deneyin.',
            'seviye': 'warning'
        },
        'FileNotFoundError': {
            'baslik': '📁 Dosya Bulunamadı',
            'mesaj': 'Gerekli dosya bulunamadı.\n\nLütfen kurulum klasörünü kontrol edin.',
            'seviye': 'critical'
        }
    }
    
    @staticmethod
    def hata_goster(exception: Exception, parent: Optional[QWidget] = None, 
                    ek_bilgi: str = "") -> None:
        """
        Hatayı kullanıcıya göster ve logla
        
        Kullanım:
            try:
                # işlem
            except Exception as e:
                HataYoneticisi.hata_goster(e, self)
        """
        # Hata türünü bul
        hata_adi = type(exception).__name__
        
        # Teknik log (geliştiriciler için)
        logger.error(f"Hata yakalandı: {hata_adi} - {str(exception)}", exc_info=True)
        
        # Kullanıcı mesajını hazırla
        if hata_adi in HataYoneticisi.HATA_MESAJLARI:
            hata_bilgi = HataYoneticisi.HATA_MESAJLARI[hata_adi]
            baslik = hata_bilgi['baslik']
            mesaj = hata_bilgi['mesaj']
            seviye = hata_bilgi['seviye']
        else:
            # Bilinmeyen hata
            baslik = "⚠️ Beklenmeyen Hata"
            mesaj = f"Bir hata oluştu.\n\nHata Kodu: {hata_adi}"
            seviye = 'critical'
        
        # Ek bilgi varsa ekle
        if ek_bilgi:
            mesaj += f"\n\n{ek_bilgi}"
        
        # Kullanıcıya göster
        if seviye == 'critical':
            QMessageBox.critical(parent, baslik, mesaj)
        else:
            QMessageBox.warning(parent, baslik, mesaj)
    
    @staticmethod
    def guvenli_calistir(fonksiyon: Callable, parent: Optional[QWidget] = None,
                        hata_mesaji: str = "İşlem sırasında hata oluştu"):
        """
        Bir fonksiyonu güvenli şekilde çalıştırır
        
        Kullanım:
            def veri_yukle():
                ws = veritabani_getir('personel', 'Personel')
                return ws.get_all_records()
            
            veriler = HataYoneticisi.guvenli_calistir(veri_yukle, self)
        """
        try:
            return fonksiyon()
        except Exception as e:
            HataYoneticisi.hata_goster(e, parent, hata_mesaji)
            return None