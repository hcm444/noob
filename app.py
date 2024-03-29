import base64
from datetime import datetime, timedelta
import re
import lorem
import random

from flask_bcrypt import generate_password_hash, check_password_hash
from flask_caching import Cache
from PIL import Image, ImageDraw, ImageFont
import threading
import time
from flask import jsonify, session, flash
from flask_login import LoginManager, login_user, logout_user

from io import BytesIO
import json
from captcha import generate_captcha_image

from flask_wtf.csrf import CSRFProtect, CSRFError

import secrets
from flask_login import login_required
from distinct_colors import generate_distinct_colors
from find_by_number import find_post_by_number
from load_highest import load_highest_post_count
from message_exists import message_exists_in_post
from save_highest import save_highest_post_count
from tripcode import generate_tripcode
import logging
from flask_login import current_user

secret_key = secrets.token_hex(32)
post_counts_lock = threading.Lock()

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, Regexp, Email
from flask_wtf import FlaskForm

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'  # Update with your desired database URI
user_data_db = SQLAlchemy(app)

app.secret_key = secret_key

app.config['SESSION_COOKIE_SECURE'] = True

csrf = CSRFProtect(app)

cache = Cache(app, config={'CACHE_TYPE': 'simple'})

login_manager = LoginManager(app)
login_manager.login_view = 'login'

all_opensky_data = []
fetch_opensky_data_lock = threading.Lock()


@app.after_request
def add_header(response):
    response.cache_control.no_store = True
    return response


@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    form = MyLoginForm()

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Replace this with your actual authentication logic
        user = User.query.filter_by(username=username).first()

        # Check if the user is an admin
        if user and user.check_password(password) and user.username == 'admin':
            login_user(user)
            return redirect(url_for('admin_dashboard'))

        session['error_message'] = 'Invalid username or password'
        return redirect(url_for('admin_login'))

    return render_template('admin_login.html', form=form)


@app.route('/api2', methods=['POST'])
@csrf.exempt
# this is the only route that needs to be exempt
def receive_opensky_data():
    try:
        opensky_data = request.json
        with fetch_opensky_data_lock:
            all_opensky_data.clear()
            all_opensky_data.extend(opensky_data['states'])
        return jsonify({'message': 'Data received successfully'}), 200
    except:
        return jsonify({'message': 'Error receiving data'})


@app.route('/api2')
def api2_data():
    with fetch_opensky_data_lock:
        formatted_data = []
        for plane in all_opensky_data:
            formatted_data.append({
                'icao24': plane[0],
                'callsign': plane[1],
                'altitude': plane[7],
                'speed': plane[9],
                'latitude': plane[6],
                'longitude': plane[5],
                'heading': plane[10]
            })
        return jsonify(formatted_data)


@app.route('/map')
def map():
    return render_template('map.html')


class User(user_data_db.Model, UserMixin):
    __tablename__ = 'user'
    id = user_data_db.Column(user_data_db.Integer, primary_key=True)
    username = user_data_db.Column(user_data_db.String(20), unique=True, nullable=False)
    hashed_password = user_data_db.Column(user_data_db.String(128), nullable=False)
    email = user_data_db.Column(user_data_db.String(128), nullable=False)
    banned = user_data_db.Column(user_data_db.Boolean, default=False)  # New field for banning status

    def set_password(self, password):
        self.hashed_password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.hashed_password, password)


@app.errorhandler(CSRFError)
@login_required
def handle_csrf_error(e):
    return jsonify({'error': 'CSRF token is missing or invalid'}), 401


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def verify_password(username, password):
    user = User.query.filter_by(username=username).first()
    if user:
        return user.check_password(password)
    return False


class MyLoginForm(FlaskForm):
    username = StringField('Username')
    password = PasswordField('Password')
    submit = SubmitField('Login')


POPULATE_RANGE = 400
POP_MIN = 0
POP_MAX = 100
POPULATE = 1  # Set to 1 to enable automatic population, 0 to disable

OPENSKY_PING = 120
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


post_counter = load_highest_post_count()


def has_too_many_repeating_characters(message):
    repeating_pattern = re.compile(r'(.)\1{%d,}' % (MAX_REPEATING_CHARACTERS - 1))
    return bool(repeating_pattern.search(message))


@app.before_request
def check_banned():
    if current_user.is_authenticated and current_user.banned:
        logout_user()
        # Optionally, you can redirect the user to a page indicating that they have been logged out due to being banned
        return render_template('banned.html')


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


class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(message='Username is required.'),
        Length(min=8, message='Username must be at least 8 characters long.')
    ])
    password = PasswordField('Password', validators=[
        DataRequired(message='Password is required.'),
        Length(min=8, message='Password must be at least 8 characters long.'),
        Regexp('^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]',
               message='Password must include uppercase, lowercase, digit, and special character.')
    ])
    email = StringField('Email', validators=[
        DataRequired(message='Email is required.'),
        Email(message='Invalid email address.')
    ])
    submit = SubmitField('Register')


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


