"""
@author Nate Gentile <nate@nategentile.com>
"""
import os
import pickle
import numpy as np
from PIL import Image
from google.auth.transport.requests import Request
import googleapiclient.discovery
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import requests
import skimage
import logging
import config

owner_profile_picture = Image.open("storage/profile_pic.jpg")


def check_is_spam(comment):
    """
    :param comment: Dictionary from API doc - https://developers.google.com/youtube/v3/docs/comments#resource
    :return: bool - is the comment spam?
    """
    # Check if it's me
    comment = comment["snippet"]
    if comment['authorChannelUrl'] == config.MY_CHANNEL_URL:
        return False
    # Check banned words in comment
    for word in config.name_banned_words:
        if comment["authorDisplayName"].lower().find(word) != -1:
            return True

    for word in config.body_banned_words:
        if comment["textOriginal"].lower().find(word) != -1:
            return True

    # Check if profile image is the same as my image
    try:
        logging.debug("Downloading image for user profile: {}".format(comment["authorProfileImageUrl"]))
        data = requests.get(comment["authorProfileImageUrl"]).content
        with open('storage/impostor.jpg', 'wb') as handle:
            handle.write(data)

        impostor = Image.open('storage/impostor.jpg')
        nate_resized_image = owner_profile_picture.resize((impostor.size[0], impostor.size[1]))

        with open('storage/nate_resized.jpg', 'wb') as handle:
            nate_resized_image.save(handle)

        difference = skimage.metrics.structural_similarity(np.asfarray(impostor.convert('L')),
                                                           np.asfarray(nate_resized_image.convert('L')))

        logging.debug("Difference score from my profile pic is {}".format(difference))
        if difference > 0.8:
            with open('impostors/{}.jpg'.format(comment["authorChannelId"]["value"]), 'wb') as handle:
                impostor.save(handle)
            return True
        return False
    except Exception:  # Too broad, but I don't have time for this
        return False


def get_them_all(api_function, api_kwargs, key_path, value_path, prepopulated_list=[]):
    """
    Query the endpoint all the way through the pages (avoing google pagination) and returns a dictionary with all the
    responses in a dictionary with the key of your choice.

    :param api_function: googleapiclient API function to query, example: youtube.playlistItems
    :param api_kwargs: list of attributes to pass to the API endpoint in a dictionary - check API docs
    :param key_path: list of strings, containing the path to the item you want to use as key from the response
    :param value_path: list of strings, containing the path to the item you want to use as value from the response
    :param prepopulated_list: in case you want to update a previously existing list, and want the queries to stop when
                              the query is returning pre-existing values, provide the values you already have.
    :return: Dictionary
    """
    next_page_token = " "
    stuff = {}
    key_path_repeated = False

    while next_page_token and not key_path_repeated:
        api_kwargs["pageToken"] = next_page_token.strip()
        yt_request = api_function().list(**api_kwargs)

        yt_response = execute_youtube_query(yt_request)

        for item in yt_response["items"]:
            current_key = item
            for key in key_path:
                current_key = current_key[key]

            current_value = item
            for key in value_path:
                current_value = current_value[key]

            if current_key in prepopulated_list:
                key_path_repeated = True
                break

            stuff[current_key] = current_value

        next_page_token = yt_response.get("nextPageToken", None)
    return stuff


