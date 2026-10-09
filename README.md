# worlds-cal

Subscribable iCalendar feed of the League of Legends World Championship.

Subscribe: `webcal://rinneso.github.io/worlds-cal/worlds.ics`

`build.py` pulls the schedule from the lolesports.com API and writes `public/worlds.ics`.
A GitHub Actions cron rebuilds it every 15 minutes and deploys to Pages. Each match
keeps a stable UID, so TBD slots update in place when teams are decided, and finished
matches show the score.

It always follows the newest Worlds tournament the API lists, so it rolls over to next
year without changes. GitHub disables scheduled workflows after 60 days with no repo
activity; re-enable it from the Actions tab before next Worlds.
