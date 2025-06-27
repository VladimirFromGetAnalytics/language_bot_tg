import logging
import random
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import asyncio
from openai import OpenAI

# Placeholders for your tokens
TELEGRAM_BOT_TOKEN = '8063605899:AAGiM43C1VDfhho6jZFLeEunuXPnrYS2VlA'

client = OpenAI(
    api_key="sk-aitunnel-xXxk6vVkEc5sIoGEequsErWeet1zxYFZ",
    base_url="https://api.aitunnel.ru/v1/",
)

# Top 10 popular languages for learning
POPULAR_LANGUAGES = {
    "🇬🇧 English": "English",
    "🇪🇸 Spanish": "Spanish", 
    "🇫🇷 French": "French",
    "🇩🇪 German": "German",
    "🇮🇹 Italian": "Italian",
    "🇵🇹 Portuguese": "Portuguese",
    "🇨🇳 Chinese": "Chinese",
    "🇯🇵 Japanese": "Japanese",
    "🇰🇷 Korean": "Korean",
    "🇷🇺 Russian": "Russian"
}

# Language levels
LANGUAGE_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]

# Example topics (will be translated based on chosen language)
EXAMPLE_TOPICS = [
    "At the airport", "In a cafe", "Job interview", "Ordering food", "Traveling abroad",
    "Shopping", "Making friends", "At the hotel", "Doctor's appointment", "Phone conversation",
    "Asking for directions", "At the bank", "At the post office", "Talking about hobbies", "Describing your city"
]

# FSM States
class DialogStates(StatesGroup):
    waiting_for_language = State()
    waiting_for_level = State()
    waiting_for_topic = State()
    in_dialog = State()

# In-memory session storage
user_sessions = {}

# Logging setup
logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Start command handler
@dp.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardBuilder()
    # Add language options in 2 columns
    languages = list(POPULAR_LANGUAGES.keys())
    for i in range(0, len(languages), 2):
        if i + 1 < len(languages):
            kb.row(KeyboardButton(text=languages[i]), KeyboardButton(text=languages[i + 1]))
        else:
            kb.row(KeyboardButton(text=languages[i]))
    
    await message.answer(
        "🌍 Welcome to the Language Practice Bot!\n"
        "Please select the language you want to practice:",
        reply_markup=kb.as_markup(resize_keyboard=True)
    )
    await state.set_state(DialogStates.waiting_for_language)

# Language selection handler
@dp.message(DialogStates.waiting_for_language)
async def language_selected(message: types.Message, state: FSMContext):
    selected_language_key = message.text.strip()
    
    if selected_language_key not in POPULAR_LANGUAGES:
        await message.answer("Please select a valid language from the keyboard.")
        return
    
    language = POPULAR_LANGUAGES[selected_language_key]
    await state.update_data(language=language, language_key=selected_language_key)
    
    kb = ReplyKeyboardBuilder()
    for level in LANGUAGE_LEVELS:
        kb.add(KeyboardButton(text=level))
    
    await message.answer(
        f"Great! You've chosen {selected_language_key}\n"
        f"Now please select your {language} level:",
        reply_markup=kb.as_markup(resize_keyboard=True)
    )
    await state.set_state(DialogStates.waiting_for_level)

# Level selection handler
@dp.message(DialogStates.waiting_for_level)
async def level_selected(message: types.Message, state: FSMContext):
    level = message.text.strip().upper()
    if level not in LANGUAGE_LEVELS:
        await message.answer("Please select a valid level from the keyboard.")
        return
    
    await state.update_data(level=level)
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="💡 Suggest 7 topics"))
    
    data = await state.get_data()
    language = data.get("language", "English")
    
    await message.answer(
        f"Perfect! Now write a topic you want to talk about in {language}, "
        f"or press '💡 Suggest 7 topics' for ideas.",
        reply_markup=kb.as_markup(resize_keyboard=True)
    )
    await state.set_state(DialogStates.waiting_for_topic)

# Topic suggestion handler
@dp.message(DialogStates.waiting_for_topic)
async def topic_handler(message: types.Message, state: FSMContext):
    text = message.text.strip()
    
    if text.lower() == "💡 suggest 7 topics" or text.lower() == "suggest 7 topics":
        data = await state.get_data()
        language = data.get("language", "English")
        
        try:
            # Get translated topics
            topics = await get_translated_topics(language)
            await message.answer(f"Here are 7 random topics for {language}:\n" + "\n".join(f"• {t}" for t in topics))
            return
        except Exception as e:
            logging.error(f"Error getting translated topics: {e}")
            topics = random.sample(EXAMPLE_TOPICS, 7)
            await message.answer("Here are 7 random topics:\n" + "\n".join(f"• {t}" for t in topics))
            return
    
    data = await state.get_data()
    language = data.get("language", "English")
    level = data.get("level", "B1")
    await state.update_data(topic=text)
    
    user_id = message.from_user.id
    user_sessions[user_id] = {
        "history": [], 
        "language": language, 
        "level": level, 
        "topic": text,
        "mistakes": []  # Track mistakes for analysis
    }
    
    try:
        # Generate first question
        question = await generate_first_question(language, level, text)
        user_sessions[user_id]["history"].append(("assistant", question))
        
        kb = ReplyKeyboardBuilder()
        kb.add(KeyboardButton(text="🔄 New topic"))
        kb.add(KeyboardButton(text="📊 Analyze mistakes"))
        
        await message.answer(
            f"🎯 Let's start a dialogue on: **{text}**\n\n{question}",
            reply_markup=kb.as_markup(resize_keyboard=True),
            parse_mode="Markdown"
        )
        await state.set_state(DialogStates.in_dialog)
    except Exception as e:
        logging.error(f"Error generating first question: {e}")
        await message.answer("Sorry, there was an error starting the conversation. Please try again.")

