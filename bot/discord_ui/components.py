"""Buttons, dropdowns and mentions, built the way the messages need them.

Buttons and dropdowns carry a custom_id like "v:n:123:all:7". The bot answers them in one place (interactions.py), by parsing
that id, so messages keep working after a restart and nothing depends on an in-memory view."""
import discord


def make_view(rows):
    """rows: a list of rows, each a list of items. Returns a View, or None when there is nothing to show
    (None clears the components when used in an edit)."""
    rows = [r for r in rows if r]
    if not rows:
        return None
    v = discord.ui.View(timeout=None)
    for i, items in enumerate(rows):
        for it in items:
            it.row = i
            v.add_item(it)
    return v


def button(custom_id, label, style=discord.ButtonStyle.secondary, disabled=False):
    return discord.ui.Button(custom_id=custom_id, label=label, style=style, disabled=disabled)


def link_button(label, url):
    return discord.ui.Button(label=label, style=discord.ButtonStyle.link, url=url)


def select(custom_id, placeholder, options, min_values=1, max_values=1):
    """options: [{'label', 'value', 'description'?, 'default'?}]. A select that picks several: max_values > 1."""
    return discord.ui.Select(
        custom_id=custom_id, placeholder=placeholder, min_values=min_values, max_values=max_values,
        options=[discord.SelectOption(label=o['label'], value=o['value'], description=o.get('description'), default=bool(o.get('default')))
                 for o in options])


def allowed(users=(), roles=()):
    """Only the listed users and roles can be pinged (never @everyone). Empty = nobody."""
    return discord.AllowedMentions(
        everyone=False, replied_user=False,
        users=[discord.Object(id=int(u)) for u in users] or False,
        roles=[discord.Object(id=int(r)) for r in roles] or False)


NO_MENTIONS = discord.AllowedMentions.none()


class FormModal(discord.ui.Modal):
    """A pop-up form. Submissions are answered in interactions.py (by custom_id), so this class only shows the form."""

    def __init__(self, custom_id, title, inputs):
        """inputs: [{'id', 'label', 'style': 'short'|'paragraph', 'required', 'max', 'placeholder'?, 'value'?}]"""
        super().__init__(title=title[:45], custom_id=custom_id, timeout=600)
        for spec in inputs:
            self.add_item(discord.ui.TextInput(
                custom_id=spec['id'], label=spec['label'][:45],
                style=discord.TextStyle.paragraph if spec.get('style') == 'paragraph' else discord.TextStyle.short,
                required=spec.get('required', False), max_length=spec.get('max'),
                placeholder=spec.get('placeholder') or None, default=(spec.get('value') or None)))

    async def on_submit(self, interaction):
        pass  # answered by the global interaction handler

    async def on_error(self, interaction, error):
        print('modal error', repr(error))


def modal_fields(interaction):
    """{custom_id: value} of a submitted modal, read from the raw interaction data."""
    out = {}
    for row in interaction.data.get('components', []):
        for c in row.get('components', []):
            out[c['custom_id']] = c.get('value') or ''
    return out
