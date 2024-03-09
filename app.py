import base64
from datetime import datetime, timedelta
import re
import lorem
import random
from flask_caching import Cache
from PIL import Image, ImageDraw, ImageFont
import threading
import colorsys
from flask_cors import CORS
import requests
import time
from flask import jsonify, session, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from wtforms.fields.simple import PasswordField
from io import BytesIO
import json
from captcha import generate_captcha_image
from flask import Flask, render_template, request
from flask_wtf.csrf import CSRFProtect
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
import secrets
import sqlite3
from flask_apscheduler import APScheduler  # Add this import
from tripcode import generate_tripcode
import logging
secret_key = secrets.token_hex(32)
post_counts_lock = threading.Lock()
app = Flask(__name__, static_url_path='/static')

all_opensky_data = []
fetch_interval_seconds = 60  # Adjust the interval as needed
fetch_opensky_data_lock = threading.Lock()

app.secret_key = secret_key


app.config['SESSION_COOKIE_SECURE'] = True
csrf = CSRFProtect(app)
cache = Cache(app, config={'CACHE_TYPE': 'simple'})

login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin):
    pass


@login_manager.user_loader
def load_user(user_id):
    user = User()
    user.id = user_id
    return user


class MyLoginForm(FlaskForm):
    username = StringField('Username')
    password = PasswordField('Password')
    submit = SubmitField('Login')



with open('config.json') as f:
    config = json.load(f)
POPULATE_RANGE = 400
POP_MIN = 0
POP_MAX = 100
POPULATE = 1  # Set to 1 to enable automatic population, 0 to disable
USERNAME = config.get('username')
PASSWORD = config.get('password')
ENLARGE_FACTOR = 40
MAX_CHAR = 500
IMAGE_GEN_TIME = 60
POSTS_PER_PAGE = 20  # 20
MAX_PARENT_POSTS = 400
POST_LIMIT_DURATION = timedelta(minutes=1)
USER_POSTS_PER_MIN = 3  # 2 or 3
MAX_REPLIES = 100
YOUR_THRESHOLD = 0.5
UNIQUE_COLORS = 400
MAX_REPEATING_CHARACTERS = 9
message_board = []
post_counts = {}

logging.basicConfig(level=logging.DEBUG)

def get_all_opensky_data(username, password):
    url = "https://opensky-network.org/api/states/all"
    auth = (username, password)

    try:
        response = requests.get(url, auth=auth)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as e:
        print(f"Error occurred while fetching OpenSky data: {e}")
        return None

def store_opensky_data(data):
    with fetch_opensky_data_lock:
        if data is not None:
            all_opensky_data.clear()
            all_opensky_data.extend(data['states'])

def fetch_opensky_data_thread():
    while True:
        username = "washoe.heli"
        password = "B0r3alB0r3al"
        opensky_data = get_all_opensky_data(username, password)
        store_opensky_data(opensky_data)
        time.sleep(fetch_interval_seconds)

@app.route('/get_latest_data', methods=['GET'])
def get_latest_data():
    opensky_data = all_opensky_data
    if opensky_data:
        return jsonify({'states': opensky_data})
    else:
        return jsonify({})

@app.route('/map')
def map():
    opensky_data = all_opensky_data
    return render_template('map.html', opensky_data=opensky_data)

def populate_board():
    global message_board, post_counter

    # Your logic to generate random posts and replies goes here
    # Example: Generating 10 random parent posts
    for _ in range(POPULATE_RANGE):
        post = {
            'post_number': post_counter,
            'timestamp': datetime.now(),
            'message': lorem.sentence(),
            'replies': [],
            'ip_address': '127.0.0.1',  # Set a dummy IP address for automated posts
            'tripcode': 'auto_generated',
        }
        post_counter += 1

        message_board.append(post)

        # Generate random replies for each parent post
        num_replies = random.randint(POP_MIN, POP_MAX)
        for _ in range(num_replies):
            reply = {
                'post_number': post_counter,
                'timestamp': datetime.now(),
                'message': lorem.sentence(),
                'ip_address': '127.0.0.1',  # Set a dummy IP address for automated posts
                'tripcode': 'auto_generated',
            }
            post_counter += 1
            post['replies'].append(reply)


