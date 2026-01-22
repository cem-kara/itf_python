# -*- coding: utf-8 -*-
import sys
import os

# --- YOL AYARLARI ---
# Bu dosya 'araclar' klasöründe olduğu için kök dizini buluyoruz
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

try:
    from google_baglanti import veritabani_getir
except ImportError:
    print("HATA: google_baglanti modülü bulunamadı.")
    def veritabani_getir(t, s): return None

class YetkiYoneticisi:
    """
    Kullanıcı rollerine göre formlardaki nesneleri (buton, menü vb.) 
    gizleyen veya pasif yapan merkezi sınıf.
    """
    
    # Hafızada tutulacak yetki haritası
    # Yapı: { 'form_kodu': { 'btn_adi': 'GIZLE', 'menu_adi': 'PASIF' } }
    _yetki_cache = {} 
    _aktif_rol = "viewer"

    @staticmethod
    def yetkileri_yukle(aktif_rol):
        """
        Login işlemi sonrası çağrılır. Veritabanından o role ait kısıtlamaları çeker.
        """
        YetkiYoneticisi._aktif_rol = aktif_rol
        YetkiYoneticisi._yetki_cache = {}

        print(f"Yetkiler yükleniyor... Rol: {aktif_rol}")

        try:
            # Sabitler veritabanındaki 'Rol_Yetkileri' sayfasına bağlan
            ws = veritabani_getir('sabit', 'Rol_Yetkileri')
            
            if not ws:
                print("UYARI: 'Rol_Yetkileri' sayfasına erişilemedi veya sayfa yok.")
                return

            records = ws.get_all_records()
            
            count = 0
            for row in records:
                # Veritabanı Sütunları: Rol | Form_Kodu | Oge_Adi | Islem
                db_rol = str(row.get('Rol', '')).strip()
                
                # Sadece şu anki kullanıcının rolüne ait kuralları al
                if db_rol == aktif_rol:
                    form_kodu = str(row.get('Form_Kodu', '')).strip()
                    oge_adi = str(row.get('Oge_Adi', '')).strip()
                    islem = str(row.get('Islem', '')).strip().upper() # GIZLE / PASIF
                    
                    if not form_kodu or not oge_adi:
                        continue

                    # Cache sözlüğünü hazırla
                    if form_kodu not in YetkiYoneticisi._yetki_cache:
                        YetkiYoneticisi._yetki_cache[form_kodu] = {}
                    
                    YetkiYoneticisi._yetki_cache[form_kodu][oge_adi] = islem
                    count += 1
            
            print(f"-> {count} adet kısıtlama kuralı yüklendi.")

        except Exception as e:
            print(f"Yetki yükleme sırasında hata: {e}")

    @staticmethod
    def uygula(form_instance, form_kodu):
        """
        Bir forma (pencereye) yetki kurallarını uygular.
        Formun __init__ veya setup_ui metodunun sonunda çağrılmalıdır.
        
        Args:
            form_instance (self): Formun kendisi (QWidget)
            form_kodu (str): Veritabanındaki 'Form_Kodu' (örn: 'personel_listesi')
        """
        # Eğer bu form için hiç kural yoksa çık
        if form_kodu not in YetkiYoneticisi._yetki_cache:
            return 

        kurallar = YetkiYoneticisi._yetki_cache[form_kodu]

        for oge_adi, islem in kurallar.items():
            # Formun içinde bu isme sahip bir widget var mı?
            if hasattr(form_instance, oge_adi):
                widget = getattr(form_instance, oge_adi)
                
                try:
                    if islem == 'GIZLE':
                        widget.setVisible(False)
                        print(f"Yetki: {form_kodu} -> {oge_adi} GİZLENDİ.")
                        
                    elif islem == 'PASIF':
                        widget.setEnabled(False)
                        print(f"Yetki: {form_kodu} -> {oge_adi} PASİF YAPILDI.")
                        
                except Exception as e:
                    print(f"Hata: {oge_adi} üzerinde işlem yapılamadı. ({e})")
            else:
                # Geliştirici için uyarı (Widget ismini yanlış yazmış olabilirsiniz)
                print(f"UYARI: {form_kodu} formunda '{oge_adi}' isimli bir nesne bulunamadı.")