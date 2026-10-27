# RAAZICID AI components and how we evaluate them

Four AI parts, all **advisory**: a person (donor or admin) always makes the final choice, and every
suggestion is stored next to that choice so it can be measured.

| Part | Method | Where |
|---|---|---|
| Photo → category | Deep learning: MobileNetV2 (PyTorch), transfer learning | `ml/train_classifier.ipynb`, `backend/app/services/classifier.py` |
| Rider recommendation | Rule-based weighted score, explainable | `backend/app/services/recommend.py` |
| Food urgency | Rule-based score with reasons | `backend/app/services/urgency.py` |
| Rider document check | Large language model with vision (Claude) | `backend/app/services/doc_review.py` |

## 1. Photo classifier

**Task.** Given a donor's photo, rank the 12 categories. The app shows the top 3 with confidence and
pre-selects the first one when it is at least 60% sure. The donor confirms or changes it.

**Why MobileNetV2.** Small (≈3.5 M parameters, ≈9 MB file) and fast on a normal CPU server, which suits a
student budget, yet accurate after transfer learning from ImageNet.

**Data (option C).**
- Training: Open Images V7, Google's openly licensed (CC BY 2.0) dataset, using its *human-verified
  image-level labels*. Each of our categories maps to several Open Images labels (see notebook, cell 2);
  each photo is given to exactly one category, most specific first (a *Coat* is Winter support, not Clothes).
  About 300 photos per category, split 70 / 15 / 15 into train / validation / test.
- Real-world test: our own phone photos of real items (20–30 per category), never used for training.

**Training.** 224×224 input, augmentation (random crop, flip, colour jitter, small rotation),
class-weighted cross-entropy with label smoothing 0.1. Stage 1: 3 epochs training only the new last layer
(lr 1e-3). Stage 2: 10 epochs fine-tuning the whole network (lr 1e-4, AdamW, cosine schedule). The epoch
with the best validation accuracy is kept.

**What to report** (all saved by the notebook in `MyDrive/raazicid/model/`):

| Metric | Open Images test | Own photos |
|---|---|---|
| Accuracy (top-1) | *from labels.json* | *from labels.json* |
| Top-3 accuracy | | |
| Macro F1 | | |

Also include `confusion_open_images_test.png`, `confusion_own_photos.png` and `training_curve.png`,
and discuss which categories get confused (expected: Clothes ↔ Winter support, Blankets ↔ Household,
Food ↔ Grocery / ration) and why the own-photo score is lower than the test score (domain shift:
real donation photos are messier than Open Images photos).

**Live evidence.** `GET /api/v1/admin/ai/stats` (and the AI card on the admin dashboard) shows, on real
donations, how often the donor kept the AI's first choice and how often their choice was in the AI's top 3.

## 2. Rider recommendation

Score 0–100 = distance to pickup (40) + current jobs (20) + available now (15) + rating (15) +
vehicle fit for the load (10). Distance uses live GPS from the last 2 hours, otherwise the rider's home
area. The admin sees the score and each reason, chooses the rider, and the score is saved on the job
(`jobs.recommendation_score`).

Evaluate by comparing the admin's choice with the top recommendation: share of jobs where the admin
picked the #1 rider, and average pickup time for #1 vs other choices. Unit tests:
`backend/tests/test_ai_unit.py`.

## 3. Food urgency

Cooked +35 (dry +5); time since cooking up to +40; quantity up to +20; distance to the nearest
NGO that takes cooked food up to +12. Capped at 100. Cooked food older than 8 hours
gets a warning. Scores are refreshed while the food is waiting, so the admin list stays in the right order.

## 4. Rider document check (Claude)

The admin presses *Run AI check*. Claude receives the four photos and the sign-up name and vehicle
number, and returns a checklist (documents readable, CNIC looks genuine, name matches, licence fits the
vehicle, registration number matches, no signs of editing), each ✓ / ✗ / ?. Saved in
`document_reviews`. It never approves or rejects by itself.

Evaluate on a small labelled set (e.g. 10 genuine and 5 deliberately wrong submissions): how many problems
it catches and how many false alarms it raises.

## Limitations to state honestly

- Open Images photos are cleaner than real donation photos; the own-photo test shows the real gap.
- Some categories (e.g. Wheelchairs / mobility aids, Baby items) have fewer public photos.
- Rule-based scores use weights we chose; they are transparent but not learned from data yet.
- Claude can misread blurry photos; the admin decision stays final.
