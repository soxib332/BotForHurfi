import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
import json
import os

TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CHANNEL_ID = int(os.environ.get("DISCORD_CHANNEL_ID", "0"))
SUBMIT_ROLE = "PDF Uploader"

# Start a tiny HTTP server in the background
PORT = int(os.environ.get("PORT", 10000))  # Render sets $PORT automatically

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")

def run_server():
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()

threading.Thread(target=run_server, daemon=True).start()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "data.json"
SETTINGS_FILE = "settings.json"


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        try:
            return json.load(f)
        except:
            return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return {"submit_hour": 22, "submit_minute": 45, "report_hour": 23, "report_minute": 15}
    with open(SETTINGS_FILE, "r") as f:
        try:
            return json.load(f)
        except:
            return {"submit_hour": 22, "submit_minute": 45, "report_hour": 23, "report_minute": 15}

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)


class PDFModal(Modal):
    def __init__(self):
        super().__init__(title="Submit PDF Count")
        self.count = TextInput(label="How many PDFs did you upload today?", placeholder="Enter a number")
        self.add_item(self.count)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            member = interaction.user
            if interaction.guild:
                member = interaction.guild.get_member(interaction.user.id)
            
            if member and hasattr(member, 'roles'):
                user_roles = [role.name for role in member.roles]
                if SUBMIT_ROLE not in user_roles:
                    await interaction.response.send_message(f"You need the **{SUBMIT_ROLE}** role to submit.", ephemeral=True)
                    return

            try:
                num = int(self.count.value)
            except:
                await interaction.response.send_message("Enter a valid number.", ephemeral=True)
                return

            data = load_data()
            data[str(interaction.user.id)] = num
            save_data(data)

            await interaction.response.send_message(f"Submitted! You uploaded **{num} PDFs** today.", ephemeral=True)
            print(f"User {interaction.user.name} submitted {num} PDFs")
        except Exception as e:
            print(f"Modal submit error: {e}")
            import traceback
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message("An error occurred. Please try again.", ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        print(f"Modal error: {error}")
        import traceback
        traceback.print_exc()
        if not interaction.response.is_done():
            await interaction.response.send_message("An error occurred.", ephemeral=True)


class PDFSubmitView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Submit PDF Count", style=discord.ButtonStyle.primary, custom_id="pdf_submit_button")
    async def submit_button(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.send_modal(PDFModal())
        except Exception as e:
            print(f"Button error: {e}")
            import traceback
            traceback.print_exc()

    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        print(f"View error: {error}")
        import traceback
        traceback.print_exc()


async def send_button_message():
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        print("Channel not found.")
        return

    role_mention = ""
    if channel.guild:
        role = discord.utils.get(channel.guild.roles, name=SUBMIT_ROLE)
        if role:
            role_mention = f"{role.mention} "

    view = PDFSubmitView()
    await channel.send(f"{role_mention}📝 **Daily PDF Submission**\nClick the button below and submit your count:", view=view)


async def send_daily_report():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return

    data = load_data()
    if len(data) == 0:
        await channel.send("⚠️ **No submissions today.**")
    else:
        msg = "📊 **Daily PDF Upload Report**\n\n"
        for user_id, count in data.items():
            user = await bot.fetch_user(int(user_id))
            msg += f"• **{user.name}** — `{count} PDFs`\n"

        await channel.send(msg)

    save_data({})


scheduler = AsyncIOScheduler(timezone=pytz.timezone("Asia/Dhaka"))

def schedule_jobs():
    scheduler.remove_all_jobs()
    settings = load_settings()
    scheduler.add_job(send_button_message, "cron", hour=settings["submit_hour"], minute=settings["submit_minute"])
    scheduler.add_job(send_daily_report, "cron", hour=settings["report_hour"], minute=settings["report_minute"])

schedule_jobs()


def is_admin(ctx):
    return ctx.author.guild_permissions.administrator


@bot.command()
@commands.check(is_admin)
async def report(ctx):
    await send_daily_report()

@bot.command()
@commands.check(is_admin)
async def reset(ctx):
    save_data({})
    await ctx.send("✅ Today's data cleared.")

@bot.command()
@commands.check(is_admin)
async def view(ctx):
    data = load_data()
    if len(data) == 0:
        await ctx.send("⚠️ No submissions yet.")
    else:
        msg = "**Current Submissions:**\n"
        for user_id, count in data.items():
            user = await bot.fetch_user(int(user_id))
            msg += f"• {user.name} — {count} PDFs\n"
        await ctx.send(msg)

@bot.command()
@commands.check(is_admin)
async def setsubmit(ctx, hour: int, minute: int):
    if not (0 <= hour <= 23) or not (0 <= minute <= 59):
        return await ctx.send("❌ Invalid time. Hour must be 0-23, minute must be 0-59.")
    settings = load_settings()
    settings["submit_hour"] = hour
    settings["submit_minute"] = minute
    save_settings(settings)
    schedule_jobs()
    await ctx.send(f"✅ Submit button time updated to {hour:02d}:{minute:02d}")

@bot.command()
@commands.check(is_admin)
async def setreport(ctx, hour: int, minute: int):
    if not (0 <= hour <= 23) or not (0 <= minute <= 59):
        return await ctx.send("❌ Invalid time. Hour must be 0-23, minute must be 0-59.")
    settings = load_settings()
    settings["report_hour"] = hour
    settings["report_minute"] = minute
    save_settings(settings)
    schedule_jobs()
    await ctx.send(f"✅ Report time updated to {hour:02d}:{minute:02d}")

@bot.command()
@commands.check(is_admin)
async def forcebutton(ctx):
    await send_button_message()

@bot.command()
@commands.check(is_admin)
async def resetschedule(ctx):
    settings = {
        "submit_hour": 22,
        "submit_minute": 45,
        "report_hour": 23,
        "report_minute": 15
    }
    save_settings(settings)
    schedule_jobs()
    await ctx.send("✅ Schedule reset to default:\n• Submit button: 22:45\n• Daily report: 23:15")


@bot.event
async def on_ready():
    print(f"Bot online as {bot.user}")
    bot.add_view(PDFSubmitView())
    if not scheduler.running:
        scheduler.start()


if __name__ == "__main__":
    if not TOKEN:
        print("Error: DISCORD_BOT_TOKEN environment variable not set!")
    elif CHANNEL_ID == 0:
        print("Error: DISCORD_CHANNEL_ID environment variable not set!")
    else:
        bot.run(TOKEN)
