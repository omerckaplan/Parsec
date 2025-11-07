Parsec üzerinden oyun yayını yaparken çalışan HSV tabanlı renk algılama ve triggerbot sistemi.

✨ Özellikler

- 🎮 Parsec Uyumlu**: Parsec pencerelerini otomatik algılar ve hedefler
- 🎨 HSV Renk Algılama**: Özelleştirilebilir renk aralıkları (Mor, Kırmızı, Sarı presetleri)
- 🎯 Hedefleme Modları**: Baş veya gövde hedefleme seçenekleri
- ⚡ Yüksek Performans**: 30-200 FPS arası ayarlanabilir tarama hızı
- 🔧 Özelleştirilebilir tarama alanı
- 🤖 Otomatik Hedefleme
- 🌙 Kullanıcı dostu arayüz

## 📋 Gereksinimler

- Windows 10/11
- Python 3.8+
- Parsec uygulaması

## 🚀 Kurulum

1. Gereksinimleri yükleyin:
```bash
pip install -r requirements.txt
```

2. Uygulamayı başlatın:
```bash
python parsec_trigger.py
```

## 📖 Kullanım

1. **Parsec'i başlatın** ve oyun yayınını açın
2. **triggerbot'u çalıştırın** - Parsec penceresi otomatik algılanacak
3. **Renk ayarlarını yapın** - HSV değerlerini hedef renge göre ayarlayın veya preset kullanın
4. **"Etkin"** kutusunu işaretleyin

### 🎨 Renk Ayarları

Oyundaki düşman rengine göre HSV değerlerini ayarlayın:

- **Mor (Purple)**: Valorant için varsayılan
- **Kırmızı (Red)**: Kırmızı takım işaretleri
- **Sarı (Yellow)**: Özel işaretlemeler

### ⚙️ Ayarlar

- **FOV**: Tarama alanı boyutu
- **Target FPS**: Tarama hızı
- **Hedef**: Baş veya gövde hedefleme

## 🔧 Nasıl Çalışır?

1. **Pencere Algılama**: Parsec penceresini otomatik bulur
2. **Ekran Yakalama**: Parsec penceresinin merkez bölgesini tarar
3. **Renk Filtreleme**: HSV uzayında belirlenen renkleri algılar
4. **Hedef Hesaplama**: En büyük renk alanını hedef olarak seçer
