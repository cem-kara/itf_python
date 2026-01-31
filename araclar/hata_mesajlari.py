# araclar/hata_mesajlari.py (YENİ)
class KullanicidostuHataMesajlari:
    
    HATA_MESAJLARI = {
        'gspread.exceptions.SpreadsheetNotFound': 
            "📋 Veritabanı dosyasına erişilemiyor.\n"
            "Lütfen Google Drive bağlantınızı kontrol edin.",
        
        'google.auth.exceptions.RefreshError':
            "🔐 Oturumunuzun süresi doldu.\n"
            "Lütfen programı yeniden başlatın.",
        
        'requests.exceptions.ConnectionError':
            "🌐 İnternet bağlantısı kurulamıyor.\n"
            "Lütfen ağ bağlantınızı kontrol edin.",
        
        'ValueError':
            "⚠️ Girdiğiniz veri hatalı.\n"
            "Lütfen bilgileri kontrol edip tekrar deneyin."
    }
    
    @staticmethod
    def kullanici_mesaji(exception: Exception) -> str:
        """Teknik hatayı kullanıcı dostu mesaja çevir"""
        exc_type = type(exception).__name__
        module = exception.__class__.__module__
        full_name = f"{module}.{exc_type}" if module != 'builtins' else exc_type
        
        # Bilinen hata mı?
        if full_name in KullanicidostuHataMesajlari.HATA_MESAJLARI:
            return KullanicidostuHataMesajlari.HATA_MESAJLARI[full_name]
        
        # Genel mesaj
        return (
            f"⚠️ Beklenmeyen bir hata oluştu.\n\n"
            f"Hata Kodu: {exc_type}\n"
            f"Lütfen sistem yöneticisine başvurun."
        )

# Kullanım:
try:
    ws = veritabani_getir('personel', 'Personel')
except Exception as e:
    logger.error(f"Veritabanı hatası: {e}", exc_info=True)  # Teknik log
    mesaj = KullanicidostuHataMesajlari.kullanici_mesaji(e)  # Kullanıcı mesajı
    QMessageBox.critical(self, "İşlem Başarısız", mesaj)