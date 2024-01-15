import base64
from datetime import datetime, timedelta
import re
from io import BytesIO

from flask_caching import Cache
from PIL import Image, ImageDraw, ImageFont
import threading
import colorsys
import time
import csv
import logging
from flask import Flask, render_template, request, jsonify, session, send_file
import random
import string
from difflib import SequenceMatcher

post_counts_lock = threading.Lock()
app = Flask(__name__, static_url_path='/static')
app.secret_key = 'your_secret_key'  # Replace with a secure secret key

cache = Cache(app, config={'CACHE_TYPE': 'simple'})

ENLARGE_FACTOR = 40
MAX_CHAR = 500
IMAGE_GEN_TIME = 60
POSTS_PER_PAGE = 20  # 20
MAX_PARENT_POSTS = 400
POST_LIMIT_DURATION = timedelta(minutes=1)
USER_POSTS_PER_MIN = 1  # 2 or 3
MAX_REPLIES = 100
YOUR_THRESHOLD = 0.5
post_counter = 1
MAX_REPEATING_CHARACTERS = 20
MAX_POSTS_PER_FINGERPRINT = 5
message_board = []
post_counts = {}
fingerprint_post_counts = {}

logging.basicConfig(level=logging.DEBUG)


def generate_captcha_image():
    captcha_length = 6
    captcha_chars = string.ascii_uppercase + string.digits
    captcha_code = ''.join(random.choice(captcha_chars) for _ in range(captcha_length))

    # Create a larger image with the captcha code
    original_width, original_height = 150, 100
    zoom_factor = 0.3  # Increase this value to zoom in further
    zoomed_width, zoomed_height = int(original_width * zoom_factor), int(original_height * zoom_factor)

    image = Image.new('RGB', (zoomed_width, zoomed_height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)

    # Use the default font
    font = ImageFont.load_default()

    # Get the size of the text to be drawn
    text_width, text_height = draw.textsize(captcha_code, font=font)

    # Center the text in the larger image
    text_position = ((zoomed_width - text_width) // 2, (zoomed_height - text_height) // 2)

    draw.text(text_position, captcha_code, font=font, fill=(0, 0, 0))

    # Resize the image to the original dimensions
    image = image.resize((original_width, original_height), Image.ANTIALIAS)

    # Save the image to a BytesIO object
    image_io = BytesIO()
    image.save(image_io, 'PNG')
    image_io.seek(0)

    # Convert the image data to base64 encoding
    base64_image = base64.b64encode(image_io.getvalue()).decode('utf-8')

    return captcha_code, base64_image


def generate_device_fingerprint():
    user_agent = request.headers.get('User-Agent', '')
    full_ip_address = request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or request.remote_addr

    # Extract the relevant part of the IP address (e.g., first three octets)
    ip_prefix = '.'.join(full_ip_address.split('.')[:3])

    # Combine relevant information to create a fingerprint
    fingerprint = f"{user_agent}_{ip_prefix}"

    return fingerprint


def check_fingerprint_rate_limit(fingerprint):
    if fingerprint in fingerprint_post_counts:
        count, timestamp = fingerprint_post_counts[fingerprint]
        time_diff = datetime.now() - timestamp

        # Calculate the cooldown period based on the user's posting frequency
        cooldown_factor = min(count, MAX_POSTS_PER_FINGERPRINT) / MAX_POSTS_PER_FINGERPRINT
        cooldown_duration = POST_LIMIT_DURATION * cooldown_factor

        if time_diff > cooldown_duration:
            fingerprint_post_counts[fingerprint] = (1, datetime.now())
        else:
            return False  # Rate limit exceeded

    else:
        fingerprint_post_counts[fingerprint] = (1, datetime.now())

    return True  # Within rate limit



def has_too_many_repeating_characters(message):
    repeating_pattern = re.compile(r'(.)\1{%d,}' % (MAX_REPEATING_CHARACTERS - 1))
    return bool(repeating_pattern.search(message))


def calculate_similarity_ratio(post1, post2):
    return SequenceMatcher(None, post1, post2).ratio()


def delete_oldest_parent_post():
    while len(message_board) > MAX_PARENT_POSTS:
        del message_board[0]


def delete_post_and_replies(post):
    if post:
        for reply in post.get('replies', []):
            delete_post_and_replies(reply)


def parse_references(message):
    references = []
    for match in re.finditer(r'>>(\d+)', message):
        referenced_post_number = int(match.group(1))
        references.append(referenced_post_number)
    return references


@app.route('/catalog')
def catalog():
    catalog_data = []
    for post in message_board:
        post_data = {
            'post_number': post['post_number'],
            'parent_post_number': post.get('parent_post_number', None),
            'message': post['message'],
            'timestamp': post['timestamp'],
            'total_replies': len(post.get('replies', []))
        }
        catalog_data.append(post_data)

    return render_template('catalog.html', catalog_data=catalog_data)


@app.route('/thread/<int:post_number>')
def thread(post_number):
    # In the 'thread' route function
    post = next((p for p in message_board if p['post_number'] == post_number), None)
    if post:
        return render_template('thread.html', post=post)
    else:
        return render_template('404.html', error='404 - Thread not found')


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html', error='404 - Page not found'), 404


@app.route('/snake')
def snake():
    return render_template('snake.html')


# In the home route
@app.route('/')
def home():
    captcha_code, captcha_image = generate_captcha_image()
    session['captcha'] = captcha_code
    page = int(request.args.get('page', 1))
    messages_per_page = POSTS_PER_PAGE
    total_pages = (len(message_board) + messages_per_page - 1) // messages_per_page
    start_index = (page - 1) * messages_per_page
    end_index = start_index + messages_per_page

    reversed_message_board = list(reversed(message_board))

    messages_to_display = reversed_message_board[start_index:end_index]

    # Pass both messages and captcha information to the template
    return render_template('index.html', messages=messages_to_display, total_pages=total_pages, current_page=page, captcha_image=captcha_image)


ip_post_counts = {}

@app.route('/post', methods=['POST'])
def post():
    global post_counts, post_counter, ip_post_counts
    message = request.form.get('message')
    ip_address = request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or request.remote_addr
    

    # Check for similarity with all existing posts
    user_captcha = request.form.get('captcha', '')
    stored_captcha = session.get('captcha', '')

    if user_captcha.upper() != stored_captcha:
        return jsonify({'error': 'Error: CAPTCHA verification failed.'})

    device_fingerprint = generate_device_fingerprint()

    # Check if the fingerprint has exceeded the rate limit
    if not check_fingerprint_rate_limit(device_fingerprint):
        return jsonify({'error': 'Error: Exceeded the maximum number of posts per minute for this device.'})

    # Increment the post count for the current IP address
    ip_post_counts[ip_address] = ip_post_counts.get(ip_address, 0) + 1

    # Print the IP address along with the post count

    for existing_post in message_board:
        similarity = calculate_similarity_ratio(existing_post['message'], message)

        if similarity > YOUR_THRESHOLD:
            return jsonify({'error': f'Error: This message is {100 * similarity}% similar to an existing post.'})

    # Check for too many repeating characters
    if has_too_many_repeating_characters(message):
        return jsonify({
                           'error': f'Error: Message contains too many repeating characters (more than {MAX_REPEATING_CHARACTERS} consecutive).'})

    if not message or message.isspace():
        return jsonify({'error': 'Error: Message should not be empty or contain only whitespace.'})

    if len(message) > MAX_CHAR:
        return jsonify({'error': f'Error: Message should not exceed {MAX_CHAR} characters.'})

    if message.strip() == '>>':
        return jsonify({'error': 'Error: Posting ">>" by itself is not allowed.'})
    with post_counts_lock:
        ip_post_counts[ip_address] = ip_post_counts.get(ip_address, 0) + 1
    if ip_address in post_counts:
        count, timestamp = post_counts[ip_address]
        time_diff = datetime.now() - timestamp

        if time_diff > POST_LIMIT_DURATION:
            post_counts[ip_address] = (1, datetime.now())
        elif count >= USER_POSTS_PER_MIN:
            remaining_time = int((POST_LIMIT_DURATION - time_diff).total_seconds())
            return jsonify({
                'error': f'Error: You can only post {USER_POSTS_PER_MIN} times per minute. Please wait {remaining_time} seconds before posting again.'})
        else:
            post_counts[ip_address] = (count + 1, datetime.now())
    else:
        post_counts[ip_address] = (1, datetime.now())

    timestamp = datetime.now()
    references = parse_references(message)

    def find_parent_post(referenced_post_number):
        for post in message_board:
            if post['post_number'] == referenced_post_number:
                return post
            for reply in post.get('replies', []):
                if reply['post_number'] == referenced_post_number:
                    return post
        return None

    def message_exists_in_post(post, message):
        if post['message'] == message:
            return True
        for reply in post.get('replies', []):
            if message_exists_in_post(reply, message):
                return True
        return False

    if references:
        parent_post_number = references[0]
        parent_post = find_parent_post(parent_post_number)

        if parent_post:

            if message_exists_in_post(parent_post, message):
                return jsonify({'error': 'Error: This message already exists as a reply to the referenced post.'})

            if 'replies' in parent_post and len(parent_post['replies']) >= MAX_REPLIES:
                return jsonify({'error': f'Error: Maximum of {MAX_REPLIES} replies per parent post exceeded.'})

            reply = {
                'post_number': post_counter,
                'timestamp': timestamp,
                'message': message,
            }
            post_counter += 1
            parent_post.setdefault('replies', []).append(reply)
            message_board.remove(parent_post)
            message_board.append(parent_post)
        else:
            return jsonify({'error': 'Error: Referenced post not found.'})
    else:
        if any(message_exists_in_post(post, message) for post in message_board):
            return jsonify({'error': 'Error: This message already exists as a parent post or a reply.'})

        post = {
            'post_number': post_counter,
            'timestamp': timestamp,
            'message': message,
            'replies': [],
        }
        post_counter += 1
        message_board.append(post)
        if len(message_board) > MAX_PARENT_POSTS:
            delete_oldest_parent_post()

    print(f"Post successful - IP: {ip_address}, Counter: {ip_post_counts[ip_address]}")

    return 'Post successfully created'


@app.route('/statistics')
def statistics():
    total_posts = len(message_board)
    total_replies = sum(len(post.get('replies', [])) for post in message_board)

    average_replies_per_post = total_replies / total_posts if total_posts > 0 else 0

    if total_posts > 0:
        total_age = sum((datetime.now() - post['timestamp']).total_seconds() for post in message_board)
        average_post_age = total_age / total_posts
    else:
        average_post_age = 0

    enlarged_image_path = 'static/enlarged_message_board_image.png'

    return render_template('statistics.html',
                           total_posts=total_posts,
                           total_replies=total_replies,
                           average_replies_per_post=average_replies_per_post,
                           average_post_age=average_post_age,
                           enlarged_image_path=enlarged_image_path)


@app.route('/api', methods=['GET'])
def api():
    posts_json = []

    for post in message_board:
        post_info = {
            'post_number': post['post_number'],
            'timestamp': post['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
            'message': post['message'],
        }

        if 'replies' in post:
            post_info['replies'] = []
            for reply in post['replies']:
                reply_info = {
                    'post_number': reply['post_number'],
                    'timestamp': reply['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                    'message': reply['message'],
                }
                post_info['replies'].append(reply_info)

        posts_json.append(post_info)

    return jsonify(posts_json)


def generate_distinct_colors(num_colors):
    colors = []
    for i in range(num_colors):
        # Calculate hue to evenly distribute colors in the HSL color space
        hue = (i / num_colors)  # Vary the hue from 0 to 1
        rgb = colorsys.hsv_to_rgb(hue, 1, 1)
        colors.append(tuple(int(c * 255) for c in rgb))
    return colors


color_palette = generate_distinct_colors(100)


def assign_color(activity_level):
    index = min(activity_level, len(color_palette) - 1)
    return color_palette[index]


def generate_message_board_image():
    while True:
        image_width = POSTS_PER_PAGE
        image_height = MAX_PARENT_POSTS // POSTS_PER_PAGE

        enlarged_width = image_width * ENLARGE_FACTOR
        enlarged_height = image_height * ENLARGE_FACTOR

        initial_image = Image.new('RGB', (image_width, image_height))
        initial_draw = ImageDraw.Draw(initial_image)

        enlarged_image = Image.new('RGB', (enlarged_width, enlarged_height))
        draw = ImageDraw.Draw(enlarged_image)

        csv_data = []

        for i in range(len(message_board)):
            post = message_board[i]
            num_replies = len(post.get('replies', []))

            activity_level = min(num_replies, len(color_palette) - 1)
            color = assign_color(activity_level)

            x_initial = i % POSTS_PER_PAGE
            y_initial = i // POSTS_PER_PAGE

            initial_image.putpixel((x_initial, y_initial), color)

            x_enlarged = (i % POSTS_PER_PAGE) * ENLARGE_FACTOR
            y_enlarged = (i // POSTS_PER_PAGE) * ENLARGE_FACTOR

            for y_offset in range(ENLARGE_FACTOR):
                for x_offset in range(ENLARGE_FACTOR):
                    enlarged_image.putpixel((x_enlarged + x_offset, y_enlarged + y_offset), color)

            text = f"{post['post_number']}|{num_replies}"
            text_position = (x_enlarged + ENLARGE_FACTOR // 2, y_enlarged + ENLARGE_FACTOR // 2)
            text_color = (0, 0, 0)
            font = ImageFont.load_default()
            draw.text(text_position, text, text_color, font=font, anchor="mm")

            csv_data.append([post['post_number'], num_replies])

        initial_image.save('static/message_board_image.png')

        enlarged_image.save('static/enlarged_message_board_image.png')

        with open('static/message_board_data.csv', 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            for i in range(0, len(csv_data), 10):
                row_data = csv_data[i:i + 10]
                csv_writer.writerow(row_data)

        time.sleep(IMAGE_GEN_TIME)


image_generation_thread = threading.Thread(target=generate_message_board_image)
image_generation_thread.start()

if __name__ == '__main__':
    app.run(debug=True)
