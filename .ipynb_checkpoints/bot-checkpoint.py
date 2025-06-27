import logging
import random
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandObject
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import asyncio
import openai
from openai import OpenAI


# Placeholders for your tokens
TELEGRAM_BOT_TOKEN = '8063605899:AAGiM43C1VDfhho6jZFLeEunuXPnrYS2VlA'
#OPENAI_API_KEY = "sk-aitunnel-xXxk6vVkEc5sIoGEequsErWeet1zxYFZ"

client = OpenAI(
    api_key="sk-aitunnel-xXxk6vVkEc5sIoGEequsErWeet1zxYFZ", # Ключ из нашего сервиса
    base_url="https://api.aitunnel.ru/v1/",)

# English levels and example topics
ENGLISH_LEVELS = ["A1","A2", "B1", "B2", "C1", "C2"]
EXAMPLE_TOPICS = [
    "At the airport", "In a cafe", "Job interview", "Ordering food", "Traveling abroad",
    "Shopping", "Making friends", "At the hotel", "Doctor's appointment", "Phone conversation",
    "Asking for directions", "At the bank", "At the post office", "Talking about hobbies", "Describing your city"
]

# FSM States
class DialogStates(StatesGroup):
    waiting_for_level = State()
    waiting_for_topic = State()
    in_dialog = State()

# In-memory session storage (can be replaced with DB)
user_sessions = {}  # user_id: {"history": [(role, message)], "level": str, "topic": str}

# Logging setup
logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Start command handler
dp.message(Command("start"))(lambda message, state: start_handler(message, state))

async def start_handler(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardBuilder()
    for level in ENGLISH_LEVELS:
        kb.add(KeyboardButton(text=level))
    await message.answer(
        "Welcome to the English Practice Bot!\nPlease select your English level:",
        reply_markup=kb.as_markup(resize_keyboard=True)
    )
    await state.set_state(DialogStates.waiting_for_level)

# Level selection handler
@dp.message(DialogStates.waiting_for_level)
async def level_selected(message: types.Message, state: FSMContext):
    level = message.text.strip().upper()
    if level not in ENGLISH_LEVELS:
        await message.answer("Please select a valid level from the keyboard.")
        return
    await state.update_data(level=level)
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="Suggest 7 topics"))
    await message.answer(
        "Great! Now write a topic you want to talk about, or press 'Suggest 7 topics' for ideas.",
        reply_markup=kb.as_markup(resize_keyboard=True)
    )
    await state.set_state(DialogStates.waiting_for_topic)

# Topic suggestion handler
@dp.message(DialogStates.waiting_for_topic)
async def topic_handler(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text.lower() == "suggest 7 topics":
        topics = random.sample(EXAMPLE_TOPICS, 7)
        await message.answer("Here are 7 random topics:\n" + "\n".join(f"- {t}" for t in topics))
        return
    data = await state.get_data()
    level = data.get("level", "B1")
    await state.update_data(topic=text)
    user_id = message.from_user.id
    user_sessions[user_id] = {"history": [], "level": level, "topic": text}
    # Generate first question using OpenAI
    question = await generate_first_question(level, text)
    user_sessions[user_id]["history"].append(("assistant", question))
    await message.answer(f"Let's start a dialogue on: {text}\n{question}")
    await state.set_state(DialogStates.in_dialog)

# Placeholder for dialog and feedback logic
@dp.message(DialogStates.in_dialog)
async def dialog_handler(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)
    if not session:
        await message.answer("Session expired. Please /start again.")
        return
    user_message = message.text.strip()
    # Store user message
    session["history"].append(("user", user_message))
    # Keep only last 20 messages
    session["history"] = session["history"][-20:]
    # Get bot reply and feedback
    bot_reply = await continue_dialogue(session["level"], session["topic"], session["history"], user_message)
    session["history"].append(("assistant", bot_reply))
    session["history"] = session["history"][-20:]
    await message.answer(bot_reply)

# Command to analyze last 20 messages
@dp.message(Command("analyze"))
async def analyze_handler(message: types.Message, state: FSMContext):
    # TODO: Analyze last 20 messages and list topics with mistakes
    await message.answer("(Feature: Analysis of last 20 messages will be shown here)")

#penai.api_key = OPENAI_API_KEY

async def generate_first_question(level, topic):
    prompt = (
        f"You are an English teacher. Start a conversation for a student with {level} level English on the topic '{topic}'. "
        "Ask the first question to begin the dialogue. Keep it simple and clear."
    )
    response = await client.ChatCompletion.acreate(
        model="gpt-3.5-turbo",
        messages=[{"role": "system", "content": prompt}]
    )
    return response.choices[0].message.content.strip()

async def continue_dialogue(level, topic, history, user_message):
    # Compose conversation history for OpenAI
    messages = [
        {"role": "system", "content": f"You are an English teacher. Continue a conversation with a student of {level} level on the topic '{topic}'. "
                                      f"After each student reply, analyze their answer, explain their mistakes in a structured way, and suggest correct alternatives. "
                                      f"Keep the conversation going with a new question or comment."}
    ]
    for role, msg in history[-10:]:
        messages.append({"role": role, "content": msg})
    messages.append({"role": "user", "content": user_message})
    response = await client.ChatCompletion.acreate(
        model="gpt-3.5-turbo",
        messages=messages
    )
    return response.choices[0].message.content.strip()

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))