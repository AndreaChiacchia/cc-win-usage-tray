"""Generate the Claude Code pixel-art logo as a PNG, matching the provided reference image."""

from PIL import Image

# The pixel art grid (from the reference image)
# 0 = transparent, 1 = coral/salmon fill (#d97757)
# Grid is designed at 16x14, will be scaled to 64x64

LOGO_GRID = [
    #0 1 2 3 4 5 6 7 8 9 A B C D E F
    [0,0,0,1,1,1,0,0,0,0,1,1,1,0,0,0],  # row 0:  two ears top
    [0,0,0,1,1,1,0,0,0,0,1,1,1,0,0,0],  # row 1
    [0,0,0,1,1,1,1,1,1,1,1,1,1,0,0,0],  # row 2:  connected top
    [0,0,0,1,1,1,1,1,1,1,1,1,1,0,0,0],  # row 3
    [0,0,1,1,1,1,1,1,1,1,1,1,1,1,0,0],  # row 4:  body wider
    [0,0,1,1,1,1,1,1,1,1,1,1,1,1,0,0],  # row 5
    [0,0,1,1,1,1,1,1,1,1,1,1,1,1,0,0],  # row 6
    [0,0,1,1,1,1,1,1,1,1,1,1,1,1,0,0],  # row 7
    [0,0,1,1,1,1,1,1,1,1,1,1,1,1,0,0],  # row 8
    [0,0,1,1,1,1,1,1,1,1,1,1,1,1,0,0],  # row 9
    [0,0,1,1,1,0,0,1,1,0,0,1,1,1,0,0],  # row 10: three legs
    [0,0,1,1,0,0,0,1,1,0,0,0,1,1,0,0],  # row 11
]

CORAL = (217, 119, 87, 255)   # #d97757
TRANSPARENT = (0, 0, 0, 0)


def create_logo(output_path: str = "claude_icon.png", size: int = 64):
    rows = len(LOGO_GRID)
    cols = len(LOGO_GRID[0])

    # Scale factor
    sx = size / cols
    sy = size / rows

    img = Image.new("RGBA", (size, size), TRANSPARENT)

    for r in range(rows):
        for c in range(cols):
            if LOGO_GRID[r][c] == 1:
                x0 = int(c * sx)
                y0 = int(r * sy)
                x1 = int((c + 1) * sx)
                y1 = int((r + 1) * sy)
                for x in range(x0, x1):
                    for y in range(y0, y1):
                        if x < size and y < size:
                            img.putpixel((x, y), CORAL)

    img.save(output_path)
    print(f"Logo saved to {output_path} ({size}x{size})")
    return img


if __name__ == "__main__":
    create_logo()
