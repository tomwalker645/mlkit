# הוראות שימוש — ניתוח יישובים מנבאים (עברית) — גרסה 2.0

> **מדריך זה מיועד למשתמשי Windows.** למשתמשי Mac/Linux — החלף `py` ב-`python3`.

**הכלי הזה קורא קובץ ייצוא טלגרם (`result_filtered.json`) ומייצר שתי טבלאות:**

1. **N יישובים מנבאים הטובים ביותר** — אלה שהאזעקה בהם מקדימה בצורה הכי אמינה אזעקה ביישוב היעד (בית חגי), בחלון זמן של 15 עד 600 שניות.
2. **K טריגרים מבצעיים מובילים** — ציון משוקלל שמשלב דיוק, עוצמת זמן הקדמה, ונפח אזעקות.

### מה חדש בגרסה 2.0
- **`--output FILE`** — כתיבה ישירה לקובץ UTF-8. **לא צריך עוד `> output.txt`** — עברית תמיד מוצגת נכון.
- **`--list-targets`** — רשימת כל היישובים הזמינים עם ספירת אזעקות, כדי לבחור יעד ספציפי.
- **`--top-n N`** — שלוט בגודל טבלה 1 (ברירת מחדל: 10).
- **`--top-k K`** — שלוט בגודל טבלה 2 (ברירת מחדל: 3).
- **תאריך התחלה דינמי** — ברירת המחדל היא 30 יום אחורה מהיום במקום תאריך קשיח.

---

## דרישות מוקדמות

1. **Python מותקן** במחשב שלך  
   לבדיקה פתח PowerShell וכתב:  
   ```powershell
   py --version
   ```  
   אם מופיע מספר גרסה (למשל `Python 3.13.x`) — הכל בסדר.  
   אם לא — הורד Python מ־ https://www.python.org/downloads/ והתקן.

2. **הקבצים הבאים באותה תיקייה** (בדרך כלל `C:\Users\User\Downloads`):
   - `analyze_predictors_en_safe.py` ← הסקריפט שמנתח את הנתונים
   - `result_filtered.json` ← ייצוא הטלגרם שלך

---

## שלב 1 — הורד את הסקריפט

1. פתח את הקישור הבא בדפדפן:  
   ```
   https://github.com/tomwalker645/mlkit/blob/master/predictor_analysis/analyze_predictors_en_safe.py
   ```
2. לחץ על כפתור **"Raw"** (בפינה הימנית העליונה של הקוד)
3. לחץ **Ctrl+S** → שמור בשם `analyze_predictors_en_safe.py` בתיקייה `C:\Users\User\Downloads`

---

## שלב 2 — הרץ את הסקריפט

פתח PowerShell (חפש "PowerShell" בתפריט התחל) והדבק את הפקודות הבאות **בדיוק כפי שהן**:

```powershell
cd "C:\Users\User\Downloads"
py analyze_predictors_en_safe.py --input result_filtered.json --target AUTO_BEIT_HAG --min-volume 20 --output output.txt
notepad output.txt
```

> **מה החידוש?** הדגל `--output output.txt` כותב את הקובץ ישירות ב-UTF-8.  
> **אין צורך ב-`> output.txt` בכלל** — העברית תמיד מוצגת נכון.

---

## שלב 2ב — גלה אילו יישובים זמינים (רשות)

אם רוצה לנתח יישוב אחר במקום בית חגי, תחילה הצג את רשימת היישובים:

```powershell
py analyze_predictors_en_safe.py --input result_filtered.json --list-targets
```

ואז הרץ עם `--target` וה-**שם המדויק** מהרשימה:

```powershell
py analyze_predictors_en_safe.py --input result_filtered.json --target "שם היישוב" --min-volume 20 --output output.txt
```

---

## שלב 3 — כל הדגלים הזמינים

