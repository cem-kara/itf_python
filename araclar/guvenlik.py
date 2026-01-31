# -*- coding: utf-8 -*-
import hashlib


class GuvenlikAraclari:
    @staticmethod
    def sifrele(sifre):
        """
        Verilen şifreyi SHA-256 algoritması ile hashler.
        """
        if not sifre: return ""
        # Şifreyi byte'a çevir
        sifre_bytes = str(sifre).encode('utf-8')
        
        # Hash nesnesi oluştur
        hash_obj = hashlib.sha256(sifre_bytes)
        
        # Hexadecimal string olarak döndür
        return hash_obj.hexdigest()

    @staticmethod
    def dogrula(girilen_sifre, kayitli_hash):
        """
        Girilen düz şifrenin hash'i ile kayıtlı hash'i karşılaştırır.
        """
        girilen_hash = GuvenlikAraclari.sifrele(girilen_sifre)
        return girilen_hash == kayitli_hash