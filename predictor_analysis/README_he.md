# הוראות שימוש — ניתוח יישובים מנבאים (עברית)

**הכלי הזה קורא קובץ ייצוא טלגרם (`result_filtered.json`) ומייצר שתי טבלאות:**

1. **10 יישובים מנבאים הטובים ביותר** — אלה שהאזעקה בהם מקדימה בצורה הכי אמינה אזעקה ביישוב היעד (בית חגי), בחלון זמן של 15 עד 600 שניות.
2. **3 טריגרים מבצעיים מובילים** — ציון משוקלל שמשלב דיוק, עוצמת זמן הקדמה, ונפח אזעקות.

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
   https://github.com/tomwalker645/mlkit/blob/copilot/create-tables-from-json/predictor_analysis/analyze_predictors_en_safe.py
   ```
2. לחץ על כפתור **"Raw"** (בפינה הימנית העליונה של הקוד)
3. לחץ **Ctrl+S** → שמור בשם `analyze_predictors_en_safe.py` בתיקייה `C:\Users\User\Downloads`

---

## שלב 2 — הרץ את הסקריפט

פתח PowerShell (חפש "PowerShell" בתפריט התחל) והדבק את הפקודות הבאות **בדיוק כפי שהן**:

```powershell
cd "C:\Users\User\Downloads"
py analyze_predictors_en_safe.py --input result_filtered.json --target AUTO_BEIT_HAG --min-volume 20 > output.txt 2>&1
type output.txt
```

---

## שלב 3 — מה הפלט אומר

```
=== Predictor Analysis ===
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

**טבלה 2** היא המסקנה המעשית — 3 היישובים שכדאי לעקוב אחריהם כדי לקבל אזהרה מוקדמת לבית חגי.

---

## פתרון תקלות נפוצות

| שגיאה שרואים | הסיבה | הפתרון |
|---|---|---|
| `ERROR: Input file not found` | הקובץ `result_filtered.json` לא נמצא בתיקייה | בדוק שהקובץ נמצא ב-`C:\Users\User\Downloads` ושאין שגיאת כתיב |
| `ERROR: No rocket-alert settlement events found` | תאריך ההתחלה מוקדם מדי או הפורמט שונה | נסה להוסיף `--start-date 2024-01-01` לפקודה |
| `ERROR: Could not auto-detect a target` | לא נמצא יישוב עם המילים "בית" + "חג" בנתונים | צור קשר ושלח את הפלט של השגיאה |
| שגיאת Python בכלל | Python לא מותקן | הורד מ- https://www.python.org |

---

## הערה חשובה — למה Copilot לא יכול לבצע זאת עבורך

הסקריפט רץ **רק על המחשב שלך** כי הקובץ `result_filtered.json` נמצא **רק אצלך** — הוא לא הועלה לאינטרנט.  
GitHub ו-Copilot יכולים לשמור את **קוד הסקריפט** בלבד, אבל הם לא יכולים לגשת לקבצים שיושבים על המחשב שלך.

**בקצרה:** הורד את הסקריפט, שים אותו ליד הקובץ JSON, והרץ את פקודת PowerShell משלב 2.
