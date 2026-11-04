"""The pinned "how to post" guides of the bug forum and the suggestions forum. Both follow the same layout, so a player who read one knows
the other: the command first (it is the easiest way), what to write, what the bot does afterwards, and a short list of good habits."""
from .env import cfg
from .ui import describe, flat, gap, head, section

COMMANDS_CHANNEL = '1563090099774816286'  # where players can use commands
UPDATES = '1562726333828702249'
NEW_GAMES = '1562961976387174452'  # whole new game ideas go here


def _steps(command, forum_id):
    return (f'1. Type `{command}` in <#{COMMANDS_CHANNEL}> or in this forum\n'
            '2. Pick the game, and add screenshots or videos if you have them\n'
            '3. Fill in the short form and send it\n'
            'Your post appears here, already tagged.')


def bugs_guide_embed():
    e = flat()
    e.title = head('🐛', 'Report a bug')
    describe(e, f'The easiest way: type **`/bug`** in <#{COMMANDS_CHANNEL}> or in any post here.\nThe bot makes the post for you and sends it to the right developer.')
    section(e, head('⌨️', 'How it works'), _steps('/bug', cfg.bugs_id))
    section(e, head('✍️', 'Posting by hand? · What to write'),
            '• **Title** · the game and the problem, like **[PaRappa] Notes stop responding**\n• **What happened** · and what you expected\n'
            '• **Steps** · how can we make it happen again?\n• **Device** · PC, mobile, PS5...\n'
            'Clear steps get fixed faster.')
    section(e, head('🤖', 'After you send it'),
            '• Your post gets a number, like **#12**\n'
            '• Something missing? The bot asks up to 3 short questions. **Reply in your post.**\n'
            '• Fixed? You get a ping when the update with your fix is released, and the post is deleted 24 hours later. **Still broken?** Reply before then and it reopens.')
    section(e, head('💡', 'Good to know'),
            '• Already reported? React 👀 on that post instead of making a new one\n'
            '• One bug per report, and please do not ping developers\n'
            '• Hide personal information in screenshots\n'
            '• Found an exploit? Use `/bug` as usual. The bot hides it and tells the developers\n'
            f'• Just an idea? Use `/improvement` and <#{cfg.suggestions_id}>')
    gap(e)
    e.set_footer(text='Thank you for helping improve every session.')
    return e


def suggestions_guide_embed():
    e = flat()
    e.title = head('💡', 'Suggest an improvement')
    describe(e, f'The easiest way: type **`/improvement`** in <#{COMMANDS_CHANNEL}> or in any post here.\nThe bot makes the post for you and sends it to the right developer.')
    section(e, head('⌨️', 'How it works'), _steps('/improvement', cfg.suggestions_id))
    section(e, head('✍️', 'Posting by hand? · What to write'),
            '• **Title** · the game and your idea, like **[PaRappa] Improve the timing**\n• **What should be added or changed?**\n'
            '• **Why** · optional, but it helps us understand\nScreenshots and videos are welcome.')
    section(e, head('🤖', 'After you send it'),
            '• Your post gets a number, like **#12**\n'
            '• Too vague? The bot asks up to 3 short questions. **Reply in your post.**\n'
            '• **React 🙏** on the ideas you want. The most voted are seen first.\n'
            '• Added ✅ or declined ❌? You get a ping and the post is deleted after 24 hours.\n'
            '• An idea is not a promise that it will be added.')
    section(e, head('💡', 'Good to know'),
            '• Someone already suggested it? Add your 🙏 there instead\n'
            f'• It may already exist: check <#{UPDATES}> first\n'
            '• One idea per post, and be respectful\n'
            f'• A whole new game? Use <#{NEW_GAMES}>\n'
            f'• Is it a bug? Use <#{cfg.bugs_id}> (or `/bug`)')
    gap(e)
    e.set_footer(text='Your feedback shapes what we build next.')
    return e


def games_guide_embed():
    """The guide of the game-suggestions forum (ideas for whole new games). It has no commands: players post and vote by hand."""
    e = flat()
    e.title = head('🎮', 'Suggest a new game')
    describe(e, 'Want your favorite game on our **Roblox PlayStation Experience**? Suggest it here!\n'
                'Games from PlayStation, Xbox, Steam, PC, Nintendo, mobile and more are welcome.')
    section(e, head('✍️', 'How to suggest'),
            '• **Title** · the name of the game\n'
            '• **One game per post.**\n'
            '• **Pick the platform tag**: PlayStation (PS1 to PS5, PSP), PC / Steam, or Xbox (Xbox, 360, One, Series)\n'
            '• **Search first.** Already suggested? Vote on it instead. Duplicates are removed.')
    section(e, head('🔥', 'Voting'),
            '• **React 🔥** on the games you want. Developers look at the most voted first.\n'
            '• Talk about an idea in its post.\n'
            '• More votes means more interest. It is **not** a promise.')
    section(e, head('🏷️', 'Status tags'),
            '🔥 **Highly Requested** · lots of support\n👀 **Under Review** · developers are looking at it\n'
            '✅ **Approved** · accepted for the future, if permissions allow\n🛠️ **In Development** · someone is building it\n'
            '❌ **Declined** · not planned or not possible\n'
            'Staff and the bot set these. Please do not ask for a change.')
    section(e, head('💡', 'Good to know'),
            '• Please do not spam, beg, ping developers, or vote with extra accounts\n'
            "• Follow Roblox's Terms of Use and Community Standards: nothing NSFW, hateful or prohibited\n"
            '• Be respectful. Developers make the final decision, and may approve, decline or postpone any idea\n'
            '• Some games are impossible or protected by copyright. Crediting the creator does not replace permission\n'
            f'• An improvement for a game we already have? Post it in <#{cfg.suggestions_id}>')
    gap(e)
    e.set_footer(text='Suggest. Vote. Play.')
    return e
