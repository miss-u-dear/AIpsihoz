import os
import re
from openai import AsyncOpenAI
import asyncio
from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam
from dotenv import load_dotenv
from datetime import datetime
from aiogram import Dispatcher, Bot, types
import json
import random

load_dotenv()
client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENAI_API_KEY"),
)
bot = Bot (token= str(os.getenv("TG_TOKEN")))
dp = Dispatcher()
USER_ID = os.getenv("USER_ID")

summary_prompt = ("You're an old acquaintance of mine who's ready to engage in any conversation. Don't be formal with me, use the informal 'you' style. You can joke and tease me as much as you want, but when I ask you, you'll always help and support me. You know everything about me and are ready to discuss anything with me. PLEASE REPLY IN RUSSIAN ONLY. Don't use English, even if I write in it. Don't talk nonsense, but don't be too dry either."
                  "RULES: "
                  "1. POLITENESS IS ONLY A LIMITED USE IN EXTREME CASES OF TROLLING/SYMPATHY"
                  "2. YOU CAN CUSS AND TROLL IF IT'S APPROPRIATE"
                  "3. KEEP YOUR RESPONSIBLE, MAXIMUM 10 WORDS PER MESSAGE. YOU CAN RARELY USE LONG SENTENCES (for example, when I ask you to write something)."
                  "4. WRITE LIKE A REAL PERSON"
                  "5. YOU CAN IGNORE PUNCTUATION IN MOMENTS"
                  "6. DONT USE EMOJIS, JUST TJE RARE ')' AND ETC"
                  "example your answers: \n"
                  "- да забей ты на это че паришься\n"
                  "- ну такое себе если честно)\n"
                  "- го в хойку я хз\n"
                  )


memory_lock = asyncio.Lock()

async def save_memory(text):
    async with memory_lock:
        today = str(datetime.now().date().isoformat())
        data = {}

        if os.path.exists("memory.json"):
            try:
                with open("memory.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                data = {}
        if today not in data:
            data[today] = {"messages": [], "summary": ""}
        data[today]["messages"].append(text)
        if len(data[today]["messages"]) % 5 == 0:
            sum_res = await client.chat.completions.create(
                model="openai/gpt-4o-mini",
            messages = [
                ChatCompletionUserMessageParam(
                    role="user",
                    content=f"Retell it in 15 words: {data[today]['messages']}"
                )
            ],
            max_tokens = 300,
            temperature = 0.4,
            )
            data[today]["summary"] = sum_res.choices[0].message.content
        with open("memory.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

async def random_recall_task():
    while True:
        await asyncio.sleep(432000)
        if random.randint(0, 1) == 1:
            if not os.path.exists("memory.json"): continue
            with open("memory.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                dates = list(data.keys())

            if len(dates) < 2: continue
            past_date = random.choice(dates[:-1])
            past_summary = data[past_date]["summary"]
            days_ago = (datetime.now().date() - datetime.strptime(past_date, "%Y-%m-%d").date()).days
            prompt = f"You have an entry left in your diary for {past_date} ({days_ago} days ago): {past_summary}. Напиши юзеру в своем стиле: 'о, а помнишь ты мне...' "
            response = await client.chat.completions.create(
                model="openai/gpt-4o-mini",
                messages=[
                        ChatCompletionSystemMessageParam(
                            role="system",
                            content=summary_prompt
                        ),
                        ChatCompletionUserMessageParam(
                            role="user",
                            content=prompt
                        )

                ]
            )
            content = response.choices[0].message.content or ""
            await bot.send_message(str(USER_ID), content.lower())

@dp.message()
async def handle_message(message: types.Message):
    image_url = None
    if message.photo:
        file = await bot.get_file(message.photo[-1].file_id)
        image_url = f"https://api.telegram.org/file/bot{os.getenv('TG_TOKEN')}/{file.file_path}"
    elif message.sticker and not message.sticker.is_animated and not message.sticker.is_video:
        file = await bot.get_file(message.sticker.file_id)
        image_url = f"https://api.telegram.org/file/bot{os.getenv('TG_TOKEN')}/{file.file_path}"
    user_text = message.text or message.caption
    if not user_text and message.sticker:
        user_text = "Я отправил тебе стикер"
    elif not user_text:
        user_text = "Look at picture"
    await save_memory(f"User {user_text}")
    history_context = await get_context(limit_days=10)

    await bot.send_chat_action(message.chat.id, "typing")
    await asyncio.sleep(random.randint(1, 2))

    try:
        user_content: list = [
                {"type": "text", "text": f"Контекст прошлых дней: {history_context}"},
                {"type": "text", "text": user_text}
            ]
        if image_url:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": image_url}
            })
        handler_messages: list = [
            ChatCompletionSystemMessageParam(role="system", content=str(summary_prompt)),
            ChatCompletionUserMessageParam(role="user", content=user_content)
            ]
        response = await client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=handler_messages,
            temperature=0.4
        )

        reply = (response.choices[0].message.content or "").strip()

        if len(reply) < 15:
            await message.answer(reply.lower())
            await save_memory(f"Bot: {reply}")
        else:
            parts = [p.strip() for p in re.split(r'[.!?,]', reply) if len(p.strip()) > 1]
            for part in parts:
                await asyncio.sleep(random.uniform(0.8, 1.5))
                await message.answer(part.lower())
                await save_memory(f"Bot: {part}")
    except Exception as e:
        print(f"Ошибка в handle_message: {e}")
        await message.answer ("смотрим в консоль, произошла ошибка")

async def get_context(limit_days=7):
     async with memory_lock:
        if not os.path.exists("memory.json"):
            return ""

        with open("memory.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        sorted_dates = sorted(data.keys(), reverse=True)
        recent_dates = sorted_dates[:limit_days]

        context = "A BRIEF HISTORY OF THE LAST DAYS: \n"

        for date in recent_dates:
            summ = data[date].get("summary", "")
            if not summ:
                messages = data[date].get("messages", [])
                if messages:
                    summ = " | ".join(messages[-3:])
                else:
                    summ = "нет переписки"
            context += f"{date}: {summ}\n"
        return context

async def coin_flip_task():
    while True:
        try:
            await asyncio.sleep(7200)
            result = random.randint(0, 1)
            print(f"кидаю монету... Выпало: {result}")

            if result == 1:
               history_context = await get_context(limit_days=5)
               prompt = "Тебе стало скучно, и ты решил написать мне, найди в дневнике какую нибудь запись из прошлых дней или просто напиши случайную адекватную мысль в своем стиле."
               naxyi_messages: list = [
                   {"role": "system", "content": summary_prompt},
                   {"role": "user", "content": f"Контекст прошлых дней: {history_context}\n\nЗадача: {prompt}"},
               ]
               response = await client.chat.completions.create(
                   model="openai/gpt-4o-mini",
                   messages=naxyi_messages,
                   temperature=0.4
               )
               reply = (response.choices[0].message.content or "").strip().lower()
               await bot.send_message(str(USER_ID), reply)
               await save_memory(f"Bot: {reply}")
        except Exception as e:
           print(f"Ошибка при генерации: {e}")

async def main():
    asyncio.create_task(coin_flip_task())
    asyncio.create_task(random_recall_task())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
