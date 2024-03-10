def message_exists_in_post(post, message):
    if post['message'] == message:
        return True
    for reply in post.get('replies', []):
        if message_exists_in_post(reply, message):
            return True
    return False
