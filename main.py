#!/usr/bin/python3

import asyncio
from enum import Enum
import dateutil.parser
import aiohttp
import discord
import logging
import toml
from osuapi import OsuApi, AHConnector, OsuMode


class Mode(Enum):
    osu = 0, "osu!standard"
    taiko = 1, "osu!taiko"
    ctb = 2, "osu!catch"
    mania = 3, "osu!mania"
    quaver_4k = 4, "Quaver 4K"
    quaver_7k = 5, "Quaver 7K"

    def __new__(cls, value, display):
        obj = object.__new__(cls)
        obj._value_ = value
        obj.display_name = display
        return obj

    def __str__(self):
        return self.display_name

    def is_osu_mode(self):
        try:
            _ = OsuMode[self.name]
            return True
        except KeyError:
            return False

    def osu_mode(self):
        return OsuMode[self.name]

    def quaver_mode(self):
        if self.value < self.quaver_4k.value:
            raise KeyError

        return self.value - self.quaver_4k.value + 1


def save_config():
    with open('config.toml', 'w') as f:
        toml.dump(config, f)


async def get_quaver_top_scores(user_id: int, mode: int):
    async with await session.get(f'https://api.quavergame.com/v1/users/scores/best?id={user_id}&mode={mode}') as resp:
        resp = await resp.json()
        return resp['scores']


async def get_top_scores(mode: Mode, user_id: int):
    logging.info(f'Getting top scores for {user_id} in {mode}.')

    try:
        scores = await osu_api.get_user_best(user_id, mode=mode.osu_mode(), limit=100)
    except KeyError:
        scores = await get_quaver_top_scores(user_id, mode=mode.quaver_mode())

    return scores


async def add_users_to_tracker():
    for channel in config.setdefault('channels', {}).values():
        for user_id, modes in channel.items():
            for mode in modes:
                await tracker.add_user(Mode[mode], user_id)


class Tracker:
    def __init__(self):
        self.scores = {mode: {} for mode in Mode}

    async def add_user(self, mode, user_id):
        scores = self.scores[mode]
        if user_id in scores:
            return

        scores[user_id] = await get_top_scores(mode, int(user_id))

    async def remove_user(self, mode, user_id):
        scores = self.scores[mode]
        if user_id in scores:
            return

        del scores[user_id]

    async def update_scores(self):
        results = {mode: {} for mode in Mode}

        for mode, scores in self.scores.items():
            for user_id, old_scores in scores.items():
                current_scores = await get_top_scores(mode, int(user_id))

                new_scores = []
                for i, score in enumerate(current_scores):
                    if score not in old_scores:
                        new_scores.append((i + 1, score))

                scores[user_id] = current_scores

                if len(new_scores) != 0:
                    results[mode][user_id] = new_scores

        return results


