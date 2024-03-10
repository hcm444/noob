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
