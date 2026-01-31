# -*- coding: utf-8 -*-
import logging
import os
import datetime
from typing import Tuple, List, Dict, Optional

try:
    from repositories.personel_repository import PersonelRepository
    from google_baglanti import veritabani_getir_cached, GoogleDriveService
    from araclar.log_yonetimi import LogYoneticisi
except ImportError:
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from repositories.personel_repository import PersonelRepository
    from google_baglanti import veritabani_getir_cached, GoogleDriveService
    from araclar.log_yonetimi import LogYoneticisi

logger = logging.getLogger("PersonelService")

class PersonelService:
    def __init__(self):
        self.repo = PersonelRepository()
        self.drive_service = None 

    def _get_drive_service(self):
        """Drive servisini ihtiyaç duyulduğunda başlatır (Lazy Loading)."""
        if not self.drive_service:
            self.drive_service = GoogleDriveService()
        return self.drive_service

    # =========================================================================
    # 1. VERİ OKUMA METOTLARI (Listeleme ve Seçim)
    # =========================================================================

    def personel_listesi_getir(self, force_refresh: bool = False) -> List[Dict]:
        """
        Tüm personel listesini Repository üzerinden çeker.
        Liste ekranı için gereklidir.
        """
        try:
            return self.repo.get_all(force_refresh=force_refresh)
        except Exception as e:
            logger.error(f"Personel listesi alma hatası: {e}")
            return []

    def sabit_degerleri_getir(self, kriter_kodu: str) -> List[str]:
        """Sabitler tablosundan Koda göre MenuEleman listesi döner."""
        try:
            tum_sabitler = veritabani_getir_cached('sabit', 'Sabitler')
            liste = [
                str(row.get('MenuEleman')).strip()
                for row in tum_sabitler 
                if row.get('Kod') == kriter_kodu and row.get('MenuEleman')
            ]
            return sorted(list(set(liste)))
        except Exception as e:
            logger.error(f"Sabit değer hatası ({kriter_kodu}): {e}")
            return []

    def benzersiz_degerleri_getir(self, kolon_adi: str) -> List[str]:
        """Personel tablosundan benzersiz verileri döner (Autocomplete için)."""
        try:
            tum_personel = self.repo.get_all(force_refresh=False)
            degerler = [
                str(row.get(kolon_adi)).strip()
                for row in tum_personel 
                if row.get(kolon_adi)
            ]
            return sorted(list(set(degerler)))
        except Exception as e:
            logger.error(f"Benzersiz değer hatası ({kolon_adi}): {e}")
            return []

    def drive_klasor_id_getir(self, klasor_adi: str) -> Optional[str]:
        """
        Sabitlerden Drive Klasör ID'sini çeker.
        Yapı: Kod='Sistem_DriveID' -> MenuEleman='Personel_Resim' -> Aciklama='ID'
        """
        try:
            tum_sabitler = veritabani_getir_cached('sabit', 'Sabitler')
            for row in tum_sabitler:
                if str(row.get('Kod')) == 'Sistem_DriveID' and str(row.get('MenuEleman')) == klasor_adi:
                    drive_id = str(row.get('Aciklama')).strip()
                    if drive_id and len(drive_id) > 10:
                        return drive_id
            return None
        except Exception as e:
            logger.error(f"Drive ID hatası: {e}")
            return None

    # =========================================================================
    # 2. İŞLEM METOTLARI (Kayıt ve Güncelleme)
    # =========================================================================

    def personel_ekle(self, veri: Dict, dosyalar: Dict, kullanici_adi: str) -> Tuple[bool, str]:
        """
        Yeni personel kaydeder ve dosyaları yükler.
        """
        try:
            # 1. Kontrol
            tc = veri.get('Kimlik_No')
            if self.repo.get_by_tc(tc):
                return False, f"{tc} numaralı personel zaten kayıtlı."

            # 2. Drive Yükleme
            drive = self._get_drive_service()
            ID_RESIM = self.drive_klasor_id_getir("Personel_Resim")
            ID_DOSYA = self.drive_klasor_id_getir("Personel_Dosya")
            
            yuklenen_linkler = {}
            for tip, yol in dosyalar.items():
                if yol and os.path.exists(yol):
                    hedef_id = ID_RESIM if tip == 'Resim' else ID_DOSYA
                    if hedef_id:
                        ext = os.path.splitext(yol)[1]
                        isim = f"{tc}_{tip}{ext}"
                        link = drive.upload_file(yol, hedef_id, custom_name=isim)
                        if link: yuklenen_linkler[tip] = link

            # Linkleri Veriye Ekle
            veri['Resim'] = yuklenen_linkler.get('Resim', '')
            veri['Diploma1'] = yuklenen_linkler.get('Diploma1', '')
            veri['Diploma2'] = yuklenen_linkler.get('Diploma2', '')
            veri['Ozluk_Dosyasi'] = yuklenen_linkler.get('Ozluk_Dosyasi', '')

            # 3. Veri Sıralaması (Sheet Sütun Sırası)
            kayit_sirasi = [
                veri.get('Kimlik_No'),
                veri.get('Ad_Soyad'),
                veri.get('Dogum_Yeri'),
                veri.get('Dogum_Tarihi'),
                veri.get('Hizmet_Sinifi'),
                veri.get('Kadro_Unvani'),
                veri.get('Gorev_Yeri'),
                veri.get('Kurum_Sicil_No'),
                veri.get('Memuriyete_Baslama_Tarihi'),
                veri.get('Cep_Telefonu'),
                veri.get('E_posta'),
                veri.get('Mezun_Olunan_Okul'),
                veri.get('Mezun_Olunan_Fakülte'),
                veri.get('Mezuniyet_Tarihi'),
                veri.get('Diploma_No'),
                veri.get('Diploma1'),
                veri.get('Mezun_Olunan_Okul_2'),
                veri.get('Mezun_Olunan_Fakülte_2'),
                veri.get('Mezuniyet_Tarihi_2'),
                veri.get('Diploma_No_2'),
                veri.get('Diploma2'),
                veri.get('Resim'),
                veri.get('Ozluk_Dosyasi'),
                veri.get('Durum', 'Aktif'),
                veri.get('Ayrılış_Tarihi', ''),
                veri.get('Ayrılma_Nedeni', '')
            ]
            
            self.repo.create(kayit_sirasi)
            LogYoneticisi.log_ekle("Personel", "Ekleme", f"{veri['Ad_Soyad']} eklendi.", kullanici_adi)
            return True, "Kayıt başarılı."

        except Exception as e:
            logger.error(f"Kayıt hatası: {e}")
            return False, f"Hata: {e}"

    def personel_durum_guncelle(self, tc_kimlik: str, yeni_durum: str) -> Tuple[bool, str]:
        """
        Personelin durumunu (Aktif/Pasif) günceller.
        Liste ekranı sağ tık menüsü için gereklidir.
        """
        try:
            # Sadece 'Durum' alanını içeren sözlük gönderiyoruz
            basarili = self.repo.update(tc_kimlik, {'Durum': yeni_durum})
            
            if basarili:
                LogYoneticisi.log_ekle("Personel", "Guncelleme", f"{tc_kimlik} durumu {yeni_durum} yapıldı.", "Sistem")
                return True, "Durum güncellendi."
            else:
                return False, "Güncelleme yapılamadı (Kayıt bulunamadı veya hata)."
        except Exception as e:
            logger.error(f"Durum güncelleme hatası: {e}")
            return False, f"Hata: {e}"
    
    # ... (Mevcut kodlar) ...

    def izin_gecmisi(self, tc_kimlik: str) -> List[Dict]:
        return self.repo.izin_gecmisi_getir(tc_kimlik)

    def izin_kaydet(self, veri_listesi: List) -> Tuple[bool, str]:
        """
        İzni kaydeder ve bakiyeyi düşer.
        veri_listesi: [Id, Sinif, TC, Ad, Tip, Baslama, Gun, Bitis, Durum]
        """
        try:
            tc = str(veri_listesi[2])
            izin_tipi = str(veri_listesi[4])
            gun = int(veri_listesi[6])
            
            # 1. Kayıt
            self.repo.izin_ekle(veri_listesi)
            
            # 2. Bakiye Düşme (Basit Mantık)
            kolon = ""
            if "Yıllık" in izin_tipi: kolon = "Yillik_Kullanilan"
            elif "Şua" in izin_tipi or "Sua" in izin_tipi: kolon = "Sua_Kullanilan"
            else: kolon = "Rapor_Mazeret_Top"
            
            if kolon:
                self.repo.bakiye_guncelle(tc, kolon, gun, islem="dus")
                
            return True, "İzin kaydedildi."
        except Exception as e:
            return False, f"Hata: {e}"

    def izin_iptal_et(self, kayit_id: str, tc: str, izin_tipi: str, gun: int) -> Tuple[bool, str]:
        """İzni iptal eder ve bakiyeyi iade eder."""
        try:
            # 1. Durum Güncelle
            if self.repo.izin_durum_guncelle(kayit_id, "İptal Edildi"):
                # 2. İade
                kolon = ""
                if "Yıllık" in izin_tipi: kolon = "Yillik_Kullanilan"
                elif "Şua" in izin_tipi or "Sua" in izin_tipi: kolon = "Sua_Kullanilan"
                else: kolon = "Rapor_Mazeret_Top"
                
                if kolon:
                    self.repo.bakiye_guncelle(tc, kolon, gun, islem="iade")
                
                return True, "İzin iptal edildi."
            return False, "İzin bulunamadı."
        except Exception as e:
            return False, f"Hata: {e}"