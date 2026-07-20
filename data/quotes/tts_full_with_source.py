import asyncio
import json
from pathlib import Path
from edge_tts import Communicate

async def speak_full(text: str, output_path: str):
    clean_text = text.replace("+", "")
    comm = Communicate(clean_text, voice="ru-RU-DmitryNeural")
    await comm.save(output_path)
    print(f"✅ {Path(output_path).name}")

async def main():
    files = ["great_people_quotes.json", "tech_quotes.json", "world_wonder_quotes.json"]
    out_dir = Path("audio_full")
    out_dir.mkdir(exist_ok=True)
    
    for json_file in files:
        print(f"\n📂 Обрабатываю: {json_file}")
        with open(json_file, encoding='utf-8') as f:
            data = json.load(f)
        
        for item in data:
            quote = item.get("quote", "").strip()
            source = item.get("tts_source", "").strip()
            
            if not quote:
                continue
                
            # Формируем полный текст
            full_text = f"«{quote}» — {source}."
            
            filename = out_dir / f"{item['id']}.mp3"
            print(f"   → {item.get('name', item['id'])}")
            await speak_full(full_text, str(filename))

if __name__ == "__main__":
    asyncio.run(main())