def generate_black_image(message_board):
    black_image = Image.new('RGB', (400, 100), color=(0, 0, 0))
    black_draw = ImageDraw.Draw(black_image)
    slice_width = 20  # Width of each slice

    slices = []

    for i, post in enumerate(message_board):
        num_replies = len(post.get('replies', []))
        x_position = i
        y_position = 100 - min(num_replies, 100)

        # Use the assigned thread color for each parent post
        thread_color = assign_color(num_replies)

        for y in range(y_position, 100):
            black_draw.point((x_position, y), fill=thread_color)

    # Create 20 slices
    for i in range(20):
        left = i * slice_width
        right = (i + 1) * slice_width
        slice_image = black_image.crop((left, 0, right, 100))
        slices.append(slice_image)

    return black_image, slices


def load_highest_post_count():
    try:
        connection = sqlite3.connect('post_count.db')  # Change the database name as needed
        cursor = connection.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS post_count (count INTEGER)')
        cursor.execute('SELECT * FROM post_count')
        result = cursor.fetchone()
        return result[0] if result else 1  # Default value if no record is found
    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
        return 1  # Default value if an error occurs
    finally:
        connection.close()


post_counter = load_highest_post_count()


def save_highest_post_count(post_count):
    try:
        connection = sqlite3.connect('post_count.db')
        cursor = connection.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS post_count (count INTEGER)')

        # Check if a record exists
        cursor.execute('SELECT * FROM post_count')
        result = cursor.fetchone()

        if result:
            # Update the existing record
            cursor.execute('UPDATE post_count SET count = ?', (post_count,))
        else:
            # Insert a new record
            cursor.execute('INSERT INTO post_count (count) VALUES (?)', (post_count,))

        connection.commit()
    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
    finally:
        connection.close()


def has_too_many_repeating_characters(message):
    repeating_pattern = re.compile(r'(.)\1{%d,}' % (MAX_REPEATING_CHARACTERS - 1))
    return bool(repeating_pattern.search(message))


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


@app.route('/replace_characters', methods=['POST'])
@login_required
def replace_characters():
    post_number = request.form.get('post_number')

    try:
        post_number = int(post_number)
    except ValueError:
        return "Invalid post number. Please enter a valid post number."

    # Find the post with the specified post number, including replies
    post_to_replace = find_post_by_number(message_board, post_number)

    if post_to_replace:
        # Replace all characters in the message with "#"
        post_to_replace['message'] = '########## POST DELETED ##########'

        # Optionally, you may want to update the timestamp or perform other actions

        return "Characters replaced successfully."
    else:
        return "Post not found. Please enter a valid post number."


def find_post_by_number(posts, post_number):
    for post in posts:
        if post['post_number'] == post_number:
            return post
        elif 'replies' in post:
            # Search for the post in replies recursively
            nested_post = find_post_by_number(post['replies'], post_number)
            if nested_post:
                return nested_post
    return None


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = MyLoginForm()  # Create an instance of the login form

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Replace this with your actual authentication logic
        if username == USERNAME and password == PASSWORD:
            user = User()
            user.id = username
            login_user(user)
            return redirect(url_for('admin_dashboard'))

        session['error_message'] = 'Invalid username or password'
        return redirect(url_for('login'))

    return render_template('login.html', form=form)  # Pass the form to the template


# Admin dashboard route

@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    form = MyLoginForm()  # Instantiate the form
    return render_template('admin_dashboard.html', username=current_user.id, form=form, message_board=message_board)


# Logout route
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))


restricted_ips = set()


def get_restricted_ips():
    return list(restricted_ips)


