# ML Kit / TFLite Tutorials

This is a collection of runnable tutorials hosted on Colaboratory. Colaboratory is a hosted Jupyter notebook environment that’s easy to use and requires no setup.

**[ML Kit Image Labeling Model Maker](https://colab.sandbox.google.com/github/googlesamples/mlkit/blob/master/tutorials/mlkit_image_labeling_model_maker.ipynb)** - Follow this Colab to learn how to use an Image Labeling model with TFLite ModelMaker. The TFLite Model Maker library simplifies the process of adapting and converting a TensorFlow neural-network model to a model suitable for on-device ML applications.


---

## Rocket-Alert Predictor Analysis (`analyze_predictors_en.py`)

A command-line Python script that reads a **Telegram JSON export** (e.g. `result_filtered.json`) and produces a clear **ASCII table** identifying which settlements' rocket alerts best predict an alert for a target settlement within a configurable time window.

### Requirements

- Python 3.8 or newer (standard library only, no extra packages needed)
- A Telegram channel export in JSON format containing Hebrew rocket-alert messages

### Quick Start

```powershell
# Windows PowerShell - safe for cp850/cp1252 terminals
cd "C:\Users\User\Downloads"
py tutorials\analyze_predictors_en.py --input result_filtered.json
```

```bash
# Linux / macOS
python3 tutorials/analyze_predictors_en.py --input result_filtered.json
```

The script auto-detects the target settlement (`AUTO_BEIT_HAG` mode) by searching for keys that contain both **bet** (\u05d1\u05d9\u05ea) and **hag** (\u05d7\u05d2).  If auto-detection finds a match it prints the detected key before the table.

### All Options

| Argument | Default | Description |
|---|---|---|
| `--input FILE` | *(required)* | Path to the JSON export file. |
| `--target NAME` | `AUTO_BEIT_HAG` | Target settlement name or `AUTO_BEIT_HAG` to auto-detect. |
| `--start-date YYYY-MM-DD` | `2026-02-28` | Earliest date to include. |
| `--end-date YYYY-MM-DD` | today | Latest date to include. |
| `--min-volume N` | `20` | Minimum alert count a settlement must have to appear in the table. |

### Example

```powershell
py tutorials\analyze_predictors_en.py --input result_filtered.json --target AUTO_BEIT_HAG --min-volume 20 > output_en.txt 2>&1
type output_en.txt
```

### Output

```
[Auto-detected target: ...]
================================================================================
 Predictor Analysis
================================================================================
 Date range : 2026-02-28 .. 2026-03-10
 Target key : ...
 Target cnt : N events (deduplicated to minute)
 Window     : 15s .. 600s lead time
 Min volume : 20

Top 10 settlements by precision:
+--------------------------------+--------+----------+----------+----------+---------+--------------+
| Settlement key                 | Total  | Precision| Avg lead | Med lead |  Recall | Success/Total|
+--------------------------------+--------+----------+----------+----------+---------+--------------+
| ...                            |   NNN  |  NN.N%   |  Nm NNs  |  Nm NNs  |  NN.N%  |    NN/NNN    |
+--------------------------------+--------+----------+----------+----------+---------+--------------+

Top 3 operational triggers (weighted score):
  1) <settlement>  |  precision= NN.N%  |  avg_lead= Nm NNs  |  total=NNN  |  score=0.NNN
```

### Error Handling

If the file path is wrong or missing, the script exits with a clear message:

```
ERROR: Input file not found: result_filtered.json
Please provide the correct path with --input, e.g.:
  python analyze_predictors_en.py --input C:\Users\User\Downloads\result_filtered.json
```

### Encoding Notes

- The JSON file is always read as **UTF-8**.
- All table output uses **ASCII-only** characters so it renders correctly in Windows PowerShell (code pages 850/1252) without any `chcp` changes.
- Hebrew settlement names are stored internally for matching. Redirect output to a file and open it in Notepad or VS Code with UTF-8 encoding if your terminal cannot display Hebrew.

---

## How to make contributions?
Please read and follow the steps in the [CONTRIBUTING.md](CONTRIBUTING.md)
