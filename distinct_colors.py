import colorsys


def generate_distinct_colors(num_colors):
    colors = []
    for i in range(num_colors):
        # Calculate hue to traverse through red, orange, yellow, green, and blue
        hue = (i / num_colors) * 0.6  # Vary the hue from 0 to 0.6 for a portion of the spectrum
        rgb = colorsys.hsv_to_rgb(hue, 1, 1)
        colors.append(tuple(int(c * 255) for c in rgb))
    return colors
