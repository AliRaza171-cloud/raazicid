# RAAZICID: train the photo classifier on our own photos. Paste this into ONE Colab cell and run it.
# Similar categories are trained together (blankets + winter support, books + school supplies);
# the app still keeps all 12 categories separate and shows both when the model picks a group.
!pip -q install pillow-heif
import os, re, json, random, datetime, numpy as np, torch
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms
from PIL import Image, ImageOps
from sklearn.model_selection import train_test_split
import pillow_heif; pillow_heif.register_heif_opener()
from google.colab import drive; drive.mount("/content/drive")

DATA = "/content/drive/MyDrive/raazicid/dataset"      # category folders are anywhere inside this folder
OUT = "/content/drive/MyDrive/raazicid/model_own"     # the trained model is saved here
os.makedirs(OUT, exist_ok=True)
IDS = {"food": 1, "grocery_ration": 2, "clothes": 3, "blankets": 4, "winter_support": 5, "hygiene": 6, "baby": 7,
       "household": 8, "school_supplies": 9, "books": 10, "mobility_aids": 11, "emergency_relief": 12}
GROUPS = {"blankets": "blankets_winter", "winter_support": "blankets_winter",   # trained as one class
          "books": "books_school", "school_supplies": "books_school"}
EXT = (".jpg", ".jpeg", ".jfif", ".png", ".webp", ".heic", ".bmp")
random.seed(42); np.random.seed(42); torch.manual_seed(42)

CLASS_IDS = {}                                       # training class -> app category ids
for slug, cid in IDS.items():
    CLASS_IDS.setdefault(GROUPS.get(slug, slug), []).append(cid)

# Folder names are matched loosely: "grocery and ration", "Grocery_Ration", "wintersupport" all work
def norm(name): return re.sub(r"[^a-z]", "", name.lower().replace(" and ", ""))
SLUG_BY_NORM = {norm(s): s for s in IDS}

# 1. Load the photos (fix phone rotation, make them smaller)
def load(path):
    try:
        im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        im.thumbnail((320, 320))
        return im
    except Exception:
        print("  skipped (cannot read):", os.path.basename(path))
        return None

paths_by_class, folder_counts, unknown = {c: [] for c in CLASS_IDS}, {}, set()
for root, _, files in os.walk(DATA):
    folder = os.path.basename(root)
    slug = SLUG_BY_NORM.get(norm(folder))
    imgs = [os.path.join(root, f) for f in files if f.lower().endswith(EXT)]
    if slug:
        paths_by_class[GROUPS.get(slug, slug)] += imgs
        folder_counts[slug] = folder_counts.get(slug, 0) + len(imgs)
    elif imgs:
        unknown.add(folder)
if unknown:
    print("Folders not matched to a category (ignored):", sorted(unknown))

images, labels, classes = [], [], []
print("Reading photos from Drive...")
for cls, paths in paths_by_class.items():
    loaded = [im for im in map(load, paths) if im is not None]
    parts = " + ".join(f"{s} {folder_counts.get(s, 0)}" for s in IDS if GROUPS.get(s, s) == cls) if cls not in IDS else ""
    print(f"  {cls:17s} {len(loaded):4d} photos" + (f"   ({parts})" if parts else "")
          + ("   <- not used, needs at least 10" if len(loaded) < 10 else ""))
    if len(loaded) >= 10:
        classes.append(cls)
        images += loaded
        labels += [len(classes) - 1] * len(loaded)
assert len(classes) >= 2, "Need at least 2 categories with 10+ photos each. Check the folder names in " + DATA
labels = np.array(labels)

# 2. Split: 70% train, 15% validation (to pick the best epoch), 15% test (final score)
idx = np.arange(len(images))
tr, rest = train_test_split(idx, test_size=0.30, stratify=labels, random_state=42)
va, te = train_test_split(rest, test_size=0.50, stratify=labels[rest], random_state=42)
print(f"\n{len(tr)} train / {len(va)} validation / {len(te)} test photos, {len(classes)} classes")

MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
train_tf = transforms.Compose([transforms.RandomResizedCrop(224, scale=(0.5, 1.0)), transforms.RandomHorizontalFlip(),
                               transforms.RandomRotation(15), transforms.ColorJitter(0.4, 0.4, 0.4),
                               transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
eval_tf = transforms.Compose([transforms.Resize(256), transforms.CenterCrop(224), transforms.ToTensor(), transforms.Normalize(MEAN, STD)])

class Photos(Dataset):
    def __init__(self, ids, tf): self.ids, self.tf = ids, tf
    def __len__(self): return len(self.ids)
    def __getitem__(self, i): return self.tf(images[self.ids[i]]), int(labels[self.ids[i]])

train_dl = DataLoader(Photos(tr, train_tf), batch_size=32, shuffle=True)
val_dl = DataLoader(Photos(va, eval_tf), batch_size=64)
test_dl = DataLoader(Photos(te, eval_tf), batch_size=64)

# 3. Model: MobileNetV2 already trained on ImageNet; we only teach it our classes (transfer learning)
device = "cuda" if torch.cuda.is_available() else "cpu"
print("Training on", device, "(choose Runtime > Change runtime type > T4 GPU if this says cpu)")
model = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.IMAGENET1K_V2)
model.classifier[1] = nn.Linear(model.last_channel, len(classes))
model = model.to(device)
loss_fn = nn.CrossEntropyLoss(label_smoothing=0.1)

def accuracy(loader):
    model.eval(); right = total = 0
    with torch.no_grad():
        for x, y in loader:
            right += (model(x.to(device)).argmax(1).cpu() == y).sum().item(); total += len(y)
    return right / total

best, best_state = -1, None
for stage, epochs, lr, freeze in [(1, 3, 1e-3, True), (2, 12, 2e-4, False)]:
    for p in model.features.parameters(): p.requires_grad = not freeze
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr, weight_decay=1e-4)
    for ep in range(epochs):
        model.train()
        for x, y in train_dl:
            opt.zero_grad(); loss_fn(model(x.to(device)), y.to(device)).backward(); opt.step()
        val = accuracy(val_dl)
        if val >= best: best, best_state = val, {k: v.clone() for k, v in model.state_dict().items()}
        print(f"  stage {stage} epoch {ep + 1:2d}: validation accuracy {val:.0%}")
model.load_state_dict(best_state)

# 4. Final test on photos the model never saw
model.eval(); top1 = top3 = 0; per = {c: [0, 0] for c in classes}
k = min(3, len(classes))
with torch.no_grad():
    for x, y in test_dl:
        out = model(x.to(device)).cpu()
        best3 = out.topk(k, 1).indices
        for i in range(len(y)):
            ok = best3[i, 0].item() == y[i].item()
            top1 += ok; top3 += y[i].item() in best3[i].tolist()
            per[classes[y[i]]][0] += ok; per[classes[y[i]]][1] += 1
n = len(te)
print(f"\nTEST RESULT: accuracy {top1 / n:.0%}  ·  right answer in top 3: {top3 / n:.0%}  ({n} test photos)")
for c in classes:
    print(f"  {c:17s} {per[c][0]}/{per[c][1]} correct")

# 5. Save for the backend
model = model.cpu().eval()
torch.jit.trace(model, torch.randn(1, 3, 224, 224)).save(f"{OUT}/raazicid_classifier.pt")
json.dump({
    "version": datetime.datetime.now(datetime.timezone.utc).strftime("own-%Y%m%d-%H%M"),
    "architecture": "MobileNetV2 (ImageNet weights, fine-tuned on own photos)",
    "input_size": 224, "resize": 256, "mean": MEAN, "std": STD,
    "categories": [{"index": i, "slug": c, "category_id": CLASS_IDS[c][0], "category_ids": CLASS_IDS[c]}
                   for i, c in enumerate(classes)],
    "train_photos": int(len(tr)),
    "metrics": {"own_photos": {"photos": n, "accuracy": round(top1 / n, 4), "top3_accuracy": round(top3 / n, 4),
                               "per_class": {c: {"correct": per[c][0], "photos": per[c][1]} for c in classes}}},
}, open(f"{OUT}/labels.json", "w"), indent=2)
print(f"\nDONE. Download raazicid_classifier.pt and labels.json from My Drive/raazicid/model_own/ into backend/models/")
