import re
import random
import requests
import humanize

from six import BytesIO
from PIL import Image
from gevent.pool import Pool
from datetime import datetime
from emoji.unicode_codes import EMOJI_ALIAS_UNICODE

from rowboat import RowboatPlugin as Plugin
from rowboat.types.plugin import PluginConfig
from rowboat.plugins.messages import Message


CDN_URL = 'https://twemoji.maxcdn.com/2/72x72/{}.png'
EMOJI_RE = re.compile(r'<:(.+):([0-9]+)>')
URL_REGEX = re.compile(r'(https?://[^\s]+)')


def get_emoji_url(emoji):
    return CDN_URL.format('-'.join(
        char.encode("unicode_escape").decode("utf-8")[2:].lstrip("0")
        for char in emoji))


class UtilitiesConfig(PluginConfig):
    pass


class UtilitiesPlugin(Plugin):
    @Plugin.command('coin')
    def coin(self, event):
        event.msg.reply(random.choice(['heads', 'tails']))

    @Plugin.command('cat')
    def cat(self, event):
        r = requests.get('http://random.cat/meow')
        r.raise_for_status()
        r = requests.get(r.json()['file'])
        r.raise_for_status()
        event.msg.reply('', attachment=('cat.jpg', r.content))

    @Plugin.command('urban', '<term:str...>')
    def urban(self, event, term):
        r = requests.get('http://api.urbandictionary.com/v0/define', params={
            'term': term,
        })
        r.raise_for_status()
        data = r.json()

        if not len(data['list']):
            return event.msg.reply(':warning: no matches')

        event.msg.reply('{} - {}'.format(
            data['list'][0]['word'],
            data['list'][0]['definition'],
        ))

    @Plugin.command('pwnd', '<email:str>')
    def pwnd(self, event, email):
        r = requests.get('https://haveibeenpwned.com/api/v2/breachedaccount/{}'.format(
            email
        ))

        if r.status_code == 404:
            return event.msg.reply(":white_check_mark: you haven't been pwnd yet, awesome!")

        r.raise_for_status()
        data = r.json()

        sites = []

        for idx, site in enumerate(data):
            sites.append('{} - {} ({})'.format(
                site['BreachDate'],
                site['Title'],
                site['Domain'],
            ))

        return event.msg.reply(":warning: You've been pwnd on {} sites:\n{}".format(
            len(sites),
            '\n'.join(sites),
        ))

    @Plugin.command('geoip', '<ip:str>')
    def geoip(self, event, ip):
        r = requests.get('http://json.geoiplookup.io/{}'.format(ip))
        r.raise_for_status()
        data = r.json()

        event.msg.reply('{} - {}, {} ({}) | {}, {}'.format(
            data['isp'],
            data['city'],
            data['region'],
            data['country_code'],
            data['latitude'],
            data['longitude'],
        ))

    @Plugin.command('emoji', '<emoji:str>')
    def emoji(self, event, emoji):
        if not EMOJI_RE.match(emoji):
            return event.msg.reply('Unknown emoji: `{}`'.format(emoji))

        fields = []

        name, eid = EMOJI_RE.findall(emoji)[0]
        fields.append('**ID:** {}'.format(eid))
        fields.append('**Name:** {}'.format(name))

        guild = self.state.guilds.find_one(lambda v: eid in v.emojis)
        if guild:
            fields.append('**Guild:** {} ({})'.format(guild.name, guild.id))

        url = 'https://discordapp.com/api/emojis/{}.png'.format(eid)
        r = requests.get(url)
        r.raise_for_status()
        return event.msg.reply('\n'.join(fields), attachment=('emoji.png', r.content))

    @Plugin.command('jumbo', '<emojis:str...>')
    def jumbo(self, event, emojis):
        urls = []

        for emoji in emojis.split(' ')[:5]:
            if ' '.join(list(emoji)) in EMOJI_ALIAS_UNICODE.values():
                urls.append(get_emoji_url(emoji))
            elif EMOJI_RE.match(emoji):
                _, eid = EMOJI_RE.findall(emoji)[0]
                urls.append('https://discordapp.com/api/emojis/{}.png'.format(eid))
            else:
                return event.msg.reply(u'Invalid emoji: `{}`'.format(emoji.replace('`', '')))

        width, height, images = 0, 0, []

        for r in Pool(6).imap(requests.get, urls):
            r.raise_for_status()
            img = Image.open(BytesIO(r.content))
            height = img.height if img.height > height else height
            width += img.width + 10
            images.append(img)

        image = Image.new('RGBA', (width, height))
        width_offset = 0
        for img in images:
            image.paste(img, (width_offset, 0))
            width_offset += img.width + 10

        combined = BytesIO()
        image.save(combined, 'png', quality=55)
        combined.seek(0)
        return event.msg.reply('', attachment=('emoji.png', combined))

    @Plugin.command('seen', '<user:user>')
    def seen(self, event, user):
        try:
            msg = Message.select(Message.timestamp).where(
                Message.author_id == user.id
            ).order_by(Message.timestamp.desc()).limit(1).get()
        except Message.DoesNotExist:
            return event.msg.reply("I've never seen {}".format(user))

        event.msg.reply('I last saw {} {} ({})'.format(
            user,
            humanize.naturaltime(datetime.utcnow() - msg.timestamp),
            msg.timestamp
        ))

    @Plugin.command('jpeg', '<url:str>')
    def jpeg(self, event, url):
        url = URL_REGEX.findall(url)

        if len(url) != 1:
            return event.msg.reply('Invalid image URL')
        url = url[0]

        if url[-1] == '>':
            url = url[:-1]

        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            img = Image.open(BytesIO(r.content))
        except:
            return event.msg.reply('Invalid image')

        output = BytesIO()
        img.save(output, 'jpeg', quality=1, subsampling=0)
        output.seek(0)
        event.msg.reply('', attachment=('image.jpg', output))
