import asyncio
from edge_tts import Communicate

async def test():
    text = "Привет, я нормально говорю по-русски? Проверим ударения: коме́дия, жи́знь, досто́йно."
    comm = Communicate(text, voice="ru-RU-DmitryNeural")
    await comm.save("test_russian.mp3")
    print("Готово. Проверь файл test_russian.mp3")

asyncio.run(test())
