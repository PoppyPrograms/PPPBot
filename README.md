# PPP-Bot

The ONLY official bot for Poppy's Programming Paradise (**PPP**). Please follow the readme!

Link to PPP: https://discord.gg/EGzpccSbb5

## Contributors:

1. Roadrunner
2. Toto
3. Lemon
4. Penne (readme engineer)

## The bot.

What does PPP Bot do?? Good question! I dont know yet 😛

## Economy and games

- `/gambleleaderboard` shows each gambler's gains, losses, and net result.
- `/eatburga` increments your burga count; count confirmations are private and big milestones are public announcements.
- Big burga milestones are 10, 100, and 1,000, then every additional 1,000; private confirmations show every count.
- The designated burga thief can pass a target to steal one available burga once per day.
- `/blackjack`, `/tictactoe`, `/poker`, and `/bingo` are wagered games with player decisions.
- Poker games are shown ephemerally, so holding cards and drawing do not spam the channel.
- Poker's revealed result is posted publicly when the hand ends.
- Bingo games are shown ephemerally, so number calls do not spam the channel.
- Bingo is played against a house bot; the house can win first, and unfinished games lose their wager.
- Bingo's final winner/loser result is posted publicly.
- Once per hour, accessible recent messages are batched with their surrounding
  Discord context and sent to the configured request recorder when available.
- Right-click a server message, choose **Apps**, then **Claim message** to
  collect it. Use `/collection` and `/item` to browse collectibles.
- Use `/give`, `/sell`, `/buy`, `/auction`, `/bid`, `/market`, and
  `/cancel_listing` to trade collectibles.

Balances, gamble statistics, collectibles, listings, bids, and transactions are
stored in `pppbot.sqlite3` at the project root. Enable Discord's **Message
Content Intent** for the bot in the Developer Portal so claimed messages can
be snapshotted.
