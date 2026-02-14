from langdetect import detect, DetectorFactory
from pathlib import Path
import os
import shutil

# Make results consistent
DetectorFactory.seed = 0

# Setup dummy files
if Path("test_content_detect").exists():
    shutil.rmtree("test_content_detect")
os.makedirs("test_content_detect", exist_ok=True)

english_text = """
1
00:00:20,000 --> 00:00:24,400
The quick brown fox jumps over the lazy dog.
I am going to the store to buy some bread and milk.
"""

spanish_text = """
1
00:00:20,000 --> 00:00:24,400
El zorro marrón rápido salta sobre el perro perezoso.
Voy a la tienda a comprar pan y leche.
"""

turkish_text = """
1
00:00:20,000 --> 00:00:24,400
Hızlı kahverengi tilki tembel köpeğin üzerine atlar.
Markete gidip ekmek ve süt alacağım.
"""

files = {
    "random_name_1.srt": english_text,
    "random_name_2.srt": spanish_text,
    "random_name_3.srt": turkish_text,
}

print(f"{'Filename':<30} | {'Detected':<10}")
print("-" * 45)

for fname, content in files.items():
    p = Path("test_content_detect") / fname
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)

    # Read and detect
    with open(p, "r", encoding="utf-8") as f:
        text = f.read()

    try:
        lang = detect(text)
    except:
        lang = "error"

    print(f"{fname:<30} | {lang:<10}")

# Cleanup
shutil.rmtree("test_content_detect")
