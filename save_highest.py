import sqlite3


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