def get_credentials(role):
    """
    Do the auth process on the google API
    :return: credentials object from google API
    """
    creds = None
    if os.path.exists('storage/token.json'):
        creds = Credentials.from_authorized_user_file('storage/token.json', config.SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(f"storage/{role}-credentials.json", config.SCOPES)
            creds = flow.run_local_server(port=2725)
        # Save the credentials for the next time
        with open('storage/token.json', 'w') as token:
            token.write(creds.to_json())
    logging.info("Authorized into Youtube")
    return creds


def load_from_storage(file_name, default_value):
    """
    Load any variable from stored pickles
    :param file_name: name of the file where the data is stored
    :param default_value: if the file doesn't exist, get a default value instead
    :return: the variable stored in the pickle
    """
    if os.path.exists(file_name):
        with open(file_name, 'rb') as handle:
            return pickle.load(handle)
    else:
        return default_value


def save_into_storage(file_name, data):
    """
    Save any variable into a pickle file, to store data between executions
    :param file_name: name of the file where the data will be stored
    :param data: data to store
    """
    with open(file_name, 'wb') as handle:
        pickle.dump(data, handle, protocol=pickle.HIGHEST_PROTOCOL)


def load_comments(youtube, videos):
    """
    Get a dictionary indexed by video Id and every comment thread with its responses inside.
    :param youtube: Youtube API client object
    :param videos: Dictionary of video names indexed by video ID
    :return: Dictionary
    """
    comment_threads = load_from_storage('storage/comments.pickle', {})

    if config.CHECK_FOR_NEW_COMMENTS:
        current_video = 0
        logging.info("\n- Checking last {} videos\n".format(config.LAST_N_VIDEOS))
        for video_id in videos.keys():
            logging.info("CURRENT VIDEO IS: {}".format(videos[video_id]))
            logging.info("Checking for new comments...")
            if video_id not in comment_threads:
                comment_threads[video_id] = {}

            new_comments = get_them_all(
                youtube.commentThreads,
                {"part": ["snippet", "replies"],
                 "videoId": video_id,
                 "order": "time",
                 "maxResults": 100},
                ["snippet", "topLevelComment", "id"],
                [])

            if len(new_comments) > 0:
                logging.info("Adding {} new comments\n".format(len(new_comments)))
            else:
                logging.info("No new comments\n")

            for key in new_comments.keys():
                comment_threads[video_id][key] = {
                    key: new_comments[key]["snippet"]["topLevelComment"]["snippet"],
                    "responses": new_comments[key].get("replies", {"comments": []})["comments"]
                }

            current_video += 1

            if current_video == config.LAST_N_VIDEOS:
                break

        save_into_storage('storage/comments.pickle', comment_threads)
    return comment_threads


def comment_purge_paginated(youtube, to_delete_comments_id, deleted):
    """
    Delete or ban comments paginated by 25 items, as Google likes
    :param youtube: Youtube API client object
    :param to_delete_comments_id: list of comments id to delete
    :param deleted: list of comments already deleted (from a previous session)
    """
    current_page = 0
    page_size = 25

    while current_page < len(to_delete_comments_id) / page_size:
        try:
            paginated_items = [a for a in to_delete_comments_id[current_page * page_size:(current_page + 1) * page_size]]
            if config.MODERATE:
                action = youtube.comments().setModerationStatus(id=paginated_items, moderationStatus="rejected",
                                                                banAuthor=True)
                logging.info("- Moderation on comments: {}".format(", ".join(paginated_items)))
                execute_youtube_query(action)
            else:
                for item in paginated_items:
                    action = youtube.comments().delete(id=item)
                    logging.info("Deletion request to youtube for {}".format(item))
                    execute_youtube_query(action)

            deleted.extend(paginated_items)
            save_into_storage('storage/deleted.pickle', deleted)
        except Exception:  # I know, is too broad, but I don't have time
            logging.info("DELETION FAILED for some comments...")
        current_page += 1


def check_comments_for_spam(comments, deleted):
    """
    Iterate over video comments to detect spam
    :param comments: Dictionary indexed by video with all the comments and responses
    :param deleted: list of previously deleted comments
    :return: list of comments id to delete/purge
    """
    spam_comments = []
    # Checking spam
    for key, comment in comments.items():
        for reply in comment["responses"]:
            if check_is_spam(reply):
                spam_comments.append(reply)

    to_delete_comments_id = []

    show_comments = True

    if not config.UNATTENDED:
        if input("Show comments to delete? [y/n]") != "y":
            show_comments = False

    logging.info("{} spam comments detected".format(len(spam_comments)))
    # Show & gather all the comments into a list, check if not deleted previously
    for comment in spam_comments:
        if comment["id"] not in deleted:
            to_delete_comments_id.append(comment["id"])
            if show_comments:
                logging.info("{}: {}".format(comment["snippet"]["authorDisplayName"], comment["snippet"]["textOriginal"]))
        else:
            logging.info("Comment {} was already deleted!".format(comment["id"]))

    if not config.UNATTENDED:
        input("Press Enter to continue...")
    return to_delete_comments_id


def load_videos(youtube):
    """
    Load a dictionary indexed by video id for all the videos on the channel.
    Only check for new videos if config CHECK_FOR_NEW_VIDEOS is set to True
    :param youtube: Youtube API client object
    :return: Dictionary
    """
    # Loading previously stored videos
    videos = load_from_storage('storage/videos.pickle', {})

    if config.CHECK_FOR_NEW_VIDEOS:
        logging.info("Checking for new videos")
        new_videos = get_them_all(youtube.playlistItems, {"part": "snippet",
                                                          "playlistId": config.PLAYLIST_UPLOADS_ID,
                                                          "maxResults": 100},
                                  ["snippet", "resourceId", "videoId"], ["snippet", "title"], videos.keys())

        if len(new_videos) > 0:
            logging.info("Adding {} new videos\n".format(len(new_videos)))
            for key, val in new_videos.items():
                videos[key] = val
        else:
            logging.info("No new videos\n")
        save_into_storage('storage/videos.pickle', videos)

    return videos


def execute_youtube_query(query):
    """
    Query the API and return the response, if settings TEST_MODE set to True, no queries will be done, and a mock empty
    dict will be returned instead.
    :param query: Google API query ready to execute
    :return: Dictionary
    """
    if not config.TEST_MODE:
        logging.debug("Making query to Youtube API")
        return query.execute()
    else:
        logging.debug("Mocked query to Youtube API (No request were made)")
        return {"items": {}}


def setup_logger():
    """
    Set a simple logger to show text on terminal and log into a file
    :return:
    """
    logging.basicConfig(filename="logfile.txt",
                        format="%(asctime)s %(message)s",
                        filemode="w",
                        level=config.LOG_LEVEL)

    logging.getLogger().addHandler(logging.StreamHandler())

    logging.info("-- YOUTUBE SPAM CHECKER RUNNING --\n")


def purge_comments(youtube, videos, comment_threads):
    """
    Purge/Delete comments from Youtube
    :param youtube: Youtube API client object
    :param videos: Dictionary of video names indexed by video ID
    :param comment_threads: Dictionary containing comment threads indexed by video_id, cointaining all responses in
                            Google API Style
    """
    # Loading deleted comments list
    logging.info("Loading previously deleted comments")
    deleted = load_from_storage('storage/deleted.pickle', [])
    logging.info("We deleted {} yet!".format(len(deleted)))

    current_video = 0

    logging.info("\n- Starting spam checks\n")
    for video_key, comments in comment_threads.items():
        logging.info("\nCURRENT VIDEO IS: {}".format(videos[video_key]))
        logging.info("Checking spam comments\n")

        to_delete_comments_id = check_comments_for_spam(comments, deleted)
        comment_purge_paginated(youtube, to_delete_comments_id, deleted)

        current_video += 1

        if current_video == config.LAST_N_VIDEOS:
            break
            
def create_client(role):
    # Query Youtube API for authentication or load from file
    creds = get_credentials(role)
    # Create API client
    youtube = googleapiclient.discovery.build(config.API_SERVICE_NAME, config.API_VERSION, credentials=creds)


def main():
    # Setup both file logging and terminal on-screen logs
    setup_logger()
    # Load videos and comments, check new ones on the API if specified on config file
    youtube_reader = create_client("reader")
    videos = load_videos(youtube_reader)
    comment_threads = load_comments(youtube_reader, videos)
    # Now we're checking all the comments video per video and purge them
    youtube_manager = create_client("manager")
    purge_comments(youtube_manager, videos, comment_threads)


if __name__ == '__main__':
    main()
