# -*- coding: utf-8 -*-
import re

class Validator:
    """
    Veri doğrulama işlemlerini yürüten yardımcı sınıf.
    Statik metodlar içerir, doğrudan çağrılabilir.
    """

    @staticmethod
    def validate_tc(tc_no: str) -> tuple[bool, str]:
        """
        TC Kimlik Numarası algoritma ve biçim kontrolü.
        Return: (Geçerli_Mi, Hata_Mesajı)
        """
        if not tc_no:
            return False, "TC Kimlik Numarası boş olamaz."
        
        if not tc_no.isdigit():
            return False, "TC Kimlik Numarası sadece rakamlardan oluşmalıdır."
        
        if len(tc_no) != 11:
            return False, "TC Kimlik Numarası 11 haneli olmalıdır."
        
        if tc_no[0] == '0':
            return False, "TC Kimlik Numarası 0 ile başlayamaz."
            
        # Algoritma Kontrolü
        try:
            digits = [int(d) for d in tc_no]
            d1, d2, d3, d4, d5, d6, d7, d8, d9, d10, d11 = digits
            
            # 10. Hane: ((Tekler * 7) - Çiftler) % 10
            odd_sum = d1 + d3 + d5 + d7 + d9
            even_sum = d2 + d4 + d6 + d8
            check_10 = ((odd_sum * 7) - even_sum) % 10
            
            # 11. Hane: (İlk 10 hane toplamı) % 10
            check_11 = sum(digits[:10]) % 10
            
            if check_10 != d10 or check_11 != d11:
                return False, "Geçersiz TC Kimlik Numarası (Algoritma Hatası)."
        except:
            return False, "TC Kimlik doğrulama sırasında hata oluştu."
            
        return True, ""

    @staticmethod
    def validate_phone(phone: str) -> tuple[bool, str]:
        """
        Türk Telefon Numarası kontrolü.
        Kabul edilen formatlar: 05XX... veya 5XX... (10 veya 11 hane)
        """
        if not phone:
            return True, "" # Zorunlu değilse boş geçebilir
            
        # Sadece rakamları al
        clean_phone = re.sub(r'[^0-9]', '', phone) 
        
        if len(clean_phone) == 11 and clean_phone.startswith('05'):
            return True, ""
        elif len(clean_phone) == 10 and clean_phone.startswith('5'):
            return True, ""
        else:
            return False, "Telefon numarası '05XX ...' formatında olmalıdır."

    @staticmethod
    def validate_email(email: str) -> tuple[bool, str]:
        """
        Standart E-posta format kontrolü.
        """
        if not email:
            return True, ""
            
        # Basit ve etkili regex deseni
        pattern = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
        
        if re.match(pattern, email):
            return True, ""
        else:
            return False, "Geçersiz E-posta adresi formatı."