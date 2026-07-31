# On-Premise LLM Belge Analizi — Araştırma Raporu & PoC

> %100 yerel çalışan, açık kaynak LLM tabanlı PDF belge analiz çözümü.
> Hiçbir bulut servisi veya API kullanılmaz — tüm işlem cihaz üzerinde gerçekleşir.

## İçindekiler

- [Proje Özeti](#proje-özeti)
- [Teknoloji Karşılaştırmaları](#teknoloji-karşılaştırmaları)
  - [PDF Parser / Layout Analiz Araçları](#pdf-parser--layout-analiz-araçları)
  - [OCR Motorları](#ocr-motorları)
  - [Yerel LLM / VLM Modelleri (Temmuz 2026)](#yerel-llm--vlm-modelleri-temmuz-2026)
  - [Model Runtime](#model-runtime)
- [Seçilen Mimari](#seçilen-mimari)
- [Standart JSON Şeması](#standart-json-şeması)
- [Kurulum](#kurulum)
- [Kullanım](#kullanım)
- [Performans Gözlemleri](#performans-gözlemleri)
- [Donanım Önerileri](#donanım-önerileri)
- [Sınırlamalar](#sınırlamalar)
- [İyileştirme Yol Haritası](#i̇yileştirme-yol-haritası)
- [Lisanslar](#lisanslar)
- [Referanslar](#referanslar)

---

## 🎯 Proje Özeti

- **Amaç:** Kurum içi (on-premise) çalışacak, veri gizliliğini maksimum seviyede tutan bir belge analiz pipeline'ı (Proof of Concept - PoC) geliştirmek.
- **Hedef:** PDF formatındaki (native veya scanned) karmaşık belgeleri alıp, tüm belge tipleri için standartlaştırılmış tek bir formata sahip yapılandırılmış JSON çıktısı üretmek.
- **Kısıtlar:** 
  - %100 yerel (on-premise) çalışmalı, dışarıya hiçbir veri gönderilmemeli.
  - Açık kaynak kodlu ve tercihen ticari kullanıma uygun (Apache 2.0 / MIT) lisanslara sahip olmalı.
  - Apple Silicon (M serisi) işlemcili ve minimum 16 GB Birleşik Belleğe (Unified Memory) sahip cihazlar üzerinde çalışabilmeli.
- **Stack:** Docling (Belge ayrıştırma) + Qwen3-VL 8B (Çok modlu dil modeli) + Ollama (Çıkarım motoru).

---

## 📊 Teknoloji Karşılaştırmaları

Bu PoC'nin temel taşlarını oluşturacak teknolojileri belirlemek için mevcut açık kaynak ekosistemi (Temmuz 2026 itibarıyla) detaylı şekilde incelenmiştir.

### 📄 PDF Parser / Layout Analiz Araçları

Görsel ve metinsel karmaşıklık içeren PDF dosyalarından (tablolar, çoklu sütunlar, başlıklar) anlamlı veri çıkarmak, LLM'in başarılı olabilmesi için en kritik aşamadır.

| Araç | Lisans | Tablo Çıkarımı | OCR Desteği | MPS/GPU Desteği | Avantaj | Dezavantaj | Sonuç |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Docling 2.x** | Apache 2.0 | Native ve Gelişmiş | ocrmac, EasyOCR, Tesseract | Var (MPS hızlandırma) | IBM tarafından geliştirilmiş çok güçlü layout anlama kapasitesi, temiz Markdown/JSON çıktısı, modern mimari. | İlk kurulumda model indirmesi gerektirir, bağımlılıkları görece büyük. | ✅ **SEÇİLDİ** |
| **Marker** | GPL | Çok İyi | Tesseract/Surya | Var | Yüksek kaliteli Markdown çıktısı üretir. Formül ve tabloları iyi ayrıştırır. | GPL lisansı ticari kullanımda (proprietary projeler için) hukuki risk yaratır. | ❌ Elendi |
| **MinerU** | Apache 2.0 | İyi | Var | Var | Bilimsel makaleler ve formüller (LaTeX) için optimize edilmiştir. | CJK (Çince/Japonca) odaklı gelişmiştir, Latin/Türkçe dillerinde optimizasyon eksikleri olabilir, ağır bağımlılıklar. | ❌ Elendi |
| **Unstructured** | Çeşitli | Temel/Orta | Var | Sınırlı (Lokal) | Kurumsal dünyada yaygın, ekosistem entegrasyonu (LangChain vb.) mükemmel. | Açık kaynak (lokal) versiyonu kısıtlıdır. En iyi özellikleri cloud/API tarafında çalışır. | ❌ Elendi |
| **PyMuPDF** | AGPL | Yok (Ham metin) | Tesseract entegrasyonu var | Yok (CPU tabanlı) | Çok hızlı metin/görsel çıkarma, düşük seviye PDF kontrolü. | Kendi başına layout analizi yapamaz (sütunları karıştırır), AGPL lisans kısıtı. | ❌ Elendi |

### 🔍 OCR Motorları

Eğer belge "Scanned" (taranmış) ise, sayfa üzerindeki piksellerin metne dönüştürülmesi için yerel bir OCR motoruna ihtiyaç duyulmaktadır.

| Motor | Platform | Kurulum | Hız | İngilizce Kalitesi | Türkçe Kalitesi | Neden / Değerlendirme |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **ocrmac** | Sadece macOS | Sıfır (Native) | Çok Hızlı (M4/MPS) | Mükemmel | Çok İyi | Apple'ın native Vision framework'ünü kullanır. Apple Silicon üzerinde rakipsiz hız ve kalite sunar. | ✅ **SEÇİLDİ** |
| **EasyOCR** | Cross-platform | Pip ile kolay | Yavaş (CPU) / Hızlı (GPU) | İyi | İyi | PyTorch tabanlıdır, başarılıdır ancak CPU'da ağır çalışır. GPU gerektirir. | ❌ Alternatif |
| **Tesseract** | Cross-platform | Sistem paketi gerektirir | Hızlı | Orta/İyi | Orta | Yılların standardı. En geniş dil desteğine sahip ancak layout karmaşıklaştıkça doğruluğu düşer. | ❌ Elendi |
| **RapidOCR** | Cross-platform | Orta | Hızlı | İyi | İyi | PaddleOCR'ın C++ portudur. Hızlıdır ancak ek bağımlılık yönetimleri zordur. | ❌ Elendi |
| **PaddleOCR** | Cross-platform | Ağır (PyTorch) | Orta | İyi | Mükemmel | Türkçe model desteği çok iyidir ancak model boyutları ve kurulum süreçleri çok ağırdır. | ❌ Elendi |

### 🧠 Yerel LLM / VLM Modelleri (Temmuz 2026)

Belgeleri analiz edip içlerinden standart bir JSON yapısına uygun veri çıkarmak (Extraction) için "Structured Outputs" yeteneği olan çok modlu (Multimodal/VLM) bir modele ihtiyaç vardır. Apple Silicon (M1/M2/M3/M4) cihazlarda 16 GB RAM ile çalışabilmesi için 4-bit (q4) kuantize modeller tercih edilmiştir.

| Model | Boyut (q4) | Context Window | Lisans | Multimodal | JSON Structured | Neden / Değerlendirme |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Qwen3-VL 8B** | 6.1 GB | 256K | Apache 2.0 | Evet (VLM + LLM) | Native Destekli | Çok uzun bağlam penceresi, mükemmel görsel zeka ve tablo okuma, Apache lisansı. 16 GB RAM'de rahat çalışır. | ✅ **SEÇİLDİ** |
| **Llama 3.2 Vision 11B** | 7.8 GB | 128K | Llama Community (AB Kısıtlı) | Evet | Var | Performansı çok iyi ancak model bir tık daha büyük ve lisansında ticari kullanım veya bölge (AB) kısıtlamaları var. | ❌ Elendi |
| **Gemma 3 12B** | 8.1 GB | 128K | Gemma Terms (Ticari kısıt) | Evet | Var | Başarılı bir model ancak 16 GB cihazlar için (işletim sistemine RAM payı bırakıldığında) sınırda/ağır. | ❌ Elendi |
| **granite3.2-vision 2B** | 1.7 GB | 16K | Apache 2.0 | Evet | Var | Çok hafif ve hızlı. Ancak 16K bağlam sınırı uzun belgelerde yetersiz kalmasına neden olur. | ❌ Elendi |
| **MiniCPM-V 2.6** | 4.5 GB | 32K | Apache 2.0 | Evet | Var | Eski nesil, HuggingFace kaydı vs. gerektiriyor. Qwen3-VL'nin gerisinde kalıyor. | ❌ Elendi |
| **Qwen3-VL 4B** | 3.3 GB | 256K | Apache 2.0 | Evet | Native Destekli | 8B'nin ağır geldiği düşük donanımlı eski cihazlar için ideal yedek plan (Fallback). | 🟡 **Yedek** |

### ⚙️ Model Runtime

Modeli bellek üzerinde tutup, API üzerinden sorgulamak ve özellikle "JSON-Schema" zorlaması (Grammar-constrained decoding) yapmak için bir sunucu katmanı gereklidir.

| Runtime | Kurulum | JSON Schema / Structured | Apple Silicon (MPS) | Batch İşleme | Neden / Değerlendirme |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Ollama** | Tek komut (Çok kolay) | Native / Mükemmel | Var (Metal/MPS tam destek) | Sınırlı/Yok | Geliştirici dostu, CLI araçları çok pratik, JSON şema dayatması sorunsuz çalışıyor. | ✅ **SEÇİLDİ** |
| **llama.cpp** | Derleme gerektirebilir | Var (Grammar dosyası ile) | Var | Sınırlı | Alt yapısal olarak Ollama'nın temelidir ancak tek başına kullanıldığında API yönetimi ve otomasyon zorlukları yaratır. | ❌ Alternatif |
| **vLLM** | Zor / Konteyner bazlı | Var (Outlines ile) | Yok (NVIDIA GPU İster) | Mükemmel | Üretim seviyesi ve çoklu istek (high throughput) için harikadır. Ancak Apple Silicon desteği eksiktir. | ❌ Elendi (Bu PoC için) |
| **MLX (Apple)** | Python paketi (Pip) | Yok / Çok Deneysel | Mükemmel (Native) | Yok | Apple tarafından geliştirildiği için M-Serisinde çok hızlıdır, ancak Structured Output desteği eksiktir. | ❌ Elendi |

---

## 🏗️ Seçilen Mimari

Pipeline (Veri Boru Hattı) baştan sona veri sızıntısı olmadan yerel cihazda çalışacak şekilde tasarlanmıştır.

```text
PDF Input (Kullanıcı Tarafından Sağlanan Belge)
  │
  ├─> [Adım 1] PyMuPDF ile Hızlı Tarama: 
  │      Belgede metin katmanı (Text Layer) var mı? (Native vs Scanned tespiti)
  │
  ├─> [Adım 2A] Eğer Native ise (Dijital olarak oluşturulmuş):
  │      └─> Docling CPU/MPS üzerinde çalışır
  │          -> Gelişmiş Layout Analizi ve Tablo Çıkarımı
  │          -> Çıktı: Temiz Markdown veya DocTags formatı
  │
  ├─> [Adım 2B] Eğer Scanned ise (Taranmış görsel):
  │      └─> Docling + ocrmac OCR entegrasyonu devreye girer
  │          -> Görüntülerden metin çıkarılır (macOS Vision Framework)
  │          -> Sayfa PNG'leri oluşturularak Qwen3-VL'ye multimodal girdi olarak hazırlanır (VLM Görsel Anlama).
  │
  ├─> [Adım 3] İçerik Birleştirme:
  │      Docling'den gelen yapısal Markdown metni ve (gerekiyorsa) sayfa görselleri LLM için tek bir prompt haline getirilir.
  │
  ├─> [Adım 4] Qwen3-VL 8B + Ollama Çıkarımı:
  │      Ollama'nın "Structured Outputs" yeteneği sayesinde Qwen3-VL modeli, metni serbest bırakmak yerine zorunlu bir JSON-Schema'ya uydurarak çıktı üretmeye zorlanır (Grammar-constrained decoding).
  │
  └─> [Adım 5] Pydantic Doğrulama:
         Ollama'dan dönen JSON, uygulamanın Pydantic modellerinden geçirilir. Tip doğrulamaları yapılır.
         -> Nihai Sonuç: Standart, doğrulanmış JSON dosyası.
```

**Mimari Rasyonel:**
Qwen3-VL gibi güçlü modeller PDF'leri doğrudan resim olarak alıp işleyebilir ancak, *Docling* ile ön ayrıştırma yapmak token tüketimini optimize eder, tabloların yapısını korur ve VLM'nin (Vision Language Model) halüsinasyon görme ihtimalini dramatik şekilde azaltır.

---

## 📋 Standart JSON Şeması

Tüm belge tiplerini tek bir genel çatı altında (Polimorfik) toplayabilmek için aşağıdaki Pydantic V2 yapısı tasarlanmıştır.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "DocumentAnalysisResult",
  "type": "object",
  "properties": {
    "metadata": {
      "type": "object",
      "properties": {
        "file_name": { "type": "string" },
        "page_count": { "type": "integer" },
        "processing_time_seconds": { "type": "number" },
        "document_type": {
          "type": "string",
          "enum": ["INVOICE", "CONTRACT", "REPORT", "FORM", "OTHER"],
          "description": "Otomatik tespit edilen belge kategorisi"
        },
        "confidence_score": {
          "type": "number",
          "minimum": 0,
          "maximum": 1,
          "description": "Modelin veriye duyduğu güven (0-1 arası)"
        }
      },
      "required": ["file_name", "page_count", "document_type", "confidence_score"]
    },
    "entities": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "key": { "type": "string", "description": "Örn: sirket_adi, toplam_tutar" },
          "value": { "type": ["string", "number", "boolean", "null"] },
          "type": { "type": "string", "enum": ["string", "date", "currency", "number"] }
        },
        "required": ["key", "value", "type"]
      },
      "description": "Belgeden çıkarılan anahtar-değer çiftleri"
    },
    "tables": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "table_title": { "type": "string" },
          "columns": { "type": "array", "items": { "type": "string" } },
          "rows": {
            "type": "array",
            "items": { "type": "object", "additionalProperties": true }
          }
        }
      },
      "description": "Belgedeki yapısal tablolar ve satırları"
    },
    "summary": {
      "type": "string",
      "description": "Belgenin 1-2 cümlelik kısa özeti"
    }
  },
  "required": ["metadata", "entities", "summary"]
}
```

### Örnek Çıktı (Fatura Analizi)

```json
{
  "metadata": {
    "file_name": "fatura_ornek_01.pdf",
    "page_count": 1,
    "processing_time_seconds": 24.5,
    "document_type": "INVOICE",
    "confidence_score": 0.98
  },
  "entities": [
    { "key": "fatura_no", "value": "INV-2026-98765", "type": "string" },
    { "key": "fatura_tarihi", "value": "2026-07-25", "type": "date" },
    { "key": "satici_unvan", "value": "Acme Teknoloji A.Ş.", "type": "string" },
    { "key": "toplam_tutar", "value": 14500.50, "type": "currency" }
  ],
  "tables": [
    {
      "table_title": "Hizmet ve Ürün Kalemleri",
      "columns": ["Sıra", "Ürün", "Miktar", "Birim Fiyat", "Toplam"],
      "rows": [
        { "Sıra": "1", "Ürün": "Sunucu Bakım", "Miktar": "2", "Birim Fiyat": "5000", "Toplam": "10000" },
        { "Sıra": "2", "Ürün": "Lisans Yenileme", "Miktar": "1", "Birim Fiyat": "4500.50", "Toplam": "4500.50" }
      ]
    }
  ],
  "summary": "Acme Teknoloji A.Ş. tarafından kesilmiş, 14,500.50 TL değerinde sunucu bakım ve lisans yenileme faturası."
}
```

---