# Dialog handler
@dp.message(DialogStates.in_dialog)
async def dialog_handler(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)
    
    if not session:
        await message.answer("Session expired. Please /start again.")
        return
    
    user_message = message.text.strip()
    
    # Check for special commands
    if user_message == "🔄 New topic":
        data = await state.get_data()
        language = data.get("language", "English")
        await message.answer(f"Please write a new topic you want to discuss in {language}:")
        await state.set_state(DialogStates.waiting_for_topic)
        return
    elif user_message == "📊 Analyze mistakes":
        await analyze_handler(message, state)
        return
    
    # Store user message
    session["history"].append(("user", user_message))
    # Keep only last 20 messages
    session["history"] = session["history"][-20:]
    
    try:
        # Get bot reply with feedback
        bot_reply = await continue_dialogue(
            session["language"], 
            session["level"], 
            session["topic"], 
            session["history"], 
            user_message
        )
        
        session["history"].append(("assistant", bot_reply))
        session["history"] = session["history"][-20:]
        
        await message.answer(bot_reply, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error in dialogue: {e}")
        await message.answer("Sorry, there was an error processing your message. Please try again.")

# Analyze command handler
@dp.message(Command("analyze"))
async def analyze_handler(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)
    
    if not session or not session["history"]:
        await message.answer("❌ No conversation history found. Start a conversation first with /start")
        return
    
    try:
        # Analyze conversation for mistakes
        analysis = await analyze_mistakes(session["language"], session["history"])
        await message.answer(f"📊 **Mistake Analysis Report**\n\n{analysis}", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error analyzing mistakes: {e}")
        await message.answer("Sorry, there was an error analyzing your mistakes. Please try again later.")

# OpenAI functions
async def get_translated_topics(language):
    """Get 7 random topics translated to the target language"""
    topics = random.sample(EXAMPLE_TOPICS, 7)
    
    if language.lower() == "english":
        return topics
    
    prompt = f"Translate these conversation topics to {language}. Return only the translated topics, one per line:\n" + "\n".join(topics)
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    
    translated_topics = response.choices[0].message.content.strip().split('\n')
    return [topic.strip('- ').strip() for topic in translated_topics if topic.strip()]

async def generate_first_question(language, level, topic):
    prompt = (
        f"You are a {language} teacher. Start a conversation for a student with {level} level {language} on the topic '{topic}'. "
        f"Ask the first question to begin the dialogue in {language}. Keep it appropriate for {level} level - simple and clear for beginners, more complex for advanced levels."
    )
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"OpenAI API error: {e}")
        return f"Let's talk about {topic}. What do you think about this topic?"

async def continue_dialogue(language, level, topic, history, user_message):
    # Compose conversation history for OpenAI
    messages = [
        {"role": "system", "content": f"You are a {language} teacher helping a student practice {language} conversation. "
                                      f"The student has {level} level {language} and you're discussing '{topic}'. "
                                      f"Your response should have TWO parts:\n"
                                      f"1. First part: Continue the conversation naturally in {language} and ask a follow-up question\n"
                                      f"2. Second part: After a line with dashes (---), provide feedback on the student's previous message in English. "
                                      f"Analyze grammar mistakes, vocabulary usage, and suggest improvements. Be constructive and encouraging.\n"
                                      f"Format your response exactly like this:\n"
                                      f"[Your conversational response in {language}]\n\n"
                                      f"---\n"
                                      f"**Feedback:** [Your analysis and corrections in English]"}
    ]
    
    # Add conversation history (last 8 messages to leave room for feedback)
    for role, msg in history[-8:]:
        messages.append({"role": role, "content": msg})
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=500
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"OpenAI API error: {e}")
        return f"I understand. Can you tell me more?\n\n---\n**Feedback:** Keep practicing! Your {language} is improving."

async def analyze_mistakes(language, history):
    """Analyze conversation history and return top 5 mistake categories"""
    # Prepare conversation text for analysis
    conversation_text = ""
    user_messages = []
    
    for role, message in history:
        if role == "user":
            user_messages.append(message)
            conversation_text += f"Student: {message}\n"
        else:
            conversation_text += f"Teacher: {message}\n"
    
    if not user_messages:
        return "❌ No student messages found to analyze."
    
    prompt = (
        f"Analyze this {language} learning conversation and identify the TOP 5 most common mistake categories made by the student. "
        f"Focus on grammar, vocabulary, sentence structure, verb tenses, articles, prepositions, etc.\n\n"
        f"Conversation:\n{conversation_text}\n\n"
        f"Please provide exactly 5 mistake categories ranked by frequency, with specific examples from the conversation. "
        f"Format as:\n"
        f"1. **Category Name** - Brief explanation with example\n"
        f"2. **Category Name** - Brief explanation with example\n"
        f"etc.\n\n"
        f"If fewer than 5 categories exist, still provide exactly 5 but mention areas for improvement instead."
    )
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600
        )
        
        analysis = response.choices[0].message.content.strip()
        return f"Based on your {language} conversation:\n\n{analysis}\n\n💡 **Tip:** Focus on practicing these areas to improve your {language} skills!"
        
    except Exception as e:
        logging.error(f"OpenAI API error in analysis: {e}")
        return "❌ Could not analyze mistakes at this time. Please try again later."

async def main():
    try:
        print("🚀 Starting multilingual language learning bot...")
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"Error starting bot: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())