# MLKit Samples

A collection of quickstart samples demonstrating the [ML Kit](https://developers.google.com/ml-kit) APIs on Android and iOS.

Note: due to how this repo works, we no longer accept pull requests directly. Instead, we'll patch them internally and then sync them out.

---

## נוכחות פלוגתית - אפליקציית הנוכחות

🔗 **קישור לאפליקציה:** https://attendance-ploga.web.app

---

## 🚀 הגדרת העלאה אוטומטית לאתר (Firebase CI/CD)

כדי שכל שינוי שנדחף ל-`main` יופיע אוטומטית באתר, יש לבצע **פעם אחת** את ההגדרה הבאה.

---

### שלב 1 — יצירת מפתח Service Account ב-Firebase

1. היכנסו ל-[Firebase Console](https://console.firebase.google.com)
2. בחרו את הפרויקט **`attendance-ploga`**
3. לחצו על **⚙️ Project settings** (הגדרות פרויקט) — בצד שמאל למעלה
4. עברו ללשונית **Service accounts**
5. לחצו על **Generate new private key** (כפתור כחול בתחתית העמוד)
6. אשרו בחלון שנפתח — קובץ JSON יוריד למחשבכם

---

### שלב 2 — העתקת תוכן הקובץ

1. פתחו את קובץ ה-JSON שהורד (בפנקס רשימות / Notepad / VS Code)
2. **בחרו הכל** (`Ctrl+A` / `Cmd+A`) והעתיקו (`Ctrl+C` / `Cmd+C`)

הקובץ נראה בערך כך (זה סוד — אל תשתפו אותו):
```json
{
  "type": "service_account",
  "project_id": "attendance-ploga",
  "private_key_id": "...",
  "private_key": "-----BEGIN RSA PRIVATE KEY-----\n...",
  ...
}
```

---

### שלב 3 — הוספת ה-Secret ב-GitHub ✅

זה השלב שמחבר בין GitHub ל-Firebase.

> ⚠️ **שימו לב:** אין צורך ליצור repository חדש! ה-repository **כבר קיים**.  
> הכפתור נקרא "New repository secret" — כלומר "secret חדש עבור ה-repository הנוכחי", **לא** repository חדש.

1. היכנסו לדף ה-repository הקיים ב-GitHub:  
   **`https://github.com/tomwalker645/mlkit`**

2. לחצו על **Settings** (הגדרות) — בשורה העליונה של ה-repo

3. בתפריט השמאלי, תחת **Security**, לחצו על:  
   **Secrets and variables → Actions**

4. לחצו על הכפתור הירוק **New repository secret**  
   *(זה רק שם של כפתור — לא יוצרים repository חדש)*

5. מלאו את השדות:
   - **Name:** `FIREBASE_SERVICE_ACCOUNT`
   - **Secret:** הדביקו כאן את תוכן קובץ ה-JSON שהעתקתם בשלב 2

6. לחצו **Add secret** — זהו! ✅

---

### איך זה עובד אחרי ההגדרה?

```
דחיפת קוד ל-main  →  GitHub Actions מופעל  →  Firebase Hosting מתעדכן  →  האתר מתעדכן תוך ~1 דקה
```

בכל פעם שתמזגו שינויים לענף `main`, האתר בכתובת  
https://attendance-ploga.web.app  
יתעדכן אוטומטית תוך כ-60 שניות.

---
