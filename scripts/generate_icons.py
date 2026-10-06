"""Rasterize the app's own vector logo for PWA install icons (Pillow)."""
from pathlib import Path

from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1] / 'apps/web/public/icons'
for size in (192, 512):
    scale = 3
    image = Image.new('RGB', (512 * scale, 512 * scale), '#7160c7')
    draw = ImageDraw.Draw(image)
    curves = [((255, 256), (213, 179), (186, 164), (150, 164)), ((150, 164), (98, 164), (72, 207), (72, 256)), ((72, 256), (72, 305), (98, 348), (150, 348)), ((150, 348), (186, 348), (213, 333), (255, 256)), ((255, 256), (297, 179), (324, 164), (360, 164)), ((360, 164), (412, 164), (438, 207), (438, 256)), ((438, 256), (438, 305), (412, 348), (360, 348)), ((360, 348), (324, 348), (297, 333), (255, 256))]
    for curve in curves:
        points = []
        for step in range(81):
            t = step / 80
            weights = ((1-t)**3, 3*(1-t)**2*t, 3*(1-t)*t*t, t**3)
            points.append(tuple(round(sum(point[axis] * weight for point, weight in zip(curve, weights)) * scale) for axis in (0, 1)))
        draw.line(points, fill='white', width=30 * scale, joint='curve')
    image.resize((size, size), Image.Resampling.LANCZOS).save(root / f'icon-{size}.png')
print('Generated PWA icons at 192 and 512 pixels.')
