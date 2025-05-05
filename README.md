# Tracking Kirin

Bot for fast osu! and Quaver score tracking. It's intended to be used on a single server, with a unique osu! API key, so that a low update interval can be used without hitting the osu! API rate limits.

![A few osu! scores reported by the bot.](https://user-images.githubusercontent.com/1794388/79680328-35ff3d80-8217-11ea-86d5-a11f73d8f0a1.png)

![A Quaver score reported by the bot.](https://user-images.githubusercontent.com/1794388/129768007-0be30cba-1041-4adb-8647-d6492e0ce8e0.png)

## Usage

You will need Python 3.9, a Discord bot user (create one [here](https://discordapp.com/developers/applications)) and an osu! API key (get one [here](https://osu.ppy.sh/p/api/)).
1. Fill in the values in `config.toml`.
1. `uv run main.py`

Bot commands:
- `!track <osu|taiko|ctb|mania|quaver_4k|quaver_7k> <username>` - track someone's top scores in the current channel.

  E.g. `!track mania YaLTeR`
- `!track-stop <osu|taiko|ctb|mania|quaver_4k|quaver_7k> <username>` - stop tracking someone in the current channel.
- `!embed` - embed debugging command, if you don't know if you need to use this then you don't.

## Code quality

Not the cleanest; the bot has worked without issues since the very first time I launched it, so I never bothered doing any refactoring.
