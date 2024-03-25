import requests
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()

class Post(Base):
    __tablename__ = 'posts'
    id = Column(Integer, primary_key=True)
    post_number = Column(Integer)
    parent_post_number = Column(Integer, ForeignKey('posts.post_number'), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    message = Column(String)
    tripcode = Column(String)

def fetch_all_data():
    try:
        response = requests.get('https://stingray-app-85uqm.ondigitalocean.app/api')
        if response.status_code == 200:
            data = response.json()
            return data
        else:
            print(f"Failed to fetch data. Status code: {response.status_code}")
            return None
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return None

def save_post_to_database(session, post_data, parent_post_number=None):
    post = Post(post_number=post_data['post_number'], message=post_data['message'], tripcode=post_data['tripcode'], parent_post_number=parent_post_number)
    session.add(post)
    session.flush()
    if 'replies' in post_data:
        for reply_data in post_data['replies']:
            save_post_to_database(session, reply_data, parent_post_number=post.post_number)  # Use post.post_number here instead of post['post_number']

def save_to_database(data):
    engine = create_engine('sqlite:///forum_data.db')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    for post_data in data:
        save_post_to_database(session, post_data)

    session.commit()
    session.close()

def main():
    all_data = fetch_all_data()
    if all_data:
        print("Data fetched successfully.")
        save_to_database(all_data)
        print("Data saved to database.")
    else:
        print("Failed to fetch data.")

if __name__ == "__main__":
    main()
