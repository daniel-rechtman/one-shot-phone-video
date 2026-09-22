# one-shot-phone-video

סקיל ל-Claude Code + כלי CLI לייצור סרטוני AI קצרים שנראים **מצולמים בטלפון** —
אנכי 9:16, שוט אחד רציף, מסגור חובבני, סאונד סביבתי טבעי, בלי מוזיקה.

רץ על [fal.ai](https://fal.ai) מול **MiniMax H3** (ברירת מחדל) או **Seedance 2.0**.

## מה יש פה

```
skill/SKILL.md                 הדוקטרינה — שיטת התסריט, ההוק, עקביות דמות
skill/references/              תסריט עבודה מלא עם פירוק של כל ביט
cli/seedance.py                הכלי. stdlib בלבד, אין תלויות
cli/README.md                  תיעוד הכלי, תמחור, מלכודות
cli/characters/baby.jpg        character sheet לדוגמה
```

## התקנה

```bash
git clone <this-repo> && cd one-shot-phone-video
ln -s "$PWD/skill" ~/.claude/skills/one-shot-phone-video
echo '{"FAL_KEY":"<מפתח מ-fal.ai/dashboard/keys>"}' > ~/.claude/secrets/fal.json
chmod 600 ~/.claude/secrets/fal.json
```

## שימוש

```bash
cd cli
./seedance.py cost --dur 15 --ar 9:16
./seedance.py ref "<תסריט>" -i characters/baby.jpg --engine h3 --dur 15 --res 2k --ar 9:16
./seedance.py spend
```

## מפתחות

**אין מפתחות בריפו הזה.** הכלי קורא `FAL_KEY` מהסביבה, ואם אין — מ-`~/.claude/secrets/fal.json`
בזמן ריצה. ה-`.gitignore` חוסם `fal.json`, `secrets/`, `.env` ו-`*.key`.

## שני מנועים

| | Seedance 2.0 | MiniMax H3 |
|---|---|---|
| תמחור | לפי טוקנים, ריבועי ברזולוציה | שטוח לשנייה |
| 15ש' ב-2K | — | **$1.95** |
| 15ש' ב-4K | ~$40 | **$2.40** |

H3 זול פי 5 עד פי 17 על אותה משימה. ראה `cli/README.md` לפירוט.
