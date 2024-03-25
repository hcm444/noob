import requests
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import time

Base = declarative_base()

class Post(Base):
    __tablename__ = 'posts'
    id = Column(Integer, primary_key=True)
    post_number = Column(Integer, unique=True)
    parent_post_number = Column(Integer, ForeignKey('posts.post_number'), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    message = Column(String)
    tripcode = Column(String)
    replies = relationship("Post")

def fetch_new_data():
    try:
        response = requests.get('https://stingray-app-85uqm.ondigitalocean.app/api')
        if response.status_code == 200:
            data = response.json()
            # Convert timestamp strings to datetime objects
            for post in data:
                post['timestamp'] = datetime.strptime(post['timestamp'], '%Y-%m-%d %H:%M:%S')
            return data
        else:
            print(f"Failed to fetch data. Status code: {response.status_code}")
            return None
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return None

def save_post(session, post_data, parent=None):
    try:
        post = Post(
            post_number=post_data['post_number'],
            timestamp=post_data['timestamp'],
            message=post_data['message'],
            tripcode=post_data['tripcode']
        )
        if parent:
            parent.replies.append(post)
        session.add(post)
        session.commit()
        print(f"Inserted post {post_data['post_number']} into the database.")
    except Exception as e:
        session.rollback()
        print(f"Error occurred while inserting post {post_data['post_number']}: {str(e)}")

def save_to_database(session, data, Post):
    for post_data in data:
        save_post(session, post_data, parent=None)
        if 'replies' in post_data:
            for reply_data in post_data['replies']:
                save_to_database(session, [reply_data], Post)

def main():
    engine = create_engine('sqlite:///forum_data.db')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    while True:
        new_data = fetch_new_data()
        if new_data:
            print("Data fetched successfully.")
            with Session() as session:
                save_to_database(session, new_data, Post)
        else:
            print("Failed to fetch new data.")
        # Sleep for some time before fetching new data again
        time.sleep(60)  # Adjust the sleep duration as needed

if __name__ == "__main__":
    main()