@app.route('/ip_restrictions')
@login_required
def ip_restrictions():
    # Call the function to get the restricted IPs
    restricted_ips_list = get_restricted_ips()
    return render_template('ip_restrictions.html', ip_restrictions=restricted_ips_list)


@app.route('/add_ip_restriction', methods=['POST'])
@login_required
def add_ip_restriction():
    ip_to_restrict = request.form.get('ip_to_restrict')
    restricted_ips.add(ip_to_restrict)
    # Optionally, save the updated IP restrictions to a persistent storage
    return redirect(url_for('ip_restrictions'))


@app.route('/remove_ip_restriction', methods=['POST'])
@login_required
def remove_ip_restriction():
    ip_to_remove = request.form.get('ip_to_remove')
    restricted_ips.discard(ip_to_remove)
    # Optionally, save the updated IP restrictions to a persistent storage
    return redirect(url_for('ip_restrictions'))


@app.route('/catalog')
def catalog():
    catalog_data = []
    for post in message_board:
        post_data = {
            'post_number': post['post_number'],
            'parent_post_number': post.get('parent_post_number', None),
            'message': post['message'],
            'timestamp': post['timestamp'],
            'total_replies': len(post.get('replies', [])),
            'parent_post_color': assign_color(len(post.get('replies', []))),
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
    # Generate black image and slices
    black_image, slices = generate_black_image(reversed_message_board)

    # Extract color information for each parent post
    parent_post_colors = [assign_color(len(post.get('replies', []))) for post in messages_to_display]
    # Convert each slice to base64 representation
    slice_base64_list = []
    for i, slice_img in enumerate(slices):
        slice_io = BytesIO()
        slice_img.save(slice_io, 'PNG')
        slice_io.seek(0)
        slice_base64 = base64.b64encode(slice_io.getvalue()).decode('utf-8')
        slice_base64_list.append(slice_base64)

    # Convert the black image to base64 representation
    image_io = BytesIO()
    black_image.save(image_io, 'PNG')
    image_io.seek(0)
    base64_image = base64.b64encode(image_io.getvalue()).decode('utf-8')

    # Pass both messages, color information, and captcha to the template
    return render_template(
        'index.html',
        messages=messages_to_display,
        total_pages=total_pages,
        current_page=page,
        captcha_image=captcha_image,
        form=MyLoginForm(),
        thread_image=base64_image,
        thread_slices=slice_base64_list,  # Pass the slice base64 representations
        error_message=session.pop('error_message', None),
        parent_post_colors=parent_post_colors
    )


ip_post_counts = {}


def message_exists_in_post(post, message):
    if post['message'] == message:
        return True
    for reply in post.get('replies', []):
        if message_exists_in_post(reply, message):
            return True
    return False


@app.route('/post', methods=['POST'])
def post():
    csrf.protect()
    global post_counts, post_counter, ip_post_counts
    message = request.form.get('message')
    ip_address = request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or request.remote_addr
    tripcode = generate_tripcode(ip_address)
    user_captcha = request.form.get('captcha', '')
    stored_captcha = session.get('captcha', '')

    # Check if the IP address is restricted
    if ip_address in restricted_ips:
        session['error_message'] = 'IP address is restricted from posting.'
        return redirect(url_for('home'))

    if user_captcha.upper() != stored_captcha:
        session['error_message'] = 'CAPTCHA verification failed.'
        return redirect(url_for('home'))

    if has_too_many_repeating_characters(message):
        session[
            'error_message'] = f'Message contains too many repeating characters (more than {MAX_REPEATING_CHARACTERS} consecutive).'
        return redirect(url_for('home'))

    if not message or message.isspace():
        session['error_message'] = 'Message should not be empty or contain only whitespace.'
        return redirect(url_for('home'))

    if len(message) > MAX_CHAR:
        session['error_message'] = f'Message should not exceed {MAX_CHAR} characters.'
        return redirect(url_for('home'))

    if message.strip() == '>>':
        session['error_message'] = 'Posting ">>" by itself is not allowed.'
        return redirect(url_for('home'))

    with post_counts_lock:
        ip_post_counts[ip_address] = ip_post_counts.get(ip_address, 0) + 1

    if ip_address in post_counts:
        count, timestamp = post_counts[ip_address]
        time_diff = datetime.now() - timestamp

        if time_diff > POST_LIMIT_DURATION:
            post_counts[ip_address] = (1, datetime.now())
        elif count >= USER_POSTS_PER_MIN:
            remaining_time = int((POST_LIMIT_DURATION - time_diff).total_seconds())
            session[
                'error_message'] = f'You can only post {USER_POSTS_PER_MIN} times per minute. Please wait {remaining_time} seconds before posting again.'
            return redirect(url_for('home'))
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

    if references:
        parent_post_number = references[0]
        parent_post = find_parent_post(parent_post_number)

        if parent_post:
            if message_exists_in_post(parent_post, message):
                session['error_message'] = 'This message already exists as a reply to the referenced post.'
                return redirect(url_for('home'))

            if 'replies' in parent_post and len(parent_post['replies']) >= MAX_REPLIES:
                session['error_message'] = f'Maximum of {MAX_REPLIES} replies per parent post exceeded.'
                return redirect(url_for('home'))

            reply = {
                'post_number': post_counter,
                'timestamp': timestamp,
                'message': message,
                'ip_address': ip_address,
                'tripcode': tripcode,
            }
            post_counter += 1
            parent_post.setdefault('replies', []).append(reply)
            message_board.remove(parent_post)
            message_board.append(parent_post)

        else:
            session['error_message'] = 'Referenced post not found.'
            return redirect(url_for('home'))
    else:
        if any(message_exists_in_post(post, message) for post in message_board):
            session['error_message'] = 'This message already exists as a parent post or a reply.'
            return redirect(url_for('home'))

        post = {
            'post_number': post_counter,
            'timestamp': timestamp,
            'message': message,
            'replies': [],
            'ip_address': ip_address,
            'tripcode': tripcode,  # Include the tripcode in the post information
        }
        post_counter += 1
        message_board.append(post)
        if len(message_board) > MAX_PARENT_POSTS:
            delete_oldest_parent_post()

    session['error_message'] = 'Post successfully created.'

    save_highest_post_count(post_counter)
    return redirect(url_for('home'))


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/api', methods=['GET'])
def api():
    posts_json = []

    for post in message_board:
        post_info = {
            'post_number': post['post_number'],
            'timestamp': post['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
            'message': post['message'],
            'tripcode': post['tripcode'],
        }

        if 'replies' in post:
            post_info['replies'] = []
            for reply in post['replies']:
                reply_info = {
                    'post_number': reply['post_number'],
                    'timestamp': reply['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                    'message': reply['message'],
                    'tripcode': reply['tripcode'],
                }
                post_info['replies'].append(reply_info)

        posts_json.append(post_info)

    return jsonify(posts_json)


def generate_distinct_colors(num_colors):
    colors = []
    for i in range(num_colors):
        # Calculate hue to traverse through red, orange, yellow, green, and blue
        hue = (i / num_colors) * 0.6  # Vary the hue from 0 to 0.6 for a portion of the spectrum
        rgb = colorsys.hsv_to_rgb(hue, 1, 1)
        colors.append(tuple(int(c * 255) for c in rgb))
    return colors


color_palette = generate_distinct_colors(UNIQUE_COLORS)


def assign_color(activity_level):
    max_activity = len(color_palette) - 1
    normalized_activity = min(activity_level / MAX_REPLIES, 1.0)
    index = int(normalized_activity * max_activity)
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

        time.sleep(IMAGE_GEN_TIME)


image_generation_thread = threading.Thread(target=generate_message_board_image)
image_generation_thread.start()


if POPULATE:
    populate_board()

if __name__ == '__main__':
    fetch_thread = threading.Thread(target=fetch_opensky_data_thread, daemon=True)
    fetch_thread.start()
    app.run(debug=False)