# Update user registration route
@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()

    if form.validate_on_submit():  # Ensure validate_on_submit() is called
        username = form.username.data
        password = form.password.data
        email = form.email.data
        # Hash the password before storing it
        hashed_password = generate_password_hash(password)
        hashed_email = generate_password_hash(email)

        # Save the user to the database using SQLAlchemy
        user = User(username=username, hashed_password=hashed_password, email=hashed_email)
        user_data_db.session.add(user)
        user_data_db.session.commit()

        session['error_message'] = 'Registration successful. Please log in.'
        return redirect(url_for('login'))

    # If not submitted or validation failed, errors will be displayed in the template
    return render_template('register.html', form=form)


# Update login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = MyLoginForm()

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Replace this with your actual authentication logic
        user = User.query.filter_by(username=username).first()
        if user:
            if user.check_password(password):
                if user.banned:
                    session['error_message'] = 'Your account has been banned. You are not allowed to login.'
                    return redirect(url_for('login'))
                else:
                    login_user(user)
                    return redirect(url_for('home'))
            else:
                session['error_message'] = 'Invalid username or password'
                return redirect(url_for('login'))
        else:
            session['error_message'] = 'Invalid username or password'
            return redirect(url_for('login'))

    return render_template('login.html', form=form)


# Admin dashboard route

@app.route('/admin_dashboard', methods=['GET', 'POST'])
@login_required
def admin_dashboard():
    if current_user.username != 'admin':
        flash('You are not authorized to access this page.', 'error')
        return redirect(url_for('admin_login'))

    form = MyLoginForm()

    if request.method == 'POST':
        user_id = request.form.get('user_id')
        action = request.form.get('action')

        if action == 'ban':
            user = User.query.get(user_id)
            if user:
                user.banned = True
                user_data_db.session.commit()
                flash(f'User {user.username} has been banned.', 'success')
            else:
                flash('User not found.', 'error')

        elif action == 'unban':
            user = User.query.get(user_id)
            if user:
                user.banned = False
                user_data_db.session.commit()
                flash(f'User {user.username} has been unbanned.', 'success')
            else:
                flash('User not found.', 'error')

        else:
            flash('Invalid action.', 'error')

        return redirect(url_for('admin_dashboard'))

    # Fetch users for display
    users = User.query.all()
    return render_template('admin_dashboard.html', username=current_user.username, form=form, users=users,
                           message_board=message_board)


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


@app.route('/ban_user', methods=['POST'])
@login_required
def ban_user():
    if current_user.username != 'admin':
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        username = request.form.get('username')

        # Query the database to find the user with the provided username
        user_to_ban = User.query.filter_by(username=username).first()

        if user_to_ban:
            # Set the 'banned' attribute of the user to True
            user_to_ban.banned = True
            user_data_db.session.commit()

            flash(f'User {username} has been banned.', 'success')
        else:
            flash('User not found.', 'error')

        return redirect(url_for('admin_dashboard'))


@app.route('/unban_user', methods=['POST'])
@login_required
def unban_user():
    if current_user.username != 'admin':
        return redirect(url_for('admin_login'))
    if request.method == 'POST':
        username = request.form.get('username2')

        # Query the database to find the user with the provided username
        user_to_unban = User.query.filter_by(username=username).first()

        if user_to_unban:
            # Set the 'banned' attribute of the user to True
            user_to_unban.banned = False
            user_data_db.session.commit()

            flash(f'User {username} has been un-banned.', 'success')
        else:
            flash('User not found.', 'error')

        return redirect(url_for('admin_dashboard'))


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
@login_required
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
@login_required
def thread(post_number):
    # In the 'thread' route function
    post = next((p for p in message_board if p['post_number'] == post_number), None)
    if post:
        return render_template('thread.html', post=post)
    else:
        return render_template('404.html', error='404 - Thread not found')


@app.errorhandler(404)
@login_required
def page_not_found(e):
    return render_template('404.html', error='404 - Page not found'), 404


@app.route('/')
def login_page():
    form = MyLoginForm()  # Instantiate the login form
    return render_template('login.html', form=form)


@app.route('/snake')
@login_required
def snake():
    return render_template('snake.html')


# In the home route
@app.route('/forum')
@login_required
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
        'forum.html',
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


@app.route('/post', methods=['POST'])
@login_required
def post():
    csrf.protect()
    global post_counts, post_counter, ip_post_counts
    message = request.form.get('message')
    ip_address = request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or request.remote_addr
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
                'tripcode': current_user.username,
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
            'tripcode': current_user.username,  # Include the tripcode in the post information
        }
        post_counter += 1
        message_board.append(post)
        if len(message_board) > MAX_PARENT_POSTS:
            delete_oldest_parent_post()

    session['error_message'] = 'Post successfully created.'

    save_highest_post_count(post_counter)
    return redirect(url_for('home'))


@app.route('/about')
@login_required
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


color_palette = generate_distinct_colors(UNIQUE_COLORS)


def assign_color(activity_level):
    max_activity = len(color_palette) - 1
    normalized_activity = min(activity_level / MAX_REPLIES, 1.0)
    index = int(normalized_activity * max_activity)
    return color_palette[index]


terminate_thread = False


def generate_message_board_image():
    global terminate_thread

    while not terminate_thread:
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
    with app.app_context():
        user_data_db.create_all()
    app.run(debug=True)
