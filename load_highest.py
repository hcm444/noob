import sqlite3


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