| דגל | ברירת מחדל | תיאור |
|---|---|---|
| `--input` | *(חובה)* | נתיב לקובץ JSON |
| `--target` | `AUTO_BEIT_HAG` | יישוב יעד. `AUTO_BEIT_HAG` = זיהוי אוטומטי של בית חגי |
| `--start-date` | *(30 יום אחורה)* | תאריך התחלה `YYYY-MM-DD` |
| `--end-date` | *(עכשיו)* | תאריך סיום `YYYY-MM-DD` |
| `--min-volume` | `20` | מינימום אזעקות ליישוב להיכלל בניתוח |
| `--top-n` | `10` | כמה שורות בטבלה 1 |
| `--top-k` | `3` | כמה שורות בטבלה 2 |
| `--output FILE` | *(מסוף)* | שמור תוצאות לקובץ UTF-8 **(מומלץ ב-Windows)** |
| `--list-targets` | — | הצג יישובים זמינים וצא |

---

## שלב 4 — מה הפלט אומר

```
=== Predictor Analysis (v2.0) ===
Target         : בית חגי          ← היישוב שאנחנו מנבאים עבורו
Target events  : 47               ← כמה פעמים הייתה אזעקה בבית חגי
Min volume     : 20               ← רק יישובים עם לפחות 20 אזעקות נלקחים בחשבון

--- Table 1: Top 10 Predictors by Precision ---
#   Settlement   Total  Precision  Avg Lead  ...
1   יישוב_א       85     72.9%      1m 12s   ...   ← האחוז = כמה פעמים מתוך 100 שהאזעקה שם הקדימה את בית חגי
```

### הסבר עמודות הטבלה

| עמודה | משמעות |
|---|---|
| `Settlement` | שם היישוב המנבא |
| `Total` | סך האזעקות ביישוב הזה |
| `Precision` | % מהפעמים שהאזעקה שם הקדימה אזעקה בבית חגי (15–600 שניות אחר כך) |
| `Avg Lead` | זמן הקדמה ממוצע (m=דקות, s=שניות) |
| `Med Lead` | זמן הקדמה חציוני |
| `P(sett\|tgt)` | % מאזעקות בית חגי שקדמה להן אזעקה ביישוב הזה |
| `Hits/Total` | כמה "פגיעות" מתוך כלל האזעקות ביישוב |

```
--- Table 2: Top 3 Operational Triggers ---
1) יישוב_א  |  precision=72.9%  |  avg_lead=1m 12s  |  total=85  |  score=0.612
```

**טבלה 2** היא המסקנה המעשית — K היישובים שכדאי לעקוב אחריהם כדי לקבל אזהרה מוקדמת לבית חגי.

---

## פתרון תקלות נפוצות

| שגיאה שרואים | הסיבה | הפתרון |
|---|---|---|
| `ERROR: Input file not found` | הקובץ `result_filtered.json` לא נמצא בתיקייה | בדוק שהקובץ נמצא ב-`C:\Users\User\Downloads` ושאין שגיאת כתיב |
| `ERROR: No rocket-alert settlement events found` | תאריך ההתחלה מוקדם מדי או הפורמט שונה | נסה להוסיף `--start-date 2024-01-01` לפקודה |
| `ERROR: Could not auto-detect a target` | לא נמצא יישוב עם המילים "בית" + "חג" בנתונים | הרץ עם `--list-targets` ובחר יישוב ידנית |
| שגיאת Python בכלל | Python לא מותקן | הורד מ- https://www.python.org |

---

## הערה חשובה — למה Copilot לא יכול לבצע זאת עבורך

הסקריפט רץ **רק על המחשב שלך** כי הקובץ `result_filtered.json` נמצא **רק אצלך** — הוא לא הועלה לאינטרנט.  
GitHub ו-Copilot יכולים לשמור את **קוד הסקריפט** בלבד, אבל הם לא יכולים לגשת לקבצים שיושבים על המחשב שלך.

**בקצרה:** הורד את הסקריפט, שים אותו ליד הקובץ JSON, והרץ את פקודת PowerShell משלב 2.
