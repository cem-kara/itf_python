# -*- coding: utf-8 -*-
import numpy as np
import bisect
from datetime import timedelta

# --- YARDIMCI METİN FONKSİYONLARI ---
def tr_upper(text):
    """Türkçe karakter destekli büyük harfe çevirme."""
    if not isinstance(text, str):
        return str(text).upper()
    return text.replace('i', 'İ').replace('ı', 'I').replace('ğ', 'Ğ').replace('ü', 'Ü').replace('ş', 'Ş').replace('ö', 'Ö').replace('ç', 'Ç').upper()

# --- HESAPLAMA MANTIĞI ---
def sua_hak_edis_hesapla(toplam_saat):
    """
    Fiili hizmet süresi zammı (Şua) gün sayısını hesaplar.
    30 tane if-else bloğu yerine 'bisect' algoritması kullanılarak optimize edilmiştir.
    """
    try:
        saat = float(toplam_saat)
    except (ValueError, TypeError):
        return 0

    # TANIMLAMA: [Eşik Saat, Hak Edilen Gün]
    # Mantık: Solundaki saate ulaştığı an sağındaki günü hak eder.
    # Örn: 1100 saati geçince 25 gün olur.
    # Bu liste FHSZ yönetmeliğindeki tablonun karşılığıdır.
    # 50'şer artan kısım formülize edilebilir ama 1000'den sonraki düzensiz artışlar için tablo en garantisidir.
    
    araliklar = [0, 50, 100, 150, 200, 250, 300, 350, 400, 450, 
                 500, 550, 600, 650, 700, 750, 800, 850, 900, 950, 
                 1000, 1100, 1200, 1300, 1400, 1450]
    
    haklar =    [0, 1,  2,   3,   4,   5,   6,   7,   8,   9, 
                 10, 11, 12,  13,  14,  15,  16,  17,  18,  19, 
                 20,   25,   26,   28,   29,   30]

    # Bisect right, saatin hangi aralığa düştüğünü bulur.
    # Index 0 gelirse (50'den küçük) -> haklar[0-1] yani listenin sonuna gider, bunu engellemek için max(0, idx-1) kullanırız.
    idx = bisect.bisect_right(araliklar, saat)
    
    if idx == 0: return 0
    if idx > len(haklar): return 30 # 1450 üzeri
    
    return haklar[idx - 1]

def is_gunu_hesapla(baslangic, bitis, tatil_listesi=None):
    """
    İki tarih arasındaki iş günlerini hesaplar.
    Hafta sonları ve verilen tatil listesi düşülür.
    """
    if tatil_listesi is None:
        tatil_listesi = []
        
    try:
        dates_start = baslangic.strftime('%Y-%m-%d')
        # Bitiş günü dahil olsun diye +1 gün eklenir
        dates_end = (bitis + timedelta(days=1)).strftime('%Y-%m-%d')
        
        # '1111100' -> Pzt-Cum çalışılır (1), Cmt-Paz tatil (0)
        workdays = np.busday_count(dates_start, dates_end, weekmask='1111100', holidays=tatil_listesi)
        return int(workdays)
    except:
        return 0