class MyClient(discord.Client):
    def __init__(self, *args, **kwargs):
        intents = discord.Intents.default()
        intents.message_content = True
        kwargs.update(intents=intents)
        super().__init__(*args, **kwargs)
        self.bg_task = asyncio.get_event_loop().create_task(self.update_tracker())

    async def update_tracker(self):
        await self.wait_until_ready()
        while not self.is_closed():
            await asyncio.sleep(config['update_interval'])
            logging.info('Updating the tracker.')

            try:
                new_scores = await tracker.update_scores()
                print(new_scores)
                #  new_scores[Mode.taiko] = {
                #      '3910006': [(1, tracker.scores[Mode.taiko]['3910006'][0])]
                #  }
                #  new_scores[Mode.osu] = {
                #      '3910006': [(1, tracker.scores[Mode.osu]['3910006'][0])]
                #  }
                # new_scores[Mode.mania] = {
                #     '3910006': [(1, tracker.scores[Mode.mania]['3910006'][0])]
                # }
                #  new_scores[Mode.ctb] = {
                #      '3910006': [(1, tracker.scores[Mode.ctb]['3910006'][0])]
                #  }
                # new_scores[Mode.quaver_4k] = {
                #     '273': [(1, tracker.scores[Mode.quaver_4k]['273'][0])]
                # }
                # new_scores[Mode.quaver_7k] = {
                #     '273': [(1, tracker.scores[Mode.quaver_7k]['273'][0])]
                # }

                for channel_id, config_channel in config['channels'].items():
                    channel = self.get_channel(int(channel_id))

                    for user_id, modes in config_channel.items():
                        for mode in modes:
                            #  print(f'{channel_id} {user_id} {mode}')
                            mode = Mode[mode]
                            for i, score in new_scores[mode].get(user_id, []):
                                if mode.is_osu_mode():
                                    color = discord.Colour.from_rgb(255, 102, 170)
                                    icon_url = f'https://a.ppy.sh/{user_id}'
                                    name_extra = ''

                                    if mode == Mode.ctb:
                                        suffix = 'fruits'
                                    else:
                                        suffix = mode.osu_mode().name

                                    profile_url = f'https://osu.ppy.sh/users/{user_id}/{suffix}'

                                    rating = f'**{score.pp:,.0f}pp**'
                                    score_id = score.score_id
                                    map_id = score.beatmap_id
                                    mods = score.enabled_mods.shortname
                                    accuracy = score.accuracy(mode.osu_mode()) * 100
                                    grade = score.rank.replace('X', 'SS')
                                    timestamp = score.date

                                    beatmaps = await osu_api.get_beatmaps(
                                        beatmap_id=score.beatmap_id,
                                        include_converted=True)
                                    beatmap = beatmaps[0]

                                    map_artist = beatmap.artist
                                    map_title = beatmap.title
                                    map_diff = beatmap.version
                                    map_url = beatmap.url
                                    thumbnail_url = f'https://b.ppy.sh/thumb/{beatmap.beatmapset_id}l.jpg'

                                    del beatmap

                                    users = await osu_api.get_user(int(user_id),
                                                                   mode=mode,
                                                                   event_days=0)
                                    user = users[0]

                                    username = user.username
                                    total_rating = f'{user.pp_raw:,.0f}pp'
                                    rank = user.pp_rank

                                    del user
                                else:
                                    color = discord.Colour.from_rgb(69, 214, 245)
                                    profile_url = f'https://quavergame.com/user/{user_id}?mode={mode.quaver_mode()}'

                                    if mode == Mode.quaver_4k:
                                        name_extra = ' 4K'
                                    else:
                                        name_extra = ' 7K'

                                    rating = f'**{score["performance_rating"]:.2f} QR**'
                                    score_id = score['id']
                                    map_id = score['map']['id']
                                    mods = score['mods_string']
                                    mods = '' if mods == 'None' else mods
                                    accuracy = score['accuracy']
                                    grade = score['grade']
                                    timestamp = dateutil.parser.isoparse(score['time'])

                                    map_artist = score['map']['artist']
                                    map_title = score['map']['title']
                                    map_diff = score['map']['difficulty_name']
                                    map_url = f'https://quavergame.com/mapset/map/{score["map"]["id"]}'
                                    thumbnail_url = f'https://cdn.quavergame.com/mapsets/{score["map"]["mapset_id"]}.jpg'

                                    async with session.get(f'https://api.quavergame.com/v1/users/full/{user_id}') as resp:
                                        resp = await resp.json()
                                    user = resp['user']

                                    if mode == Mode.quaver_4k:
                                        mode_str = 'keys4'
                                    else:
                                        mode_str = 'keys7'

                                    username = user['info']['username']
                                    total_rating = f'{user[mode_str]["stats"]["overall_performance_rating"]:,.2f} QR'
                                    rank = user[mode_str]['globalRank']
                                    icon_url = user['info']['avatar_url']

                                    del user

                                del score

                                logging.info(
                                    f'Notifying about a new {rating} {mode} score {score_id} for {user_id} on {map_id}.'
                                )

                                mods = f' _+{mods}_' if len(mods) > 0 else ''

                                description = f'''\
{rating}
Personal Best **#{i}**
**{accuracy:.2f}%** {grade}{mods}'''

                                embed = discord.Embed(
                                    title=f'{map_artist} - {map_title} [{map_diff}]',
                                    description=description,
                                    url=map_url,
                                    timestamp=timestamp,
                                    colour=color)
                                embed.set_author(
                                    name=f'{username}: {total_rating} #{rank:,d}{name_extra}',
                                    url=profile_url,
                                    icon_url=icon_url)
                                embed.set_thumbnail(
                                    url=thumbnail_url
                                )

                                await channel.send(embed=embed)
            except Exception as e:
                logging.exception(e)

    async def on_ready(self):
        print(f'Logged on as {self.user}.')

    async def on_message(self, message):
        if message.author.id != int(config['admin_user_id']):
            return

        channel = message.channel
        fields = message.content.split(maxsplit=2)

        if fields[0] == '!track':
            if len(fields) != 3:
                await message.add_reaction('❌')
                await channel.send('`!track <osu|taiko|ctb|mania|quaver_4k|quaver_7k> <username>`')
                return

            mode, username = fields[1:]

            try:
                mode = Mode[mode]
            except KeyError:
                await message.add_reaction('❌')
                await channel.send('`!track <osu|taiko|ctb|mania|quaver_4k|quaver_7k> <username>`')
                return

            try:
                users = await osu_api.get_user(username, mode=mode.osu_mode(), event_days=0)
            except KeyError:
                async with session.get(f'https://api.quavergame.com/v1/users/search/{username}') as resp:
                    resp = await resp.json()
                    users = resp['users']

            if len(users) == 0:
                await message.add_reaction('❌')
                await channel.send(f'This user could not be found.')
                return

            user = users[0]
            channels = config.setdefault('channels', {})
            config_channel = channels.setdefault(str(channel.id), {})

            if mode.is_osu_mode():
                user_id = user.user_id
                username = user.username
                rank = user.pp_rank
            else:
                user_id = user['id']
                username = user['username']

                async with session.get(f'https://api.quavergame.com/v1/users/full/{user_id}') as resp:
                    resp = await resp.json()
                    user = resp['user']

                    if mode == Mode.quaver_4k:
                        mode_str = 'keys4'
                    else:
                        mode_str = 'keys7'

                    rank = user[mode_str]['globalRank']

            del user

            modes = config_channel.setdefault(str(user_id), set())
            if type(modes) == list:
                modes = set(modes)
                config_channel[str(user_id)] = modes

            modes.add(mode.name)

            logging.info(
                f'Added {user_id} ({username} #{rank}) with mode {mode}.'
            )

            save_config()

            await tracker.add_user(mode, str(user_id))
            await channel.send('Now tracking {} #{:,.0f}.'.format(username, rank))
        elif fields[0] == '!track-stop':
            if len(fields) != 3:
                await message.add_reaction('❌')
                await channel.send('`!track-stop <osu|taiko|ctb|mania|quaver_4k|quaver_7k> <username>`')
                return

            mode, username = fields[1:]

            try:
                mode = Mode[mode]
            except KeyError:
                await message.add_reaction('❌')
                await channel.send('`!track-stop <osu|taiko|ctb|mania|quaver_4k|quaver_7k> <username>`')
                return

            try:
                users = await osu_api.get_user(username, mode=mode.osu_mode(), event_days=0)
            except KeyError:
                async with session.get(f'https://api.quavergame.com/v1/users/search/{username}') as resp:
                    resp = await resp.json()
                    users = resp['users']

            if len(users) == 0:
                await message.add_reaction('❌')
                await channel.send(f'This user could not be found.')
                return

            user = users[0]
            channels = config.setdefault('channels', {})
            config_channel = channels.setdefault(str(channel.id), {})

            if mode.is_osu_mode():
                user_id = user.user_id
                username = user.username
                rank = user.pp_rank
            else:
                user_id = user['id']
                username = user['username']

                async with session.get(f'https://api.quavergame.com/v1/users/full/{user_id}') as resp:
                    resp = await resp.json()
                    user = resp['user']

                    if mode == Mode.quaver_4k:
                        mode_str = 'keys4'
                    else:
                        mode_str = 'keys7'

                    rank = user[mode_str]['globalRank']

            del user

            modes = config_channel.setdefault(str(user_id), set())
            if type(modes) == list:
                modes = set(modes)
                config_channel[str(user_id)] = modes

            modes.remove(mode.name)

            if len(modes) == 0:
                del config_channel[str(user_id)]
            if len(config_channel) == 0:
                del channels[str(channel.id)]

            logging.info(
                f'Removed {user_id} ({username} #{rank}) with mode {mode}.'
            )

            save_config()

            await tracker.remove_user(mode, str(user_id))
            await channel.send('Removed {} #{:,.0f}.'.format(username, rank))
        elif fields[0] == '!embed':
            fields = message.content.split('\n')[1:]
            if len(fields) < 9:
                await message.add_reaction('❌')
                return

            from osuapi.dictmodel import DateConverter

            title, url, timestamp, colour, author_name, author_url, author_icon, thumbnail = fields[:
                                                                                                    8]
            description = '\n'.join(fields[8:])

            timestamp = DateConverter(timestamp)
            r, g, b = list(map(int, colour.split()))
            colour = discord.Colour.from_rgb(r, g, b)
            embed = discord.Embed(title=title,
                                  description=description,
                                  url=url,
                                  timestamp=timestamp,
                                  colour=colour)
            embed.set_author(name=author_name,
                             url=author_url,
                             icon_url=author_icon)
            embed.set_thumbnail(url=thumbnail)

            await channel.send(embed=embed)
        else:
            return

        await message.add_reaction('✅')


logging.basicConfig(level=logging.INFO)

with open('config.toml', 'r') as f:
    config = toml.load(f)

session = aiohttp.ClientSession()
osu_api = OsuApi(config['api_keys']['osu'], connector=AHConnector())
tracker = Tracker()


async def main():
    await add_users_to_tracker()

    client = MyClient()

    try:
        await client.start(config['api_keys']['discord'])
    except KeyboardInterrupt:
        pass
    finally:
        await client.close()
        await session.close()


asyncio.get_event_loop().run_until_complete(main())