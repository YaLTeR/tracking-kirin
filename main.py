#!/usr/bin/python3

import asyncio
import discord
import logging
import toml

from osuapi import OsuApi, AHConnector, OsuMode


def save_config():
    with open('config.toml', 'w') as f:
        toml.dump(config, f)


def format_beatmap(beatmap):
    return f'{beatmap.artist} - {beatmap.title} [{beatmap.version}]'


def profile_url(mode, user_id):
    if mode == OsuMode.ctb:
        suffix = 'fruits'
    else:
        suffix = mode.name

    return f'https://osu.ppy.sh/users/{user_id}/{suffix}'


async def get_top_100(mode, user_id):
    logging.info(f'Getting top 100 scores for {user_id} in {mode}.')

    scores = await osu_api.get_user_best(user_id, mode=mode, limit=100)
    return scores


async def add_users_to_tracker():
    for channel in config.setdefault('channels', {}).values():
        for user_id, modes in channel.items():
            for mode in modes:
                await tracker.add_user(OsuMode[mode], user_id)


class Tracker():
    def __init__(self):
        self.scores = {mode: {} for mode in OsuMode}

    async def add_user(self, mode, user_id):
        scores = self.scores[mode]
        if user_id in scores:
            return

        scores[user_id] = await get_top_100(mode, int(user_id))

    async def remove_user(self, mode, user_id):
        scores = self.scores[mode]
        if user_id in scores:
            return

        del scores[user_id]

    async def update_scores(self):
        results = {mode: {} for mode in OsuMode}

        for mode, scores in self.scores.items():
            for user_id, old_scores in scores.items():
                current_scores = await get_top_100(mode, int(user_id))

                new_scores = []
                for i, score in enumerate(current_scores):
                    if score not in old_scores:
                        new_scores.append((i + 1, score))

                scores[user_id] = set(current_scores)

                if len(new_scores) != 0:
                    results[mode][user_id] = new_scores

        return results


