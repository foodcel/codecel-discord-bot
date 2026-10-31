"""The pinned "how to post" guides of the bug forum and the suggestions forum, as embeds with a red accent. They also tell players what
the bot does with a post, so its automatic replies never come as a surprise."""
import discord

from .env import cfg
from .ui import WIDE_RULE, describe, head

RED = 0xED4245
NEW_GAMES = '1562961976387174452'  # where whole new game ideas go
UPDATES = '1562726333828702249'


def _embed(title, intro):
    e = discord.Embed(color=RED)
    e.title = title
    describe(e, intro)
    return e


def _field(e, name, text):
    e.add_field(name=name, value=f'{WIDE_RULE}\n{text}'[:1024], inline=False)


def bugs_guide_embed():
    e = _embed(head('🐛', 'Bug report guidelines'),
               'Help us make **PlayStation Experience** better! Clear reports help us find and fix problems faster.\n'
               'A bot reads every post, tags it and sends it to the developer who owns the game. 🚀')
    _field(e, head('🔎', 'Before you post'),
           f'• **Search first.** Already reported? Add your details there instead.\n'
           f'• **Check support.** Missing features marked **WIP** are still in development.\n'
           f'• **One bug per post.** Separate issues get separate reports.\n'
           f'• **Pick your tags.** The affected **game** and your **device**.\n'
           f'• **An idea, not a bug?** Improvements go in <#{cfg.suggestions_id}>, new games in <#{NEW_GAMES}>.')
    _field(e, head('📝', 'Writing your report'),
           'Give it a title that describes the problem:\n**[PaRappa] Notes stop responding after restarting a song**\n'
           '```\nGame:\nDevice / model:\nWhat happened:\nAccount verified? What age?\nError message, if any:\nScreenshot or video:\n```'
           '“It’s broken” alone won’t help us. Add enough detail for someone else to reproduce it.')
    _field(e, head('🤖', 'What the bot does'),
           '• Reads your post, sets the tags and numbers it, like **#12**.\n'
           '• Missing something? It asks, up to 3 short questions. **Just reply in your post**, no need to post again.\n'
           '• Already reported? It points you to the first post.\n'
           '• Fixed? You and everyone who reacted 👀 get a ping, and the post is deleted after 24 hours. '
           '**Still broken?** Reply before then and it reopens.')
    _field(e, head('🛠️', 'Report status'),
           '🔎 **Investigating** · we are looking into it\n❓ **Needs Info** · we need more from you\n🛠️ **Fix in Progress** · a fix is being made\n'
           '✅ **Fixed** · it is fixed\n🔁 **Duplicate** · already reported\nℹ️ **Not a Bug** · intended behavior or a feature request')
    _field(e, head('🤝', 'Keep it helpful'),
           '• React with **👀** if you have the same issue.\n• Add evidence or useful details, not repeated bumps.\n'
           '• Be patient and answer questions. **Please do not ping developers.**\n• Hide personal information in screenshots.\n'
           '• **Found an exploit?** Do not post how to abuse it. The bot removes posts like that and asks you to message staff.')
    _field(e, head('🧪', 'Testers'),
           f'Testers send reports with **`/bug`** in <#{cfg.testing_id}>: pick the game, attach screenshots and fill in the form. The bot makes the post for you.')
    e.set_footer(text='Thank you for helping improve every session. 💙')
    return e


def suggestions_guide_embed():
    e = _embed(head('💡', 'Game improvements & suggestions'),
               'Welcome to the **PlayStation Experience** improvement forum! 🎮\n'
               'Got an idea that makes one of our games better? We want to hear it! 💙 A bot reads each post and sends it to the right developer.')
    _field(e, head('🔎', 'Before you post'),
           f'• **Search first.** Someone may have suggested it already: add your vote 🙏 there.\n'
           f'• **Check the updates.** Look in <#{UPDATES}>. It may already be added or in development (WIP).\n'
           f'• **One improvement per post.**\n• **Pick the game tag.**\n'
           f'• **A whole new game?** Use <#{NEW_GAMES}> instead.')
    _field(e, head('✏️', 'How to write it'),
           'Title: **[Game] Short description of the improvement**\nExample: **[PaRappa] Improve the timing accuracy**\n'
           '```\nGame:\nCurrent behavior:\nThe improvement you want to see:\nSteps to reproduce (if it applies):\n```'
           '💡 More detail makes it easier to evaluate. Screenshots and videos are welcome!')
    _field(e, head('🤖', 'What happens next'),
           '• The bot tags and numbers your post, like **#12**, and sends it to the game\'s developer.\n'
           '• Too vague? It asks up to 3 short questions. **Just reply in your post.**\n'
           '• Same idea twice? It points you to the first post.\n'
           '• **Votes matter:** react 🙏 on the ideas you want. Developers see the most voted first.\n'
           '• ✅ **Added** or ❌ **Declined**: you get a ping and the post is deleted after 24 hours.\n'
           '• Posted a **bug** by mistake? The bot turns it into a bug report for you.\n'
           '• Submitting an idea does not guarantee it is added.')
    _field(e, head('❤️', 'Community guidelines'),
           '✅ Be respectful and constructive\n✅ Explain things clearly\n✅ Stay on topic\n'
           '❌ No spam or duplicate posts\n❌ No harassing others over differing opinions')
    e.set_footer(text='Your feedback shapes our future! Thank you for helping us build a better PlayStation Experience. 🚀')
    return e
