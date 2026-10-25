# Donation photo classifier (Phase 5)

Suggests a donation's category from its photo, e.g. *Blankets 92% · Winter support 5% · Clothes 2%*.
The donor always confirms or changes it; the suggestion and the donor's choice are both saved, so we can
measure how often the AI was right on real donations.

| | |
|---|---|
| Model | MobileNetV2 (PyTorch / torchvision), ImageNet weights, fine-tuned on our 12 categories |
| Training data | Open Images V7 (Google, CC BY 2.0), ~300 photos per category, matched by label |
| Real-world test | Our own phone photos, 20–30 per category, **never used for training** |
| Training | Google Colab, free T4 GPU, about 30–60 minutes |
| Output | `raazicid_classifier.pt` (TorchScript) + `labels.json` (categories, preprocessing, metrics) |

## Two experiments

| Notebook | Trains on | Tests on | Result so far |
|---|---|---|---|
| `train_classifier.ipynb` (experiment 1) | Open Images V7 | Open Images test split (+ own photos) | 59.5% top-1, 86% top-3 |
| `train_own_dataset.ipynb` (experiment 2) | **Our own photos** | Our own photos of **different** items | |
| `train_colab_cell.py` (simplest, one Colab cell) | Our own photos, similar categories grouped | Automatic 15% test split | 96% top-1 on 6 categories (first run) |

**Simplest way:** paste `train_colab_cell.py` into one Colab cell (T4 GPU) and run it. It reads
`MyDrive/raazicid/dataset/` (any folder layout, loose folder names, `.jfif` too) and trains
*blankets + winter support* and *books + school supplies* as one class each, because they look alike.
The app still keeps all 12 categories: when the model picks a group, it shows both and the donor taps one.

Experiment 1 showed that Open Images labels are noisy for our task (a photo labelled "Clothing" is usually a
person, not a pile of clothes), so experiment 2 trains on photos that look like real donations.

### Experiment 2: our own dataset

In Google Drive:

```
MyDrive/raazicid/dataset/
  train/   food/ grocery_ration/ clothes/ blankets/ winter_support/ hygiene/
           baby/ household/ school_supplies/ books/ mobility_aids/ emergency_relief/
  test/    (same 12 folders)
```

- **train/**: 100+ photos per category if possible (at least 50). Many different items, rooms, angles, light.
- **test/**: 20–30 per category of **other items** than in train (photos of the same blanket from two angles
  must not be split between train and test, or the score is too optimistic).
- Without a `test/` folder, put the 12 folders straight into `dataset/` and 20% is kept aside automatically.
- JPG, PNG, WEBP and iPhone HEIC work. The notebook fixes phone rotation, skips unreadable files, warns
  about unknown folder names, and removes exact duplicates of train photos from test.

Run it in Colab the same way (T4 GPU, Run all). Output goes to `MyDrive/raazicid/model_own/`:
`raazicid_classifier.pt`, `labels.json`, `confusion_own_test.png`, `training_curve.png`, `mistakes.png`.
Copy the first two into `backend/models/`.

## 1. Take your own test photos (experiment 1)

Take 20–30 photos per category with a phone, like a donor would: items on a bed, floor or table,
normal light, some messy backgrounds. Different items, not 30 photos of the same blanket.

In Google Drive, make these folders and put the photos in them:

```
MyDrive/raazicid/own_test/
  food/  grocery_ration/  clothes/  blankets/  winter_support/  hygiene/
  baby/  household/  school_supplies/  books/  mobility_aids/  emergency_relief/
```

(The notebook also creates `MyDrive/raazicid/own_test/` if it is missing.)

## 2. Train

1. Open `ml/train_classifier.ipynb` in Google Colab (colab.research.google.com → Upload).
2. Runtime → Change runtime type → **T4 GPU**.
3. Runtime → **Run all**. Allow Google Drive access when asked.
4. Cell 3 prints which Open Images labels exist for each category; cell 5 warns if a category got
   fewer than 100 photos. Those categories need more of your own photos.

## 3. Use it in the backend

1. From `MyDrive/raazicid/model/`, download `raazicid_classifier.pt` and `labels.json`.
2. Put both in `backend/models/` (this folder is not in git: the model is about 9 MB).
3. Install PyTorch (CPU is enough) in the backend virtual environment:
   ```powershell
   pip install torch --index-url https://download.pytorch.org/whl/cpu
   pip install pillow
   ```
4. Restart the backend. `GET /api/v1/ai/status` should say `"classifier": "ready"`.

Without the model or PyTorch, everything still works; the app just asks the donor to choose the
category themselves.

## 4. For the thesis

`MyDrive/raazicid/model/` also has `confusion_open_images_test.png`, `confusion_own_photos.png`,
`training_curve.png`, and `labels.json → metrics` with accuracy, top-3 accuracy and per-category
precision / recall / F1. See `docs/ai-evaluation.md` for how to report them.