class MyClient(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bg_task = self.loop.create_task(self.update_tracker())

    async def update_tracker(self):
        await self.wait_until_ready()
        while not self.is_closed():
            await asyncio.sleep(config['update_interval'])
            logging.info('Updating the tracker.')

            try:
                new_scores = await tracker.update_scores()
                print(new_scores)
                #  new_scores[OsuMode.taiko] = {
                #      '3910006':
                #      set(list(tracker.scores[OsuMode.taiko]['3910006'])[:1])
                #  }
                #  new_scores[OsuMode.osu] = {
                #      '3910006':
                #      set(list(tracker.scores[OsuMode.osu]['3910006'])[:1])
                #  }
                #  new_scores[OsuMode.mania] = {
                #      '3910006':
                #      set(list(tracker.scores[OsuMode.mania]['3910006'])[:1])
                #  }
                #  new_scores[OsuMode.ctb] = {
                #      '3910006':
                #      set(list(tracker.scores[OsuMode.ctb]['3910006'])[:1])
                #  }

                for channel_id, config_channel in config['channels'].items():
                    channel = self.get_channel(int(channel_id))

                    for user_id, modes in config_channel.items():
                        for mode in modes:
                            #  print(f'{channel_id} {user_id} {mode}')
                            mode = OsuMode[mode]
                            for i, score in new_scores[mode].get(user_id, []):
                                logging.info(
                                    f'Notifying about a new {score.pp}pp {mode} score {score.score_id} for {user_id} on {score.beatmap_id}.'
                                )

                                beatmaps = await osu_api.get_beatmaps(
                                    beatmap_id=score.beatmap_id,
                                    include_converted=True)
                                beatmap = beatmaps[0]

                                users = await osu_api.get_user(int(user_id),
                                                               mode=mode,
                                                               event_days=0)
                                user = users[0]

                                mods = score.enabled_mods.shortname
                                mods = f' _+{mods}_' if len(mods) > 0 else ''

                                description = '**{:,.0f}pp**\n'.format(
                                                   score.pp) +\
                                               'Personal Best **#{}**\n'.format(i) +\
                                               '**{:.2f}%** {}{}'.format(
                                                   score.accuracy(mode) * 100,
                                                   score.rank.replace('X',
                                                                      'SS'),
                                                   mods)

                                embed = discord.Embed(
                                    title=format_beatmap(beatmap),
                                    description=description,
                                    url=beatmap.url,
                                    timestamp=score.date,
                                    colour=discord.Colour.from_rgb(
                                        255, 102, 170))
                                embed.set_author(
                                    name='{}: {:,.0f}pp #{:,d}'.format(
                                        user.username, user.pp_raw,
                                        user.pp_rank),
                                    url=profile_url(mode, user_id),
                                    icon_url=f'https://a.ppy.sh/{user_id}')
                                embed.set_thumbnail(
                                    url=
                                    f'https://b.ppy.sh/thumb/{beatmap.beatmapset_id}l.jpg'
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
                await channel.send('`!track <osu|taiko|ctb|mania> <username>`')
                return

            mode, username = fields[1:]

            try:
                mode = OsuMode[mode]
            except KeyError:
                await message.add_reaction('❌')
                await channel.send('`!track <osu|taiko|ctb|mania> <username>`')
                return

            users = await osu_api.get_user(username, mode=mode, event_days=0)
            if len(users) == 0:
                await message.add_reaction('❌')
                await channel.send(f'This user could not be found.')
                return

            user = users[0]
            channels = config.setdefault('channels', {})
            config_channel = channels.setdefault(str(channel.id), {})

            modes = config_channel.setdefault(str(user.user_id), set())
            if type(modes) == list:
                modes = set(modes)
                config_channel[str(user.user_id)] = modes

            modes.add(mode.name)

            logging.info(
                f'Added {user.user_id} ({user.username} #{user.pp_rank}) with mode {mode}.'
            )

            save_config()

            await tracker.add_user(mode, str(user.user_id))
            await channel.send('Now tracking {} #{:,.0f}.'.format(user.username, user.pp_rank))
        elif fields[0] == '!track-stop':
            if len(fields) != 3:
                await message.add_reaction('❌')
                await channel.send('`!track-stop <osu|taiko|ctb|mania> <username>`')
                return

            mode, username = fields[1:]

            try:
                mode = OsuMode[mode]
            except KeyError:
                await message.add_reaction('❌')
                await channel.send('`!track-stop <osu|taiko|ctb|mania> <username>`')
                return

            users = await osu_api.get_user(username, mode=mode, event_days=0)
            if len(users) == 0:
                await message.add_reaction('❌')
                await channel.send(f'This user could not be found.')
                return

            user = users[0]
            channels = config.setdefault('channels', {})
            config_channel = channels.setdefault(str(channel.id), {})

            modes = config_channel.setdefault(str(user.user_id), set())
            if type(modes) == list:
                modes = set(modes)
                config_channel[str(user.user_id)] = modes

            modes.remove(mode.name) # TODO: catch KeyError

            if len(modes) == 0:
                del config_channel[str(user.user_id)]
            if len(config_channel) == 0:
                del channels[str(channel.id)]

            logging.info(
                f'Removed {user.user_id} ({user.username} #{user.pp_rank}) with mode {mode}.'
            )

            save_config()

            await tracker.remove_user(mode, str(user.user_id))
            await channel.send('Removed {} #{:,.0f}.'.format(user.username, user.pp_rank))
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

osu_api = OsuApi(config['api_keys']['osu'], connector=AHConnector())

#  async def run():
#      import json
#      scores = await get_top_100(OsuMode.mania, 9914256)
#      scores = {'scores': [{'id': score.score_id, 'pp': score.pp} for score in scores]}
#      with open('scores.toml', 'w') as f:
#          toml.dump(scores, f)
#  asyncio.get_event_loop().run_until_complete(run())
#  exit()

tracker = Tracker()
asyncio.get_event_loop().run_until_complete(add_users_to_tracker())

client = MyClient()
client.run(config['api_keys']['discord'])
