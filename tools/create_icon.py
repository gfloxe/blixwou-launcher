"""Source-drawn launcher monogram; no proprietary Minecraft icon."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1]
im = Image.new("RGBA", (256, 256), (18, 10, 31, 255))
d = ImageDraw.Draw(im)
d.rounded_rectangle((8, 8, 248, 248), 48, fill="#211232", outline="#b984ff", width=6)
d.polygon([(65, 48), (151, 48), (188, 82), (166, 119), (192, 150), (174, 199), (65, 199)], fill="#ae70ff")
d.polygon([(102, 82), (144, 82), (151, 94), (142, 111), (102, 111)], fill="#211232")
d.polygon([(102, 143), (148, 143), (153, 158), (147, 168), (102, 168)], fill="#211232")
im.save(root / "assets" / "blixwou.ico", sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
