# MLKit Samples

A collection of quickstart samples demonstrating the [ML Kit](https://developers.google.com/ml-kit) APIs on Android and iOS.

Note: due to how this repo works, we no longer accept pull requests directly. Instead, we'll patch them internally and then sync them out.

## Multilingual Support / תמיכה רב-לשונית

Questions and interactions in any language are welcome, including **Hebrew (עברית)**. You may ask questions, report issues, or follow tutorials in your preferred language.

### Tips for Hebrew and Non-ASCII Users on Windows (PowerShell)

When running Python scripts that output non-ASCII characters (such as Hebrew text), you may see garbled output in PowerShell. Use the following tips to ensure correct UTF-8 display:

```powershell
# Set the console to UTF-8 before running your script
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

# Navigate to your script directory (replace with your actual path)
cd "C:\path\to\your\project"

# Run your script and save output to a file
py your_script.py > output.txt 2>&1

# View the output
type output.txt
```

If Hebrew text still appears garbled when using `type`, open `output.txt` in **Notepad** or **VS Code** which handle UTF-8 correctly.
