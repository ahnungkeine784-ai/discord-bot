import discord
from discord.ext import commands
from discord import Embed
import firebase_admin
from firebase_admin import credentials, firestore
import os
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
OWNER_ID_STR = os.getenv('OWNER_ID')
OWNER_ID = int(OWNER_ID_STR) if OWNER_ID_STR else None

# --- FIREBASE SETUP ---
cred_path = 'serviceAccount.json'
if os.path.exists(cred_path):
    cred = credentials.Certificate(cred_path)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("✅ Firebase Connected Successfully")
else:
    print("❌ serviceAccount.json not found.")
    db = None

# --- DISCORD BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Temporary storage for input steps
sessions = {}

@bot.event
async def on_ready():
    print(f'Bot is running as {bot.user.name}')

# Helper to check if user is owner
def is_owner(ctx):
    return ctx.author.id == OWNER_ID

@bot.command(name='add')
async def add_pet(ctx):
    # SECURITY CHECK
    if not is_owner(ctx):
        await ctx.send("⛔ **Access Denied.** You are not authorized to use this bot.")
        return

    if ctx.author.id in sessions:
        await ctx.send("You are already listing an item! Type `cancel` to restart.")
        return
    
    sessions[ctx.author.id] = {'step': 0, 'data': {}}
    embed = discord.Embed(title="📝 New Listing", description="**Step 1:** Enter Pet Name:", color=discord.Color.blue())
    await ctx.send(embed=embed)

@bot.command(name='cancel')
async def cancel_listing(ctx):
    if ctx.author.id in sessions:
        del sessions[ctx.author.id]
        await ctx.send("❌ Listing cancelled.")

@bot.command(name='ping')
async def ping(ctx):
    if not is_owner(ctx): return
    await ctx.send(f"Pong! {round(bot.latency * 1000)}ms")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Ignore inputs from non-owners if they try to type while owner is listing
    if message.author.id in sessions and not is_owner(message.author):
        return

    # Process listing steps
    if message.author.id in sessions:
        session = sessions[message.author.id]
        step = session['step']
        content = message.content.strip()

        if content.lower() == 'cancel':
            await message.channel.send("Type `!cancel` to stop.")
            return

        try:
            # --- STEP 0: NAME ---
            if step == 0:
                session['data']['name'] = content
                session['step'] = 1
                await message.channel.send(embed=discord.Embed(title="Step 2", description="Enter Variant (Normal, Golden, Rainbow):", color=discord.Color.blue()))

            # --- STEP 1: VARIANT ---
            elif step == 1:
                valid = ['normal', 'golden', 'rainbow']
                if content.lower() not in valid:
                    return await message.channel.send("❌ Invalid. Type: Normal, Golden, or Rainbow.")
                session['data']['variant'] = content.capitalize()
                session['step'] = 2
                await message.channel.send(embed=discord.Embed(title="Step 3", description="Enter Rarity (Secret, Mythical, Legendary):", color=discord.Color.blue()))

            # --- STEP 2: RARITY ---
            elif step == 2:
                valid = ['secret', 'mythical', 'legendary']
                if content.lower() not in valid:
                    return await message.channel.send("❌ Invalid. Type: Secret, Mythical, or Legendary.")
                session['data']['rarity'] = content.capitalize()
                session['step'] = 3
                await message.channel.send(embed=discord.Embed(title="Step 4", description="Enter Amount:", color=discord.Color.blue()))

            # --- STEP 3: AMOUNT ---
            elif step == 3:
                if not content.isdigit():
                    return await message.channel.send("❌ Please enter a number.")
                session['data']['amount'] = int(content)
                session['step'] = 4
                await message.channel.send(embed=discord.Embed(title="Step 5", description="Enter Price:", color=discord.Color.blue()))

            # --- STEP 4: PRICE (FINAL) ---
            elif step == 4:
                if not content.isdigit():
                    return await message.channel.send("❌ Please enter a number.")
                
                # Final Data
                session['data']['price'] = int(content)
                session['data']['discord'] = str(message.author)
                session['data']['negotiable'] = False
                session['data']['userId'] = "BOT_ADDED"
                session['data']['expiresAt'] = int(time.time() * 1000) + (365 * 24 * 60 * 60 * 1000)
                session['data']['createdAt'] = firestore.SERVER_TIMESTAMP

                if db:
                    # Save to Firebase
                    db.collection('market_listings').document().set(session['data'])
                    
                    embed = discord.Embed(title="✅ Success", color=discord.Color.green())
                    embed.add_field(name="Pet", value=session['data']['name'], inline=True)
                    embed.add_field(name="Price", value=session['data']['price'], inline=True)
                    embed.add_field(name="Rarity", value=session['data']['rarity'], inline=True)
                    await message.channel.send(embed=embed)
                else:
                    await message.channel.send("❌ Database not connected.")

                del sessions[message.author.id]

        except Exception as e:
            await message.channel.send(f"Error: {e}")
            if message.author.id in sessions:
                del sessions[message.author.id]

    await bot.process_commands(message)

if __name__ == "__main__":
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        print("DISCORD_TOKEN is missing. Set it in Railway Env Vars.")
